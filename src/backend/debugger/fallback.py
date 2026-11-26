"""Rule-based stage 1 questions, used when the model is unavailable or its
answer fails the guardrails twice. Deliberately conservative: they point at
the right place and concept, never at the fix."""

from __future__ import annotations

import re

from .analysis import ErrorReport

_ATTR_RE = re.compile(r"^'(?P<type>[\w.]+)' object has no attribute '(?P<attr>\w+)'")
_MOD_ATTR_RE = re.compile(r"^module '(?P<mod>[\w.]+)' has no attribute '(?P<attr>\w+)'")
_NAME_RE = re.compile(r"^name '(?P<name>\w+)' is not defined")
_IMPORT_HINT_RE = re.compile(r"Did you forget to import '(?P<mod>[\w.]+)'")
_NO_MODULE_RE = re.compile(r"^No module named '(?P<mod>[\w.]+)'")
_CANT_IMPORT_RE = re.compile(r"^cannot import name '(?P<name>\w+)' from '(?P<mod>[\w.]+)'")

_FRIENDLY_TYPE = {
    "str": "a string", "list": "a list", "dict": "a dictionary", "int": "an integer",
    "float": "a float", "tuple": "a tuple", "set": "a set", "bool": "a boolean",
}


def fallback_question(report: ErrorReport) -> str:
    line = f"line {report.line}" if report.line else "the line Python stopped at"
    msg = report.message or ""
    et = report.error_type

    if report.kind == "timeout":
        loop = _first_loop_line(report)
        where = f"the loop on line {loop}" if loop else "each loop in your program"
        return (f"Your program never finished. What should make {where} stop, and does that value "
                "actually change each time around?")
    if et == "AttributeError":
        m = _ATTR_RE.match(msg)
        if m and m.group("type") == "NoneType":
            return (f"On {line}, the value before .{m.group('attr')} turns out to be None. Where did that "
                    "value come from, and does that step actually hand a value back?")
        if m:
            kind = _FRIENDLY_TYPE.get(m.group("type"), f"a {m.group('type')} value")
            return (f"On {line} you use {m.group('attr')} on {kind}. Is {m.group('attr')} actually "
                    f"something that {kind} has?")
        m = _MOD_ATTR_RE.match(msg)
        if m:
            return (f"On {line} you use {m.group('mod')}.{m.group('attr')}. Does the {m.group('mod')} "
                    f"module really contain something called {m.group('attr')}?")
    if et == "ModuleNotFoundError":
        m = _NO_MODULE_RE.match(msg)
        if m:
            mod = m.group("mod")
            return (f"On {line} you import {mod}. Is {mod} a module that comes with Python, and if so, "
                    "is its name spelled exactly the way Python spells it?")
    if et == "ImportError":
        m = _CANT_IMPORT_RE.match(msg)
        if m:
            return (f"On {line} you import {m.group('name')} from {m.group('mod')}. Does the "
                    f"{m.group('mod')} module really contain something called {m.group('name')}?")
        return f"On {line}, what exactly is this import line asking Python to load?"
    if et == "NameError":
        m = _NAME_RE.match(msg)
        if m and _IMPORT_HINT_RE.search(msg):
            n = m.group("name")
            return (f"On {line} you use {n}. Where in your program is {n} imported, and does that "
                    f"happen before {line}?")
        if m:
            n = m.group("name")
            return (f"On {line} you use {n}. Where in your program is {n} created, and is it spelled "
                    "exactly the same there?")
    if et == "UnboundLocalError":
        return (f"On {line} the function reads a variable before giving it a value. Which variable is it, "
                "and where does this function assign to it?")
    if et == "TypeError":
        if "NoneType" in msg:
            return (f"On {line} one of the values is None. Which step was supposed to produce that value, "
                    "and does that step actually hand a value back?")
        return (f"On {line}, what type does each value involved have at that moment, and is each one "
                "the type you expected?")
    if et == "ValueError" and report.details.get("empty_call"):
        return _empty_iterable_question(report, line, 0)
    if et == "ValueError":
        return f"On {line}, what exactly does the value being converted look like, and can it be read as that type?"
    if et == "IndexError":
        return (f"On {line}, how many items are in the sequence at that moment, and which position "
                "are you asking for?")
    if et == "KeyError":
        return f"On {line}, which keys does the dictionary actually contain at that moment?"
    if et == "ZeroDivisionError":
        return f"On {line}, what value is the number you divide by, and where does that value come from?"
    if et == "OverflowError":
        return (f"On {line}, roughly how big would the result be, and is there a limit to how big a "
                "decimal number can get in Python?")
    if et in ("IndentationError", "TabError"):
        return f"Look at the indentation around {line}: which block is each of these lines meant to belong to?"
    if et == "SyntaxError":
        return (f"Python could not read {line}. Compare that line, and the one just above it, with "
                "the shape that kind of statement normally has: is anything missing or extra?")
    if et == "RecursionError":
        return (f"The function called on {line} keeps calling itself. Which value of its input should "
                "make it stop, and is there anything in the function that stops there?")
    return (f"On {line}, what values do the variables used there actually have? Try printing them "
            "just before that line: are they what you expected?")


