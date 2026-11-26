"""Deterministic checks that a stage 1 question follows the rules.

The model is instructed well, but a tutor that sometimes blurts out the answer
is worse than one that is slightly vague, so every question is checked here
before a student sees it.
"""

from __future__ import annotations

import re

MAX_WORDS = 45
MAX_WORDS_AFTER_QUESTION = 20

# Phrases that turn a leading question into an instruction or a reveal.
_BANNED_PHRASES = [
    r"\byou should\b",
    r"\bshould (?:be|use|have)\b",
    r"\binstead\b",
    r"\breplace\b",
    r"\bchange (?:it|this|that|the|\w+) to\b",
    r"\bdid you mean\b",
    # "Try using isupper" hands over the fix; "try adding print(type(x))" is an experiment
    # that lets the student see for themselves, which is exactly what a hint should do.
    r"\btry (?:using|adding|writing)\b(?! (?:a |an |the |this |another |one )?(?:print|type|len|repr|dir)\b)",
    r"\btry (?:changing|removing|replacing)\b",
    r"\bthe (?:correct|right) (?:method|function|name|way|value)\b",
    r"\bforgot to\b",
    r"\bfix\b",
]

_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# Markdown bold (**word**) or a heading. A bare ** is Python's power operator and
# __name__ is a normal identifier, so neither counts.
_MARKDOWN_RE = re.compile(r"(?<![\w)\]])\*\*[A-Za-z](?:[^*]*?[A-Za-z.!?])?\*\*(?![\w(\[])|^#")


def check_question(
    question: str,
    *,
    giveaways: set[str],
    code: str,
    student_line_text: str | None = None,
    max_words: int = MAX_WORDS,
    visible_text: str = "",
) -> list[str]:
    """Return a list of problems. An empty list means the question passes.

    `visible_text` is what the student can already see on screen (the error line in the
    Output tab). Quoting it is never a leak, so wording and names in it are not flagged."""
    problems: list[str] = []
    q = question.strip()
    if not q:
        return ["The question is empty."]

    if q.count("?") != 1:
        problems.append("It must contain exactly one question (one question mark).")
    else:
        # One short pointer after the question is fine ("You can run dir(str) to see the
        # list."); a second paragraph of explanation is not.
        after = q.split("?", 1)[1].strip()
        if len(after.split()) > MAX_WORDS_AFTER_QUESTION or len(re.findall(r"[.!](?:\s|$)", after)) > 1:
            problems.append(
                "After the question, add at most one short sentence (or nothing); end soon after the question."
            )
    words = len(q.split())
    if words > max_words:
        problems.append(f"It is {words} words long; keep it to {max_words - 5} words or fewer.")
    if "`" in q or "```" in q or _MARKDOWN_RE.search(q):
        problems.append("It contains Markdown or backticks; write plain text.")
    if "\n" in q:
        problems.append("It must be a single paragraph.")

    lowered = q.lower()
    seen = visible_text.lower()
    for pattern in _BANNED_PHRASES:
        m = re.search(pattern, lowered)
        if m and m.group(0) not in seen:
            problems.append(
                f"It uses wording that instructs or reveals the fix (\"{m.group(0)}\"). Suggesting something "
                "to print or inspect is fine; telling them what to change is not."
            )

    # Words the student already wrote on the failing line are fair to quote back.
    problems += _giveaway_problems(q, giveaways, student_words(student_line_text or "") | student_words(visible_text))

    if not _is_anchored(q, code):
        problems.append(
            "It is not anchored to the student's code: mention the line number or quote an identifier "
            "or expression from their program."
        )
    return problems


def _is_anchored(question: str, code: str) -> bool:
    if re.search(r"\bline \d+\b", question, flags=re.IGNORECASE):
        return True
    code_idents = {t for t in _IDENT_RE.findall(code) if len(t) >= 3}
    q_idents = set(_IDENT_RE.findall(question))
    common_words = {"the", "and", "for", "you", "your", "are", "this", "that", "what", "does", "not", "with", "print"}
    return bool((code_idents & q_idents) - common_words)


MAX_ANSWER_WORDS = 80
MAX_FOLLOWUP_QUESTION_WORDS = 60

