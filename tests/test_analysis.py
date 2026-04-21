"""
Unit & integration tests for the CK + MI analysis pipeline.

Run with:
    python -m pytest tests/test_analysis.py -v
"""

import os
import sys
import math
import shutil
import tempfile
from unittest.mock import patch, MagicMock

import pytest

# Ensure the project root is on sys.path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.halstead import compute_halstead, strip_comments_and_strings, tokenize_java
from app.services.mi_calculator import (
    compute_mi,
    compute_cyclomatic_complexity,
    count_sloc,
    analyze_directory_mi,
)
from app.services.ck_metrics import compute_class_quality
from app.services.analysis_pipeline import analyze_project


# ---------------------------------------------------------------------------
# Fixtures – reusable Java source snippets
# ---------------------------------------------------------------------------

CALCULATOR_SRC = """\
public class Calculator {
    public int add(int a, int b) {
        return a + b;
    }
}
"""

BRANCHING_SRC = """\
public class Branching {
    public String classify(int x) {
        if (x > 0) {
            return "positive";
        } else if (x < 0) {
            return "negative";
        } else {
            return "zero";
        }
    }
}
"""

STRATEGY_INTERFACE = """\
public interface Strategy {
    int execute(int a, int b);
}
"""

ADD_STRATEGY = """\
public class AddStrategy implements Strategy {
    @Override
    public int execute(int a, int b) {
        return a + b;
    }
}
"""

SUBTRACT_STRATEGY = """\
public class SubtractStrategy implements Strategy {
    @Override
    public int execute(int a, int b) {
        return a - b;
    }
}
"""

CONTEXT_SRC = """\
public class Context {
    private Strategy strategy;

    public Context(Strategy strategy) {
        this.strategy = strategy;
    }

    public void setStrategy(Strategy strategy) {
        this.strategy = strategy;
    }

    public int executeStrategy(int a, int b) {
        return strategy.execute(a, b);
    }
}
"""


# ===================================================================
# Test 1: Halstead on simple Java
# ===================================================================

class TestHalstead:
    def test_simple_class(self):
        result = compute_halstead(CALCULATOR_SRC)
        assert result.distinct_operators > 0, "Should find distinct operators"
        assert result.distinct_operands > 0, "Should find distinct operands"
        assert result.volume > 0, "Volume should be positive"
        assert result.program_length > 0, "Program length should be positive"
        assert result.vocabulary > 0, "Vocabulary should be positive"

    def test_empty_source(self):
        result = compute_halstead("")
        assert result.volume == 0.0
        assert result.difficulty == 0.0
        assert result.effort == 0.0

    def test_comment_only(self):
        src = "// This is a comment\n/* Block comment */\n"
        result = compute_halstead(src)
        assert result.volume == 0.0

    def test_derived_metrics(self):
        result = compute_halstead(CALCULATOR_SRC)
        # Volume = N * log2(eta)
        expected_vol = result.program_length * math.log2(result.vocabulary)
        assert abs(result.volume - expected_vol) < 0.01

        # Difficulty = (eta1 / 2) * (N2 / eta2)
        if result.distinct_operands > 0:
            expected_diff = (result.distinct_operators / 2.0) * (
                result.total_operands / result.distinct_operands
            )
            assert abs(result.difficulty - expected_diff) < 0.01

    def test_strip_comments_and_strings(self):
        src = '''
        String url = "http://example.com"; // a url
        /* block
           comment */
        char c = '\\n';
        '''
        cleaned = strip_comments_and_strings(src)
        assert "http://example.com" not in cleaned
        assert "block" not in cleaned
        assert "comment" not in cleaned
        assert "a url" not in cleaned
        assert "STRING_LITERAL" in cleaned
        assert "CHAR_LITERAL" in cleaned

    def test_multichar_operators(self):
        src = "if (a >= b && c != d || e << 2 >>> 1) {}"
        cleaned = strip_comments_and_strings(src)
        ops, _ = tokenize_java(cleaned)
        assert ">=" in ops
        assert "&&" in ops
        assert "!=" in ops
        assert "||" in ops
        assert "<<" in ops
        assert ">>>" in ops

    def test_structural_keywords_excluded(self):
        """Structural keywords like 'public', 'class' should NOT be counted."""
        result = compute_halstead(CALCULATOR_SRC)
        cleaned = strip_comments_and_strings(CALCULATOR_SRC)
        ops, opds = tokenize_java(cleaned)
        assert "public" not in ops, "'public' should not be an operator"
        assert "public" not in opds, "'public' should not be an operand"
        assert "class" not in ops, "'class' should not be an operator"
        assert "return" in ops, "'return' should be an operator"

    def test_delimiters_excluded(self):
        """Delimiters like ( ) { } ; , should NOT be counted."""
        cleaned = strip_comments_and_strings(CALCULATOR_SRC)
        ops, opds = tokenize_java(cleaned)
        for delim in ['(', ')', '{', '}', ';', ',']:
            assert delim not in ops, f"'{delim}' should not be an operator"
            assert delim not in opds, f"'{delim}' should not be an operand"