def _first_loop_line(report: ErrorReport) -> int | None:
    code = report.code or ""
    for i, text in enumerate(code.splitlines(), 1):
        if re.match(r"\s*(while|for)\b", text):
            return i
    return None


def followup_fallback(report: ErrorReport, turn: int) -> str:
    """A more concrete question for stage 2, used when the model is unavailable or its
    responses fail the checks. `turn` is the follow-up number (1, 2, ...): later turns
    point at something smaller and more specific."""
    line = f"line {report.line}" if report.line else "the line Python stopped at"
    msg = report.message or ""
    et = report.error_type
    text = (report.line_text or "").strip()

    if report.kind == "timeout":
        loop = _first_loop_line(report)
        where = f"line {loop}" if loop else "your loop"
        if turn == 1:
            return (f"Add a print of the loop variable as the first line inside the loop at {where}. "
                    "When you run it, does that value ever change?")
        return f"Which line inside the loop at {where} is supposed to move the loop variable towards the stopping condition?"
    if et == "NameError":
        m = _NAME_RE.match(msg)
        if m:
            n = m.group("name")
            if _IMPORT_HINT_RE.search(msg):
                return f"Before {line}, which lines of your program bring in modules, and is {n} one of them?"
            if turn == 1:
                return (f"Python only knows names that were created before {line} runs. Which line "
                        f"creates something called exactly {n}, letter for letter, including capitals?")
            return f"Look at every name on {line}: which of them is not created anywhere above it in your program?"
    if et == "AttributeError":
        m = _ATTR_RE.match(msg)
        if m and m.group("type") != "NoneType":
            kind = _FRIENDLY_TYPE.get(m.group("type"), f"a {m.group('type')} value")
            return (f"Try running print(dir({m.group('type')})) on its own. Does {m.group('attr')} appear "
                    f"in that list of things {kind} can do?")
        if m:
            return (f"On {line}, add a print of the value just before .{m.group('attr')}. What does it "
                    "print, and which earlier line gave it that value?")
        m = _MOD_ATTR_RE.match(msg)
        if m:
            return (f"Try running print(dir({m.group('mod')})) after the import. Is {m.group('attr')} in "
                    "that list, spelled exactly the same?")
    if et == "ModuleNotFoundError":
        m = _NO_MODULE_RE.match(msg)
        if m:
            return (f"Which modules does your course use, and does {m.group('mod')} on {line} match one of "
                    "them letter for letter?")
    if et == "TypeError" and text:
        return (f"Add a line just before {line} that prints type() of each value used on that line. "
                "Which type is not the one you expected?")
    if et == "ValueError" and report.details.get("empty_call"):
        return _empty_iterable_question(report, line, turn)
    if et == "ValueError":
        return f"Just before {line}, print the value being converted with repr(). What exactly is inside the quotes?"
    if et == "IndexError":
        return (f"Just before {line}, print len() of the sequence and the position you ask for. Is the "
                "position smaller than the length?")
    if et == "KeyError":
        return f"Just before {line}, print the dictionary's keys(). Is the key you ask for in that list, spelled exactly the same?"
    if et == "ZeroDivisionError":
        return f"Just before {line}, print the number you divide by. Which earlier line gave it that value?"
    if et == "OverflowError":
        return (f"Try print(10.0 ** 300) and then print(10.0 ** 400) on their own. Which one works, and "
                f"what does that tell you about the number on {line}?")
    if et in ("SyntaxError", "IndentationError", "TabError"):
        if turn == 1:
            return (f"Read {line} one symbol at a time, and the line just above it. Is every bracket and "
                    "quote that opens also closed, and does it end the way that kind of line should?")
        return f"Compare {line} with a line in your course notes that does the same kind of thing. What is different?"
    if et == "UnboundLocalError":
        return f"Inside the function containing {line}, which line assigns to the variable, and does it come before or after {line}?"
    return (f"Just before {line}, add a print for each variable used on that line. Which printed value is "
            "not what you expected?")


