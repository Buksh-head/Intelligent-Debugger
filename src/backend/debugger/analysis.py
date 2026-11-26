"""Turn a raw run result into a structured, verified error report.

Everything here is deterministic. The facts it produces are handed to the model
as ground truth, so the model does not have to guess things like "is isvowel a
str method?". It also collects the names that would give the fix away (for
example Python's own "Did you mean: 'isupper'?" suggestion), which the
guardrails later use to reject a hint that leaks the answer.
"""

from __future__ import annotations

import ast
import builtins
import difflib
import keyword
import re
import sys
from dataclasses import dataclass, field

from .runner import STUDENT_FILENAME, RunResult

_FRAME_RE = re.compile(r'^\s*File "(?P<file>[^"]+)", line (?P<line>\d+)(?:, in (?P<func>.+))?$')
_EXC_LINE_RE = re.compile(r"^(?P<type>[A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt|Warning|Iteration))(?::\s?(?P<msg>.*))?$")
_DID_YOU_MEAN_RE = re.compile(r"Did you mean:? '?([^'?]+)'?\??")
_ATTR_RE = re.compile(r"^'(?P<type>[\w.]+)' object has no attribute '(?P<attr>\w+)'")
_MODULE_ATTR_RE = re.compile(r"^module '(?P<mod>[\w.]+)' has no attribute '(?P<attr>\w+)'")
_NAME_RE = re.compile(r"^name '(?P<name>\w+)' is not defined")
_UNBOUND_RE = re.compile(r"cannot access local variable '(?P<name>\w+)'")

_BUILTIN_TYPES: dict[str, type] = {
    "str": str, "list": list, "dict": dict, "int": int, "float": float,
    "tuple": tuple, "set": set, "bool": bool, "bytes": bytes,
    "NoneType": type(None), "range": range, "frozenset": frozenset,
}


@dataclass
class ErrorReport:
    kind: str                      # "runtime" | "syntax" | "timeout" | "logic" | "none"
    error_type: str | None = None  # e.g. "AttributeError"
    message: str | None = None     # e.g. "'str' object has no attribute 'isvowel'"
    line: int | None = None        # line in the student's file where Python stopped
    line_text: str | None = None
    call_chain: list[int] = field(default_factory=list)  # student-code lines, outermost first
    facts: list[str] = field(default_factory=list)       # verified statements for the model
    giveaways: set[str] = field(default_factory=set)     # strings a stage 1 hint must not contain
    details: dict = field(default_factory=dict)          # structured findings for the rule-based hints
    traceback: str = ""
    code: str = ""

    @property
    def has_error(self) -> bool:
        # "logic": the program ran, but its output differs from what the student expected (logic.py).
        return self.kind in ("runtime", "syntax", "timeout", "logic")


def numbered_code(code: str) -> str:
    lines = code.splitlines() or [""]
    width = len(str(len(lines)))
    return "\n".join(f"{i:>{width}} | {text}" for i, text in enumerate(lines, 1))


def analyse(run: RunResult) -> ErrorReport:
    if run.timed_out:
        return ErrorReport(
            kind="timeout",
            error_type="Timeout",
            message="The program did not finish within the time limit.",
            facts=[
                "The program was stopped because it ran too long. It is most likely stuck in a loop "
                "that never ends, or it is waiting for input that was never given."
            ],
            traceback=run.stderr,
            code=run.code,
        )
    if run.returncode == 0:
        return ErrorReport(kind="none", traceback=run.stderr, code=run.code)

    tb = _last_exception_block(run.stderr)
    report = ErrorReport(kind="runtime", traceback=tb, code=run.code)
    _parse_exception_line(tb, report)
    _parse_location(tb, run.code, report)
    if report.error_type in ("SyntaxError", "IndentationError", "TabError"):
        report.kind = "syntax"
    _add_facts(run.code, report)
    return report


def _last_exception_block(stderr: str) -> str:
    # With chained exceptions, the last block is the one that actually stopped the program.
    separators = (
        "During handling of the above exception, another exception occurred:",
        "The above exception was the direct cause of the following exception:",
    )
    block = stderr
    for sep in separators:
        if sep in block:
            block = block.rsplit(sep, 1)[1]
    return block.strip("\n")


def _parse_exception_line(tb: str, report: ErrorReport) -> None:
    for raw in reversed(tb.splitlines()):
        line = raw.rstrip()
        if not line or line.startswith(" "):
            continue
        m = _EXC_LINE_RE.match(line)
        if m:
            report.error_type = m.group("type").split(".")[-1]
            report.message = (m.group("msg") or "").strip()
            return
    lines = [l for l in tb.splitlines() if l.strip()]
    report.error_type = "Error"
    report.message = lines[-1].strip() if lines else "The program stopped with an error."


