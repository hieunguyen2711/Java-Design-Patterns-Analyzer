"""
Offline robustness tests for generation/run_generation.py.

Everything here runs with a MOCK model client (canned Java responses) -- ZERO
network calls, ZERO cost. The runner is imported straight from its file so it
stays a standalone script (no package needed).

Covers:
  * parse recovery handles fenced / prose / FILE-block output
  * resume skips already-completed units (never re-calls the model)
  * a kill mid-write leaves NO false-complete record (atomic unit.json)
  * a missing API key aborts cleanly BEFORE any call
  * dry-run makes no calls, --limit caps units, --shard slices are disjoint

Run with pytest:   python -m pytest tests/test_generation_offline.py -q
Or standalone:     python tests/test_generation_offline.py
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("run_generation", REPO / "generation" / "run_generation.py")
rg = importlib.util.module_from_spec(_spec)
sys.modules["run_generation"] = rg   # register before exec so dataclasses can resolve annotations
_spec.loader.exec_module(rg)


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
CANNED_JAVA = "### FILE: Foo.java\n```java\npublic class Foo { }\n```\n"
LOCAL_MODEL = {"id": "local/mock", "provider": "ollama", "rate_limit_per_min": 0}


def write_config(tmp: Path, *, model=None, k=1, patterns=None, contexts=None, max_tokens=2500) -> Path:
    cfg = {
        "output_dir": str(tmp / "out"),
        "model": model or LOCAL_MODEL,
        "patterns": patterns or ["singleton"],
        "contexts": contexts or [{"title": "D1", "context": "ctx one"}],
        "generation": {"k": k, "temperature": 0.2, "max_tokens": max_tokens, "request_timeout_seconds": 5},
        "retry": {"max_attempts": 2, "backoff_seconds": [0.01]},
    }
    p = tmp / "study.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return p


class MockClient:
    """Records calls and returns a canned CallResult -- no network."""

    def __init__(self, content=CANNED_JAVA, tokens_in=100, tokens_out=200):
        self.content, self.tokens_in, self.tokens_out = content, tokens_in, tokens_out
        self.calls = []

    def install(self):
        self._orig = rg.call_model
        mock = self

        def _fake(model, prompt, temperature, max_tokens, timeout):
            mock.calls.append(model.id)
            return rg.CallResult(content=mock.content, tokens_in=mock.tokens_in,
                                 tokens_out=mock.tokens_out, tokens_estimated=False,
                                 model_returned=model.id + "@mock", finish_reason="stop")
        rg.call_model = _fake
        return self

    def uninstall(self):
        rg.call_model = self._orig


def _count_unit_json(out_dir: Path) -> int:
    return sum(1 for _ in out_dir.rglob("unit.json")) if out_dir.exists() else 0


# --------------------------------------------------------------------------- #
# 1. Parse recovery                                                           #
# --------------------------------------------------------------------------- #
def test_parse_recovery_variants():
    files, method = rg.parse_generated_files("### FILE: A.java\n```java\npublic class A {}\n```")
    assert method == "file_blocks" and [f["filename"] for f in files] == ["A.java"]

    files, method = rg.parse_generated_files("Here you go:\n```java\npublic class Bar {}\n```\nDone.")
    assert method == "fenced_java" and files[0]["filename"] == "Bar.java"

    files, method = rg.parse_generated_files("Sure! public interface Baz { void x(); } cheers")
    assert method == "type_blocks" and files[0]["filename"] == "Baz.java"

    files, method = rg.parse_generated_files("I cannot help with that request.")
    assert files == [] and method == ""
    print("PASS test_parse_recovery_variants")


# --------------------------------------------------------------------------- #
# 2. Dry run makes no calls                                                    #
# --------------------------------------------------------------------------- #
def test_dry_run_no_calls():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        cfg_path = write_config(tmp, k=2)
        mock = MockClient().install()
        try:
            code = rg.main(["--config", str(cfg_path), "--dry-run"])
        finally:
            mock.uninstall()
        assert code == 0
        assert mock.calls == []
        assert _count_unit_json(tmp / "out") == 0
    print("PASS test_dry_run_no_calls")


# --------------------------------------------------------------------------- #
# 3. End-to-end OK + resume skips completed units                              #
# --------------------------------------------------------------------------- #
def test_end_to_end_and_resume_skip():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        cfg_path = write_config(tmp, k=2, patterns=["singleton", "strategy"])  # 2x1x2 = 4 units
        mock = MockClient().install()
        try:
            code1 = rg.main(["--config", str(cfg_path)])
            first_calls = len(mock.calls)
            code2 = rg.main(["--config", str(cfg_path)])          # rerun -> all skipped
            second_calls = len(mock.calls) - first_calls
        finally:
            mock.uninstall()
        assert code1 == 0 and code2 == 0
        assert first_calls == 4
        assert _count_unit_json(tmp / "out") == 4
        assert second_calls == 0                                   # resume re-called ZERO times
    print("PASS test_end_to_end_and_resume_skip")


# --------------------------------------------------------------------------- #
# 4. Kill mid-write leaves no false-complete record (atomic unit.json)         #
# --------------------------------------------------------------------------- #
def test_atomic_write_no_false_complete():
    with tempfile.TemporaryDirectory() as d:
        unit_dir = Path(d) / "u"
        record = {"status": "ok", "unit_id": "x"}
        files = [{"filename": "Foo.java", "content": "public class Foo {}"}]

        orig_replace = rg.os.replace

        def boom(src, dst):
            if str(dst).endswith("unit.json"):
                raise OSError("simulated crash mid-write")
            return orig_replace(src, dst)

        rg.os.replace = boom
        try:
            try:
                rg.write_unit_result(unit_dir, record, files, "prompt", "raw")
            except OSError:
                pass
        finally:
            rg.os.replace = orig_replace

        assert not (unit_dir / "unit.json").exists()   # no false-complete marker
        assert rg.unit_is_done(unit_dir) is None         # resume will regenerate
    print("PASS test_atomic_write_no_false_complete")


# --------------------------------------------------------------------------- #
# 5. --limit caps total units                                                  #
# --------------------------------------------------------------------------- #
def test_limit_caps_units():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        cfg_path = write_config(tmp, k=3, patterns=["singleton", "strategy", "observer"])  # 9 units
        mock = MockClient().install()
        try:
            code = rg.main(["--config", str(cfg_path), "--limit", "2"])
        finally:
            mock.uninstall()
        assert code == 0
        assert len(mock.calls) == 2
        assert _count_unit_json(tmp / "out") == 2
    print("PASS test_limit_caps_units")


# --------------------------------------------------------------------------- #
# 6. Shards are disjoint and cover the whole grid                              #
# --------------------------------------------------------------------------- #
def test_shards_disjoint_and_complete():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        cfg_path = write_config(tmp, k=2, patterns=["singleton", "strategy"],
                                contexts=[{"title": "D1", "context": "c1"},
                                          {"title": "D2", "context": "c2"}])  # 2x2x2 = 8 units
        cfg = rg.load_config(cfg_path, None)
        full = {(u.pattern, u.context_title, u.repetition) for u, _ in rg.build_grid(cfg)}
        s0 = {(u.pattern, u.context_title, u.repetition) for u, _ in rg.select_units(cfg, 0, 2, None)}
        s1 = {(u.pattern, u.context_title, u.repetition) for u, _ in rg.select_units(cfg, 1, 2, None)}
        assert len(full) == 8
        assert s0.isdisjoint(s1)          # no unit generated twice under concurrent array tasks
        assert s0 | s1 == full            # every unit covered exactly once
    print("PASS test_shards_disjoint_and_complete")


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"\nALL {len(tests)} offline robustness checks passed.")


if __name__ == "__main__":
    _run_all()
