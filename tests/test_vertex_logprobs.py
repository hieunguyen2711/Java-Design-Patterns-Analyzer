"""
Offline unit tests for the VERTEX (Google Gemini 2.5) arm of the logprob pilot
(generation/run_generation_logprobs.py).

Everything here is PURE and synthetic: NO GPU, NO torch, NO google credits, NO
network. We build fake response objects shaped EXACTLY like the real
google-genai LogprobsResult (chosen_candidates[*].token / .log_probability,
resolved from the installed SDK's typed schema) and drive:

  * the chosen-token logprob PARSING (_parse_vertex_logprobs),
  * the full parse -> three-number path (_parse_vertex_response), which reuses
    the SAME compute_logprob_summary the HuggingFace path uses,
  * vertex_generate end-to-end with a STUB client (parse -> summary), asserting
    the request config carried response_logprobs / logprobs,
  * the transient-vs-permanent error mapping for the shared retry loop,
  * the SAVE path (generate_unit -> write_unit_result) with a stub client, and
    that the UNCHANGED analyze_logprob_separation.py reads the vertex unit.json.

Run with pytest:   python -m pytest tests/test_vertex_logprobs.py -q
Or standalone:     python tests/test_vertex_logprobs.py
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

REPO = Path(__file__).resolve().parent.parent
GEN = REPO / "generation"


def _load(mod_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(mod_name, GEN / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod            # register before exec (matches repo style)
    spec.loader.exec_module(mod)
    return mod


# Importing the generation module must NOT import torch OR google.genai at module
# load (both are loaded lazily inside their backends). If this works, that holds.
rg = _load("run_generation_logprobs", "run_generation_logprobs.py")
al = _load("analyze_logprob_separation", "analyze_logprob_separation.py")

assert "torch" not in sys.modules, "importing the runner must not import torch"
assert "google.genai" not in sys.modules, "importing the runner must not import google.genai"


def _close(a, b, tol=1e-9):
    return a is not None and b is not None and math.isclose(a, b, rel_tol=0, abs_tol=tol)


# --------------------------------------------------------------------------- #
# Fakes shaped like the real google-genai response objects                     #
# (getattr-based access in the parser means SimpleNamespace is a faithful stub) #
# --------------------------------------------------------------------------- #
def _chosen(pairs):
    """pairs: list[(token_str, logprob | None)] -> list of LogprobsResultCandidate."""
    return [NS(token=t, log_probability=lp, token_id=None) for t, lp in pairs]


def _logprobs_result(pairs):
    return NS(chosen_candidates=_chosen(pairs), top_candidates=None, log_probability_sum=None)


def _candidate(text, pairs, finish="STOP"):
    parts = [NS(text=text)] if text is not None else []
    return NS(
        content=NS(parts=parts),
        finish_reason=NS(name=finish),                       # mimic FinishReason enum member
        logprobs_result=_logprobs_result(pairs) if pairs is not None else None,
    )


def _usage(pin=10, pout=5, thoughts=0):
    return NS(prompt_token_count=pin, candidates_token_count=pout,
              thoughts_token_count=thoughts, total_token_count=pin + pout + thoughts)


def _response(text, pairs, finish="STOP", pin=10, pout=5, thoughts=0,
              has_candidate=True, block_reason=None):
    cands = [_candidate(text, pairs, finish)] if has_candidate else []
    pf = NS(block_reason=(NS(name=block_reason) if block_reason else None),
            block_reason_message=("blocked: " + block_reason) if block_reason else None,
            safety_ratings=None)
    return NS(candidates=cands, usage_metadata=_usage(pin, pout, thoughts), prompt_feedback=pf)


class _FakeModels:
    """Stand-in for client.models. Captures the request; returns a canned response
    or raises a canned exception."""

    def __init__(self, resp_or_exc):
        self._resp_or_exc = resp_or_exc
        self.captured = {}

    def generate_content(self, model, contents, config):
        self.captured = {"model": model, "contents": contents, "config": config}
        if isinstance(self._resp_or_exc, Exception):
            raise self._resp_or_exc
        return self._resp_or_exc


class _FakeClient:
    def __init__(self, resp_or_exc):
        self.models = _FakeModels(resp_or_exc)


# --------------------------------------------------------------------------- #
# 1. Chosen-token logprob PARSING (the core of this arm)                        #
# --------------------------------------------------------------------------- #
def test_parse_logprobs_values_and_alignment():
    lpr = _logprobs_result([("public", -0.1), (" class", -0.2), ("Foo", -0.05)])
    tl, ts = rg._parse_vertex_logprobs(lpr)
    assert tl == [-0.1, -0.2, -0.05]
    assert ts == ["public", " class", "Foo"]


def test_parse_logprobs_skips_none_logprob_keeps_alignment():
    # A candidate whose log_probability is None is dropped so the float list and
    # the token-string list stay 1:1.
    lpr = _logprobs_result([("a", -0.1), ("b", None), ("c", -0.3)])
    tl, ts = rg._parse_vertex_logprobs(lpr)
    assert tl == [-0.1, -0.3]
    assert ts == ["a", "c"]


def test_parse_logprobs_missing_result_is_empty():
    assert rg._parse_vertex_logprobs(None) == ([], [])
    assert rg._parse_vertex_logprobs(NS(chosen_candidates=None)) == ([], [])
    assert rg._parse_vertex_logprobs(NS(chosen_candidates=[])) == ([], [])


# --------------------------------------------------------------------------- #
# 2. Full parse -> the SAME three numbers as HF (via compute_logprob_summary)   #
# --------------------------------------------------------------------------- #
def test_parse_response_three_numbers_with_critical_line():
    # token pieces reconstruct to two lines:
    #   line0 "public class Foo {"  -> CRITICAL (contains 'class')
    #   line1 "x = 1"               -> not critical
    # line0 logprobs: -0.1,-0.9,-0.2,-0.3 and the '\n' -0.05 (newline ends line0)
    # line1 logprobs: -0.4,-0.5,-1.5  (global min -1.5 lives on the NON-critical line)
    pairs = [
        ("public ", -0.1), ("class ", -0.9), ("Foo ", -0.2), ("{", -0.3), ("\n", -0.05),
        ("x ", -0.4), ("= ", -0.5), ("1", -1.5),
    ]
    resp = _response("public class Foo {\nx = 1", pairs, finish="STOP", pin=10, pout=5)
    cr = rg._parse_vertex_response(resp, "PROMPT", "gemini-2.5-flash", 2500)

    assert cr.token_logprobs == [p[1] for p in pairs]
    assert cr.token_strings == [p[0] for p in pairs]
    assert cr.num_logprob_tokens == 8
    assert _close(cr.mean_logprob, sum(p[1] for p in pairs) / 8)
    assert _close(cr.min_logprob, -1.5)            # global min (non-critical line)
    assert _close(cr.min_logprob_critical, -0.9)   # min restricted to the critical line
    assert cr.critical_fallback is False
    assert cr.finish_reason == "stop"
    assert cr.tokens_in == 10 and cr.tokens_out == 5
    assert cr.tokens_estimated is False
    assert cr.content == "public class Foo {\nx = 1"


def test_parse_response_no_critical_line_falls_back():
    pairs = [("foo ", -0.1), ("bar ", -0.2), ("baz", -0.3)]   # no structural keyword
    resp = _response("foo bar baz", pairs)
    cr = rg._parse_vertex_response(resp, "PROMPT", "gemini-2.5-pro", 2500)
    assert _close(cr.min_logprob, -0.3)
    assert _close(cr.min_logprob_critical, -0.3)   # falls back to the global min
    assert cr.critical_fallback is True
    assert cr.num_logprob_tokens == 3


def test_parse_response_empty_logprobs_gives_nulls():
    resp = _response("some text with class Foo {}", pairs=[], finish="STOP")
    cr = rg._parse_vertex_response(resp, "PROMPT", "gemini-2.5-flash", 2500)
    assert cr.token_logprobs == []
    assert cr.mean_logprob is None
    assert cr.min_logprob is None
    assert cr.min_logprob_critical is None
    assert cr.critical_fallback is False
    assert cr.num_logprob_tokens == 0
    assert cr.content == "some text with class Foo {}"   # text is still returned


def test_max_tokens_finish_reason_maps_to_length():
    resp = _response("partial", [("p", -0.1)], finish="MAX_TOKENS")
    cr = rg._parse_vertex_response(resp, "PROMPT", "gemini-2.5-flash", 2500)
    assert cr.finish_reason == "length"     # so the shared truncation check fires


def test_usage_metadata_absent_estimates_tokens():
    resp = NS(candidates=[_candidate("hello class X{}", [("a", -0.1)])],
              usage_metadata=None, prompt_feedback=None)
    cr = rg._parse_vertex_response(resp, "a prompt of some length", "gemini-2.5-flash", 2500)
    assert cr.tokens_estimated is True
    assert cr.tokens_in >= 1


# --------------------------------------------------------------------------- #
# 3. Safety / empty responses -> parse_failed (terminal), raw reason saved      #
# --------------------------------------------------------------------------- #
def test_blocked_prompt_no_candidate():
    resp = _response(None, None, has_candidate=False, block_reason="SAFETY")
    cr = rg._parse_vertex_response(resp, "PROMPT", "gemini-2.5-flash", 2500)
    assert cr.finish_reason == "blocked"
    assert cr.num_logprob_tokens == 0
    assert cr.content.startswith("VERTEX_BLOCKED")
    assert "prompt_block_reason=SAFETY" in cr.content
    # The saved marker must NOT parse to any Java file -> the unit becomes parse_failed.
    files, method = rg.parse_generated_files(cr.content)
    assert files == [] and method == ""


def test_empty_candidate_safety_saves_reason():
    resp = _response("", [("x", -0.1)], finish="SAFETY")   # candidate present but empty text
    cr = rg._parse_vertex_response(resp, "PROMPT", "gemini-2.5-pro", 2500)
    assert cr.finish_reason == "safety"
    assert cr.content.startswith("VERTEX_BLOCKED")
    files, _ = rg.parse_generated_files(cr.content)
    assert files == []


# --------------------------------------------------------------------------- #
# 4. vertex_generate with a STUB client (offline, zero cost)                    #
# --------------------------------------------------------------------------- #
def _reset_usage():
    rg._VERTEX_USAGE.update(calls=0, prompt_tokens=0, candidates_tokens=0,
                            thoughts_tokens=0, total_tokens=0)


def test_vertex_generate_uses_stub_and_sets_config():
    _reset_usage()
    pairs = [("public ", -0.1), ("class ", -0.7), ("A", -0.2)]
    resp = _response("public class A", pairs, pin=12, pout=3, thoughts=4)
    fake = _FakeClient(resp)
    model = rg.ModelConfig(id="gemini-2.5-flash", provider="vertex")

    cr = rg.vertex_generate(model, "the prompt", temperature=0.7, max_tokens=2500,
                            timeout=120, client=fake)

    # Correct request config (the exact flags the pilot requires).
    cfg = fake.models.captured["config"]
    assert fake.models.captured["model"] == "gemini-2.5-flash"
    assert fake.models.captured["contents"] == "the prompt"
    assert cfg.response_logprobs is True
    assert cfg.logprobs == 5
    assert cfg.temperature == 0.7
    assert cfg.max_output_tokens == 2500
    assert cfg.http_options is not None and cfg.http_options.timeout == 120 * 1000  # ms

    # Correct parse + summary.
    assert cr.token_logprobs == [-0.1, -0.7, -0.2]
    assert _close(cr.min_logprob_critical, -0.7)   # 'class' line is critical
    assert cr.tokens_in == 12 and cr.tokens_out == 3

    # Cost ledger updated (prompt/candidates/thoughts all counted).
    assert rg._VERTEX_USAGE["calls"] == 1
    assert rg._VERTEX_USAGE["prompt_tokens"] == 12
    assert rg._VERTEX_USAGE["candidates_tokens"] == 3
    assert rg._VERTEX_USAGE["thoughts_tokens"] == 4


# --------------------------------------------------------------------------- #
# 5. Error mapping for the SHARED call_with_retries loop                        #
# --------------------------------------------------------------------------- #
def test_error_mapping_transient_vs_permanent():
    from google.genai import errors

    # 429 rate limit -> transient (retry)
    with pytest.raises(rg.RetryableError):
        rg.vertex_generate(rg.ModelConfig(id="gemini-2.5-flash", provider="vertex"),
                           "p", 0.7, 2500, 120,
                           client=_FakeClient(errors.ClientError(429, {"error": {"message": "rate"}})))
    # 400 bad request -> permanent (do not retry)
    with pytest.raises(rg.PermanentError):
        rg.vertex_generate(rg.ModelConfig(id="gemini-2.5-flash", provider="vertex"),
                           "p", 0.7, 2500, 120,
                           client=_FakeClient(errors.ClientError(400, {"error": {"message": "bad"}})))
    # 503 server error -> transient
    with pytest.raises(rg.RetryableError):
        rg.vertex_generate(rg.ModelConfig(id="gemini-2.5-flash", provider="vertex"),
                           "p", 0.7, 2500, 120,
                           client=_FakeClient(errors.ServerError(503, {"error": {"message": "down"}})))
    # a bare network/timeout error -> transient
    with pytest.raises(rg.RetryableError):
        rg.vertex_generate(rg.ModelConfig(id="gemini-2.5-flash", provider="vertex"),
                           "p", 0.7, 2500, 120, client=_FakeClient(TimeoutError("read timeout")))


def test_call_with_retries_records_failed_unit_on_exhaustion():
    # A retryable (429) error every attempt -> call_with_retries gives up cleanly
    # (result None, an error string) instead of crashing the run. Backoff is [0.0]s.
    from google.genai import errors
    model = rg.ModelConfig(id="gemini-2.5-flash", provider="vertex")
    cfg = _study_cfg(Path("/tmp/does-not-matter"), model)
    client = _FakeClient(errors.ClientError(429, {"error": {"message": "rate"}}))
    with _patched(rg, "_get_vertex_client", lambda *a, **k: client):
        result, err, attempts = rg.call_with_retries(model, "p", cfg)
    assert result is None
    assert attempts == cfg.retry_max_attempts
    assert "retryable exhausted" in err


# --------------------------------------------------------------------------- #
# 6. SAVE path + analyze compatibility (stub client, offline)                  #
# --------------------------------------------------------------------------- #
def _study_cfg(out_dir: Path, model: rg.ModelConfig):
    ctx = rg.Context(title="Some Project", context="a shared project context")
    return rg.StudyConfig(
        output_dir=out_dir, model=model, patterns=["Singleton"], contexts=[ctx],
        seed=40, k=1, temperature=0.7, max_tokens=2500, request_timeout_seconds=120,
        retry_max_attempts=3, retry_backoff_seconds=[0.0],
    )


class _patched:
    """Tiny setattr context manager (avoids a pytest monkeypatch fixture dep in
    the standalone-run path)."""

    def __init__(self, obj, name, value):
        self.obj, self.name, self.value = obj, name, value

    def __enter__(self):
        self.old = getattr(self.obj, self.name)
        setattr(self.obj, self.name, self.value)
        return self

    def __exit__(self, *exc):
        setattr(self.obj, self.name, self.old)


def test_generate_unit_vertex_save_path_and_analyze(tmp_path):
    _reset_usage()
    java = ("### FILE: Singleton.java\n```java\n"
            "public class Singleton {\n"
            "    private static Singleton instance;\n"
            "    public static Singleton getInstance() { return instance; }\n"
            "}\n```")
    pairs = [("public ", -0.1), ("class ", -0.6), ("Singleton", -0.2), ("{", -0.3)]
    resp = _response(java, pairs, finish="STOP", pin=20, pout=40, thoughts=5)
    fake = _FakeClient(resp)

    model = rg.ModelConfig(id="gemini-2.5-flash", provider="vertex")
    cfg = _study_cfg(tmp_path / "out", model)
    ctx = cfg.contexts[0]
    unit = rg.Unit("Singleton", ctx.title, 0)
    limiter = rg.RateLimiter()

    # Route the real path (generate_unit -> call_with_retries -> call_model ->
    # vertex_generate -> _get_vertex_client) at the stub client; skip RNG seeding
    # (irrelevant to a mocked backend, keeps the test torch-free & fast).
    with _patched(rg, "_get_vertex_client", lambda *a, **k: fake), \
         _patched(rg, "apply_seed", lambda *a, **k: None):
        rec = rg.generate_unit(unit, ctx, cfg, limiter)

    assert rec["status"] == "ok"
    assert rec["provider"] == "vertex"
    assert rec["mean_logprob"] is not None
    assert _close(rec["min_logprob_critical"], -0.6)
    assert rec["num_logprob_tokens"] == 4

    unit_dir = unit.dir_under(cfg.output_dir, ctx.slug)
    assert (unit_dir / "unit.json").exists()
    assert (unit_dir / "token_logprobs.json").exists()
    assert (unit_dir / "Singleton.java").exists()

    # token_logprobs.json schema is IDENTICAL to the HF path.
    tlj = json.loads((unit_dir / "token_logprobs.json").read_text(encoding="utf-8"))
    assert tlj["num_logprob_tokens"] == 4
    assert len(tlj["tokens"]) == 4
    assert set(tlj["tokens"][0].keys()) == {"token_str", "logprob"}
    assert tlj["tokens"][1]["token_str"] == "class "

    # The UNCHANGED analyze_logprob_separation.py reads the vertex unit.json.
    summaries = al.load_unit_summaries(cfg.output_dir)
    assert rec["unit_id"] in summaries
    got = summaries[rec["unit_id"]]
    assert got["mean_logprob"] == rec["mean_logprob"]
    assert got["min_logprob_critical"] == rec["min_logprob_critical"]


def test_generate_unit_vertex_blocked_is_parse_failed(tmp_path):
    _reset_usage()
    resp = _response(None, None, has_candidate=False, block_reason="PROHIBITED_CONTENT")
    fake = _FakeClient(resp)
    model = rg.ModelConfig(id="gemini-2.5-pro", provider="vertex")
    cfg = _study_cfg(tmp_path / "out", model)
    ctx = cfg.contexts[0]
    unit = rg.Unit("Singleton", ctx.title, 0)

    with _patched(rg, "_get_vertex_client", lambda *a, **k: fake), \
         _patched(rg, "apply_seed", lambda *a, **k: None):
        rec = rg.generate_unit(unit, ctx, cfg, rg.RateLimiter())

    assert rec["status"] == "parse_failed"          # terminal -> resume skips it
    assert rec["status"] in rg.TERMINAL_STATUSES
    unit_dir = unit.dir_under(cfg.output_dir, ctx.slug)
    raw = (unit_dir / "raw_response.txt").read_text(encoding="utf-8")
    assert raw.startswith("VERTEX_BLOCKED")         # the reason is saved
    assert "PROHIBITED_CONTENT" in raw


# --------------------------------------------------------------------------- #
# 7. Gemini 3.x guard (config-time, no API call)                               #
# --------------------------------------------------------------------------- #
def test_gemini_3x_rejected_at_config_time():
    args = _fake_args(model_id="gemini-3-pro-preview", provider="vertex")
    with pytest.raises(SystemExit):
        rg.build_config(args)
    # 2.5 is accepted.
    ok = rg.build_config(_fake_args(model_id="gemini-2.5-flash", provider="vertex"))
    assert ok.model.provider == "vertex"


def _fake_args(model_id, provider):
    return NS(
        model_id=model_id, provider=provider, dtype="auto", device="auto", attn="sdpa",
        trust_remote_code=False, base_url=None, rate_limit_per_min=0.0,
        patterns=None, patterns_file=None,
        contexts_file=str(REPO / "data" / "input" / "common_java_projects.json"),
        k=1, seed=40, model_tag=None, temperature=0.7, max_tokens=2500, timeout=120,
        retry_max_attempts=3, retry_backoff="2,4,8", output_dir="generated_logprobs_vertex",
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