def _parse_location(tb: str, code: str, report: ErrorReport) -> None:
    code_lines = code.splitlines()
    for raw in tb.splitlines():
        m = _FRAME_RE.match(raw)
        if m and m.group("file").replace("\\", "/").split("/")[-1] == STUDENT_FILENAME:
            report.call_chain.append(int(m.group("line")))
    if report.call_chain:
        report.line = report.call_chain[-1]
        if 1 <= report.line <= len(code_lines):
            report.line_text = code_lines[report.line - 1]


def _add_facts(code: str, report: ErrorReport) -> None:
    msg = report.message or ""
    for suggestion in _DID_YOU_MEAN_RE.findall(msg):
        report.giveaways.add(suggestion.strip().rstrip("."))

    if report.line is not None:
        report.facts.append(f"Python stopped at line {report.line}.")
    if len(report.call_chain) > 1:
        chain = " -> ".join(str(n) for n in report.call_chain)
        report.facts.append(f"The failing call path through the student's code is line {chain}.")

    etype = report.error_type
    if etype == "AttributeError":
        _facts_attribute(msg, report)
    elif etype == "NameError":
        _facts_name(code, msg, report)
    elif etype in ("ModuleNotFoundError", "ImportError"):
        _facts_import(code, msg, report)
    elif etype == "ValueError" and _EMPTY_ITERABLE_RE.match(msg):
        _facts_empty_iterable(code, msg, report)
    elif etype == "OverflowError":
        report.facts.append(
            "Python whole numbers (int) have no size limit, but decimal numbers (float) do: the largest "
            "float is about 1.8e308 (a number roughly 309 digits long). A float calculation whose result "
            "goes past that, or an int too big to convert to a float, raises OverflowError."
        )
    elif etype == "EOFError":
        report.facts.append(
            "The program called input() but there was no more input to read. Either no input was "
            "provided when the program ran, or input() is called more times than there are lines of input."
        )
    elif etype == "UnboundLocalError":
        m = _UNBOUND_RE.search(msg)
        if m:
            report.facts.append(
                f"'{m.group('name')}' is assigned somewhere inside the function, so Python treats it as a "
                "local variable for the whole function, but it is read before that assignment runs."
            )


def _facts_attribute(msg: str, report: ErrorReport) -> None:
    m = _ATTR_RE.match(msg)
    if m:
        tname, attr = m.group("type"), m.group("attr")
        if tname == "NoneType":
            report.facts.append(
                f"The value before '.{attr}' is None at that moment. Something that was expected to hand "
                "back a value handed back None instead (for example a function with no return, or a "
                "method like list.sort() or list.append() that changes a list in place and returns None)."
            )
            return
        t = _BUILTIN_TYPES.get(tname)
        if t is not None:
            members = [n for n in dir(t) if not n.startswith("_")]
            report.facts.append(
                f"Verified: '{attr}' is not an attribute or method of Python's built-in {tname} type."
            )
            close = difflib.get_close_matches(attr, members, n=3, cutoff=0.6)
            report.giveaways.update(close)
            if close:
                report.facts.append(
                    "Real {0} methods with similar names exist ({1}); do NOT mention these to the "
                    "student.".format(tname, ", ".join(close))
                )
        else:
            report.facts.append(
                f"The value is an object of type '{tname}', which has no attribute '{attr}'."
            )
        return
    m = _MODULE_ATTR_RE.match(msg)
    if m:
        report.facts.append(
            f"Verified: the module '{m.group('mod')}' has nothing called '{m.group('attr')}'."
        )


_EMPTY_ITERABLE_RE = re.compile(
    r"^(?P<fn>max|min)\(\) (?:iterable argument is empty|arg is an empty sequence)"
)
# Calls that give back a one-pass iterator rather than a list.
_ONE_PASS_CALLS = {"map", "filter", "zip", "iter", "reversed", "enumerate", "open"}
# Ways a later line can use up an iterator.
_CONSUMERS = {"sum", "list", "tuple", "set", "sorted", "max", "min", "len", "any", "all", "dict", "next"}


