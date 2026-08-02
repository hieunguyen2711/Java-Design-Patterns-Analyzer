#!/usr/bin/env python3
"""
run_generation_logprobs.py -- LOGPROB PILOT sibling of run_generation.py.

Near-exact copy of run_generation.py. Same cluster-safe behavior, with two
deliberate differences for a small confidence-vs-correctness pilot:
  1. DEFAULT_PATTERNS is fixed to the 8 PIQS-supported patterns (below).
  2. The HuggingFace backend additionally captures per-token log-probabilities
     and three summary confidence numbers per generation (mean / min /
     min-on-critical-lines). The ollama backend is unchanged and leaves the new
     logprob fields null (a local server does not reliably return per-token
     logprobs). Everything else -- prompts, parsing, atomic writes, resume,
     sharding, retries, the transformers 4.x/5.x + cuDNN-SDPA handling -- is
     preserved exactly as in run_generation.py.

ALL generation logic lives in this one file so it is trivial to read, copy to a
compute node, and debug from Slurm --output/--error log files. Its core needs
only the Python standard library plus PyYAML (config). Model backends are
loaded lazily, so you only need a backend's libraries if you actually use it.

Model backends (config model.provider)
-----------------------------------------
* huggingface  -- load the model weights IN-PROCESS on the local GPU and generate
                  with transformers (+ torch). No server, NO API key. This is
                  the default backend for this study (Llama 3.1 8B, Qwen 2.5 7B).
* ollama       -- POST to a local OpenAI-compatible server (Ollama / vLLM / TGI /
                  LM Studio) at model.base_url. No API key. Needs requests.

There is NO hosted/paid backend and NO API key anywhere.

What it does
------------
Generates one Java project per unit of work. A UNIT OF WORK is:

    (pattern, project_context, repetition)

for a single configured model. For each unit it builds a prompt, generates with
the configured backend, parses the returned text into Java files LOCALLY, and
writes one self-contained result directory per unit.

Cluster guarantees
------------------
* Resumable by construction: a unit is skipped if its unit.json already exists
  with a terminal status (ok / parse_failed). Results are written atomically
  (temp file + os.replace) so a killed/preempted job never leaves a
  half-written record that looks complete. Re-running the same config resumes
  and does only the missing units -- never duplicates work.
* Sharding: --shard i/n splits the grid into disjoint slices. (For the
  in-process huggingface backend a single task is usually best, since the model
  loads once and does the whole grid; sharding across tasks reloads it per task.)
* Robust I/O: failures are captured per unit -- the unit is recorded failed
  and the run MOVES ON. One bad unit never kills the whole run. Truncation is
  logged.

Usage
-----
There is NO config file: every knob is a command-line flag with a study default,
so a run is fully described by the command that launched it.

    python run_generation_logprobs.py --model-id Qwen/Qwen2.5-7B-Instruct --dry-run
    python run_generation_logprobs.py --model-id Qwen/Qwen2.5-7B-Instruct --limit 3
    python run_generation_logprobs.py --model-id Qwen/Qwen2.5-7B-Instruct \
        --k 1 --temperature 0.7 --output-dir generated_logprobs_qwen25_7b
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Pilot: python run_generation_logprobs.py --model-id Qwen/Qwen2.5-7B-Instruct \
#        --k 1 --temperature 0.7 --output-dir generated_logprobs_qwen25_7b
# (k=1, breadth-first, at the study temperature; HuggingFace backend on a local
# GPU node. The default flags below are unchanged from run_generation.py.)

DEFAULT_OLLAMA_BASE = "http://127.0.0.1:11434"     # native Ollama OpenAI-compatible port
VALID_PROVIDERS = {"huggingface", "ollama"}

# The study grid is patterns x contexts x reps. These are EXACTLY the 8 patterns
# our PIQS checker scores (this is the logprob pilot: "Abstract Factory" and
# "Adapter" are dropped because PIQS does not support them, and "Template Method"
# is added). Against the 12 projects in common_java_projects.json at k=1 they give
# the 96 units the run scripts expect. Override with --patterns or --patterns-file.
DEFAULT_PATTERNS = [
    "Singleton",
    "Factory Method",
    "Strategy",
    "Composite",
    "Observer",
    "Builder",
    "Decorator",
    "Template Method",
]
DEFAULT_CONTEXTS_FILE = "common_java_projects.json"

TERMINAL_STATUSES = {"ok", "parse_failed"}          # these units are DONE; skip on resume
RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}

logger = logging.getLogger("run_generation")


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    lowered = str(value).lower().strip()
    sanitized = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return sanitized or "x"


# --------------------------------------------------------------------------- #
# Typed errors so the retry loop can distinguish transient vs permanent        #
# --------------------------------------------------------------------------- #
class RetryableError(Exception):
    """A transient failure (e.g. a local server 429/5xx/timeout) worth retrying."""


class PermanentError(Exception):
    """A non-transient failure (bad config, OOM, missing library) -- do not retry."""


# --------------------------------------------------------------------------- #
# Config                                                                       #
# --------------------------------------------------------------------------- #
@dataclass
class ModelConfig:
    id: str
    provider: str = "huggingface"         # "huggingface" | "ollama"
    # huggingface backend:
    dtype: str = "auto"                   # auto | bfloat16 | float16 | float32
    device: str = "auto"                  # auto | cuda | cpu
    attn: str = "sdpa"                    # sdpa | eager (eager if cuDNN is broken)
    trust_remote_code: bool = False
    # ollama (local server) backend:
    base_url: Optional[str] = None
    rate_limit_per_min: float = 0.0       # per-process request cap (0 = no throttle)

    @property
    def slug(self) -> str:
        return slugify(self.id)


@dataclass
class Context:
    title: str
    context: str

    @property
    def slug(self) -> str:
        return slugify(self.title)


@dataclass
class StudyConfig:
    output_dir: Path
    model: ModelConfig
    patterns: list[str]
    contexts: list[Context]
    seed: int
    k: int
    temperature: float
    max_tokens: int
    request_timeout_seconds: int
    retry_max_attempts: int
    retry_backoff_seconds: list[float]


def _load_patterns(spec_inline, patterns_file: Optional[str]) -> list[str]:
    """Patterns come from an inline list OR a JSON file (list of strings, or list
    of objects with a pattern field, optionally filtered to Status == 'pass')."""
    if spec_inline:
        return [str(p).strip() for p in spec_inline if str(p).strip()]
    if not patterns_file:
        raise SystemExit("Config error: provide patterns (inline) or patterns_file.")
    path = Path(patterns_file)
    if not path.exists():
        raise SystemExit(f"Config error: patterns_file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"Config error: patterns_file must be a JSON array: {path}")
    out: list[str] = []
    seen: set[str] = set()
    for row in data:
        if isinstance(row, str):
            name = row.strip()
        elif isinstance(row, dict):
            if "Status" in row and str(row.get("Status", "")).strip().lower() != "pass":
                continue
            name = str(row.get("pattern", "")).strip()
        else:
            continue
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    if not out:
        raise SystemExit(f"Config error: no patterns loaded from {path}.")
    return out


def _load_contexts(spec_inline, contexts_file: Optional[str]) -> list[Context]:
    """Contexts come from an inline list OR a JSON file (objects with
    project_title / project_context, e.g. data/input/common_java_projects.json)."""
    if spec_inline:
        out = []
        for d in spec_inline:
            if not isinstance(d, dict) or not d.get("title") or not d.get("context"):
                raise SystemExit(f"Config error: each inline context needs title + context. Got {d!r}")
            out.append(Context(title=str(d["title"]), context=str(d["context"])))
        return out
    if not contexts_file:
        raise SystemExit("Config error: provide contexts (inline) or contexts_file.")
    path = Path(contexts_file)
    if not path.exists():
        raise SystemExit(f"Config error: contexts_file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"Config error: contexts_file must be a JSON array: {path}")
    out = []
    for row in data:
        if not isinstance(row, dict):
            continue
        title = str(row.get("project_title") or row.get("title") or "").strip()
        ctx = str(row.get("project_context") or row.get("context") or "").strip()
        if title and ctx:
            out.append(Context(title=title, context=ctx))
    if not out:
        raise SystemExit(f"Config error: no contexts loaded from {path}.")
    return out


def build_config(args: argparse.Namespace) -> StudyConfig:
    """Assemble the study config from command-line arguments. There is no config
    file: every knob is a flag with a study default, so a run is fully described
    by the command that launched it (and by the copy saved into run.log)."""
    provider = str(args.provider).lower()
    if provider not in VALID_PROVIDERS:
        raise SystemExit(f"Config error: --provider must be one of {sorted(VALID_PROVIDERS)}, "
                         f"got {provider!r}")
    base_url = args.base_url or (DEFAULT_OLLAMA_BASE if provider == "ollama" else None)
    model = ModelConfig(
        id=args.model_id,
        provider=provider,
        dtype=args.dtype,
        device=args.device,
        attn=args.attn,
        trust_remote_code=args.trust_remote_code,
        base_url=base_url,
        rate_limit_per_min=args.rate_limit_per_min,
    )

    # --patterns wins over --patterns-file, which wins over the built-in list.
    inline_patterns = [p.strip() for p in args.patterns.split(",") if p.strip()] if args.patterns else None
    if inline_patterns or args.patterns_file:
        patterns = _load_patterns(inline_patterns, args.patterns_file)
    else:
        patterns = list(DEFAULT_PATTERNS)
    contexts = _load_contexts(None, args.contexts_file)

    # Results are laid out as <output-dir>/<model-tag>/seed_<seed>/<pattern>/...
    # so the seeds of one model sit side by side and never overwrite each other.
    tag = args.model_tag or model.slug
    out_dir = Path(args.output_dir) / tag / f"seed_{args.seed}"

    cfg = StudyConfig(
        output_dir=out_dir,
        model=model,
        patterns=patterns,
        contexts=contexts,
        seed=args.seed,
        k=args.k,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        request_timeout_seconds=args.timeout,
        retry_max_attempts=args.retry_max_attempts,
        retry_backoff_seconds=[float(x) for x in args.retry_backoff.split(",") if x.strip()],
    )
    if cfg.k < 1:
        raise SystemExit("Config error: --k must be >= 1.")
    if not cfg.retry_backoff_seconds:
        raise SystemExit("Config error: --retry-backoff must list at least one delay.")
    return cfg


# --------------------------------------------------------------------------- #
# Unit of work                                                                 #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Unit:
    pattern: str
    context_title: str
    repetition: int

    def dir_under(self, root: Path, context_slug: str) -> Path:
        return root / self.pattern / context_slug / f"rep{self.repetition}"

    @property
    def label(self) -> str:
        return f"{self.pattern} | {self.context_title} | rep{self.repetition}"


def build_grid(cfg: StudyConfig) -> list[tuple[Unit, Context]]:
    """Full ordered grid (pattern x context x rep). Order is deterministic and
    stable so --shard slices are disjoint and reproducible across runs/nodes."""
    pairs: list[tuple[Unit, Context]] = []
    for pattern in cfg.patterns:
        for ctx in cfg.contexts:
            for rep in range(cfg.k):
                pairs.append((Unit(pattern, ctx.title, rep), ctx))
    pairs.sort(key=lambda t: (t[0].pattern, t[1].slug, t[0].repetition))
    return pairs


def apply_shard(items: list, shard_index: int, shard_count: int) -> list:
    if shard_count <= 1:
        return items
    return [it for i, it in enumerate(items) if i % shard_count == shard_index]


def select_units(cfg: StudyConfig, shard_index: int, shard_count: int, limit: Optional[int]
                 ) -> list[tuple[Unit, Context]]:
    grid = apply_shard(build_grid(cfg), shard_index, shard_count)
    return grid[:limit] if limit is not None else grid


# --------------------------------------------------------------------------- #
# Prompt (kept identical to app/services/prompt_service.build_batch_generate_prompt
# so generated output stays comparable to the existing generated_batches/ jobs)  #
# --------------------------------------------------------------------------- #
def build_prompt(pattern: str, project_context: str) -> str:
    lines = [
        "You are a senior Java software engineer and design pattern expert.",
        "Generate a complete, minimal Java project that clearly demonstrates exactly ONE design pattern.",
        "The requested design pattern must be implemented faithfully and be easy to recognize.",
        "IMPORTANT: Output each class or interface in its own separate file using EXACTLY this format:",
        "",
        "### FILE: ClassName.java",
        "```java",
        "// code here",
        "```",
        "",
        "Rules:",
        "- One class or interface per file.",
        "- The filename must match the public class/interface name exactly.",
        "- Include package declaration when appropriate.",
        "- Keep code compilable and coherent as a single project.",
        "- Do not include any explanation outside the file blocks.",
        "",
        f"Design Pattern: {pattern}",
        f"Shared Project Context: {project_context}",
    ]
    return "\n".join(lines)


def prompt_sha256(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# LOCAL parse recovery (never re-generates)                                    #
# --------------------------------------------------------------------------- #
_FILE_BLOCK_RE = re.compile(
    r"###\s*FILE:\s*(\S+?\.java)\s*\n(?:```[a-zA-Z]*\s*\n)?(.*?)(?:```|(?=###\s*FILE:|\Z))",
    re.DOTALL,
)
_FENCED_JAVA_RE = re.compile(r"```(?:java)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
_TYPE_DECL_RE = re.compile(
    r"(?:public\s+|final\s+|abstract\s+)*\b(?:class|interface|enum|record)\s+([A-Za-z_]\w*)",
)


def _derive_filename(java_source: str, fallback_index: int) -> str:
    m = re.search(r"public\s+(?:final\s+|abstract\s+)*(?:class|interface|enum|record)\s+([A-Za-z_]\w*)", java_source)
    if not m:
        m = _TYPE_DECL_RE.search(java_source)
    return f"{m.group(1)}.java" if m else f"GeneratedCode{fallback_index}.java"


def _extract_type_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    for m in _TYPE_DECL_RE.finditer(text):
        start = m.start()
        brace = text.find("{", m.end())
        if brace == -1:
            continue
        depth, end = 0, None
        for i in range(brace, len(text)):
            c = text[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end is not None:
            blocks.append(text[start:end])
    return blocks


def parse_generated_files(raw: str) -> tuple[list[dict[str, str]], str]:
    """Return (files, method). NEVER re-generates."""
    files: list[dict[str, str]] = []
    for m in _FILE_BLOCK_RE.finditer(raw):
        filename = m.group(1).strip()
        content = m.group(2).strip()
        if filename and content:
            files.append({"filename": filename, "content": content})
    if files:
        return files, "file_blocks"

    for i, m in enumerate(_FENCED_JAVA_RE.finditer(raw)):
        content = m.group(1).strip()
        if any(kw in content for kw in ("class", "interface", "enum", "record")):
            files.append({"filename": _derive_filename(content, i), "content": content})
    if files:
        return files, "fenced_java"

    for i, block in enumerate(_extract_type_blocks(raw)):
        files.append({"filename": _derive_filename(block, i), "content": block.strip()})
    if files:
        return files, "type_blocks"

    return [], ""


# --------------------------------------------------------------------------- #
# Model backends                                                               #
# --------------------------------------------------------------------------- #
@dataclass
class CallResult:
    content: str
    tokens_in: int
    tokens_out: int
    tokens_estimated: bool
    model_returned: str
    finish_reason: str
    # ---- logprob pilot fields (HuggingFace backend ONLY) -------------------- #
    # Optional and default to None/False/0 so the ollama path -- which never
    # sets them -- still constructs a CallResult exactly as before.
    token_logprobs: Optional[list] = None      # per generated token, in order
    token_strings: Optional[list] = None       # convert_ids_to_tokens, same order
    mean_logprob: Optional[float] = None
    min_logprob: Optional[float] = None
    min_logprob_critical: Optional[float] = None
    critical_fallback: bool = False
    num_logprob_tokens: int = 0


# --------------------------------------------------------------------------- #
# Logprob summary helpers (pilot)                                              #
#                                                                             #
# Pure, torch-free functions so they unit-test with hand-made inputs and are  #
# reachable ONLY from the HuggingFace backend. The "critical line" set is a    #
# deliberate keyword/token APPROXIMATION standing in for precise predicate-    #
# span alignment; replace it with real span alignment IF the pilot shows       #
# signal. Whole-word matching only (pass-3 lesson): "class" must not fire      #
# inside "getClass".                                                           #
# --------------------------------------------------------------------------- #
# Java structural markers that make a line "critical-ish" for the proxy.
_CRITICAL_KEYWORDS = ("implements", "extends", "abstract", "interface", "class", "return", "new")
_CRITICAL_KEYWORD_RE = re.compile(r"\b(?:" + "|".join(_CRITICAL_KEYWORDS) + r")\b")
# a method call: a '.' immediately followed by an identifier and '(' -- e.g. .doThing(
_METHOD_CALL_RE = re.compile(r"\.\s*[A-Za-z_]\w*\s*\(")
_OVERRIDE_RE = re.compile(r"@Override\b")


def _line_is_critical(line: str) -> bool:
    """True if a source line carries a structural Java marker (APPROXIMATION)."""
    if _CRITICAL_KEYWORD_RE.search(line):
        return True
    if _METHOD_CALL_RE.search(line):
        return True
    if _OVERRIDE_RE.search(line):
        return True
    return False


def _tokens_to_lines(token_pieces: list) -> tuple[list, list]:
    """Reconstruct the generated text from per-token decoded pieces and map each
    token to the line index/indices its characters land on.

    Returns (lines, token_line_indices) where lines is the text split on '\\n'
    and token_line_indices[t] is the sorted list of line indices token t touches.
    A '\\n' is attributed to the line it terminates (not the empty line it opens),
    so a token is only tied to lines it actually contributes characters to.
    """
    lines: list = [""]
    token_line_indices: list = []
    cur = 0
    for piece in token_pieces:
        touched: set = set()
        for ch in piece:
            if ch == "\n":
                touched.add(cur)          # the newline belongs to the line it ends
                cur += 1
                lines.append("")
            else:
                lines[cur] += ch
                touched.add(cur)
        if not touched:                    # empty piece: attribute to current line
            touched.add(cur)
        token_line_indices.append(sorted(touched))
    return lines, token_line_indices


def compute_logprob_summary(token_logprobs: list, token_pieces: list) -> dict:
    """Compute the three pilot confidence numbers from per-token logprobs.

    token_logprobs : list[float]  logprob of each generated token, in order.
    token_pieces   : list[str]    decoded text contribution of each token, in the
                                   same order/alignment as token_logprobs.

    Returns mean_logprob, min_logprob, min_logprob_critical, critical_fallback,
    num_logprob_tokens. Empty token_logprobs -> Nones / False / 0.
    """
    n = len(token_logprobs)
    if n == 0:
        return {
            "mean_logprob": None,
            "min_logprob": None,
            "min_logprob_critical": None,
            "critical_fallback": False,
            "num_logprob_tokens": 0,
        }

    mean_lp = sum(token_logprobs) / n
    min_lp = min(token_logprobs)

    # --- critical-line proxy (APPROXIMATION -- see helpers above) ------------ #
    lines, token_line_indices = _tokens_to_lines(token_pieces)
    critical_lines = {i for i, ln in enumerate(lines) if _line_is_critical(ln)}
    critical_lps: list = []
    # token_pieces may be shorter than token_logprobs on a version off-by-one;
    # align on the shorter length so we never index past either.
    m = min(n, len(token_line_indices))
    for t in range(m):
        if any(li in critical_lines for li in token_line_indices[t]):
            critical_lps.append(token_logprobs[t])

    if critical_lps:
        min_lp_crit = min(critical_lps)
        crit_fallback = False
    else:
        # No critical lines found (rare): fall back to the global min and flag it.
        min_lp_crit = min_lp
        crit_fallback = True

    return {
        "mean_logprob": mean_lp,
        "min_logprob": min_lp,
        "min_logprob_critical": min_lp_crit,
        "critical_fallback": crit_fallback,
        "num_logprob_tokens": n,
    }


# ---- in-process Hugging Face (transformers) -------------------------------- #
_HF_CACHE: dict[str, Any] = {}   # model_id -> (tokenizer, model, device)


def _load_hf(model: ModelConfig):
    """Load (and cache) a Hugging Face causal LM once per process."""
    if model.id in _HF_CACHE:
        return _HF_CACHE[model.id]
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:  # pragma: no cover - environment-specific
        raise PermanentError(
            "provider 'huggingface' needs transformers + torch. Install: "
            "pip install -r requirements-hf.txt (and a torch build for your CUDA)."
        ) from exc

    device = model.device
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    if model.dtype in ("auto", ""):
        torch_dtype = torch.bfloat16 if device == "cuda" else torch.float32
    else:
        torch_dtype = getattr(torch, model.dtype, torch.float32)

    # This cluster's cuDNN does not match the torch cu130 build: the cuDNN SDPA
    # backend fails every unit with CUDNN_STATUS_SUBLIBRARY_VERSION_MISMATCH and
    # then segfaults the process. Disable only that backend. Flash and
    # mem-efficient SDPA stay on, so attention is still fused and fast, unlike
    # --attn eager which falls back to the slow math path.
    if device == "cuda" and hasattr(torch.backends.cuda, "enable_cudnn_sdp"):
        torch.backends.cuda.enable_cudnn_sdp(False)
        logger.info("Disabled cuDNN SDPA backend (cluster cuDNN/CUDA mismatch).")

    logger.info("Loading HF model %s (device=%s, dtype=%s, attn=%s) -- first load can take a while...",
                model.id, device, torch_dtype, model.attn)
    tokenizer = AutoTokenizer.from_pretrained(model.id, trust_remote_code=model.trust_remote_code)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    # transformers 5 renamed torch_dtype to dtype; 4.x only knows the old
    # name. Pick by version so this works on either.
    import transformers
    dtype_kw = "dtype" if int(transformers.__version__.split(".")[0]) >= 5 else "torch_dtype"
    hf_model = AutoModelForCausalLM.from_pretrained(
        model.id, trust_remote_code=model.trust_remote_code,
        attn_implementation=model.attn, **{dtype_kw: torch_dtype},
    ).to(device)
    hf_model.eval()
    _HF_CACHE[model.id] = (tokenizer, hf_model, device)
    logger.info("Loaded HF model %s.", model.id)
    return _HF_CACHE[model.id]


def hf_generate(model: ModelConfig, prompt: str, temperature: float, max_tokens: int) -> CallResult:
    import torch
    tokenizer, hf_model, device = _load_hf(model)
    messages = [{"role": "user", "content": prompt}]
    # transformers 5 returns a BatchEncoding (input_ids + attention_mask) from
    # apply_chat_template; 4.x returned a bare tensor. Handle both.
    encoded = tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, return_tensors="pt", return_dict=True
    ).to(device)
    if isinstance(encoded, torch.Tensor):
        input_ids = encoded
        attention_mask = torch.ones_like(input_ids)
    else:
        input_ids = encoded["input_ids"]
        attention_mask = encoded.get("attention_mask")
        if attention_mask is None:
            attention_mask = torch.ones_like(input_ids)

    do_sample = bool(temperature and temperature > 0)
    gen_kwargs: dict[str, Any] = {
        "max_new_tokens": max_tokens,
        "do_sample": do_sample,
        "pad_token_id": tokenizer.pad_token_id,
    }
    if do_sample:
        gen_kwargs["temperature"] = float(temperature)
    # --- logprob pilot: ask generate for per-step scores + a structured output.
    # This turns `output` into a generate-output object (not a bare tensor), so
    # the generated ids move from output[0] to output.sequences[0] below.
    gen_kwargs["return_dict_in_generate"] = True
    gen_kwargs["output_scores"] = True

    try:
        with torch.no_grad():
            output = hf_model.generate(input_ids, attention_mask=attention_mask, **gen_kwargs)
    except Exception as exc:  # OOM, generation errors -- not transient
        raise PermanentError(f"HF generation failed: {exc}") from exc

    prompt_len = int(input_ids.shape[-1])
    gen_ids = output.sequences[0][prompt_len:]
    text = tokenizer.decode(gen_ids, skip_special_tokens=True)
    tokens_out = int(gen_ids.shape[-1])
    finish_reason = "length" if tokens_out >= max_tokens else "stop"

    # --- logprob pilot: per-token logprob of each GENERATED token -------------
    # output.scores is a tuple (one logits tensor [batch, vocab] per generated
    # step). NOTE: these are the scores AFTER logits processing (e.g. temperature
    # warping when sampling), which is what generate exposes. log_softmax over the
    # vocab, then pick the logprob of the id actually generated at that step.
    # Everything is pulled to CPU python floats immediately so NO GPU tensor is
    # kept alive past this block.
    token_logprobs: list = []
    token_strings: list = []
    token_pieces: list = []
    with torch.no_grad():
        gen_id_list = gen_ids.tolist()
        scores = getattr(output, "scores", None) or ()
        # A model/version off-by-one can make len(scores) != len(gen_ids); align
        # on the shorter length so we never index past either (never crash).
        n_steps = min(len(scores), len(gen_id_list))
        for t in range(n_steps):
            step_logprobs = torch.log_softmax(scores[t][0].float(), dim=-1)
            token_logprobs.append(float(step_logprobs[gen_id_list[t]].item()))
        # Per-token strings: the raw token (convert_ids_to_tokens) for the saved
        # record, plus the actual decoded text piece used by the critical-line
        # proxy. The text piece is decode(ids[:i+1]) minus decode(ids[:i]) so BPE
        # markers (Ġ / ▁) never leak into the whole-word matching.
        if gen_id_list:
            token_strings = list(tokenizer.convert_ids_to_tokens(gen_id_list))
            prev = ""
            for i in range(len(gen_id_list)):
                whole = tokenizer.decode(gen_id_list[: i + 1], skip_special_tokens=True)
                if whole.startswith(prev):
                    token_pieces.append(whole[len(prev):])
                else:
                    # rare: decode isn't a clean prefix-extension; decode this
                    # single id so the proxy still gets real (BPE-marker-free) text.
                    token_pieces.append(tokenizer.decode([gen_id_list[i]], skip_special_tokens=True))
                prev = whole

    summary = compute_logprob_summary(token_logprobs, token_pieces)
    return CallResult(
        text, prompt_len, tokens_out, False, model.id, finish_reason,
        token_logprobs=token_logprobs,
        token_strings=token_strings,
        mean_logprob=summary["mean_logprob"],
        min_logprob=summary["min_logprob"],
        min_logprob_critical=summary["min_logprob_critical"],
        critical_fallback=summary["critical_fallback"],
        num_logprob_tokens=summary["num_logprob_tokens"],
    )


# ---- local OpenAI-compatible server (Ollama / vLLM / TGI), no API key ------ #
def ollama_generate(model: ModelConfig, prompt: str, temperature: float, max_tokens: int,
                    timeout: int) -> CallResult:
    try:
        import requests
    except ImportError as exc:  # pragma: no cover
        raise PermanentError("provider 'ollama' needs requests. pip install -r requirements-generation.txt") from exc

    base = (model.base_url or DEFAULT_OLLAMA_BASE).rstrip("/")
    url = f"{base}/v1/chat/completions"
    payload = {
        "model": model.id,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    try:
        resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=timeout)
    except requests.exceptions.Timeout as exc:
        raise RetryableError(f"timeout after {timeout}s") from exc
    except requests.exceptions.RequestException as exc:
        raise RetryableError(f"connection error: {exc}") from exc

    if resp.status_code in RETRYABLE_STATUS_CODES:
        raise RetryableError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    if not resp.ok:
        raise PermanentError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    try:
        data = resp.json()
        choice = data["choices"][0]
        content = str(choice["message"]["content"] or "")
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise RetryableError(f"malformed response: {str(getattr(resp, 'text', ''))[:200]}") from exc

    finish_reason = str(choice.get("finish_reason", "") or "")
    usage = data.get("usage") or {}
    tokens_in = int(usage.get("prompt_tokens", 0) or 0)
    tokens_out = int(usage.get("completion_tokens", 0) or 0)
    estimated = False
    if tokens_in == 0 and tokens_out == 0:
        tokens_in, tokens_out, estimated = max(1, len(prompt) // 4), max(1, len(content) // 4), True
    return CallResult(content, tokens_in, tokens_out, estimated, str(data.get("model") or model.id), finish_reason)


def call_model(model: ModelConfig, prompt: str, temperature: float, max_tokens: int, timeout: int) -> CallResult:
    """Dispatch to the configured backend."""
    if model.provider == "huggingface":
        return hf_generate(model, prompt, temperature, max_tokens)
    if model.provider == "ollama":
        return ollama_generate(model, prompt, temperature, max_tokens, timeout)
    raise PermanentError(f"unknown provider: {model.provider}")


def call_with_retries(model: ModelConfig, prompt: str, cfg: StudyConfig
                      ) -> tuple[Optional[CallResult], Optional[str], int]:
    attempts = 0
    last_err = "unknown"
    for attempt in range(1, cfg.retry_max_attempts + 1):
        attempts = attempt
        try:
            return call_model(model, prompt, cfg.temperature, cfg.max_tokens,
                              cfg.request_timeout_seconds), None, attempts
        except PermanentError as exc:
            return None, f"permanent: {exc}", attempts
        except RetryableError as exc:
            last_err = str(exc)
            if attempt < cfg.retry_max_attempts:
                backoff = cfg.retry_backoff_seconds[min(attempt - 1, len(cfg.retry_backoff_seconds) - 1)]
                logger.warning("  transient error (attempt %d/%d): %s -- backing off %ss",
                               attempt, cfg.retry_max_attempts, last_err, backoff)
                time.sleep(backoff)
    return None, f"retryable exhausted: {last_err}", attempts


# --------------------------------------------------------------------------- #
# Per-model rate limiter (per process; only relevant for the ollama backend)   #
# --------------------------------------------------------------------------- #
class RateLimiter:
    def __init__(self) -> None:
        self._last: dict[str, float] = {}

    def wait(self, model: ModelConfig) -> None:
        if model.rate_limit_per_min <= 0:
            return
        min_interval = 60.0 / model.rate_limit_per_min
        last = self._last.get(model.id)
        if last is not None:
            elapsed = time.time() - last
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
        self._last[model.id] = time.time()


# --------------------------------------------------------------------------- #
# Per-unit persistence (atomic)                                                #
# --------------------------------------------------------------------------- #
def unit_id(unit: Unit, model: ModelConfig) -> str:
    return f"{model.slug}__{unit.pattern}__{slugify(unit.context_title)}__rep{unit.repetition}"


def seed_for_unit(base_seed: int, uid: str) -> int:
    """Derive a per-unit seed from (base_seed, unit_id).

    Seeding once per process would make results depend on the ORDER units run
    in, so a resumed run would not reproduce a fresh one, and --shard slices
    would disagree with the whole grid. Deriving the seed from the unit id makes
    each unit reproducible on its own, whatever else runs alongside it.
    """
    h = hashlib.sha256(f"{base_seed}:{uid}".encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big")


def apply_seed(seed: int) -> None:
    """Seed every RNG that can affect sampling.

    torch is imported here rather than read out of sys.modules: run_generation
    imports it lazily inside hf_generate, so on the first unit of a run it is
    not loaded yet and a sys.modules lookup would silently skip seeding it. The
    import is a no-op once cached. Missing torch is fine (ollama backend).
    """
    random.seed(seed)
    try:
        import torch
    except ImportError:
        return
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def atomic_write_text(path: Path, text: str) -> None:
    """Write to a temp file in the same dir, then os.replace (atomic on POSIX).
    A crash mid-write leaves only the temp file, never a half-written target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.tmp.{os.getpid()}"
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def unit_is_done(unit_dir: Path) -> Optional[str]:
    unit_json = unit_dir / "unit.json"
    if not unit_json.exists():
        return None
    try:
        rec = json.loads(unit_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    status = rec.get("status")
    return status if status in TERMINAL_STATUSES else None


def write_unit_result(unit_dir: Path, record: dict[str, Any], files: list[dict[str, str]],
                      prompt: str, raw_response: str,
                      token_logprobs_data: Optional[dict[str, Any]] = None) -> None:
    """Write the .java files, prompt, raw response, the (optional) full per-token
    logprob file, then unit.json LAST (and atomically) so the presence of a
    terminal unit.json means everything else is already on disk."""
    unit_dir.mkdir(parents=True, exist_ok=True)
    for f in files:
        name = Path(str(f.get("filename", "GeneratedCode.java"))).name
        if not name.endswith(".java"):
            name = f"{name}.java"
        atomic_write_text(unit_dir / name, str(f.get("content", "")))
    atomic_write_text(unit_dir / "prompt.txt", prompt)
    atomic_write_text(unit_dir / "raw_response.txt", raw_response)
    # The FULL per-token list goes to its own file so unit.json stays small.
    # Written BEFORE unit.json (like every other artifact) so the resume
    # guarantee -- terminal unit.json => everything else already on disk -- holds.
    if token_logprobs_data:
        atomic_write_text(unit_dir / "token_logprobs.json",
                          json.dumps(token_logprobs_data, indent=2, ensure_ascii=False))
    atomic_write_text(unit_dir / "unit.json", json.dumps(record, indent=2, ensure_ascii=False))


# --------------------------------------------------------------------------- #
# Generate one unit                                                            #
# --------------------------------------------------------------------------- #
def generate_unit(unit: Unit, ctx: Context, cfg: StudyConfig, limiter: RateLimiter) -> dict[str, Any]:
    unit_dir = unit.dir_under(cfg.output_dir, ctx.slug)
    prompt = build_prompt(unit.pattern, ctx.context)

    uid = unit_id(unit, cfg.model)
    unit_seed = seed_for_unit(cfg.seed, uid)
    apply_seed(unit_seed)

    limiter.wait(cfg.model)
    started = time.time()
    result, err, attempts = call_with_retries(cfg.model, prompt, cfg)
    latency_ms = int((time.time() - started) * 1000)

    base_record: dict[str, Any] = {
        "unit_id": uid,
        "seed": cfg.seed,
        "unit_seed": unit_seed,
        "model": cfg.model.id,
        "provider": cfg.model.provider,
        "pattern": unit.pattern,
        "context": ctx.slug,
        "context_title": ctx.title,
        "repetition": unit.repetition,
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
        "prompt_sha256": prompt_sha256(prompt),
        "prompt_chars": len(prompt),
        "attempts": attempts,
        "latency_ms": latency_ms,
        "created_at_utc": now_utc_iso(),
    }

    if result is None:
        record = {
            **base_record, "status": "failed", "error": err,
            "model_returned": None, "finish_reason": None, "truncated": False,
            "tokens_in": 0, "tokens_out": 0, "tokens_estimated": False,
            "extracted_files": [], "num_files": 0, "parse_method": None,
            # logprob pilot fields -- failed units keep them null.
            "mean_logprob": None, "min_logprob": None, "min_logprob_critical": None,
            "critical_fallback": None, "num_logprob_tokens": None,
        }
        write_unit_result(unit_dir, record, [], prompt, err or "")
        logger.error("FAILED  %s :: %s", unit.label, err)
        return record

    truncated = result.finish_reason == "length"
    if truncated:
        logger.warning("  TRUNCATED (finish_reason=length) %s -- consider raising max_tokens", unit.label)

    files, parse_method = parse_generated_files(result.content)
    status = "ok" if files else "parse_failed"
    record = {
        **base_record,
        "status": status,
        "error": None if files else "no Java type found in response (local recovery exhausted)",
        "model_returned": result.model_returned,
        "finish_reason": result.finish_reason,
        "truncated": truncated,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
        "tokens_estimated": result.tokens_estimated,
        "extracted_files": [f["filename"] for f in files],
        "num_files": len(files),
        "parse_method": parse_method or None,
        # logprob pilot summary numbers (HF backend; null on the ollama path).
        # The FULL per-token list is written to token_logprobs.json, NOT here,
        # so unit.json stays small.
        "mean_logprob": result.mean_logprob,
        "min_logprob": result.min_logprob,
        "min_logprob_critical": result.min_logprob_critical,
        "critical_fallback": result.critical_fallback,
        "num_logprob_tokens": result.num_logprob_tokens,
    }

    # Build the separate per-token payload only when the backend captured
    # logprobs (HuggingFace). The ollama path leaves result.token_logprobs None,
    # so no token_logprobs.json is written for it.
    token_logprobs_data = None
    if result.token_logprobs is not None and result.num_logprob_tokens > 0:
        tokstrs = result.token_strings or []
        pairs = [
            {"token_str": (tokstrs[i] if i < len(tokstrs) else None), "logprob": lp}
            for i, lp in enumerate(result.token_logprobs)
        ]
        token_logprobs_data = {
            "unit_id": uid,
            "model": cfg.model.id,
            "mean_logprob": result.mean_logprob,
            "min_logprob": result.min_logprob,
            "min_logprob_critical": result.min_logprob_critical,
            "critical_fallback": result.critical_fallback,
            "num_logprob_tokens": result.num_logprob_tokens,
            "tokens": pairs,
        }

    write_unit_result(unit_dir, record, files, prompt, result.content, token_logprobs_data)
    logger.info("%-6s %s :: %d file(s) via %s, tok in/out=%d/%d, %dms",
                status.upper(), unit.label, len(files), parse_method or "-",
                result.tokens_in, result.tokens_out, latency_ms)
    return record


# --------------------------------------------------------------------------- #
# Modes                                                                        #
# --------------------------------------------------------------------------- #
def run_dry_run(cfg: StudyConfig, shard_index: int, shard_count: int, limit: Optional[int]) -> int:
    grid = select_units(cfg, shard_index, shard_count, limit)
    logger.info("DRY RUN -- no generation will happen.")
    logger.info("Model: %s (%s)", cfg.model.id, cfg.model.provider)
    logger.info("Grid: %d patterns x %d contexts x k=%d = %d total units "
                "(this shard %d/%d -> %d units%s).",
                len(cfg.patterns), len(cfg.contexts), cfg.k, len(build_grid(cfg)),
                shard_index, shard_count, len(grid), f", limited to {limit}" if limit else "")
    for unit, _ in grid[:10]:
        logger.info("  WOULD GENERATE: %s", unit.label)
    if len(grid) > 10:
        logger.info("  ... and %d more.", len(grid) - 10)
    return 0


def run(cfg: StudyConfig, shard_index: int, shard_count: int, limit: Optional[int]) -> int:
    grid = select_units(cfg, shard_index, shard_count, limit)
    limiter = RateLimiter()
    counts = {"ok": 0, "parse_failed": 0, "failed": 0, "skipped": 0}
    total = len(grid)
    logger.info("RUN shard %d/%d: %d units to consider. Model: %s (%s). Output dir: %s",
                shard_index, shard_count, total, cfg.model.id, cfg.model.provider, cfg.output_dir)

    for i, (unit, ctx) in enumerate(grid, start=1):
        unit_dir = unit.dir_under(cfg.output_dir, ctx.slug)
        done = unit_is_done(unit_dir)
        if done is not None:
            counts["skipped"] += 1
            logger.info("[%d/%d] SKIP (already %s) %s", i, total, done, unit.label)
            continue
        logger.info("[%d/%d] %s", i, total, unit.label)
        record = generate_unit(unit, ctx, cfg, limiter)
        counts[record["status"]] = counts.get(record["status"], 0) + 1

    logger.info("Done: ok=%d parse_failed=%d failed=%d skipped=%d.",
                counts["ok"], counts["parse_failed"], counts["failed"], counts["skipped"])
    attempted = counts["ok"] + counts["parse_failed"] + counts["failed"]
    if attempted > 0 and counts["ok"] == 0 and counts["parse_failed"] == 0:
        return 4     # every attempted unit failed -> surface a broken run to Slurm
    return 0


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def parse_shard(value: str) -> tuple[int, int]:
    try:
        i_str, n_str = value.split("/", 1)
        i, n = int(i_str), int(n_str)
    except ValueError as exc:
        raise SystemExit(f"--shard must look like i/n (e.g. 0/8), got {value!r}") from exc
    if n < 1 or i < 0 or i >= n:
        raise SystemExit(f"--shard i/n must satisfy 0 <= i < n and n >= 1, got {value!r}")
    return i, n


def setup_logging(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)
    fh = logging.FileHandler(output_dir / "run.log", encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Standalone cluster-safe LLM code-generation runner.")

    g = parser.add_argument_group("model")
    g.add_argument("--model-id", required=True, help="HF model id, e.g. meta-llama/Llama-3.1-8B-Instruct.")
    g.add_argument("--provider", default="huggingface", choices=sorted(VALID_PROVIDERS),
                   help="huggingface = in-process weights; ollama = local OpenAI-compatible server.")
    g.add_argument("--dtype", default="auto", help="auto | bfloat16 | float16 | float32 (default auto).")
    g.add_argument("--device", default="auto", help="auto | cuda | cpu (default auto).")
    g.add_argument("--attn", default="sdpa", choices=["sdpa", "eager"],
                   help="Attention kernel. Use eager if fused attention still crashes.")
    g.add_argument("--trust-remote-code", action="store_true", help="Allow custom modelling code.")
    g.add_argument("--base-url", default=None,
                   help=f"ollama backend only; defaults to {DEFAULT_OLLAMA_BASE}.")
    g.add_argument("--rate-limit-per-min", type=float, default=0.0,
                   help="Per-process request cap (0 = no throttle).")

    g = parser.add_argument_group("grid")
    g.add_argument("--patterns", default=None,
                   help=f"Comma-separated pattern names. Default: the {len(DEFAULT_PATTERNS)} study patterns.")
    g.add_argument("--patterns-file", default=None,
                   help="JSON array of pattern names, or objects with a pattern field.")
    g.add_argument("--contexts-file", default=DEFAULT_CONTEXTS_FILE,
                   help=f"JSON array of project_title/project_context objects (default {DEFAULT_CONTEXTS_FILE}).")
    g.add_argument("--k", type=int, default=1, help="Repetitions per (pattern, context) cell (default 1).")
    g.add_argument("--seed", type=int, default=40,
                   help="Sampling seed. Also names the output subdir (seed_40). Default 40.")
    g.add_argument("--model-tag", default=None,
                   help="Short dir name for this model (e.g. qwen25_14b). Defaults to the model slug.")

    g = parser.add_argument_group("generation")
    g.add_argument("--temperature", type=float, default=0.2)
    g.add_argument("--max-tokens", type=int, default=2500)
    g.add_argument("--timeout", type=int, default=120, help="Per-request timeout in seconds.")
    g.add_argument("--retry-max-attempts", type=int, default=3)
    g.add_argument("--retry-backoff", default="2,4,8", help="Comma-separated backoff delays in seconds.")

    g = parser.add_argument_group("run")
    g.add_argument("--output-dir", default="generated_batches",
                   help="Base dir; results go to <base>/<model-tag>/seed_<seed>/.")
    g.add_argument("--shard", default="0/1", help="Shard as i/n (default 0/1 = whole grid). "
                   "Slurm arrays: --shard $SLURM_ARRAY_TASK_ID/$SLURM_ARRAY_TASK_COUNT.")
    g.add_argument("--dry-run", action="store_true", help="List units; NO generation.")
    g.add_argument("--limit", type=int, default=None, help="Cap total units this run (smoke test).")
    args = parser.parse_args(argv)

    cfg = build_config(args)
    shard_index, shard_count = parse_shard(args.shard)
    setup_logging(cfg.output_dir)

    logger.info("=" * 78)
    logger.info("run_generation start | model=%s | seed=%d | shard=%d/%d | dry_run=%s | limit=%s",
                cfg.model.id, cfg.seed, shard_index, shard_count, args.dry_run, args.limit)
    logger.info("Grid: %d patterns x %d contexts x k=%d = %d units",
                len(cfg.patterns), len(cfg.contexts), cfg.k,
                len(cfg.patterns) * len(cfg.contexts) * cfg.k)
    logger.info("Command: %s", " ".join(sys.argv))
    logger.info("Output dir: %s", cfg.output_dir.resolve())

    if args.dry_run:
        return run_dry_run(cfg, shard_index, shard_count, args.limit)
    return run(cfg, shard_index, shard_count, args.limit)


if __name__ == "__main__":
    sys.exit(main())
