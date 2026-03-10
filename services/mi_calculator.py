"""
Maintainability Index calculator for Java source files.
Combines Halstead Volume, Cyclomatic Complexity, and SLOC.

Formula (Microsoft / SEI variant):
    MI = MAX(0, (171 - 5.2 × ln(HV) - 0.23 × CC - 16.2 × ln(SLOC)) × 100 / 171)

References:
- Oman, P. & Hagemeister, J. (1992). Metrics for assessing a software system's
  maintainability. Proc. ICSM.
- Code Health Meter (ACM TOSEM 2025) — formula adapted for Java.
"""

import re
import math
import os
import logging
from dataclasses import dataclass
from typing import Optional

from services.halstead import compute_halstead, strip_comments_and_strings, HalsteadResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MI thresholds — adjusted for Java file-level analysis.
#
# The original Microsoft/SEI thresholds (85 / 65) were designed for
# *per-method* analysis on C#.  When applied at file level to Java code
# (which is inherently more verbose — braces, type declarations, access
# modifiers), the raw MI scores are systematically lower.  The thresholds
# below are calibrated so that:
#   • Small / simple classes  (≤ 15 SLOC)  → green  (MI ≥ 65)
#   • Medium / moderate classes (15–80 SLOC) → yellow (MI 35–64)
#   • Large / complex classes   (> 80 SLOC)  → red   (MI < 35)
# ---------------------------------------------------------------------------
MI_THRESHOLDS = {
    "high_maintainability":      {"min": 65, "label": "Highly Maintainable",      "color": "green"},
    "moderate_maintainability":  {"min": 35, "label": "Moderately Maintainable",  "color": "yellow"},
    "low_maintainability":       {"min": 0,  "label": "Difficult to Maintain",    "color": "red"},
}


@dataclass
class MIResult:
    """Result of the Maintainability Index computation for a single file."""

    # Core MI
    mi_score: float                  # 0–100
    mi_label: str                    # human-readable label
    mi_color: str                    # green / yellow / red

    # Component values used in the formula
    halstead_volume: float
    cyclomatic_complexity: int
    sloc: int

    # Full Halstead breakdown
    halstead: HalsteadResult

    # Metadata
    file_path: str
    class_name: str


# ── SLOC counter ──────────────────────────────────────────────────────────

def count_sloc(source: str) -> int:
    """Count Source Lines of Code (non-blank, non-comment lines).

    Steps:
      1. Remove block comments (``/* … */`` including multiline).
      2. For each remaining line strip leading/trailing whitespace,
         remove trailing ``//`` comments, and count if non-empty.
    """

    # 1. Remove block comments
    no_block = re.sub(r'/\*[\s\S]*?\*/', '', source)

    count = 0
    for line in no_block.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith('//'):
            continue
        # Skip brace-only lines — Java convention places { and } on
        # their own lines, which inflates physical SLOC relative to
        # languages like C (where the MI formula was calibrated).
        if stripped in ('{', '}', '};'):
            continue
        count += 1
    return count


# ── Cyclomatic Complexity ──────────────────────────────────────────────────

# Decision-point keywords (word-boundary matched)
_CC_KW_RE = re.compile(r'\b(?:if|for|while|case|catch)\b')
# Short-circuit / ternary operators
_CC_OP_RE = re.compile(r'&&|\|\||\?')


def compute_cyclomatic_complexity(source: str) -> int:
    """Compute Cyclomatic Complexity from Java source.

    Rules:
      - Base CC = 1.
      - Each ``if``, ``for``, ``while``, ``case``, ``catch`` → +1.
      - ``do`` is NOT separately counted because its paired ``while`` keyword
        already contributes +1.
      - Each ``&&``, ``||`` → +1.
      - Each ``?`` (ternary) → +1.
      - ``else`` is **not** counted.

    The source is first cleaned (comments & strings stripped) to avoid
    false positives inside literals.
    """

    cleaned = strip_comments_and_strings(source)

    cc = 1  # base path

    # Keyword decisions
    cc += len(_CC_KW_RE.findall(cleaned))

    # Logical / ternary operators
    cc += len(_CC_OP_RE.findall(cleaned))

    return cc