# An answer may confirm and explain, but must still leave the change to the student.
_ANSWER_BANNED = [
    r"\bdid you mean\b",
    r"\bchange (?:it|this|that|the|\w+) to\b",
    r"\breplace (?:it|this|that|the|\w+) with\b",
    r"\bthe (?:correct|right|fixed) (?:code|line|version) (?:is|would be)\b",
]


def check_answer(
    answer: str,
    *,
    giveaways: set[str],
    code: str,
    allowed_words: set[str] = frozenset(),
    visible_text: str = "",
) -> list[str]:
    """Checks for a stage 2 answer. `allowed_words` are words the student already wrote
    (their code's failing line and their replies), which may be quoted back."""
    problems: list[str] = []
    a = answer.strip()
    if not a:
        return ["The answer is empty."]
    words = len(a.split())
    if words > MAX_ANSWER_WORDS:
        problems.append(f"It is {words} words long; keep it to {MAX_ANSWER_WORDS - 5} words or fewer.")
    if "`" in a or _MARKDOWN_RE.search(a):
        problems.append("It contains Markdown or backticks; write plain text.")
    if "\n" in a:
        problems.append("It must be a single paragraph.")
    lowered = a.lower()
    seen = visible_text.lower()
    for pattern in _ANSWER_BANNED:
        m = re.search(pattern, lowered)
        if m and m.group(0) not in seen:
            problems.append(
                f"It tells the student what to write (matched '{pattern.strip(chr(92) + 'b')}'); "
                "explain the cause and leave the change to them."
            )
    problems += _giveaway_problems(a, giveaways, set(allowed_words) | student_words(visible_text))
    if not _is_anchored(a, code):
        problems.append("Mention the line number or quote an identifier from the student's program.")
    return problems


_STRING_RE = re.compile(r"""(['"])(.*?)\1""")


def student_words(text: str) -> set[str]:
    """Identifiers and the contents of string literals the student wrote, e.g. for
    `print(student["Name"])`: {"print", "student", "Name"}."""
    return set(_IDENT_RE.findall(text)) | {m.group(2) for m in _STRING_RE.finditer(text) if m.group(2)}


def _unquote(text: str) -> str:
    return text.strip().strip("\"'")


# Everyday words a tutor needs to ask good questions ("is it a list you can read again, or
# something that hands out its values once?"). Models sometimes list these as giveaways; on
# their own they never state the fix. Conversion names (int, str, float), keywords (return,
# True, None) and code such as "list(" are not in here, so those stay blocked.
_COMMON_WORDS = {
    "list", "lists", "string", "strings", "number", "numbers", "value", "values", "type", "types",
    "loop", "loops", "once", "twice", "again", "variable", "variables", "function", "functions",
    "method", "methods", "line", "lines", "index", "item", "items", "key", "keys", "dictionary",
    "text", "whole", "decimal", "empty", "first", "last", "before", "after", "inside", "outside",
    "brackets", "spelling", "capital", "letter", "letters", "order", "copy", "same", "different",
}


def _giveaway_problems(text: str, giveaways: set[str], allowed_words: set[str]) -> list[str]:
    """Giveaways are matched ignoring case, so "TRUE" or "True" is caught. But quoting
    the student's own spelling back, exactly as they wrote it, is fine: for `done = true`
    the giveaway is True and the hint must be able to say "true"; for student["Name"]
    the giveaway is "name" and the hint must be able to say "Name"."""
    allowed = {_unquote(w) for w in allowed_words}
    problems = []
    for term in sorted(giveaways):
        term = term.strip()
        core = _unquote(term)
        if len(core) < 3 or term in allowed_words or core.lower() in _COMMON_WORDS:
            continue
        # Quotes around the term don't matter: 'name', "name" and name are the same giveaway.
        pattern = rf"(?<![A-Za-z0-9_])['\"]?{re.escape(core)}['\"]?(?![A-Za-z0-9_])"
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            if _unquote(match.group(0)) not in allowed:
                problems.append(f"It mentions '{term}', which gives the answer away.")
                break
    return problems


