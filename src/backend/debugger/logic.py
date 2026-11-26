"""Logic errors: the program ran without crashing, but printed something different
from what the student expected.

The student types the output they expected. `compare_output` checks it against what
the program printed. When they differ, `analyse_logic` builds an ErrorReport (kind
"logic") that the stage 1 and stage 2 hint flow use just like a crash report:

* facts: verified statements for the model, e.g. which output line differs, which
  function calls itself and where it stops, which ranges the loops use, how Python
  groups an expression. All computed here from the code and the two outputs.
* details["category"]: a first guess at the kind of mistake (off_by_one,
  recursion_base_case, calculation or other), with the clues behind it. The model
  makes the final call; without a model the rule-based questions use this guess.

Everything here is deterministic and never runs the student's code again.
"""

from __future__ import annotations

import ast
import re
from dataclasses import asdict, dataclass, field

from .analysis import ErrorReport

CATEGORIES = ("off_by_one", "recursion_base_case", "calculation", "missing_return", "other")
# How the kind of mistake is named to the student, after "Looks like".
CATEGORY_LABELS = {
    "off_by_one": "an off-by-one mistake",
    "recursion_base_case": "a recursion base case mistake",
    "calculation": "a calculation mistake",
    "missing_return": "a missing return value",
    "other": "a logic mistake",
}

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


# === Comparing the outputs ===


@dataclass
class OutputComparison:
    matches: bool
    expected_lines: list[str]
    actual_lines: list[str]
    first_diff: int | None = None      # 1-based output line where they first differ
    expected_line: str | None = None   # None when the program printed more lines than expected
    actual_line: str | None = None     # None when the program printed fewer lines than expected
    # Numbers on the first differing line, when both lines hold the same count of them.
    number_pairs: list[tuple[float, float]] = field(default_factory=list)  # (expected, actual)
    only_whitespace: bool = False      # same text apart from spaces or case

    def to_dict(self) -> dict:
        return asdict(self)