def _empty_iterable_question(report: ErrorReport, line: str, turn: int) -> str:
    """max()/min() got nothing, often because a generator was already used up."""
    d = report.details
    fn, name, used = d["empty_call"], d.get("empty_name"), d.get("used_up_on")
    if not name:
        return f"Just before {line}, print what you give to {fn}(). What's in it at that moment?"
    if not used:
        return f"On {line}, {fn}() finds nothing in {name}. What does {name} contain just before that line runs?"
    if turn == 0:
        return (f"On {line}, {fn}() finds nothing in {name}. What do you think {name} still contains after "
                f"line {used} has already gone through it?")
    if turn == 1:
        return (f"Try putting print(sum({name})) twice in a row straight after line {d['one_pass_line']}. "
                "Do both lines print the same number?")
    return (f"Look at how {name} is made on line {d['one_pass_line']}. Is it a list that keeps its values, "
            "or something that hands them out one at a time?")


# === Logic errors (logic.py): the program ran but printed something unexpected ===


def _quote(text: str, limit: int = 50) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _difference(report: ErrorReport) -> str:
    if report.details.get("category") == "missing_return":
        return "Your program printed None where you expected a value."
    gap = report.details.get("gap")
    if gap and gap["kind"] == "missing":
        return f"Your output is missing the line \"{_quote(gap['text'], 30)}\"."
    if gap:
        return f"Your output has an extra line, \"{_quote(gap['text'], 30)}\"."
    c = report.details.get("comparison") or {}
    e, a = c.get("expected_line"), c.get("actual_line")
    if len(c.get("number_pairs") or []) == 1:
        # Quote the two numbers exactly as they were printed and typed.
        nums = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
        diff = [(x, y) for x, y in zip(nums.findall(e), nums.findall(a)) if float(x) != float(y)]
        if len(diff) == 1:
            return f"Your output shows {diff[0][1]} where you expected {diff[0][0]}."
    if e is not None and a is not None:
        return f"Your output shows \"{_quote(a, 30)}\" where you expected \"{_quote(e, 30)}\"."
    if e is not None:
        return f"Your output is missing the line \"{_quote(e, 30)}\"."
    if a is not None:
        return f"Your output has an extra line, \"{_quote(a, 30)}\"."
    return "Your output is not what you expected."


def _code(report: ErrorReport) -> str:
    """The cause line as the student wrote it, in quotes, without a trailing colon."""
    return f"\"{_quote((report.line_text or '').strip().rstrip(':'))}\""


def _function_at(report: ErrorReport) -> str | None:
    """The function defined on the cause line or the nearest one above it."""
    lines = (report.code or "").splitlines()[: report.line or 0]
    for text in reversed(lines):
        m = re.match(r"\s*def (\w+)", text)
        if m:
            return m.group(1)
    m = re.search(r"^def (\w+)", report.code or "", flags=re.MULTILINE)
    return m.group(1) if m else None


def _while_test(report: ErrorReport) -> str | None:
    m = re.match(r"\s*while (.+?):?\s*$", report.line_text or "")
    return m.group(1) if m else None


def logic_fallback_question(report: ErrorReport) -> str:
    """Stage 1 for a logic error, when the model is unavailable."""
    cat = report.details.get("category", "other")
    diff = _difference(report)
    n = report.line
    if cat == "off_by_one" and n:
        test = _while_test(report)
        if test:
            return (f"{diff} On line {n} the loop keeps going while \"{_quote(test)}\". What is the last value "
                    "it runs with, and is that the last one you wanted?")
        if not re.match(r"\s*for\b", report.line_text or "") and "[" in (report.line_text or ""):
            return (f"{diff} On line {n} you wrote {_code(report)}. Which position does that pick, counting "
                    "from 0, and what is at that position?")
        return (f"{diff} On line {n} you wrote {_code(report)}. What are the first and last values that "
                "actually go through it?")
    if cat == "recursion_base_case" and n:
        fn = _function_at(report) or "your function"
        return (f"{diff} On line {n}, {fn} stops calling itself. What does it give back for that smallest "
                "case, and how does that value feed into the bigger answers?")
    if cat == "missing_return" and n:
        fn = _function_at(report) or "your function"
        return (f"{diff} When {fn} on line {n} finishes, what value does it hand back to the line that "
                "called it?")
    if cat == "calculation" and n:
        return (f"{diff} Work out line {n}, {_code(report)}, by hand with your program's values, in the "
                "order Python does it. What number do you get?")
    return f"{diff} Which line of your code makes that part of the output, and what values does it use when it runs?"