_STOP = {
    "the", "and", "you", "your", "are", "this", "that", "what", "does", "with", "line", "have", "has",
    "there", "when", "which", "into", "from", "then", "than", "about", "after", "before", "just", "look",
    "think", "would", "could", "still", "each", "they", "them", "it's", "you're", "let's", "okay", "right",
}


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z_][a-z0-9_']+", text.lower()) if len(w) >= 4 and w not in _STOP}


def repeats_earlier_question(question: str, earlier: list[str], threshold: float = 0.8) -> bool:
    """True when the question is the same as, or a light rewording of, one already asked:
    nearly the same text, or mostly the same content words."""
    from difflib import SequenceMatcher

    q = question.strip().lower()
    words = _content_words(question)
    for e in earlier:
        if SequenceMatcher(None, q, e.strip().lower()).ratio() >= threshold:
            return True
        other = _content_words(e)
        if words and other and len(words & other) / len(words | other) >= 0.6:
            return True
    return False


# === Logic errors ===

_CALL_FRAGMENT_RE = re.compile(r"\b([A-Za-z_]\w*)\(([^()]*)\)")
_COMPARE_FRAGMENT_RE = re.compile(r"\b([A-Za-z_]\w*)\s*(<=|>=|==|!=|<|>)\s*([\w.]+)")
# Calls a hint may suggest as an experiment even though they are not in the student's code.
_EXPERIMENT_CALLS = {"print", "type", "len", "repr", "dir", "str"}


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def new_code_problems(text: str, code: str) -> list[str]:
    """For logic errors the fix is often tiny (range(1, 6), <=, + 32), and it is easy to write
    it into the question. Code-like fragments must already be in the student's program,
    apart from print() and friends, which are experiments."""
    squashed = _squash(code)
    idents = set(_IDENT_RE.findall(code))
    problems = []
    for m in _CALL_FRAGMENT_RE.finditer(text):
        if m.group(1) in _EXPERIMENT_CALLS:
            continue
        if (m.group(1) in idents or m.group(1) == "range") and _squash(m.group(0)) not in squashed:
            problems.append(f"It writes {m.group(0)}, which is not in the student's code, so it may give the fix "
                            "away. Quote their code exactly as they wrote it.")
    for m in _COMPARE_FRAGMENT_RE.finditer(text):
        if m.group(1) in idents and _squash(m.group(0)) not in squashed:
            problems.append(f"It writes {m.group(0)}, which is not in the student's code, so it may give the fix "
                            "away. Quote their code exactly as they wrote it.")
    return problems


def logic_giveaway_problems(text: str, giveaways: set[str], allowed: str) -> list[str]:
    """Like the usual giveaway check, but short terms count too (a range limit such as 6, or
    an operator such as <=): unless they are in `allowed` (the code and both outputs)."""
    allowed_tokens = set(re.findall(r"[\w.]+|[<>=!/*+-]+", allowed))
    problems = []
    for term in sorted(giveaways):
        term = term.strip()
        if not term or len(term) >= 3 or term in allowed_tokens:
            continue  # long terms are already covered by check_question
        if re.search(rf"(?<![\w.<>=!/*+-]){re.escape(term)}(?![\w.<>=!/*+-])", text):
            problems.append(f"It mentions '{term}', which gives the answer away.")
    return problems


def visible_error_text(error_type: str | None, message: str | None) -> str:
    """The error line exactly as the Output tab shows it (Python's full message)."""
    if not error_type:
        return ""
    return f"{error_type}: {message}" if message else error_type


# Wording that sounds like the tutor is brushing the student off or doubting them.
_UNKIND = [
    r"\bthe real question\b",
    r"\bhave you (?:ever )?(?:used|learn(?:ed|t)|studied|seen|done|heard of|read)\b",
    r"\bdid you (?:even|actually|ever|learn|study)\b",
    r"\bdo you (?:even )?know what\b",
    r"\bobviously\b",
    r"\bclearly\b",
    r"\bsimply\b",
]


def tone_problems(text: str) -> list[str]:
    """Stage 2 replies talk to a student who just told us what they think. These phrases
    make a tutor sound dismissive or like they doubt the student, so they are rejected."""
    lowered = text.lower()
    found = [m.group(0) for p in _UNKIND if (m := re.search(p, lowered))]
    if not found:
        return []
    quoted = ", ".join(f'"{w}"' for w in found)
    return [
        f"It can sound dismissive or like you doubt the student ({quoted}). Build on what they "
        "said and ask about the code, not about them or what they have done before."
    ]
