"""
CK (Chidamber & Kemerer) metrics runner.
Invokes the CK JAR via subprocess and parses CSV output.

CK GitHub: https://github.com/mauricioaniche/ck
"""

import subprocess
import tempfile
import shutil
import os
import csv
import math
import logging
from typing import Optional

logger = logging.getLogger(__name__)

CK_JAR_PATH = os.getenv("CK_JAR_PATH", "/opt/tools/ck.jar")

# ---------------------------------------------------------------------------
# CK quality thresholds (Filó et al. 2015, NASA SATC)
# ---------------------------------------------------------------------------
CK_THRESHOLDS: dict[str, dict] = {
    "wmc":    {"good": 11,  "moderate": 20},     # lower is better
    "cbo":    {"good": 6,   "moderate": 14},     # lower is better
    "dit":    {"good": 2,   "moderate": 4},      # moderate is ideal
    "rfc":    {"good": 35,  "moderate": 50},     # lower is better
    "lcom*":  {"good": 0.2, "moderate": 0.7},    # lower is better (0-1)
    "tcc":    {"good": 0.5, "moderate": 0.3},    # HIGHER is better (inverted)
}

# Halstead-derived thresholds
HALSTEAD_THRESHOLDS: dict[str, dict] = {
    "volume":     {"good": 100,  "moderate": 1000,  "concerning": 8000},
    "difficulty":  {"good": 10,   "moderate": 30,    "concerning": 50},
    "effort":     {"good": 1000, "moderate": 20000, "concerning": 100000},
    "bugs":       {"good": 0.05, "moderate": 0.5,   "concerning": 1.0},
}

# Integer columns in class.csv
_CK_INT_COLS = {
    'cbo', 'cboModified', 'wmc', 'dit', 'noc', 'rfc', 'lcom',
    'loc', 'totalMethodsQty', 'staticMethodsQty', 'publicMethodsQty',
    'privateMethodsQty', 'protectedMethodsQty', 'defaultMethodsQty',
    'visibleMethodsQty', 'abstractMethodsQty', 'finalMethodsQty',
    'synchronizedMethodsQty', 'totalFieldsQty', 'staticFieldsQty',
    'publicFieldsQty', 'privateFieldsQty', 'protectedFieldsQty',
    'defaultFieldsQty', 'finalFieldsQty', 'synchronizedFieldsQty',
    'nosi', 'returnQty', 'loopQty', 'comparisonsQty',
    'tryCatchQty', 'parenthesizedExpsQty', 'stringLiteralsQty',
    'numbersQty', 'assignmentsQty', 'mathOperationsQty',
    'variablesQty', 'maxNestedBlocksQty', 'anonymousClassesDecl',
    'innerClassesDecl', 'uniqueWordsQty', 'modifiers',
    'logStatementsQty', 'fanin', 'fanout',
}

# Float columns (may contain "NaN")
_CK_FLOAT_COLS = {'lcom*', 'tcc', 'lcc'}

# Method CSV integer columns
_METHOD_INT_COLS = {
    'cbo', 'cboModified', 'wmc', 'rfc', 'loc',
    'returnsQty', 'variablesQty', 'parametersQty',
    'maxNestedBlocksQty', 'line',
    'loopQty', 'comparisonsQty', 'tryCatchQty',
    'parenthesizedExpsQty', 'stringLiteralsQty', 'numbersQty',
    'assignmentsQty', 'mathOperationsQty', 'anonymousClassesDecl',
    'innerClassesDecl', 'uniqueWordsQty', 'logStatementsQty',
}


def _safe_int(val: str) -> int:
    """Convert a CSV value to int; return 0 on failure."""
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0


def _safe_float(val: str) -> float:
    """Convert a CSV value to float; NaN → 0.0."""
    try:
        f = float(val)
        return 0.0 if math.isnan(f) else f
    except (ValueError, TypeError):
        return 0.0


def _parse_csv(path: str, int_cols: set[str], float_cols: set[str]) -> list[dict]:
    """Parse a CK CSV file, converting numeric columns appropriately."""
    if not os.path.isfile(path):
        return []

    rows: list[dict] = []
    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            row: dict = {}
            for key, val in raw.items():
                if key in int_cols:
                    row[key] = _safe_int(val)
                elif key in float_cols:
                    row[key] = _safe_float(val)
                else:
                    row[key] = val
            rows.append(row)
    return rows