# ===================================================================
# Test 2: Cyclomatic Complexity
# ===================================================================

class TestCyclomaticComplexity:
    def test_branching(self):
        cc = compute_cyclomatic_complexity(BRANCHING_SRC)
        # base 1 + 2 if keywords = 3
        assert cc == 3, f"Expected CC=3, got {cc}"

    def test_simple_class(self):
        cc = compute_cyclomatic_complexity(CALCULATOR_SRC)
        # base 1, no decisions
        assert cc == 1, f"Expected CC=1, got {cc}"

    def test_logical_operators(self):
        src = """\
        public class LogicTest {
            public boolean check(int a, int b, int c) {
                return a > 0 && b > 0 || c > 0;
            }
        }
        """
        cc = compute_cyclomatic_complexity(src)
        # base 1 + && + || = 3
        assert cc == 3, f"Expected CC=3, got {cc}"

    def test_switch_case(self):
        src = """\
        public class SwitchTest {
            public String day(int d) {
                switch (d) {
                    case 1: return "Mon";
                    case 2: return "Tue";
                    case 3: return "Wed";
                    default: return "Other";
                }
            }
        }
        """
        cc = compute_cyclomatic_complexity(src)
        # base 1 + 3 case = 4
        assert cc == 4, f"Expected CC=4, got {cc}"

    def test_ternary(self):
        src = """\
        public class Ternary {
            public int abs(int x) {
                return x > 0 ? x : -x;
            }
        }
        """
        cc = compute_cyclomatic_complexity(src)
        # base 1 + ternary ? = 2
        assert cc == 2, f"Expected CC=2, got {cc}"

    def test_for_while_do_catch(self):
        src = """\
        public class Loops {
            public void process() {
                for (int i = 0; i < 10; i++) {}
                while (true) { break; }
                do { } while (false);
                try { } catch (Exception e) { }
            }
        }
        """
        cc = compute_cyclomatic_complexity(src)
        # base 1 + for + while + while(from do-while) + catch = 5
        assert cc == 5, f"Expected CC=5, got {cc}"


# ===================================================================
# Test 3: MI Score
# ===================================================================