def logic_followup_fallback(report: ErrorReport, turn: int) -> str:
    cat = report.details.get("category", "other")
    n = report.line
    line = f"line {n}" if n else "your loop"
    if cat == "off_by_one":
        if turn <= 1:
            return (f"Put a print of the loop variable as the first line inside the loop on {line}. Which values "
                    "get printed, and is one missing or extra at the start or the end?")
        return (f"Compare the values printed with the ones you need. What would {line} need to reach "
                "for that value to be included or left out?")
    if cat == "recursion_base_case":
        fn = _function_at(report) or "the function"
        if turn <= 1:
            return (f"Work out {fn} by hand for the smallest input, the one that reaches {line}. What does it "
                    "return there, and what does the call just above it then return?")
        return (f"Add a print at the start of {fn} that shows its argument. On the last call, what is the "
                "argument, and is that the smallest case you meant to stop at?")
    if cat == "missing_return":
        fn = _function_at(report) or "the function"
        if turn <= 1:
            return (f"Inside {fn}, the answer is worked out and stored. After that line, does anything send it "
                    "back out of the function?")
        return (f"Add a print as the last line inside {fn} that shows the value it works out. If that prints "
                f"the right number, what happens to the number when {fn} finishes?")
    if cat == "calculation":
        if turn <= 1:
            return (f"Just before {line}, print each variable used on that line. Using those values, which part "
                    "of the calculation gives a different number from the one you'd work out yourself?")
        return (f"Split {line} into smaller steps, one operation per line, printing each result. Which step "
                "first gives a number you didn't expect?")
    return ("Add a print of each variable just before the line that prints the wrong value. Which value is "
            "the first one that isn't what you expected?")


# Without a model, a reply that names the kind of mistake counts as found.
_LOGIC_FOUND = {
    "off_by_one": r"off[ -]by[ -]one|one (?:too )?(?:many|more|less|fewer|short|extra)|too (?:early|soon|far)|"
                  r"(?:doesn'?t|does not|not) (?:include|reach|count)|stops? (?:one )?before",
    "recursion_base_case": r"base case|smallest case|stop(?:s|ping)? (?:case|condition)",
    "calculation": r"order of|brackets?|parenthes|precedence|integer division|//|divides? first|wrong (?:formula|number)",
    "missing_return": r"\breturn",
}


def logic_reply_found_it(report: ErrorReport, reply: str) -> bool:
    pattern = _LOGIC_FOUND.get(report.details.get("category", ""))
    return bool(pattern and re.search(pattern, reply, flags=re.IGNORECASE))


def logic_explanation(report: ErrorReport) -> str:
    """Plain-English answer for the last follow-up, without writing the fix."""
    cat = report.details.get("category", "other")
    n = report.line
    at = f"line {n}" if n else "your code"
    if cat == "off_by_one":
        tail = " Remember that range stops just before its end value." if "range(" in (report.line_text or "") else ""
        return (f"This is an off-by-one mistake: the loop on {at} runs one step too few or too many, or starts "
                f"one step off, so one value is left out or added.{tail}")
    if cat == "recursion_base_case":
        return (f"This comes from the base case on {at}: where the function stops calling itself, it returns the "
                "wrong value or stops at the wrong point, and every bigger answer is built from that value.")
    if cat == "missing_return":
        return (f"The function on {at} works out the answer but never hands it back, so the line that calls it "
                "gets None, which is what Python gives back when a function has no return value.")
    if cat == "calculation":
        return (f"This is a calculation mistake on {at}: with your program's values, the formula Python works out "
                "is not the one you meant. Check the order Python does each step, and the numbers you used.")
    return f"Your program does something slightly different from what you meant around {at}."