def run_ck(project_dir: str, timeout: int = 120) -> dict:
    """Run the CK tool on *project_dir* and return parsed results.

    Returns
    -------
    dict
        ``{"classes": [...], "methods": [...]}`` where each element is
        a dict parsed from the corresponding CK CSV file.

    Raises
    ------
    FileNotFoundError
        If the CK JAR does not exist at ``CK_JAR_PATH``.
    RuntimeError
        If the ``java`` command is not found.
    TimeoutError
        If the CK process exceeds *timeout* seconds.
    """

    if not os.path.isfile(CK_JAR_PATH):
        raise FileNotFoundError(
            f"CK JAR not found at {CK_JAR_PATH}. "
            "Set the CK_JAR_PATH environment variable to the correct path."
        )

    output_dir = tempfile.mkdtemp(prefix="ck_output_")
    try:
        cmd = [
            "java", "-jar", CK_JAR_PATH,
            project_dir,
            "false",   # use_jars
            "0",       # max_files (auto)
            "false",   # variables
            output_dir + "/",
        ]
        logger.info("Running CK: %s", " ".join(cmd))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "Java runtime not found. Install Java (JDK 8+) to enable CK metrics."
            )
        except subprocess.TimeoutExpired:
            raise TimeoutError(
                f"CK analysis timed out after {timeout}s on {project_dir}"
            )

        if result.returncode != 0:
            logger.warning("CK exited with code %d: %s", result.returncode, result.stderr)

        class_csv = os.path.join(output_dir, "class.csv")
        method_csv = os.path.join(output_dir, "method.csv")

        classes = _parse_csv(class_csv, _CK_INT_COLS, _CK_FLOAT_COLS)
        methods = _parse_csv(method_csv, _METHOD_INT_COLS, set())

        logger.info("CK produced %d class rows, %d method rows", len(classes), len(methods))
        return {"classes": classes, "methods": methods}

    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Quality scoring
# ---------------------------------------------------------------------------

def _rate(value: float, good: float, moderate: float, higher_is_better: bool = False) -> str:
    """Rate a metric value as 'good', 'moderate', or 'concerning'."""
    if higher_is_better:
        if value >= good:
            return "good"
        if value >= moderate:
            return "moderate"
        return "concerning"
    else:
        if value <= good:
            return "good"
        if value <= moderate:
            return "moderate"
        return "concerning"


