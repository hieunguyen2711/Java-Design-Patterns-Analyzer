"""
Pure-Python Halstead metrics calculator for Java source code.
No external dependencies — uses regex-based tokenization.

References:
- Halstead, M.H. (1977). Elements of Software Science.
- Code Health Meter (ACM TOSEM 2025) — adapted for Java.
"""

import re
import math
from dataclasses import dataclass


@dataclass
class HalsteadResult:
    distinct_operators: int    # η₁
    distinct_operands: int     # η₂
    total_operators: int       # N₁
    total_operands: int        # N₂
    vocabulary: int            # η = η₁ + η₂
    program_length: int        # N = N₁ + N₂
    volume: float              # N × log₂(η)
    difficulty: float          # (η₁ / 2) × (N₂ / η₂)
    effort: float              # Difficulty × Volume
    estimated_bugs: float      # Volume / 3000
    estimated_time: float      # Effort / 18 (seconds)


# ---------------------------------------------------------------------------
# Java operator set — keywords that behave as operators + symbolic operators
# ---------------------------------------------------------------------------
JAVA_OPERATORS: set[str] = {
    # Arithmetic
    '+', '-', '*', '/', '%', '++', '--',
    # Assignment
    '=', '+=', '-=', '*=', '/=', '%=', '&=', '|=', '^=', '<<=', '>>=', '>>>=',
    # Comparison
    '==', '!=', '<', '>', '<=', '>=',
    # Logical
    '&&', '||', '!',
    # Bitwise
    '&', '|', '^', '~', '<<', '>>', '>>>',
    # Other symbolic
    '?', ':', '::', '->', '.', ',', ';',
    '(', ')', '[', ']', '{', '}',
    # Keywords that act as operators
    'new', 'instanceof', 'return', 'throw', 'throws',
    'if', 'else', 'for', 'while', 'do', 'switch', 'case', 'default',
    'try', 'catch', 'finally', 'break', 'continue',
    'class', 'interface', 'extends', 'implements', 'import', 'package',
    'public', 'private', 'protected', 'static', 'final', 'abstract',
    'void', 'synchronized', 'volatile', 'transient', 'native', 'strictfp',
    'assert', 'enum', 'super', 'this',
}

# Regex that matches ALL symbolic operators, longest-first (greedy)
_OPERATOR_RE = re.compile(
    r'>>>='
    r'|<<<'
    r'|>>>|<<='
    r'|>>='
    r'|<<|>>'
    r'|->'
    r'|::'
    r'|\+\+|--'
    r'|[+\-*/%&|^~<>=!]=?'  # single-char ops optionally followed by =
    r'|&&|\|\|'
    r'|[(){}\[\];,.\?:~]'
)

# Pattern for identifiers and keywords
_WORD_RE = re.compile(r'[A-Za-z_$][A-Za-z0-9_$]*')

# Pattern for numeric literals (int, long, float, double, hex, binary, octal)
_NUMBER_RE = re.compile(
    r'0[xX][0-9a-fA-F_]+[lL]?'
    r'|0[bB][01_]+[lL]?'
    r'|[0-9][0-9_]*\.?[0-9_]*(?:[eE][+-]?[0-9_]+)?[fFdDlL]?'
)


def strip_comments_and_strings(source: str) -> str:
    """Remove comments and string/char literals from Java source.

    Uses a single regex pass that matches (in priority order):
      1. Block comments   /* ... */
      2. Single-line comments  // ...
      3. String literals  "..."  (with escaped quotes)
      4. Char literals    '.'    (with escaped chars)

    String and char literals are replaced with placeholder tokens
    (``STRING_LITERAL`` / ``CHAR_LITERAL``) so that downstream
    tokenisation still counts them as operands.
    """

    _TOKEN_PATTERN = re.compile(
        r'/\*[\s\S]*?\*/'       # block comment
        r'|//[^\n]*'            # line comment
        r'|"(?:[^"\\]|\\.)*"'   # string literal
        r"|'(?:[^'\\]|\\.)*'"   # char literal
    )

    def _replacer(m: re.Match) -> str:
        text = m.group(0)
        if text.startswith('/*') or text.startswith('//'):
            # Replace comment with a space (preserves token separation)
            return ' '
        if text.startswith('"'):
            return ' STRING_LITERAL '
        if text.startswith("'"):
            return ' CHAR_LITERAL '
        return ' '

    return _TOKEN_PATTERN.sub(_replacer, source)