class TestMaintainabilityIndex:
    def test_simple_class_mi(self):
        result = compute_mi(CALCULATOR_SRC, "Calculator.java")
        assert 65 <= result.mi_score <= 100, \
            f"Simple class MI should be 65-100, got {result.mi_score}"
        assert result.mi_label in ("Highly Maintainable", "Moderately Maintainable")

    def test_mi_range(self):
        result = compute_mi(CALCULATOR_SRC)
        assert 0 <= result.mi_score <= 100

    def test_mi_empty(self):
        result = compute_mi("")
        # Empty file: trivial -> MI near 100
        assert result.mi_score >= 90

    def test_mi_class_name_extraction(self):
        result = compute_mi(CALCULATOR_SRC, "/some/path/Calculator.java")
        assert result.class_name == "Calculator"

    def test_mi_cc_override(self):
        """When cc_override is provided, it should be used instead of computed CC."""
        r1 = compute_mi(CALCULATOR_SRC, cc_override=1)
        r2 = compute_mi(CALCULATOR_SRC, cc_override=50)
        assert r1.mi_score > r2.mi_score, "Higher CC should lower MI"

    def test_mi_color_classification(self):
        result = compute_mi(CALCULATOR_SRC)
        assert result.mi_color in ("green", "yellow", "red")

    def test_context_not_red(self):
        """A simple Context class should NOT be red."""
        result = compute_mi(CONTEXT_SRC, "Context.java")
        assert result.mi_color != "red", \
            f"Context MI={result.mi_score} should not be red"

    def test_file_path_is_absolute(self):
        """MIResult.file_path should be an absolute (realpath) when given a path."""
        result = compute_mi(CALCULATOR_SRC, "some/relative/Calculator.java")
        assert os.path.isabs(result.file_path), \
            f"file_path should be absolute, got {result.file_path}"


# ===================================================================
# Test 4: SLOC
# ===================================================================

class TestSLOC:
    def test_simple_class(self):
        sloc = count_sloc(CALCULATOR_SRC)
        assert sloc > 0

    def test_blank_lines_excluded(self):
        src = "\n\n\nint x = 1;\n\n\n"
        assert count_sloc(src) == 1

    def test_comment_lines_excluded(self):
        src = "// comment\n/* block */\nint x = 1;\n"
        assert count_sloc(src) == 1

    def test_inline_comment_still_counts(self):
        src = "int x = 5; // init\n"
        assert count_sloc(src) == 1

    def test_brace_only_lines_excluded(self):
        """Lines containing only { or } should not count as SLOC."""
        src = "public class Foo {\n    int x = 1;\n}\n"
        # 'public class Foo {' counts, 'int x = 1;' counts, '}' is brace-only
        assert count_sloc(src) == 2


# ===================================================================
# Test 5: Full pipeline with Strategy pattern
# ===================================================================

class TestFullPipeline:
    @pytest.fixture(autouse=True)
    def setup_strategy_files(self, tmp_path):
        """Create a temp directory with Strategy pattern Java files."""
        self.project_dir = str(tmp_path)
        files = {
            "Strategy.java": STRATEGY_INTERFACE,
            "AddStrategy.java": ADD_STRATEGY,
            "SubtractStrategy.java": SUBTRACT_STRATEGY,
            "Context.java": CONTEXT_SRC,
        }
        for name, content in files.items():
            (tmp_path / name).write_text(content, encoding="utf-8")

    def test_mi_only_analysis(self):
        """Test MI analysis without CK (mock CK as unavailable)."""
        with patch("app.services.analysis_pipeline.run_ck", side_effect=FileNotFoundError("no CK")):
            result = analyze_project(self.project_dir, "strategy")

        assert "summary" in result
        assert "classes" in result
        assert "methods" in result

        summary = result["summary"]
        classes = result["classes"]

        # Should have 4 classes (including the interface)
        assert summary["total_files"] == 4
        assert len(classes) == 4

        # All MI scores should be in valid range
        for cls in classes:
            mi = cls["mi"]
            assert 0 <= mi["mi_score"] <= 100, \
                f"{cls['class_name']}: MI {mi['mi_score']} out of range"

        # Concrete strategies should be moderately-to-highly maintainable
        for cls in classes:
            if cls["class_name"] in ("AddStrategy", "SubtractStrategy"):
                assert cls["mi"]["mi_score"] > 65, \
                    f"{cls['class_name']}: MI {cls['mi']['mi_score']} should be > 65"

        # Distribution: no red entries for clean design-pattern code
        assert summary["mi_distribution"].get("red", 0) == 0

        # CK should be None (unavailable)
        for cls in classes:
            assert cls["ck"] is None

        # Methods list should be empty (CK unavailable)
        assert result["methods"] == []

    def test_mi_directory_analysis(self):
        """Test analyze_directory_mi directly."""
        results = analyze_directory_mi(self.project_dir)
        assert len(results) == 4
        for r in results:
            assert r.mi_score > 0
            assert r.sloc > 0

    def test_no_duplicate_classes(self):
        """Verify no duplicate class entries when CK is unavailable."""
        with patch("app.services.analysis_pipeline.run_ck", side_effect=FileNotFoundError("no CK")):
            result = analyze_project(self.project_dir, "strategy")

        names = [c["class_name"] for c in result["classes"]]
        assert len(names) == len(set(names)), f"Duplicate classes found: {names}"