def _lines(text: str) -> list[str]:
    lines = [l.rstrip() for l in text.replace("\r\n", "\n").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    while lines and not lines[0]:
        lines.pop(0)
    return lines


def input_prompts(code: str) -> list[str]:
    """The literal prompts the program passes to input(), e.g. "Enter a number: "."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    prompts = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "input"
                and node.args and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str) and node.args[0].value):
            prompts.append(node.args[0].value)
    return sorted(set(prompts), key=len, reverse=True)


def strip_prompts(stdout: str, code: str) -> str:
    """input() prompts end up in stdout with no newline after them ("Enter n: 15"),
    but a student writes only what the program prints. Drop the prompts first."""
    for prompt in input_prompts(code):
        stdout = stdout.replace(prompt, "")
    return stdout


def _numbers(text: str) -> list[float]:
    return [float(n) for n in _NUMBER_RE.findall(text)]


def compare_output(actual: str, expected: str, code: str = "") -> OutputComparison:
    """Line by line, ignoring spaces at the end of lines and blank lines at either end."""
    # Some students type the prompt too ("Celsius: 212.0"), so it is dropped from both.
    exp = _lines(strip_prompts(expected, code) if code else expected)
    act = _lines(strip_prompts(actual, code) if code else actual)
    if exp == act:
        return OutputComparison(True, exp, act)
    n = next((i for i, (e, a) in enumerate(zip(exp, act)) if e != a), min(len(exp), len(act)))
    e_line = exp[n] if n < len(exp) else None
    a_line = act[n] if n < len(act) else None
    cmp = OutputComparison(False, exp, act, first_diff=n + 1, expected_line=e_line, actual_line=a_line)
    if e_line is not None and a_line is not None:
        en, an = _numbers(e_line), _numbers(a_line)
        if en and len(en) == len(an):
            cmp.number_pairs = [(e, a) for e, a in zip(en, an) if e != a]
        squash = lambda s: re.sub(r"\s+", "", s).lower()  # noqa: E731
        cmp.only_whitespace = squash(e_line) == squash(a_line)
    return cmp


def _fmt(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else repr(x)


def describe_difference(cmp: OutputComparison) -> tuple[str, str]:
    """A plain-English title and message for the "What happened" box."""
    if cmp.matches:
        return ("Your output matches what you expected",
                "Every line your program printed is the same as the output you expected.")
    title = "Your output is different from what you expected"
    n = cmp.first_diff
    gap = one_line_gap(cmp)
    if gap is not None and gap + 1 < max(len(cmp.expected_lines), len(cmp.actual_lines)):
        if len(cmp.actual_lines) < len(cmp.expected_lines):
            return (title, f"Your program printed {len(cmp.actual_lines)} lines, but you expected "
                    f"{len(cmp.expected_lines)}. The line \"{cmp.expected_lines[gap]}\" (line {gap + 1} of what you "
                    "expected) is missing; the other lines match.")
        return (title, f"Your program printed {len(cmp.actual_lines)} lines, but you expected only "
                f"{len(cmp.expected_lines)}. Line {gap + 1}, \"{cmp.actual_lines[gap]}\", is extra; the other lines match.")
    if cmp.actual_line is None:
        same = f" The first {n - 1} line{'s' if n - 1 != 1 else ''} match." if n > 1 else ""
        return (title, f"Your program printed {len(cmp.actual_lines)} line"
                f"{'s' if len(cmp.actual_lines) != 1 else ''}, but you expected {len(cmp.expected_lines)}.{same} "
                f"The missing line {n} should be \"{cmp.expected_line}\".")
    if cmp.expected_line is None:
        same = f" The first {n - 1} line{'s' if n - 1 != 1 else ''} match." if n > 1 else ""
        return (title, f"Your program printed {len(cmp.actual_lines)} lines, but you expected only "
                f"{len(cmp.expected_lines)}.{same} The extra line {n} is \"{cmp.actual_line}\".")
    if cmp.only_whitespace:
        return (title, f"Line {n} of the output is \"{cmp.actual_line}\", but you expected \"{cmp.expected_line}\". "
                "The words are the same; the difference is in spaces or capital letters.")
    return (title, f"Line {n} of the output is \"{cmp.actual_line}\", but you expected \"{cmp.expected_line}\".")


# === Reading the code ===


@dataclass
class _Clue:
    category: str
    weight: int
    line: int | None
    fact: str


def _src(code: str, node: ast.AST) -> str:
    return (ast.get_source_segment(code, node) or "").strip()


def _calls_itself(fn: ast.FunctionDef) -> list[ast.Call]:
    return [n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == fn.name]


def _recursion_clues(code: str, tree: ast.AST) -> list[_Clue]:
    clues = []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef):
            continue
        calls = _calls_itself(fn)
        if not calls:
            continue
        call_lines = sorted({c.lineno for c in calls})
        base_cases = []
        for stmt in ast.walk(fn):
            if isinstance(stmt, ast.If):
                returns = [s for s in stmt.body if isinstance(s, ast.Return)]
                recursive = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                                and n.func.id == fn.name for s in stmt.body for n in ast.walk(s))
                if returns and not recursive:
                    value = _src(code, returns[0].value) if returns[0].value is not None else "None"
                    base_cases.append((stmt.lineno, _src(code, stmt.test), value))
        where = ", ".join(str(l) for l in call_lines)
        clues.append(_Clue("recursion_base_case", 3, None,
                           f"The function {fn.name} (line {fn.lineno}) calls itself on line {where}, so it is recursive."))
        if base_cases:
            for line, test, value in base_cases:
                clues.append(_Clue("recursion_base_case", 1, line,
                                   f"{fn.name} stops calling itself when {test} (line {line}) and returns {value} there."))
        else:
            clues.append(_Clue("recursion_base_case", 2, fn.lineno,
                               f"{fn.name} has no if-statement that returns without calling {fn.name} again."))
    return clues


def _range_bounds(call: ast.Call) -> list[float]:
    vals = []
    for a in call.args[:2]:
        if isinstance(a, ast.Constant) and isinstance(a.value, (int, float)):
            vals.append(float(a.value))
    return vals


def _loop_bounds(tree: ast.AST) -> list[float]:
    """The literal numbers loops start or stop at: range(1, 5) and while i < 10."""
    bounds = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "range":
            bounds += _range_bounds(n)
        elif isinstance(n, ast.While) and isinstance(n.test, ast.Compare):
            bounds += [float(c.value) for c in n.test.comparators
                       if isinstance(c, ast.Constant) and isinstance(c.value, (int, float))]
    return bounds


def _loop_clues(code: str, tree: ast.AST) -> list[_Clue]:
    clues = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "range":
            text = _src(code, node)
            n = len(node.args)
            if n == 1:
                what = f"counts from 0 and stops before reaching {_src(code, node.args[0])}"
            elif n >= 2:
                what = f"starts at {_src(code, node.args[0])} and stops before reaching {_src(code, node.args[1])}"
            else:
                continue
            clues.append(_Clue("off_by_one", 1, node.lineno, f"On line {node.lineno}, {text} {what}."))
        elif isinstance(node, ast.While) and isinstance(node.test, ast.Compare):
            clues.append(_Clue("off_by_one", 1, node.lineno,
                               f"The while loop on line {node.lineno} keeps going while {_src(code, node.test)}."))
        elif isinstance(node, ast.Subscript):
            idx = node.slice
            text = _src(code, idx)
            if isinstance(idx, ast.BinOp) and isinstance(idx.op, (ast.Add, ast.Sub)) or "len(" in text:
                clues.append(_Clue("off_by_one", 2, node.lineno,
                                   f"Line {node.lineno} picks a position worked out as {text}."))
    return clues


def _calc_clues(code: str, tree: ast.AST) -> list[_Clue]:
    clues = []
    seen: set[tuple[int, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.BinOp):
            continue
        line = node.lineno
        # a + b / 2: Python divides before it adds.
        if isinstance(node.op, (ast.Add, ast.Sub)):
            for side in (node.left, node.right):
                if isinstance(side, ast.BinOp) and isinstance(side.op, (ast.Div, ast.Mult, ast.FloorDiv, ast.Mod)):
                    key = (line, "prec")
                    if key not in seen:
                        seen.add(key)
                        clues.append(_Clue("calculation", 2, line,
                                           f"On line {line}, Python works out {_src(code, side)} first, and only then "
                                           f"does the {'+' if isinstance(node.op, ast.Add) else '-'} in {_src(code, node)}."))
        if isinstance(node.op, ast.FloorDiv):
            clues.append(_Clue("calculation", 2, line,
                               f"On line {line}, {_src(code, node)} uses //, which drops anything after the decimal point."))
        elif isinstance(node.op, (ast.Mult, ast.Div, ast.Add, ast.Sub, ast.Pow, ast.Mod)) and (line, "op") not in seen:
            seen.add((line, "op"))
            clues.append(_Clue("calculation", 1, line, f"Line {line} calculates {_src(code, node)}."))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("int", "round")
                and node.args and not (isinstance(node.args[0], ast.Call) and isinstance(node.args[0].func, ast.Name)
                                       and node.args[0].func.id == "input")):
            clues.append(_Clue("calculation", 1, node.lineno,
                               f"On line {node.lineno}, {_src(code, node)} turns the value into a whole number."))
    return clues


def one_line_gap(cmp: OutputComparison) -> int | None:
    """When the two outputs differ by exactly one line, added or left out, its 0-based position."""
    exp, act = cmp.expected_lines, cmp.actual_lines
    if abs(len(exp) - len(act)) != 1:
        return None
    shorter, longer = (exp, act) if len(exp) < len(act) else (act, exp)
    for i in range(len(longer)):
        if longer[:i] + longer[i + 1:] == shorter:
            return i
    return None


def _gap_detail(cmp: OutputComparison) -> dict | None:
    gap = one_line_gap(cmp)
    if gap is None:
        return None
    if len(cmp.actual_lines) < len(cmp.expected_lines):
        return {"kind": "missing", "line": gap + 1, "text": cmp.expected_lines[gap]}
    return {"kind": "extra", "line": gap + 1, "text": cmp.actual_lines[gap]}


def _output_clues(cmp: OutputComparison, code: str, tree: ast.AST | None) -> list[_Clue]:
    """What the shape of the difference suggests."""
    clues = []
    exp, act = cmp.expected_lines, cmp.actual_lines
    gap = one_line_gap(cmp)
    if gap is not None:
        more = "one more line" if len(act) > len(exp) else "one line fewer"
        which = {0: "first", len(max(exp, act, key=len)) - 1: "last"}.get(gap, f"line {gap + 1}")
        clues.append(_Clue("off_by_one", 3, None,
                           f"The program printed {more} than expected; apart from the {which} line, the lines match."))
    if len(exp) == len(act) > 1 and (exp[1:] == act[:-1] or exp[:-1] == act[1:]):
        clues.append(_Clue("off_by_one", 3, None,
                           "Every expected line is there, but shifted by one place."))
    for e, a in cmp.number_pairs:
        diff = a - e
        if abs(diff) == 1:
            clues.append(_Clue("off_by_one", 1, None,
                               f"The program printed {_fmt(a)} where {_fmt(e)} was expected: one {'more' if diff > 0 else 'less'}."))
        bounds = _loop_bounds(tree) if tree is not None else []
        if abs(diff) > 1 and (abs(diff) in bounds or abs(diff) - 1 in bounds or abs(diff) + 1 in bounds):
            clues.append(_Clue("off_by_one", 2, None,
                               f"The difference between {_fmt(a)} and {_fmt(e)} is {_fmt(abs(diff))}, close to one of the "
                               "range limits in the code, as if one value was left out or added."))
        if a == 0 and e != 0:
            clues.append(_Clue("recursion_base_case", 1, None, f"The program printed 0 where {_fmt(e)} was expected."))
            clues.append(_Clue("calculation", 1, None, f"The program printed 0 where {_fmt(e)} was expected."))
        if e and a and not float(e).is_integer() and float(a).is_integer() and int(a) == int(e):
            clues.append(_Clue("calculation", 2, None,
                               f"The program printed {_fmt(a)} where {_fmt(e)} was expected: the part after the decimal point is missing."))
        elif e and a and diff and abs(diff) != 1:
            clues.append(_Clue("calculation", 1, None,
                               f"The program printed {_fmt(a)} where {_fmt(e)} was expected (a difference of {_fmt(abs(diff))})."))
    if any("None" in l.split() for l in act) and not any("None" in l.split() for l in exp):
        clues.append(_Clue("missing_return", 2, None,
                           "The program printed None, which is what a function gives back when it has no return value."))
        if tree is not None:
            for fn in ast.walk(tree):
                if isinstance(fn, ast.FunctionDef) and not any(
                        isinstance(n, ast.Return) and n.value is not None for n in ast.walk(fn)):
                    clues.append(_Clue("missing_return", 2, fn.lineno,
                                       f"The function {fn.name} (line {fn.lineno}) has no return statement that gives back a value."))
    return clues


def analyse_logic(code: str, stdout: str, expected: str) -> ErrorReport | None:
    """None when the output matches. Otherwise a report like a crash report, with kind 'logic'."""
    cmp = compare_output(stdout, expected, code)
    if cmp.matches:
        return None
    try:
        tree: ast.AST | None = ast.parse(code)
    except SyntaxError:
        tree = None
    clues = _output_clues(cmp, code, tree)
    if tree is not None:
        clues += _recursion_clues(code, tree) + _loop_clues(code, tree) + _calc_clues(code, tree)

    scores = {c: 0 for c in CATEGORIES}
    recursive = any(c.category == "recursion_base_case" and c.weight >= 3 for c in clues)
    for clue in clues:
        scores[clue.category] += clue.weight
        # A wrong base case shifts or skews every result built on it, so in a recursive
        # program an output that is "one off" counts towards the base case too.
        if recursive and clue.line is None and clue.category == "off_by_one":
            scores["recursion_base_case"] += clue.weight
    # Ties go to the more specific kind of mistake.
    order = ["missing_return", "recursion_base_case", "off_by_one", "calculation"]
    best = max(order, key=lambda c: (scores[c], -order.index(c)))
    category = best if scores[best] >= 2 else "other"

    code_lines = code.splitlines()
    cause = next((c.line for c in sorted(clues, key=lambda c: -c.weight)
                  if c.category == category and c.line), None)
    title, message = describe_difference(cmp)
    facts = [message]
    facts += [f"{len(cmp.actual_lines)} line(s) printed, {len(cmp.expected_lines)} line(s) expected."]
    facts += list(dict.fromkeys(c.fact for c in clues))
    return ErrorReport(
        kind="logic",
        error_type="LogicError",
        message=message,
        line=cause,
        line_text=code_lines[cause - 1] if cause and cause <= len(code_lines) else None,
        facts=facts,
        details={
            "category": category,
            "scores": scores,
            "comparison": cmp.to_dict(),
            "gap": _gap_detail(cmp),
            "title": title,
            "expected": "\n".join(cmp.expected_lines),
            "actual": "\n".join(cmp.actual_lines),
        },
        traceback="",
        code=code,
    )