# ── MI computation ─────────────────────────────────────────────────────────

def _classify_mi(score: float) -> tuple[str, str]:
    """Return ``(label, color)`` for a given MI score."""
    if score >= 65:
        return MI_THRESHOLDS["high_maintainability"]["label"], "green"
    if score >= 35:
        return MI_THRESHOLDS["moderate_maintainability"]["label"], "yellow"
    return MI_THRESHOLDS["low_maintainability"]["label"], "red"


def _extract_class_name(file_path: str, source: str) -> str:
    """Best-effort extraction of the primary class name."""
    if file_path:
        basename = os.path.basename(file_path)
        if basename.endswith('.java'):
            return basename[:-5]
    # Fallback: parse from source
    m = re.search(r'\b(?:class|interface|enum)\s+([A-Za-z_$][A-Za-z0-9_$]*)', source)
    return m.group(1) if m else "Unknown"


def compute_mi(
    source: str,
    file_path: str = "",
    cc_override: Optional[int] = None,
) -> MIResult:
    """Compute the Maintainability Index for a single Java source file.

    Parameters
    ----------
    source : str
        Raw Java source code.
    file_path : str
        Path to the file (metadata only).
    cc_override : int, optional
        If given, use this CC value instead of computing one. Allows
        substituting CK's more accurate ``wmc`` value when available.
    """

    halstead = compute_halstead(source)
    hv = halstead.volume
    cc = cc_override if cc_override is not None else compute_cyclomatic_complexity(source)
    sloc = count_sloc(source)

    # Guard against log(0)
    ln_hv = math.log(hv) if hv > 0 else 0.0
    ln_sloc = math.log(sloc) if sloc > 0 else 0.0

    raw = 171 - 5.2 * ln_hv - 0.23 * cc - 16.2 * ln_sloc
    mi_score = max(0.0, raw * 100.0 / 171.0)
    mi_score = min(mi_score, 100.0)  # clamp upper bound

    label, color = _classify_mi(mi_score)
    class_name = _extract_class_name(file_path, source)

    return MIResult(
        mi_score=round(mi_score, 2),
        mi_label=label,
        mi_color=color,
        halstead_volume=round(hv, 2),
        cyclomatic_complexity=cc,
        sloc=sloc,
        halstead=halstead,
        file_path=file_path,
        class_name=class_name,
    )


# ── Directory-level analysis ──────────────────────────────────────────────

def analyze_directory_mi(
    project_dir: str,
    ck_class_data: Optional[list[dict]] = None,
) -> list[MIResult]:
    """Compute MI for every ``.java`` file under *project_dir* (recursive).

    Parameters
    ----------
    project_dir : str
        Root directory to scan.
    ck_class_data : list[dict], optional
        Rows from CK's ``class.csv``.  When supplied, the CK ``wmc``
        value is used as ``cc_override`` for higher accuracy.
    """

    # Build a lookup: normalised file path → sum of wmc for all classes in that file
    wmc_by_file: dict[str, int] = {}
    if ck_class_data:
        for row in ck_class_data:
            fpath = os.path.normpath(row.get("file", ""))
            wmc = row.get("wmc", 0)
            if isinstance(wmc, str):
                try:
                    wmc = int(wmc)
                except ValueError:
                    wmc = 0
            wmc_by_file[fpath] = wmc_by_file.get(fpath, 0) + wmc

    results: list[MIResult] = []
    file_count = 0

    for root, _dirs, files in os.walk(project_dir):
        for fname in sorted(files):
            if not fname.endswith('.java'):
                continue
            full_path = os.path.join(root, fname)
            try:
                with open(full_path, 'r', encoding='utf-8', errors='replace') as fh:
                    source = fh.read()
            except OSError as exc:
                logger.warning("Could not read %s: %s", full_path, exc)
                continue

            norm_path = os.path.normpath(full_path)
            cc_override = wmc_by_file.get(norm_path)

            results.append(compute_mi(source, full_path, cc_override))
            file_count += 1

    logger.info("MI analysis complete — %d Java files processed in %s", file_count, project_dir)
    return results