def tokenize_java(cleaned_source: str) -> tuple[list[str], list[str]]:
    """Tokenize cleaned (comment/string-free) Java source into operators & operands.

    Returns ``(operators_list, operands_list)`` where each list contains
    **all** occurrences (not just unique ones).

    Strategy:
      1. Walk through the source using a master regex that alternates between
         operator tokens, numeric literals, and word tokens.
      2. Classify each match:
         - Symbolic match → operator
         - Word match in ``JAVA_OPERATORS`` → operator (keyword-operator)
         - Numeric literal → operand
         - Placeholder (``STRING_LITERAL`` / ``CHAR_LITERAL``) → operand
         - Other word → operand (identifier / type name)
    """

    # Master pattern: try operators first (longest match), then numbers, then words
    _MASTER_RE = re.compile(
        r'(?P<op>'
        r'>>>='
        r'|<<<'
        r'|>>>|<<='
        r'|>>='
        r'|<<|>>'
        r'|->'
        r'|::'
        r'|\+\+|--'
        r'|\+='
        r'|-='
        r'|\*='
        r'|/='
        r'|%='
        r'|&='
        r'|\|='
        r'|\^='
        r'|=='
        r'|!='
        r'|<='
        r'|>='
        r'|&&'
        r'|\|\|'
        r'|[+\-*/%&|^~<>=!]'
        r'|[(){}\[\];,.\?:]'
        r')'
        r'|(?P<num>'
        r'0[xX][0-9a-fA-F_]+[lL]?'
        r'|0[bB][01_]+[lL]?'
        r'|[0-9][0-9_]*\.?[0-9_]*(?:[eE][+-]?[0-9_]+)?[fFdDlL]?'
        r')'
        r'|(?P<word>[A-Za-z_$][A-Za-z0-9_$]*)'
    )

    operators: list[str] = []
    operands: list[str] = []

    for m in _MASTER_RE.finditer(cleaned_source):
        if m.group('op'):
            operators.append(m.group('op'))
        elif m.group('num'):
            operands.append(m.group('num'))
        elif m.group('word'):
            word = m.group('word')
            if word in JAVA_OPERATORS:
                operators.append(word)
            elif word in ('true', 'false', 'null'):
                operands.append(word)
            elif word in ('STRING_LITERAL', 'CHAR_LITERAL'):
                operands.append(word)
            else:
                # Identifier, type name, etc. → operand
                operands.append(word)

    return operators, operands


def compute_halstead(source: str) -> HalsteadResult:
    """Compute Halstead metrics for a raw Java source string.

    Steps:
      1. Strip comments & string literals
      2. Tokenize into operators / operands
      3. Compute base counts (η₁, η₂, N₁, N₂)
      4. Derive volume, difficulty, effort, bugs, time
    """

    cleaned = strip_comments_and_strings(source)
    operators, operands = tokenize_java(cleaned)

    eta1 = len(set(operators))   # distinct operators
    eta2 = len(set(operands))    # distinct operands
    n1 = len(operators)          # total operators
    n2 = len(operands)           # total operands

    eta = eta1 + eta2            # vocabulary
    n = n1 + n2                  # program length

    # Volume — guard against log₂(0)
    volume = n * math.log2(eta) if eta > 0 else 0.0

    # Difficulty — guard against division by zero
    difficulty = (eta1 / 2.0) * (n2 / eta2) if eta2 > 0 else 0.0

    effort = difficulty * volume
    bugs = volume / 3000.0
    time_s = effort / 18.0

    return HalsteadResult(
        distinct_operators=eta1,
        distinct_operands=eta2,
        total_operators=n1,
        total_operands=n2,
        vocabulary=eta,
        program_length=n,
        volume=volume,
        difficulty=difficulty,
        effort=effort,
        estimated_bugs=bugs,
        estimated_time=time_s,
    )
