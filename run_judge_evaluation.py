#!/usr/bin/env python3
"""
run_judge_evaluation.py

Steps 4, 5, 6: Send judge prompts to OpenRouter models, decode results,
and produce final validation report with checkpoint/resume support.

Usage examples:
  python3 run_judge_evaluation.py --dry-run
  python3 run_judge_evaluation.py --judges meta-llama/llama-3.3-70b-instruct
    python3 run_judge_evaluation.py --max-tokens 300 --parse-retry-max-tokens 500
  python3 run_judge_evaluation.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import openai
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency: openai. Install with: pip install openai"
    ) from exc


DEFAULT_JUDGES = [
    "openai/gpt-4o",
    "anthropic/claude-sonnet-4",
    "mistralai/codestral-2508",
]

SUPPORTED_JUDGES = {
    "openai/gpt-4o",
    "anthropic/claude-sonnet-4",
    "meta-llama/llama-3.3-70b-instruct",
    "mistralai/codestral-2508",
}

MODEL_COST_PER_MTOKENS = {
    "openai/gpt-4o": {"input": 2.50, "output": 10.00},
    "anthropic/claude-sonnet-4": {"input": 3.00, "output": 15.00},
    "meta-llama/llama-3.3-70b-instruct": {"input": 0.30, "output": 0.30},
    # Approximate OpenRouter pricing; update if your account uses different rates.
    "mistralai/codestral-2508": {"input": 0.30, "output": 0.90},
}

PROMPTS_FILE_CANDIDATES = [
    Path("judge_prompts.json"),
    Path("data/reports/judge_prompts.json"),
]

CHECKPOINT_FILE = Path("data/reports/judge_results_checkpoint.jsonl")
OUTPUT_FILE = Path("data/reports/judge_validation_results.json")


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run LLM-as-judge evaluation via OpenRouter.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the first prompt and exit without API calls.",
    )
    parser.add_argument(
        "--judges",
        type=str,
        default=",".join(DEFAULT_JUDGES),
        help="Comma-separated judge model IDs.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Delay between API calls in seconds (default: 2.0).",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Retry attempts per API call (default: 3).",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=200,
        help="Primary completion token limit per judge call (default: 200).",
    )
    parser.add_argument(
        "--parse-retry-max-tokens",
        type=int,
        default=400,
        help="Token limit used for one extra retry when response looks truncated (default: 400).",
    )
    parser.add_argument(
        "--retry-parse-errors",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Re-run checkpointed parse_error calls on resume (default: true).",
    )
    return parser.parse_args()


def pick_prompts_file() -> Path:
    for path in PROMPTS_FILE_CANDIDATES:
        if path.exists():
            return path
    raise FileNotFoundError(
        "Could not find judge prompts file. Tried: "
        + ", ".join(str(p) for p in PROMPTS_FILE_CANDIDATES)
    )


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def parse_judges(judges_arg: str) -> List[str]:
    models = [m.strip() for m in judges_arg.split(",") if m.strip()]
    invalid = [m for m in models if m not in SUPPORTED_JUDGES]
    if invalid:
        raise ValueError(
            "Unsupported judges: "
            + ", ".join(invalid)
            + f". Allowed: {', '.join(sorted(SUPPORTED_JUDGES))}"
        )
    if not models:
        raise ValueError("No judges selected.")
    return models


def winner_balance_check(pairs: List[dict]) -> Tuple[float, float, bool]:
    if not pairs:
        return 0.0, 0.0, False

    a_count = sum(1 for p in pairs if str(p.get("expected_winner", "")).upper() == "A")
    b_count = sum(1 for p in pairs if str(p.get("expected_winner", "")).upper() == "B")
    total = len(pairs)

    a_pct = (a_count / total) * 100.0
    b_pct = (b_count / total) * 100.0
    warning = not (40.0 <= a_pct <= 60.0 and 40.0 <= b_pct <= 60.0)
    return a_pct, b_pct, warning


def load_checkpoint(path: Path) -> Dict[Tuple[int, str], dict]:
    out: Dict[Tuple[int, str], dict] = {}
    if not path.exists():
        return out

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                key = (int(row["pair_id"]), str(row["judge_model"]))
                out[key] = row
            except Exception:
                continue
    return out


def append_checkpoint(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def extract_first_json_object(text: str) -> Optional[str]:
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False

    for idx in range(start, len(text)):
        ch = text[idx]

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]

    return None


def parse_judge_response(raw_text: str) -> Tuple[Optional[dict], Optional[str]]:
    cleaned = strip_code_fences(raw_text)

    # First attempt: direct JSON parse.
    try:
        payload = json.loads(cleaned)
        return normalize_payload(payload), None
    except Exception:
        pass

    # Second attempt: first JSON object within surrounding text.
    fragment = extract_first_json_object(cleaned)
    if fragment:
        try:
            payload = json.loads(fragment)
            return normalize_payload(payload), None
        except Exception as exc:
            return None, f"json_parse_error: {exc}"

    return None, "no_json_object_found"


def normalize_payload(payload: Any) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Judge response JSON is not an object")

    winner = str(payload.get("winner", "")).strip().upper()
    confidence = str(payload.get("confidence", "")).strip().lower()
    reason = str(payload.get("reason", "")).strip()

    if winner not in {"A", "B"}:
        raise ValueError(f"Invalid winner: {winner}")
    if confidence not in {"high", "medium", "low"}:
        confidence = "low"

    return {
        "winner": winner,
        "confidence": confidence,
        "reason": reason,
    }


def usage_tokens(response: Any) -> Tuple[int, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0, 0

    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    return prompt_tokens, completion_tokens


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    rates = MODEL_COST_PER_MTOKENS.get(model)
    if not rates:
        return 0.0
    return (
        (prompt_tokens / 1_000_000.0) * rates["input"]
        + (completion_tokens / 1_000_000.0) * rates["output"]
    )


def load_env_var_from_dotenv(var_name: str, dotenv_path: Path = Path(".env")) -> str:
    """Best-effort read for a single env var from .env without extra deps."""
    if not dotenv_path.exists():
        return ""

    try:
        lines = dotenv_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return ""

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        # Support either `KEY=value` or `export KEY=value`.
        if line.startswith("export "):
            line = line[len("export ") :].strip()

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if key != var_name:
            continue

        value = value.strip().strip('"').strip("'")
        return value

    return ""


def resolve_openrouter_api_key() -> str:
    # Primary expected name.
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if api_key:
        return api_key

    # Backward-compatible alias used in some setups.
    api_key = os.getenv("OPEN_ROUTER_API_KEY", "").strip()
    if api_key:
        return api_key

    # .env fallback, in case shell variables were not exported.
    api_key = load_env_var_from_dotenv("OPENROUTER_API_KEY")
    if api_key:
        return api_key

    api_key = load_env_var_from_dotenv("OPEN_ROUTER_API_KEY")
    if api_key:
        return api_key

    return ""


def make_client() -> Any:
    api_key = resolve_openrouter_api_key()
    if not api_key:
        raise EnvironmentError(
            "OpenRouter API key not found. Set OPENROUTER_API_KEY in your shell "
            "or add OPENROUTER_API_KEY=... to .env"
        )

    return openai.OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )


def should_retry_parse_with_more_tokens(
    parse_err: Optional[str],
    completion_tokens: int,
    initial_max_tokens: int,
) -> bool:
    """Heuristic: retry once with larger token budget when output likely got truncated."""
    if not parse_err:
        return False

    likely_truncated = parse_err in {"no_json_object_found"} or parse_err.startswith("json_parse_error")
    if not likely_truncated:
        return False

    # If completion is near cap, truncation is likely.
    return completion_tokens >= max(1, int(initial_max_tokens * 0.9))


def is_retryable_checkpoint_parse_error(record: dict) -> bool:
    if str(record.get("status", "")) != "parse_error":
        return False
    parse_err = str(record.get("parse_error", ""))
    return parse_err == "no_json_object_found" or parse_err.startswith("json_parse_error")


def call_judge_with_retries(
    client: Any,
    model: str,
    prompt: str,
    max_retries: int,
    max_tokens: int,
) -> Tuple[Optional[Any], Optional[str], int]:
    backoffs = [2, 4, 8]

    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0,
                max_tokens=max_tokens,
                messages=[
                    {"role": "user", "content": prompt},
                ],
            )
            return response, None, attempt
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
            if attempt < max_retries:
                wait_seconds = backoffs[min(attempt - 1, len(backoffs) - 1)]
                print(f"    retry {attempt}/{max_retries} after error: {err}")
                time.sleep(wait_seconds)
            else:
                return None, err, attempt

    return None, "unknown_error", max_retries


def build_record(
    pair: dict,
    model: str,
    status: str,
    raw_response: str = "",
    parsed: Optional[dict] = None,
    parse_error: Optional[str] = None,
    api_error: Optional[str] = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    retries_used: int = 1,
) -> dict:
    expected = str(pair.get("expected_winner", "")).upper()
    pick = (parsed or {}).get("winner")

    agreed = status == "agreed"
    disagreed = status == "disagreed"

    return {
        "timestamp_utc": now_utc_iso(),
        "pair_id": int(pair.get("pair_id")),
        "category": pair.get("category"),
        "judge_model": model,
        "expected_winner": expected,
        "metric_used": pair.get("metric_used"),
        "metric_gap": pair.get("metric_gap"),
        "status": status,
        "pick": pick,
        "confidence": (parsed or {}).get("confidence"),
        "reason": (parsed or {}).get("reason"),
        "agreed": agreed,
        "disagreed": disagreed,
        "parse_error": parse_error,
        "api_error": api_error,
        "raw_response": raw_response,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "estimated_cost_usd": round(
            estimate_cost_usd(model, prompt_tokens, completion_tokens), 6
        ),
        "retries_used": retries_used,
    }


def aggregate_report(
    prompts_data: dict,
    records: Dict[Tuple[int, str], dict],
    selected_judges: List[str],
) -> dict:
    pairs = prompts_data.get("pairs", [])

    detailed_results: List[dict] = []

    total_calls = len(pairs) * len(selected_judges)
    successful_calls = 0
    parse_errors = 0

    overall_total = 0
    overall_agreed = 0

    by_category = defaultdict(lambda: {"total_judgments": 0, "agreed": 0})
    by_judge = defaultdict(lambda: {"total": 0, "agreed": 0})

    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_estimated_cost = 0.0

    unanimity_all = 0

    for pair in pairs:
        pair_id = int(pair["pair_id"])
        category = pair["category"]
        expected = str(pair["expected_winner"]).upper()

        judgments: Dict[str, dict] = {}
        valid_picks: List[str] = []

        for model in selected_judges:
            rec = records.get((pair_id, model))
            if rec is None:
                judgments[model] = {
                    "pick": None,
                    "confidence": None,
                    "reason": None,
                    "agreed": False,
                    "status": "missing",
                }
                continue

            status = rec.get("status", "")

            if status in {"agreed", "disagreed", "parse_error"}:
                successful_calls += 1
            if status == "parse_error":
                parse_errors += 1

            prompt_tokens = int(rec.get("prompt_tokens", 0) or 0)
            completion_tokens = int(rec.get("completion_tokens", 0) or 0)
            total_prompt_tokens += prompt_tokens
            total_completion_tokens += completion_tokens
            total_estimated_cost += float(rec.get("estimated_cost_usd", 0.0) or 0.0)

            pick = rec.get("pick")
            agreed = bool(rec.get("agreed", False))

            judgments[model] = {
                "pick": pick,
                "confidence": rec.get("confidence"),
                "reason": rec.get("reason"),
                "agreed": agreed,
                "status": status,
                "parse_error": rec.get("parse_error"),
                "api_error": rec.get("api_error"),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "estimated_cost_usd": rec.get("estimated_cost_usd", 0.0),
            }

            # Agreement accounting excludes parse_error/api_error/missing
            if status in {"agreed", "disagreed"}:
                overall_total += 1
                by_category[category]["total_judgments"] += 1
                by_judge[model]["total"] += 1
                if agreed:
                    overall_agreed += 1
                    by_category[category]["agreed"] += 1
                    by_judge[model]["agreed"] += 1

            if status in {"agreed", "disagreed"} and pick in {"A", "B"}:
                valid_picks.append(pick)

        unanimous = len(valid_picks) == len(selected_judges) and len(set(valid_picks)) == 1
        if unanimous:
            unanimity_all += 1

        agreed_votes = sum(1 for model in selected_judges if judgments[model].get("agreed") is True)
        majority_agreed = agreed_votes >= ((len(selected_judges) // 2) + 1)

        detailed_results.append(
            {
                "pair_id": pair_id,
                "category": category,
                "expected_winner": expected,
                "metric_gap": pair.get("metric_gap"),
                "judgments": judgments,
                "unanimous": unanimous,
                "majority_agreed": majority_agreed,
            }
        )

    category_summary = {}
    for cat in ["cqs_validation", "compqs_validation", "domain_sensitivity"]:
        total = by_category[cat]["total_judgments"]
        agreed = by_category[cat]["agreed"]
        pct = (agreed / total * 100.0) if total else 0.0
        category_summary[cat] = {
            "total_judgments": total,
            "agreed": agreed,
            "agreement_pct": round(pct, 1),
        }

    judge_summary = {}
    for model in selected_judges:
        total = by_judge[model]["total"]
        agreed = by_judge[model]["agreed"]
        pct = (agreed / total * 100.0) if total else 0.0
        judge_summary[model] = {
            "total": total,
            "agreed": agreed,
            "agreement_pct": round(pct, 1),
        }

    overall_pct = (overall_agreed / overall_total * 100.0) if overall_total else 0.0
    unanimity_pct = (unanimity_all / len(pairs) * 100.0) if pairs else 0.0

    judge_names = ", ".join(selected_judges)
    paper_ready = (
        f"LLM judges ({judge_names}) evaluated "
        f"{len(pairs)} project pairs via OpenRouter. "
        f"CQS validation: {category_summary['cqs_validation']['agreement_pct']}% agreement. "
        f"CompQS validation: {category_summary['compqs_validation']['agreement_pct']}% agreement. "
        f"Domain sensitivity: {category_summary['domain_sensitivity']['agreement_pct']}%. "
        f"Inter-judge unanimity: {round(unanimity_pct, 1)}%."
    )

    return {
        "metadata": {
            "generated_at": now_utc_iso(),
            "total_pairs": len(pairs),
            "judges": selected_judges,
            "api_provider": "OpenRouter",
            "total_calls": total_calls,
            "successful_calls": successful_calls,
            "parse_errors": parse_errors,
            "checkpoint_file": str(CHECKPOINT_FILE),
            "input_prompts_file": prompts_data.get("metadata", {}).get("input_pairs_file"),
            "token_usage": {
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_completion_tokens,
            },
            "estimated_cost_usd": round(total_estimated_cost, 4),
        },
        "summary": {
            "overall_agreement_pct": round(overall_pct, 1),
            "by_category": category_summary,
            "by_judge": judge_summary,
            "inter_judge_unanimity": {
                "total_pairs": len(pairs),
                "all_3_agree": unanimity_all,
                "unanimity_pct": round(unanimity_pct, 1),
            },
        },
        "detailed_results": detailed_results,
        "paper_ready_text": paper_ready,
    }


def print_final_table(report: dict) -> None:
    summary = report["summary"]
    meta = report["metadata"]

    print("\n" + "=" * 78)
    print("FINAL SUMMARY")
    print("=" * 78)
    print(f"Total calls planned:   {meta['total_calls']}")
    print(f"Successful API calls:  {meta['successful_calls']}")
    print(f"Parse errors:          {meta['parse_errors']}")
    print(f"Overall agreement:     {summary['overall_agreement_pct']}%")
    print("-")
    print("By category:")
    for category, row in summary["by_category"].items():
        print(
            f"  {category:20s} "
            f"agreed={row['agreed']:>3d}/{row['total_judgments']:<3d} "
            f"({row['agreement_pct']:>5.1f}%)"
        )
    print("-")
    print("By judge:")
    for model, row in summary["by_judge"].items():
        print(
            f"  {model:35s} "
            f"agreed={row['agreed']:>3d}/{row['total']:<3d} "
            f"({row['agreement_pct']:>5.1f}%)"
        )

    unanim = summary["inter_judge_unanimity"]
    print("-")
    print(
        "Inter-judge unanimity: "
        f"{unanim['all_3_agree']}/{unanim['total_pairs']} "
        f"({unanim['unanimity_pct']}%)"
    )
    print(
        "Estimated total cost: "
        f"${meta['estimated_cost_usd']:.4f} "
        f"(prompt={meta['token_usage']['prompt_tokens']}, "
        f"completion={meta['token_usage']['completion_tokens']})"
    )


def main() -> None:
    args = parse_args()

    if args.max_tokens <= 0:
        raise SystemExit("--max-tokens must be > 0")
    if args.parse_retry_max_tokens <= 0:
        raise SystemExit("--parse-retry-max-tokens must be > 0")
    if args.parse_retry_max_tokens < args.max_tokens:
        raise SystemExit("--parse-retry-max-tokens must be >= --max-tokens")

    selected_judges = parse_judges(args.judges)
    prompts_file = pick_prompts_file()
    prompts_data = load_json(prompts_file)
    pairs = prompts_data.get("pairs", [])

    if not pairs:
        raise SystemExit("No pairs found in judge prompts file")

    print(f"Using prompts file: {prompts_file}")
    print(f"Selected judges: {', '.join(selected_judges)}")
    print(f"Token caps: primary={args.max_tokens}, parse-retry={args.parse_retry_max_tokens}")

    a_pct, b_pct, imbalance_warning = winner_balance_check(pairs)
    print(f"Expected-winner balance: A={a_pct:.1f}% B={b_pct:.1f}%")
    if imbalance_warning:
        print("WARNING: Winner position split exceeds 40/60 threshold.")

    if args.dry_run:
        first = pairs[0]
        print("\nDRY RUN: first prompt preview")
        print("=" * 78)
        print(f"Pair ID: {first.get('pair_id')} | Category: {first.get('category')}")
        print(first.get("prompt", "")[:4000])
        print("=" * 78)
        print("Dry run complete. No API calls made.")
        return

    client = make_client()

    checkpoint = load_checkpoint(CHECKPOINT_FILE)
    total_calls = len(pairs) * len(selected_judges)

    print(f"Checkpoint file: {CHECKPOINT_FILE}")
    print(f"Already completed calls in checkpoint: {len(checkpoint)}")

    completed_counter = 0
    for pair in pairs:
        for model in selected_judges:
            key = (int(pair["pair_id"]), model)
            rec = checkpoint.get(key)
            if rec is None:
                continue
            if args.retry_parse_errors and is_retryable_checkpoint_parse_error(rec):
                continue
            completed_counter += 1

    for pair in pairs:
        pair_id = int(pair["pair_id"])
        category = pair["category"]
        prompt = pair["prompt"]
        expected = str(pair.get("expected_winner", "")).upper()

        for model in selected_judges:
            key = (pair_id, model)
            existing = checkpoint.get(key)
            if existing is not None:
                if args.retry_parse_errors and is_retryable_checkpoint_parse_error(existing):
                    print(
                        f"[resume] Re-running pair {pair_id} -> {model} "
                        f"due to retryable parse_error ({existing.get('parse_error')})"
                    )
                else:
                    continue

            current_index = completed_counter + 1
            print(f"[{current_index}/{total_calls}] Pair {pair_id} ({category}) -> {model} ...", end=" ")

            response, api_err, attempts = call_judge_with_retries(
                client=client,
                model=model,
                prompt=prompt,
                max_retries=args.max_retries,
                max_tokens=args.max_tokens,
            )

            if api_err is not None or response is None:
                rec = build_record(
                    pair=pair,
                    model=model,
                    status="api_error",
                    api_error=api_err,
                    retries_used=attempts,
                )
                checkpoint[key] = rec
                append_checkpoint(CHECKPOINT_FILE, rec)
                completed_counter += 1
                print(f"x api error ({api_err})")
                if args.delay > 0:
                    time.sleep(args.delay)
                continue

            content = ""
            try:
                content = response.choices[0].message.content or ""
            except Exception:
                content = ""

            parsed, parse_err = parse_judge_response(content)
            prompt_tokens, completion_tokens = usage_tokens(response)
            est_cost = estimate_cost_usd(model, prompt_tokens, completion_tokens)

            # One additional attempt with larger max_tokens when parse looks truncated.
            if parsed is None and should_retry_parse_with_more_tokens(
                parse_err=parse_err,
                completion_tokens=completion_tokens,
                initial_max_tokens=args.max_tokens,
            ):
                print(
                    f"x parse_error ({parse_err}); retrying once with max_tokens={args.parse_retry_max_tokens}...",
                    end=" ",
                )
                response2, api_err2, attempts2 = call_judge_with_retries(
                    client=client,
                    model=model,
                    prompt=prompt,
                    max_retries=args.max_retries,
                    max_tokens=args.parse_retry_max_tokens,
                )
                attempts += attempts2
                if api_err2 is None and response2 is not None:
                    try:
                        content2 = response2.choices[0].message.content or ""
                    except Exception:
                        content2 = ""
                    parsed2, parse_err2 = parse_judge_response(content2)
                    p2, c2 = usage_tokens(response2)
                    prompt_tokens += p2
                    completion_tokens += c2
                    est_cost += estimate_cost_usd(model, p2, c2)
                    if parsed2 is not None:
                        parsed = parsed2
                        parse_err = None
                        content = content2
                        print("ok")
                    else:
                        parse_err = parse_err2
                        content = content2
                        print(f"still parse_error ({parse_err2})")
                else:
                    print(f"api_error ({api_err2})")

            if parsed is None:
                rec = build_record(
                    pair=pair,
                    model=model,
                    status="parse_error",
                    raw_response=content,
                    parse_error=parse_err,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    retries_used=attempts,
                )
                checkpoint[key] = rec
                append_checkpoint(CHECKPOINT_FILE, rec)
                completed_counter += 1
                print(
                    f"x parse_error ({parse_err}); tokens in/out={prompt_tokens}/{completion_tokens}; "
                    f"est=${est_cost:.4f}"
                )
                if args.delay > 0:
                    time.sleep(args.delay)
                continue

            pick = parsed["winner"]
            status = "agreed" if pick == expected else "disagreed"

            rec = build_record(
                pair=pair,
                model=model,
                status=status,
                raw_response=content,
                parsed=parsed,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                retries_used=attempts,
            )
            checkpoint[key] = rec
            append_checkpoint(CHECKPOINT_FILE, rec)
            completed_counter += 1

            print(
                f"ok picked {pick} ({status}); "
                f"tokens in/out={prompt_tokens}/{completion_tokens}; "
                f"est=${est_cost:.4f}"
            )

            if args.delay > 0:
                time.sleep(args.delay)

    report = aggregate_report(prompts_data, checkpoint, selected_judges)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\nWrote validation report: {OUTPUT_FILE}")
    print_final_table(report)


if __name__ == "__main__":
    main()