def compute_class_quality(class_metrics: dict, pattern_name: str = "") -> dict:
    """Compute quality scores for a single class based on CK thresholds.

    Returns
    -------
    dict
        ``scores`` — metric name → ``"good"`` / ``"moderate"`` / ``"concerning"``
        ``overall_score`` — weighted 0–100 score
        ``flags`` — red-flag descriptions
        ``pattern_notes`` — pattern-specific observations
    """

    scores: dict[str, str] = {}
    flags: list[str] = []
    pattern_notes: list[str] = []

    wmc = class_metrics.get("wmc", 0)
    cbo = class_metrics.get("cbo", 0)
    dit = class_metrics.get("dit", 0)
    rfc = class_metrics.get("rfc", 0)
    lcom_star = class_metrics.get("lcom*", 0.0)
    tcc = class_metrics.get("tcc", 0.0)

    scores["wmc"] = _rate(wmc, CK_THRESHOLDS["wmc"]["good"], CK_THRESHOLDS["wmc"]["moderate"])
    scores["cbo"] = _rate(cbo, CK_THRESHOLDS["cbo"]["good"], CK_THRESHOLDS["cbo"]["moderate"])
    scores["dit"] = _rate(dit, CK_THRESHOLDS["dit"]["good"], CK_THRESHOLDS["dit"]["moderate"])
    scores["rfc"] = _rate(rfc, CK_THRESHOLDS["rfc"]["good"], CK_THRESHOLDS["rfc"]["moderate"])
    scores["lcom*"] = _rate(lcom_star, CK_THRESHOLDS["lcom*"]["good"], CK_THRESHOLDS["lcom*"]["moderate"])
    scores["tcc"] = _rate(tcc, CK_THRESHOLDS["tcc"]["good"], CK_THRESHOLDS["tcc"]["moderate"], higher_is_better=True)

    # ── Overall score (weighted) ───────────────────────────────────────
    # Weights: WMC 25%, CBO 25%, LCOM* 20%, TCC 15%, RFC 10%, DIT 5%
    _SCORE_MAP = {"good": 100, "moderate": 60, "concerning": 20}
    weighted = (
        0.25 * _SCORE_MAP[scores["wmc"]]
        + 0.25 * _SCORE_MAP[scores["cbo"]]
        + 0.20 * _SCORE_MAP[scores["lcom*"]]
        + 0.15 * _SCORE_MAP[scores["tcc"]]
        + 0.10 * _SCORE_MAP[scores["rfc"]]
        + 0.05 * _SCORE_MAP[scores["dit"]]
    )
    overall_score = round(weighted, 2)

    # ── Red flags ──────────────────────────────────────────────────────
    if wmc > 20:
        flags.append(f"High complexity (WMC={wmc} > 20)")
    if cbo > 14:
        flags.append(f"High coupling (CBO={cbo} > 14)")
    if lcom_star > 0.7:
        flags.append(f"Poor cohesion (LCOM*={lcom_star:.2f} > 0.7)")
    if tcc < 0.3 and tcc > 0:
        flags.append(f"Weak tight class cohesion (TCC={tcc:.2f} < 0.3)")
    if rfc > 50:
        flags.append(f"High response set (RFC={rfc} > 50)")

    # ── Pattern-specific notes ─────────────────────────────────────────
    pn = pattern_name.lower().replace(" ", "").replace("_", "").replace("-", "")
    class_type = class_metrics.get("type", "class")
    class_name = class_metrics.get("class", "").split(".")[-1]

    if "strategy" in pn:
        if class_type == "interface":
            pattern_notes.append("Strategy interface — expect near-zero complexity.")
        elif cbo > 8:
            pattern_notes.append(f"Strategy concrete class CBO={cbo} is above typical range (3–8).")
        if wmc > 8 and class_type != "interface":
            pattern_notes.append(f"Strategy concrete WMC={wmc} is above typical range (3–8).")
        if lcom_star > 0.3 and class_type != "interface":
            pattern_notes.append(f"Strategy concrete LCOM*={lcom_star:.2f} > 0.3 — check cohesion.")

    elif "observer" in pn:
        if "subject" in class_name.lower():
            if cbo > 6:
                pattern_notes.append(f"Subject CBO={cbo} above typical range (2–6).")
            if wmc > 12:
                pattern_notes.append(f"Subject WMC={wmc} above typical range (5–12).")
        else:
            if lcom_star > 0.3 and class_type != "interface":
                pattern_notes.append(f"Observer LCOM*={lcom_star:.2f} > 0.3 — check cohesion.")

    elif "factory" in pn:
        if wmc > 15:
            pattern_notes.append(f"Factory WMC={wmc} above typical range (8–15).")
        # Factories naturally have moderate coupling
        if cbo > 12:
            pattern_notes.append(f"Factory CBO={cbo} above typical range (6–12).")

    elif "singleton" in pn:
        if wmc > 15:
            pattern_notes.append(f"Singleton WMC={wmc} > 15 — possible God class.")
        if lcom_star > 0.3:
            pattern_notes.append(f"Singleton LCOM*={lcom_star:.2f} > 0.3 — check for God class accumulation.")

    elif "decorator" in pn:
        if wmc > 10:
            pattern_notes.append(f"Decorator WMC={wmc} above typical range (3–10).")
        if dit > 3:
            pattern_notes.append(f"Decorator DIT={dit} above typical range (2–3).")
        if tcc < 0.5 and class_type != "interface":
            pattern_notes.append(f"Decorator TCC={tcc:.2f} < 0.5 — check cohesion.")

    return {
        "scores": scores,
        "overall_score": overall_score,
        "flags": flags,
        "pattern_notes": pattern_notes,
    }
