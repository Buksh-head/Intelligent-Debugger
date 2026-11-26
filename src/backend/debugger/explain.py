"""Plain-English versions of Python's error messages, for beginners.

Python's own message ("TypeError: unsupported operand type(s) for +:
'NoneType' and 'int'") is written for experienced programmers. explain()
turns it into a short headline and one or two sentences a first-year student
can follow.

The rules are deliberate:

* Say what Python said, in plain words, and nothing more. The explanation
  describes what happened and where; it never says why it happened or how to
  fix it. Finding the cause is the job of the stage 1 question.
* For runtime errors, never repeat Python's "Did you mean ...?" suggestions
  (e.g. the real variable name), which are the answer.
* For syntax errors, do use Python's suggestion ("Perhaps you forgot a
  comma?", "Maybe you meant '=='..."), explained in plain words. Here the
  suggestion is part of what Python is telling the student about how it read
  the line, and the generic "Python couldn't read this line" says too little.
* Every error gets something readable: specific wording for the errors
  first-years hit most often, and a general sentence per error type otherwise.

This is deterministic (no model call), so it is instant, free and always
available, even when the hint model is not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from .analysis import ErrorReport

# What a beginner would call each type, with an article.
_TYPE_NAMES = {
    "str": "a string (text)",
    "int": "an integer (a whole number)",
    "float": "a float (a decimal number)",
    "bool": "a boolean (True or False)",
    "list": "a list",
    "dict": "a dictionary",
    "tuple": "a tuple",
    "set": "a set",
    "NoneType": "None (which means \"no value\")",
    "function": "a function",
    "builtin_function_or_method": "a built-in function",
    "method": "a method",
    "module": "a module",
    "range": "a range",
}


def type_name(t: str) -> str:
    return _TYPE_NAMES.get(t, f"a value of type {t}")


def _bare(t: str) -> str:
    """'a string (text)' -> 'string (text)', for use after 'this'."""
    name = type_name(t)
    return name.split(" ", 1)[1] if name.startswith(("a ", "an ")) else name


def _short(t: str) -> str:
    """A very short name for titles: 'a number', 'None', 'a list'."""
    if t in ("int", "float"):
        return "a number"
    if t == "NoneType":
        return "None"
    return type_name(t).split(" (")[0]


_OPERATORS = {
    "+": "+ (add or join)",
    "-": "- (subtract)",
    "*": "* (multiply)",
    "/": "/ (divide)",
    "//": "// (whole-number divide)",
    "%": "% (remainder)",
    "**": "** (power)",
    "<": "<", ">": ">", "<=": "<=", ">=": ">=",
}


@dataclass(frozen=True)
class FriendlyError:
    title: str    # short headline, e.g. "Text and a number can't be joined with +"
    message: str  # one or two plain sentences, starting with where it happened


Rule = tuple[str, re.Pattern[str], Callable[[re.Match[str], str], tuple[str, str]]]


_TOKEN_NAMES = {
    "(": "an opening bracket (", ")": "a closing bracket )",
    "[": "an opening bracket [", "]": "a closing bracket ]",
    "{": "an opening bracket {", "}": "a closing bracket }",
    ":": "a colon (:)", ",": "a comma (,)", "=": "an equals sign (=)", ".": "a dot (.)",
}


def _token_name(tok: str) -> str:
    """'(' -> 'an opening bracket (', 'in' -> 'the word in'."""
    if tok in _TOKEN_NAMES:
        return _TOKEN_NAMES[tok]
    return f"the word {tok}" if tok.isidentifier() else f"'{tok}'"


def _r(error_type: str, pattern: str):
    def wrap(fn: Callable[[re.Match[str], str], tuple[str, str]]) -> Rule:
        return (error_type, re.compile(pattern), fn)
    return wrap


RULES: list[Rule] = [
    # === NameError / UnboundLocalError ===
    # Python 3.12+ adds "Did you forget to import 'math'?" when the name is a standard module.
    _r("NameError", r"^name '(?P<n>\w+)' is not defined\. Did you forget to import '(?P<mod>[\w.]+)'")(lambda m, at: (
        f"{m['n']} is a module that hasn't been imported",
        f"{at} you use {m['n']}. Python has a built-in module called {m['mod']}, but a module can only "
        "be used after the program has imported it, and Python hasn't seen that happen before this line.",
    )),
    _r("NameError", r"^name '(?P<n>\w+)' is not defined")(lambda m, at: (
        f"Python doesn't know the name {m['n']}",
        f"{at} you use {m['n']}, but at that point Python has not seen any variable or function "
        f"called {m['n']}.",
    )),
    _r("UnboundLocalError", r"local variable '(?P<n>\w+)'")(lambda m, at: (
        f"{m['n']} is used before it has a value",
        f"{at} the function reads {m['n']}, but inside this function {m['n']} has not been given "
        "a value yet when that line runs.",
    )),
    # === AttributeError ===
    _r("AttributeError", r"^'NoneType' object has no attribute '(?P<a>\w+)'")(lambda m, at: (
        f"The value is None, so it has no .{m['a']}",
        f"{at} you use .{m['a']} on a value, but that value is None, which means \"no value\". "
        f"None doesn't have anything called {m['a']}.",
    )),
    _r("AttributeError", r"^'(?P<t>[\w.]+)' object has no attribute '(?P<a>\w+)'")(lambda m, at: (
        f"This {_bare(m['t']).split(' (')[0]} has nothing called {m['a']}",
        f"{at} you use .{m['a']} on {type_name(m['t'])}. Python looked for something called "
        f"{m['a']} on it and couldn't find one.",
    )),
    _r("AttributeError", r"^module '(?P<mod>[\w.]+)' has no attribute '(?P<a>\w+)'")(lambda m, at: (
        f"The {m['mod']} module has nothing called {m['a']}",
        f"{at} you use {m['mod']}.{m['a']}, but Python couldn't find anything called {m['a']} "
        f"inside the {m['mod']} module.",
    )),
    # === TypeError ===
    _r("TypeError", r'^can only concatenate str \(not "(?P<t>\w+)"\) to str')(lambda m, at: (
        f"Text and {_short(m['t'])} can't be joined with +",
        f"{at} you use + between a string (text) and {type_name(m['t'])}. Python only uses + to "
        "join text with text, or to add numbers to numbers.",
    )),
    _r("TypeError", r"^unsupported operand type\(s\) for (?P<op>\S+): '(?P<a>\w+)' and '(?P<b>\w+)'")(lambda m, at: (
        f"Python can't use {m['op']} on these two values",
        f"{at} you use {_OPERATORS.get(m['op'], m['op'])} with {type_name(m['a'])} on the left and "
        f"{type_name(m['b'])} on the right. Python doesn't know how to do that with these two types.",
    )),
    _r("TypeError", r"^'(?P<op>[<>]=?)' not supported between instances of '(?P<a>\w+)' and '(?P<b>\w+)'")(lambda m, at: (
        f"Python can't compare these two values with {m['op']}",
        f"{at} you compare {type_name(m['a'])} with {type_name(m['b'])} using {m['op']}. Python "
        "can't tell which is bigger when the types are this different.",
    )),
    _r("TypeError", r"^can't multiply sequence by non-int of type '(?P<t>\w+)'")(lambda m, at: (
        "Text or a list can only be repeated a whole number of times",
        f"{at} you multiply a string or list by {type_name(m['t'])}. Python can repeat text or "
        "lists with *, but only a whole number of times.",
    )),
    _r("TypeError", r"^'NoneType' object is not subscriptable")(lambda m, at: (
        "The value is None, so you can't use [ ] on it",
        f"{at} you use square brackets [ ] to get something out of a value, but that value is None, "
        "which means \"no value\". There is nothing inside None to get.",
    )),
    _r("TypeError", r"^'(?P<t>\w+)' object is not subscriptable")(lambda m, at: (
        f"You can't use [ ] on {type_name(m['t']).split(' (')[0]}",
        f"{at} you use square brackets [ ] on {type_name(m['t'])}. Square brackets only work on "
        "things that hold other values, like lists, strings and dictionaries.",
    )),
    _r("TypeError", r"^'(?P<t>\w+)' object is not callable")(lambda m, at: (
        f"{type_name(m['t']).split(' (')[0].capitalize()} can't be called like a function",
        f"{at} you put round brackets ( ) after something, which tells Python to run it as a "
        f"function. But it is {type_name(m['t'])}, not a function.",
    )),
    _r("TypeError", r"^'(?P<t>\w+)' object is not iterable")(lambda m, at: (
        f"You can't loop over {type_name(m['t']).split(' (')[0]}",
        f"{at} your code tries to go through the items of {type_name(m['t'])} one by one (for "
        "example in a for loop), but it doesn't hold a collection of items.",
    )),
    _r("TypeError", r"^'(?P<t>\w+)' object does not support item assignment")(lambda m, at: (
        f"Parts of {type_name(m['t']).split(' (')[0]} can't be changed",
        f"{at} you try to change one item of {type_name(m['t'])} using [ ] and =. Python doesn't "
        "allow changing a single part of this type of value.",
    )),
    _r("TypeError", r"^object of type '(?P<t>\w+)' has no len\(\)")(lambda m, at: (
        f"len() can't measure {type_name(m['t']).split(' (')[0]}",
        f"{at} you call len() on {type_name(m['t'])}. len() counts the items in things like "
        "strings, lists and dictionaries, and this value isn't one of those.",
    )),
    _r("TypeError", r"^type (?P<t>\w+) doesn't define __round__ method")(lambda m, at: (
        "round() was not given a number",
        f"{at} you call round() on {type_name(m['t'])}. round() only works on numbers.",
    )),
    _r("TypeError", r"^(?:list|tuple|string) indices must be integers(?: or slices)?, not (?P<t>\w+)")(lambda m, at: (
        "Positions in a list or string must be whole numbers",
        f"{at} you use [ ] with {type_name(m['t'])} inside the brackets. Positions in lists, tuples "
        "and strings have to be integers (whole numbers).",
    )),
    _r("TypeError", r"^unhashable type: '(?P<t>\w+)'")(lambda m, at: (
        f"{type_name(m['t']).split(' (')[0].capitalize()} can't be used as a dictionary key or set item",
        f"{at} you use {type_name(m['t'])} as a dictionary key or put it in a set. Python only "
        "allows values that can't change for that.",
    )),
    _r("TypeError", r"^(?P<f>[\w.]+)\(\) missing (?P<n>\d+) required positional arguments?: (?P<names>.+)")(lambda m, at: (
        f"{m['f']}() was called without all the values it needs",
        f"{at} you call {m['f']}(), but it was not given a value for {m['names'].replace(chr(39), '')}.",
    )),
    _r("TypeError", r"^(?P<f>[\w.]+)\(\) takes (?P<want>\d+) positional arguments? but (?P<got>\d+) (?:was|were) given")(lambda m, at: (
        f"{m['f']}() got the wrong number of values",
        f"{at} you call {m['f']}() with {m['got']} value(s) in the brackets, but it is written to "
        f"take {m['want']}.",
    )),
    # === ValueError ===
    _r("ValueError", r"^(?P<f>max|min)\(\) (?:iterable argument is empty|arg is an empty sequence)")(lambda m, at: (
        f"{m['f']}() was given nothing to look at",
        f"{at} you call {m['f']}() on something that has no values in it at that moment, so there is no "
        f"{'biggest' if m['f'] == 'max' else 'smallest'} value for it to give back.",
    )),
    _r("ValueError", r"^invalid literal for int\(\) with base 10: (?P<v>.+)")(lambda m, at: (
        f"int() couldn't turn {m['v']} into a whole number",
        f"{at} you give int() the text {m['v']}. int() can only turn text into a number when the "
        "text is a whole number, like '42'.",
    )),
    _r("ValueError", r"^could not convert string to float: (?P<v>.+)")(lambda m, at: (
        f"float() couldn't turn {m['v']} into a number",
        f"{at} you give float() the text {m['v']}, which doesn't look like a number to Python.",
    )),
    _r("ValueError", r"^too many values to unpack \(expected (?P<n>\d+)")(lambda m, at: (
        "More values than variables",
        f"{at} you split a group of values into {m['n']} variables, but the group has more than "
        f"{m['n']} values in it.",
    )),
    _r("ValueError", r"^not enough values to unpack \(expected (?P<n>\d+), got (?P<g>\d+)\)")(lambda m, at: (
        "Fewer values than variables",
        f"{at} you split a group of values into {m['n']} variables, but the group only has "
        f"{m['g']}.",
    )),
    _r("ValueError", r"^math domain error")(lambda m, at: (
        "A maths function was given a number it can't work with",
        f"{at} a function from the math module was given a number outside the range it works for "
        "(for example the square root of a negative number).",
    )),
    # === Lookups and arithmetic ===
    _r("IndexError", r"^(?P<t>list|string|tuple|range object) index out of range")(lambda m, at: (
        f"That position doesn't exist in the {m['t'].replace(' object', '')}",
        f"{at} you ask for an item by its position with [ ], but the "
        f"{m['t'].replace(' object', '')} doesn't have an item at that position.",
    )),
    _r("IndexError", r"^pop from empty list")(lambda m, at: (
        "You took an item out of an empty list",
        f"{at} you call pop() on a list that has nothing in it.",
    )),
    _r("KeyError", r"^(?P<k>.+)$")(lambda m, at: (
        f"The dictionary has no key {m['k']}",
        f"{at} you look up {m['k']} in a dictionary, but the dictionary doesn't contain that key.",
    )),
    _r("ZeroDivisionError", r"")(lambda m, at: (
        "Your code divided by zero",
        f"{at} your code divides a number by zero, which has no answer in maths, so Python stops.",
    )),
    # === OverflowError: a number too big for what it is used in ===
    _r("OverflowError", r"Numerical result out of range|integer division result too large")(lambda m, at: (
        "The result is too big for a decimal number",
        f"{at} the calculation gives a result too big to store as a decimal number (a float). Floats "
        "have a size limit, roughly a number 309 digits long, and this result goes past it.",
    )),
    _r("OverflowError", r"^math range error")(lambda m, at: (
        "A math function's result is too big",
        f"{at} a function from the math module gives back a result too big to store as a decimal number "
        "(a float). Floats have a size limit, roughly a number 309 digits long, and this result goes past it.",
    )),
    _r("OverflowError", r"too large to convert to float")(lambda m, at: (
        "This whole number is too big to turn into a decimal",
        f"{at} a whole number (an int) has to become a decimal number (a float), but it is too big. "
        "Whole numbers in Python can be as big as you like, but floats have a size limit, roughly "
        "a number 309 digits long.",
    )),
    _r("OverflowError", r"cannot convert float (?P<what>infinity|NaN) to integer")(lambda m, at: (
        f"{'Infinity' if m['what'] == 'infinity' else 'NaN (not a number)'} can't become a whole number",
        f"{at} you turn a decimal value into a whole number, but the value is "
        f"{'infinity (inf)' if m['what'] == 'infinity' else 'NaN, which means not a number'}, and there "
        "is no whole number for that.",
    )),
    _r("OverflowError", r"too large to convert to C")(lambda m, at: (
        "This number is too big for that function",
        f"{at} you give a function a number that is bigger than it can handle, even though Python itself "
        "can store a number that big.",
    )),
    _r("RecursionError", r"")(lambda m, at: (
        "A function kept calling itself and never stopped",
        f"{at} a function calls itself, which calls itself again, and so on, until Python gave up "
        "after about a thousand calls.",
    )),
    # === Input and files ===
    _r("EOFError", r"")(lambda m, at: (
        "The program asked for input but there was none",
        f"{at} input() waits for something to be typed, but there was no input left to read. "
        "Put what you would type in the \"Input for your program\" box, one line per input().",
    )),
    _r("FileNotFoundError", r"No such file or directory: (?P<f>.+)$")(lambda m, at: (
        f"Python couldn't find the file {m['f']}",
        f"{at} your code opens the file {m['f']}, but there is no file with that name where the "
        "program runs.",
    )),
    _r("ModuleNotFoundError", r"^No module named '(?P<mod>[\w.]+)'")(lambda m, at: (
        f"Python can't find a module called {m['mod']}",
        f"{at} you import {m['mod']}, but Python has no module with that name installed.",
    )),
    _r("ImportError", r"^cannot import name '(?P<n>\w+)' from '(?P<mod>[\w.]+)'")(lambda m, at: (
        f"{m['mod']} has nothing called {m['n']}",
        f"{at} you import {m['n']} from {m['mod']}, but {m['mod']} doesn't contain anything with "
        "that name.",
    )),
    # === Syntax ===
    # Python's own suggestions first: they say the most about what went wrong.
    _r("SyntaxError", r"Perhaps you forgot a comma")(lambda m, at: (
        "Python thinks a comma (,) is missing",
        f"{at} Python found two things next to each other with nothing between them, and thinks a "
        "comma (,) may be missing, for example between the items of a list or the values inside "
        "the brackets of a function call.",
    )),
    _r("SyntaxError", r"^cannot assign to (?P<what>.+?) here\. Maybe you meant '==' instead of '='")(lambda m, at: (
        "A single = is used where Python expected a comparison",
        f"{at} there is an = with a {m['what']} on its left. A single = stores a value in a "
        "variable, so Python thinks you may have meant ==, which checks whether two values are equal.",
    )),
    _r("SyntaxError", r"Maybe you meant '==' or ':=' instead of '='")(lambda m, at: (
        "A single = is used where Python expected a comparison",
        f"{at} there is a single = in a place where Python expected a comparison, such as after if "
        "or while. A single = stores a value in a variable, while == checks whether two values are equal.",
    )),
    _r("SyntaxError", r"^Missing parentheses in call to '(?P<f>\w+)'")(lambda m, at: (
        f"{m['f']} needs round brackets",
        f"{at} you use {m['f']} without round brackets ( ). In Python 3, {m['f']} is a function, so "
        f"Python expects what comes after it to be inside brackets, like {m['f']}(...).",
    )),
    _r("SyntaxError", r"^invalid character '(?P<c>[\u2018\u2019\u201c\u201d])'")(lambda m, at: (
        "There are curly quote marks in your code",
        f"{at} there is a curly quote mark {m['c']}. This often happens when code is copied from a "
        "document or a website. Python only understands straight quote marks: \" and '.",
    )),
    _r("SyntaxError", r"^invalid character '(?P<c>.)'")(lambda m, at: (
        f"Python doesn't understand the character {m['c']}",
        f"{at} there is a character {m['c']} that Python can't read. It may look like a normal "
        "symbol but be a different character, which often happens with copied code.",
    )),
    _r("SyntaxError", r"^invalid decimal literal")(lambda m, at: (
        "A number has letters stuck to it",
        f"{at} something starts with a number and has letters straight after it (like 2nd). Python "
        "reads anything that starts with a digit as a number, and names can't start with a digit.",
    )),
    _r("SyntaxError", r"^'(?P<kw>return|yield)' outside function")(lambda m, at: (
        f"{m['kw']} is only allowed inside a function",
        f"{at} you use {m['kw']}, but Python doesn't see this line as part of any function.",
    )),
    _r("SyntaxError", r"^'(?P<kw>break|continue)' (?:outside loop|not properly in loop)")(lambda m, at: (
        f"{m['kw']} is only allowed inside a loop",
        f"{at} you use {m['kw']}, but Python doesn't see this line as part of a for or while loop.",
    )),
    _r("SyntaxError", r"^expected 'except' or 'finally' block")(lambda m, at: (
        "A try block is missing its except part",
        f"{at} Python expected an except: (or finally:) block to come after the try: block, and "
        "didn't find one.",
    )),
    _r("SyntaxError", r"^expected 'else' after 'if' expression")(lambda m, at: (
        "An if inside a value needs an else",
        f"{at} if is used inside a value on the same line (for example after =). Written that way, "
        "Python needs an else part as well.",
    )),
    _r("SyntaxError", r"^closing parenthesis '(?P<c>.)' does not match opening parenthesis '(?P<o>.)'")(lambda m, at: (
        "The brackets don't match",
        f"{at} a bracket opened with {m['o']} is closed with {m['c']}. Each bracket has to be closed "
        "by the same kind of bracket.",
    )),
    _r("SyntaxError", r"^unexpected character after line continuation character")(lambda m, at: (
        "There is something after a backslash (\\)",
        f"{at} there is a backslash \\ with more code after it on the same line. Outside of text, a "
        "backslash tells Python the line carries on onto the next line.",
    )),
    _r("SyntaxError", r"^expected argument value expression")(lambda m, at: (
        "A value is missing after =",
        f"{at} there is an = inside the brackets with no value after it.",
    )),
    _r("SyntaxError", r"^f-string: expecting '}'")(lambda m, at: (
        "A { in an f-string is never closed",
        f"{at} the f-string has an opening {{ with no matching }} after it.",
    )),
    _r("SyntaxError", r"^expected ':'")(lambda m, at: (
        "Python expected a colon (:)",
        f"{at} Python expected a colon (:), which has to end lines like if, else, for, while and "
        "def, and didn't find one where it should be.",
    )),
    _r("SyntaxError", r"^expected '\('")(lambda m, at: (
        "Python expected an opening bracket (",
        f"{at} Python was expecting an opening round bracket ( at this point and didn't find one, "
        "for example straight after a function's name on a def line.",
    )),
    _r("SyntaxError", r"^[Ee]xpected one or more names after '(?P<kw>\w+)'")(lambda m, at: (
        f"Nothing comes after {m['kw']}",
        f"{at} Python expected at least one name after {m['kw']}, but the line ends there.",
    )),
    _r("SyntaxError", r"^expected '(?P<tok>[^']+)'")(lambda m, at: (
        f"Python expected {_token_name(m['tok'])}",
        f"{at} Python was expecting {_token_name(m['tok'])} at this point and didn't find one.",
    )),
    _r("SyntaxError", r"^'(?P<b>[(\[{])' was never closed")(lambda m, at: (
        f"A bracket {m['b']} is opened but never closed",
        f"{at} there is an opening bracket {m['b']} with no matching closing bracket after it.",
    )),
    _r("SyntaxError", r"^unmatched '(?P<b>[)\]}])'")(lambda m, at: (
        f"A closing bracket {m['b']} has no opening bracket",
        f"{at} there is a closing bracket {m['b']} with no opening bracket before it.",
    )),
    _r("SyntaxError", r"^unterminated (?:triple-quoted )?string literal")(lambda m, at: (
        "A piece of text is missing its closing quote",
        f"{at} some text starts with a quote mark but doesn't have a matching quote mark to end it.",
    )),
    _r("SyntaxError", r"^cannot assign to (?P<what>.+?)(?:\s*here)?\.?(?: Maybe.*)?$")(lambda m, at: (
        f"Python can't store a value into a {m['what']}",
        f"{at} there is an = with a {m['what']} on its left. = stores the value on the right into "
        "the variable on the left, so the left side has to be a variable name.",
    )),
    _r("IndentationError", r"^expected an indented block after (?P<what>.+?) on line (?P<n>\d+)")(lambda m, at: (
        "Python expected an indented block",
        f"{at} Python expected the line to be indented (pushed in with spaces), because it comes "
        f"right after the {m['what']} on line {m['n']} and belongs inside it.",
    )),
    _r("IndentationError", r"^unexpected indent")(lambda m, at: (
        "This line is indented when Python didn't expect it",
        f"{at} the line is pushed in further than Python expected. Indentation tells Python which "
        "block a line belongs to.",
    )),
    _r("IndentationError", r"^unindent does not match any outer indentation level")(lambda m, at: (
        "The indentation doesn't line up",
        f"{at} the line is indented by an amount that doesn't line up with any of the lines above it.",
    )),
    _r("TabError", r"")(lambda m, at: (
        "Tabs and spaces are mixed",
        f"{at} the indentation mixes tab characters and spaces, and Python can't tell how far in "
        "the line is meant to be.",
    )),
]

# A general sentence for each error type, used when no specific rule matches.
_GENERAL = {
    "SyntaxError": ("Python couldn't read this line",
                    "{at} something in how the line is written doesn't follow Python's rules, so Python "
                    "couldn't understand it and didn't run any of the program."),
    "IndentationError": ("The indentation is not what Python expected",
                         "{at} the line is not indented (pushed in) the way Python expected."),
    "TypeError": ("A value is the wrong type for this",
                  "{at} your code does something with a value whose type (text, number, list, None, ...) "
                  "doesn't allow it."),
    "OverflowError": ("A number got too big",
                      "{at} a calculation produced a number too big for what it is used in."),
    "ValueError": ("A value has the right type but can't be used",
                   "{at} a function was given a value of the right type, but the value itself doesn't "
                   "make sense for it."),
    "AttributeError": ("This value doesn't have that",
                       "{at} you use a dot (.) to get something from a value, but that value doesn't have it."),
    "NameError": ("Python doesn't know this name",
                  "{at} you use a name that Python hasn't seen yet."),
    "IndexError": ("That position doesn't exist",
                   "{at} you ask for an item at a position that doesn't exist."),
    "KeyError": ("That key isn't in the dictionary",
                 "{at} you look up a key that the dictionary doesn't contain."),
}


def explain(report: ErrorReport) -> FriendlyError | None:
    """A beginner-friendly headline and explanation, or None if there is no error."""
    if report.kind == "timeout":
        return FriendlyError(
            "Your program ran for too long and was stopped",
            "It didn't finish within the time limit. A loop that never ends, or a program waiting "
            "for input it never gets, are the usual reasons.",
        )
    if not report.has_error:
        return None
    if report.kind == "logic":
        return FriendlyError(report.details.get("title", "Your output is different from what you expected"),
                             report.message or "")

    at = f"On line {report.line}," if report.line else "Somewhere in your program,"
    raw = report.message or ""
    # Syntax errors keep Python's suggestion; runtime errors lose it (see the module docstring).
    syntax = report.error_type in ("SyntaxError", "IndentationError", "TabError")
    message = raw if syntax else _clean(raw)
    for error_type, pattern, build in RULES:
        if report.error_type == error_type:
            m = pattern.search(message)
            if m:
                title, text = build(m, at)
                return FriendlyError(title, text)

    if report.error_type in _GENERAL:
        title, text = _GENERAL[report.error_type]
        return FriendlyError(title, text.format(at=at))
    return FriendlyError(
        f"Your program stopped with a {report.error_type}",
        f"{at} something went wrong while the program was running, and Python stopped it there.",
    )


def _clean(message: str) -> str:
    """Python's message without its 'Did you mean' / 'Maybe you meant' suggestions."""
    message = re.sub(r"\.?\s*(Did you mean|Maybe you meant)\b.*$", "", message)
    return message.strip()
