"""
Offline unit tests for the logprob pilot (generation/run_generation_logprobs.py
and generation/analyze_logprob_separation.py).

Everything here is PURE and synthetic: NO GPU, NO model, NO torch, NO network.
We feed hand-made token_logprobs / token-piece lists straight into the three-
number computation and the critical-line proxy and assert the results, then run
the separation reporter over a couple of fake unit.json files + a fake PIQS map.

Run with pytest:   python -m pytest tests/test_generation_logprobs.py -q
Or standalone:     python tests/test_generation_logprobs.py
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import math
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GEN = REPO / "generation"


def _load(mod_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(mod_name, GEN / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod            # register before exec (matches repo style)
    spec.loader.exec_module(mod)
    return mod


# Importing the generation module must NOT import torch (it is loaded lazily
# inside hf_generate). If this line works with torch absent, that invariant holds.
rg = _load("run_generation_logprobs", "run_generation_logprobs.py")
al = _load("analyze_logprob_separation", "analyze_logprob_separation.py")


def _close(a, b, tol=1e-9):
    return a is not None and b is not None and math.isclose(a, b, rel_tol=0, abs_tol=tol)


# --------------------------------------------------------------------------- #
# 1. Three-number computation: basics (single non-critical line)              #
# --------------------------------------------------------------------------- #
def test_summary_basic_no_critical():
    s = rg.compute_logprob_summary([-0.1, -0.5, -0.2], ["a", "b", "c"])
    assert _close(s["mean_logprob"], -0.8 / 3)
    assert _close(s["min_logprob"], -0.5)
    # no critical line -> min_logprob_critical falls back to the global min
    assert _close(s["min_logprob_critical"], -0.5)
    assert s["critical_fallback"] is True
    assert s["num_logprob_tokens"] == 3
    print("PASS test_summary_basic_no_critical")


# --------------------------------------------------------------------------- #
# 2. min_logprob_critical differs from min_logprob when the least-confident    #
#    token sits on a NON-critical line                                         #
# --------------------------------------------------------------------------- #
def test_summary_critical_distinguishes():
    pieces = ["int", " x", " =", " 5", ";", "\n", "return", " obj", ".doThing", "();"]
    lps = [-0.3, -0.2, -0.1, -3.0, -0.05, -0.02, -0.5, -0.4, -0.6, -0.7]
    #  line0 "int x = 5;"          -> NOT critical (least-confident token -3.0 here)
    #  line1 "return obj.doThing();" -> critical (return + method call)
    s = rg.compute_logprob_summary(lps, pieces)
    assert _close(s["mean_logprob"], sum(lps) / len(lps))
    assert _close(s["min_logprob"], -3.0)             # global min is on the non-critical line
    assert _close(s["min_logprob_critical"], -0.7)    # min among critical-line tokens only
    assert s["critical_fallback"] is False
    assert s["num_logprob_tokens"] == 10
    print("PASS test_summary_critical_distinguishes")


# --------------------------------------------------------------------------- #
# 3. No critical line anywhere -> fallback to min_logprob + flag               #
# --------------------------------------------------------------------------- #
def test_summary_no_critical_fallback():
    s = rg.compute_logprob_summary([-1.0, -2.0], ["hello", " world"])
    assert _close(s["min_logprob"], -2.0)
    assert _close(s["min_logprob_critical"], -2.0)
    assert s["critical_fallback"] is True
    print("PASS test_summary_no_critical_fallback")


# --------------------------------------------------------------------------- #
# 4. Empty generation                                                          #
# --------------------------------------------------------------------------- #
def test_summary_empty():
    s = rg.compute_logprob_summary([], [])
    assert s["mean_logprob"] is None
    assert s["min_logprob"] is None
    assert s["min_logprob_critical"] is None
    assert s["critical_fallback"] is False
    assert s["num_logprob_tokens"] == 0
    print("PASS test_summary_empty")


# --------------------------------------------------------------------------- #
# 5. Off-by-one alignment: more logprobs than pieces must NOT crash            #
# --------------------------------------------------------------------------- #
def test_summary_offbyone_alignment():
    s = rg.compute_logprob_summary([-0.1, -0.2, -0.3], ["a", "b"])  # pieces shorter
    assert s["num_logprob_tokens"] == 3                 # mean/min use ALL logprobs
    assert _close(s["mean_logprob"], -0.2)
    assert _close(s["min_logprob"], -0.3)
    assert s["critical_fallback"] is True               # "ab" has no critical marker
    print("PASS test_summary_offbyone_alignment")


# --------------------------------------------------------------------------- #
# 6. Critical-line proxy: WHOLE-WORD matching (pass-3 lesson)                  #
# --------------------------------------------------------------------------- #
def test_line_is_critical_whole_word():
    # keywords, method calls, @Override -> critical
    assert rg._line_is_critical("public class Foo {") is True
    assert rg._line_is_critical("    return x;") is True
    assert rg._line_is_critical("class A extends B implements C {") is True
    assert rg._line_is_critical("abstract void run();") is True
    assert rg._line_is_critical("Foo f = new Foo();") is True          # 'new'
    assert rg._line_is_critical("    obj.doThing();") is True          # method call
    assert rg._line_is_critical("@Override") is True
    # NOT critical: 'class' must not match inside a longer identifier
    assert rg._line_is_critical("int myclass = 0;") is False
    assert rg._line_is_critical("    int a = b + c;") is False
    assert rg._line_is_critical("String greeting = value;") is False
    print("PASS test_line_is_critical_whole_word")


# --------------------------------------------------------------------------- #
# 7. Token -> line mapping                                                     #
# --------------------------------------------------------------------------- #
def test_tokens_to_lines():
    lines, idx = rg._tokens_to_lines(["ab", "c\nde", "f"])
    assert lines == ["abc", "def"]
    assert idx == [[0], [0, 1], [1]]     # middle token spans both lines it touches
    print("PASS test_tokens_to_lines")


# --------------------------------------------------------------------------- #
# 8. analyze_logprob_separation over a synthetic fixture                       #
# --------------------------------------------------------------------------- #
def _write_unit(out_dir: Path, sub: str, uid: str, mean, mn, mnc, status="ok"):
    d = out_dir / sub
    d.mkdir(parents=True, exist_ok=True)
    rec = {"unit_id": uid, "status": status,
           "mean_logprob": mean, "min_logprob": mn, "min_logprob_critical": mnc}
    (d / "unit.json").write_text(json.dumps(rec), encoding="utf-8")


def test_analyze_reports_both_piles():
    with tempfile.TemporaryDirectory() as dtmp:
        out = Path(dtmp) / "out"
        _write_unit(out, "a", "m__Singleton__d1__rep0", -0.20, -1.0, -0.8)   # will be PASS
        _write_unit(out, "b", "m__Strategy__d2__rep0", -0.90, -3.0, -2.5)    # will be FAIL
        piqs = Path(dtmp) / "piqs.csv"
        piqs.write_text("unit_id,status\nm__Singleton__d1__rep0,pass\nm__Strategy__d2__rep0,fail\n",
                        encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = al.main(["--output-dir", str(out), "--piqs-results", str(piqs)])
        text = buf.getvalue()
        assert code == 0
        assert "PIQS PASS : 1" in text
        assert "PIQS FAIL : 1" in text
        assert "EMPTY" not in text                    # both piles non-empty
        for metric in ("mean_logprob", "min_logprob", "min_logprob_critical"):
            assert metric in text
    print("PASS test_analyze_reports_both_piles")


def test_analyze_warns_on_empty_pile():
    with tempfile.TemporaryDirectory() as dtmp:
        out = Path(dtmp) / "out"
        _write_unit(out, "a", "u1", -0.2, -1.0, -0.8)
        _write_unit(out, "b", "u2", -0.3, -1.5, -0.9)
        piqs = Path(dtmp) / "piqs.json"
        piqs.write_text(json.dumps({"u1": "pass", "u2": "pass"}), encoding="utf-8")  # no fails
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = al.main(["--output-dir", str(out), "--piqs-results", str(piqs)])
        text = buf.getvalue()
        assert code == 0
        assert "PIQS PASS : 2" in text
        assert "PIQS FAIL : 0" in text
        assert "EMPTY" in text                         # loud warning fired
    print("PASS test_analyze_warns_on_empty_pile")


def test_analyze_threshold_scores():
    # numeric PIQS scores + --threshold -> pass/fail split
    with tempfile.TemporaryDirectory() as dtmp:
        out = Path(dtmp) / "out"
        _write_unit(out, "a", "u1", -0.2, -1.0, -0.8)
        _write_unit(out, "b", "u2", -0.9, -3.0, -2.5)
        piqs = Path(dtmp) / "piqs.json"
        piqs.write_text(json.dumps({"u1": 0.95, "u2": 0.40}), encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = al.main(["--output-dir", str(out), "--piqs-results", str(piqs),
                            "--threshold", "0.8"])
        text = buf.getvalue()
        assert code == 0
        assert "PIQS PASS : 1" in text and "PIQS FAIL : 1" in text
    print("PASS test_analyze_threshold_scores")


# --------------------------------------------------------------------------- #
# 9. Persistence wiring (CHANGE 4): generate_unit -> files, WITHOUT torch      #
#    apply_seed() degrades gracefully when torch is absent, and call_model is  #
#    mocked, so the whole unit path runs with no GPU/model.                    #
# --------------------------------------------------------------------------- #
OK_JAVA = "### FILE: Foo.java\n```java\npublic class Foo { }\n```\n"


def _make_cfg(tmp: Path, provider: str = "huggingface"):
    model = rg.ModelConfig(id="test/model", provider=provider)
    ctx = rg.Context(title="Demo One", context="a demo context")
    return rg.StudyConfig(
        output_dir=tmp / "out", model=model, patterns=["Singleton"], contexts=[ctx],
        seed=40, k=1, temperature=0.7, max_tokens=64, request_timeout_seconds=5,
        retry_max_attempts=2, retry_backoff_seconds=[0.01],
    ), ctx


def _install_call_model(fn):
    orig = rg.call_model
    rg.call_model = fn
    return orig


def test_generate_unit_writes_token_logprobs_file():
    with tempfile.TemporaryDirectory() as dtmp:
        tmp = Path(dtmp)
        cfg, ctx = _make_cfg(tmp, provider="huggingface")
        unit = rg.Unit(pattern="Singleton", context_title=ctx.title, repetition=0)

        def fake(model, prompt, temperature, max_tokens, timeout):
            return rg.CallResult(
                content=OK_JAVA, tokens_in=10, tokens_out=2, tokens_estimated=False,
                model_returned="test/model", finish_reason="stop",
                token_logprobs=[-0.1, -0.5], token_strings=["Ġpublic", "Ġclass"],
                mean_logprob=-0.3, min_logprob=-0.5, min_logprob_critical=-0.5,
                critical_fallback=True, num_logprob_tokens=2,
            )

        orig = _install_call_model(fake)
        try:
            rec = rg.generate_unit(unit, ctx, cfg, rg.RateLimiter())
        finally:
            rg.call_model = orig

        assert rec["status"] == "ok"
        unit_dir = unit.dir_under(cfg.output_dir, ctx.slug)
        uj = json.loads((unit_dir / "unit.json").read_text())
        # summary numbers ARE in unit.json ...
        assert _close(uj["mean_logprob"], -0.3) and _close(uj["min_logprob"], -0.5)
        assert uj["num_logprob_tokens"] == 2
        # ... but the per-token list is NOT (unit.json stays small)
        assert "tokens" not in uj and "token_logprobs" not in uj
        # the full per-token list lives in its own file, in order, with a header
        tlp = json.loads((unit_dir / "token_logprobs.json").read_text())
        assert tlp["unit_id"] == rec["unit_id"] and tlp["model"] == "test/model"
        assert _close(tlp["mean_logprob"], -0.3)
        assert tlp["tokens"] == [
            {"token_str": "Ġpublic", "logprob": -0.1},
            {"token_str": "Ġclass", "logprob": -0.5},
        ]
    print("PASS test_generate_unit_writes_token_logprobs_file")


def test_generate_unit_ollama_leaves_fields_null_and_no_file():
    with tempfile.TemporaryDirectory() as dtmp:
        tmp = Path(dtmp)
        cfg, ctx = _make_cfg(tmp, provider="ollama")
        unit = rg.Unit(pattern="Singleton", context_title=ctx.title, repetition=0)

        def fake(model, prompt, temperature, max_tokens, timeout):
            # ollama path: CallResult built WITHOUT any logprob fields (defaults)
            return rg.CallResult(content=OK_JAVA, tokens_in=10, tokens_out=2,
                                 tokens_estimated=False, model_returned="test/model",
                                 finish_reason="stop")

        orig = _install_call_model(fake)
        try:
            rec = rg.generate_unit(unit, ctx, cfg, rg.RateLimiter())
        finally:
            rg.call_model = orig

        assert rec["status"] == "ok"
        unit_dir = unit.dir_under(cfg.output_dir, ctx.slug)
        uj = json.loads((unit_dir / "unit.json").read_text())
        assert uj["mean_logprob"] is None and uj["min_logprob"] is None
        assert uj["min_logprob_critical"] is None
        assert not (unit_dir / "token_logprobs.json").exists()   # HF-only file
    print("PASS test_generate_unit_ollama_leaves_fields_null_and_no_file")


def test_generate_unit_failed_leaves_nulls_and_no_file():
    with tempfile.TemporaryDirectory() as dtmp:
        tmp = Path(dtmp)
        cfg, ctx = _make_cfg(tmp, provider="huggingface")
        unit = rg.Unit(pattern="Singleton", context_title=ctx.title, repetition=0)

        def boom(model, prompt, temperature, max_tokens, timeout):
            raise rg.PermanentError("simulated backend failure")

        orig = _install_call_model(boom)
        try:
            rec = rg.generate_unit(unit, ctx, cfg, rg.RateLimiter())
        finally:
            rg.call_model = orig

        assert rec["status"] == "failed"
        unit_dir = unit.dir_under(cfg.output_dir, ctx.slug)
        uj = json.loads((unit_dir / "unit.json").read_text())
        assert uj["mean_logprob"] is None and uj["num_logprob_tokens"] is None
        assert not (unit_dir / "token_logprobs.json").exists()
    print("PASS test_generate_unit_failed_leaves_nulls_and_no_file")


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"\nALL {len(tests)} logprob-pilot checks passed.")


if __name__ == "__main__":
    _run_all()