def _facts_empty_iterable(code: str, msg: str, report: ErrorReport) -> None:
    """max()/min() got nothing. The classic first-year cause: the value is a generator
    (or map/filter/zip...) that an earlier line already went through."""
    fn = _EMPTY_ITERABLE_RE.match(msg).group("fn")
    report.details["empty_call"] = fn
    report.facts.append(f"{fn}() was given something that had no values in it when line {report.line} ran.")
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return
    # The argument of max()/min() on the failing line, if it is a plain name.
    name = None
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == fn
                and node.lineno == report.line and node.args and isinstance(node.args[0], ast.Name)):
            name = node.args[0].id
            break
    if not name:
        return
    report.details["empty_name"] = name
    made = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            if node.lineno < (report.line or 0):
                made = node
    if made is None:
        return
    value = made.value
    one_pass = isinstance(value, ast.GeneratorExp) or (
        isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id in _ONE_PASS_CALLS
    )
    if not one_pass:
        return
    kind = "a generator expression (round brackets)" if isinstance(value, ast.GeneratorExp) else \
        f"the result of {value.func.id}(), which is a one-pass iterator"
    report.details.update(one_pass_line=made.lineno, one_pass_generator=isinstance(value, ast.GeneratorExp))
    report.facts.append(
        f"'{name}' is created on line {made.lineno} as {kind}. It is not a list: it produces its values "
        "one at a time and can only be gone through once. After that it is empty."
    )
    # Earlier lines that already went through it.
    used = sorted({
        node.lineno for node in ast.walk(tree)
        if made.lineno < getattr(node, "lineno", 0) < (report.line or 0) and (
            (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _CONSUMERS
             and any(isinstance(a, ast.Name) and a.id == name for a in node.args))
            or (isinstance(node, (ast.For, ast.comprehension)) and isinstance(node.iter, ast.Name)
                and node.iter.id == name)
        )
    })
    if used:
        report.details["used_up_on"] = used[0]
        report.facts.append(
            f"Line {used[0]} already went through every value of '{name}', so by line {report.line} it is "
            f"empty, which is why {fn}() has nothing to look at. The cause is on line {made.lineno}, "
            "where it is created, not on the line where Python stopped."
        )
    # The fix (make it a list) is the answer; the concept (one pass only) is fair to ask about.
    report.giveaways.update({"list comprehension", "square brackets", "list("})


_NO_MODULE_RE = re.compile(r"^No module named '(?P<mod>[\w.]+)'")
_CANT_IMPORT_RE = re.compile(r"^cannot import name '(?P<name>\w+)' from '(?P<mod>[\w.]+)'")


def _facts_import(code: str, msg: str, report: ErrorReport) -> None:
    m = _NO_MODULE_RE.match(msg)
    if m:
        mod = m.group("mod")
        top = mod.split(".")[0]
        if top in sys.stdlib_module_names:
            report.facts.append(f"'{top}' is a standard library module, but '{mod}' does not exist inside it.")
        else:
            report.facts.append(
                f"'{top}' is not a module that comes with Python, and the student's program is a single "
                f"file (main.py), so there is no {top}.py next to it to import."
            )
            close = difflib.get_close_matches(top, sorted(sys.stdlib_module_names), n=2, cutoff=0.75)
            if close:
                report.facts.append(f"Close standard library module names: {', '.join(close)}.")
                report.giveaways.update(close)
        return
    m = _CANT_IMPORT_RE.match(msg)
    if m:
        report.facts.append(
            f"Verified: the module '{m.group('mod')}' has nothing called '{m.group('name')}' to import."
        )
        sugg = re.search(r"Did you mean: '(\w+)'", msg)
        if sugg:
            report.giveaways.add(sugg.group(1))


def _facts_name(code: str, msg: str, report: ErrorReport) -> None:
    m = _NAME_RE.match(msg)
    if not m:
        return
    name = m.group("name")
    imp = re.search(r"Did you forget to import '([\w.]+)'", msg)
    if imp:
        report.facts.append(
            f"Python reports that '{imp.group(1)}' is a standard library module that the program "
            f"uses without importing it first."
        )
    defined = _names_defined_in(code)
    if name in defined:
        first = min(defined[name])
        if report.line is not None and first > report.line:
            report.facts.append(
                f"'{name}' is first given a value on line {first}, which is after it is used on "
                f"line {report.line}."
            )
        else:
            report.facts.append(
                f"'{name}' is assigned on line {first}, but not in a place that is visible where it is "
                f"used (for example it is local to another function, or that line never ran)."
            )
    else:
        report.facts.append(f"Nothing called '{name}' is defined anywhere in the student's program.")
        candidates = set(defined) | set(dir(builtins)) | set(keyword.kwlist)
        close = difflib.get_close_matches(name, sorted(candidates), n=3, cutoff=0.7)
        if close:
            report.giveaways.update(close)
            report.facts.append(
                "Similar names that do exist: {0}; do NOT mention these to the student.".format(
                    ", ".join(close)
                )
            )
        if name in ("true", "false", "none", "null", "TRUE", "FALSE"):
            report.facts.append(f"'{name}' looks like a literal written with the wrong capitalisation.")


def _names_defined_in(code: str) -> dict[str, list[int]]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {}
    found: dict[str, list[int]] = {}

    def add(n: str, line: int) -> None:
        found.setdefault(n, []).append(line)

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            add(node.id, node.lineno)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            add(node.name, node.lineno)
        elif isinstance(node, ast.arg):
            add(node.arg, node.lineno)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                add((alias.asname or alias.name).split(".")[0], node.lineno)
    return found