# ===================================================================
# Test 6: Graceful degradation (CK unavailable)
# ===================================================================

class TestGracefulDegradation:
    @pytest.fixture(autouse=True)
    def setup_temp_file(self, tmp_path):
        self.project_dir = str(tmp_path)
        (tmp_path / "Test.java").write_text(CALCULATOR_SRC, encoding="utf-8")

    def test_missing_java_runtime(self):
        """Simulate java not found -> MI-only results."""
        with patch("app.services.analysis_pipeline.run_ck",
                    side_effect=RuntimeError("Java runtime not found")):
            result = analyze_project(self.project_dir)

        assert len(result["classes"]) >= 1
        for cls in result["classes"]:
            assert cls["ck"] is None
            assert cls["mi"]["mi_score"] > 0

    def test_missing_ck_jar(self):
        """Simulate CK JAR not found -> MI-only results."""
        with patch("app.services.analysis_pipeline.run_ck",
                    side_effect=FileNotFoundError("CK JAR not found")):
            result = analyze_project(self.project_dir)

        assert len(result["classes"]) >= 1
        assert result["summary"]["avg_wmc"] is None

    def test_timeout(self):
        """Simulate CK timeout -> MI-only results."""
        with patch("app.services.analysis_pipeline.run_ck",
                    side_effect=TimeoutError("CK timed out")):
            result = analyze_project(self.project_dir)

        assert len(result["classes"]) >= 1
        for cls in result["classes"]:
            assert cls["ck"] is None


# ===================================================================
# Test 7: CK quality scoring
# ===================================================================

class TestCKQualityScoring:
    def test_good_metrics(self):
        cls = {
            "class": "com.example.GoodClass",
            "type": "class",
            "wmc": 5, "cbo": 3, "dit": 1, "rfc": 20,
            "lcom*": 0.1, "tcc": 0.8, "lcc": 0.9,
            "loc": 50, "noc": 0, "lcom": 0,
        }
        quality = compute_class_quality(cls)
        assert quality["scores"]["wmc"] == "good"
        assert quality["scores"]["cbo"] == "good"
        assert quality["overall_score"] >= 80

    def test_concerning_metrics(self):
        cls = {
            "class": "com.example.BadClass",
            "type": "class",
            "wmc": 30, "cbo": 20, "dit": 6, "rfc": 60,
            "lcom*": 0.9, "tcc": 0.1, "lcc": 0.1,
            "loc": 500, "noc": 0, "lcom": 50,
        }
        quality = compute_class_quality(cls)
        assert quality["scores"]["wmc"] == "concerning"
        assert quality["scores"]["cbo"] == "concerning"
        assert quality["overall_score"] < 40
        assert len(quality["flags"]) > 0

    def test_pattern_notes_strategy(self):
        cls = {
            "class": "ConcreteStrategy",
            "type": "class",
            "wmc": 15, "cbo": 10, "dit": 1, "rfc": 20,
            "lcom*": 0.5, "tcc": 0.6, "lcc": 0.7,
            "loc": 100, "noc": 0, "lcom": 0,
        }
        quality = compute_class_quality(cls, "strategy")
        assert len(quality["pattern_notes"]) > 0
