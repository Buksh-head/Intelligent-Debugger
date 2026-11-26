"""Common first-year Python mistakes, used by the tests and the live eval.

cause_line is where the mistake really is (which is not always where Python
stopped). must_not_say lists words that would give the fix away.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Case:
    id: str
    code: str
    error_type: str
    error_line: int | None
    cause_line: int | None
    must_not_say: tuple[str, ...] = ()
    stdin: str = ""
    note: str = ""


CASES: list[Case] = [
    Case("str-isvowel", 'word = input("Enter a letter: ")\n\nif word.isvowel():\n    print("vowel")\nelse:\n    print("not a vowel")\n',
         "AttributeError", 3, 3, ("in \"aeiou\"", "aeiou", "in "), stdin="a\n",
         note="The example from the brief: isvowel is not a str method."),
    Case("str-append", 'name = "sam"\nname.append("!")\nprint(name)\n',
         "AttributeError", 2, 2, ("+", "concatenat", "join")),
    Case("name-typo", 'total = 0\nfor n in [1, 2, 3]:\n    total = total + n\nprint(totl)\n',
         "NameError", 4, 4, ("total",)),
    Case("input-is-str", 'age = input("How old are you? ")\nnext_year = age + 1\nprint(next_year)\n',
         "TypeError", 2, 1, ("int(", "int", "convert"), stdin="18\n",
         note="Python stops on line 2 but the misunderstanding is about what input() on line 1 returns."),
    Case("off-by-one", 'scores = [70, 85, 90]\nfor i in range(len(scores) + 1):\n    print(scores[i])\n',
         "IndexError", 3, 2, ("- 1", "remove the + 1", "len(scores))")),
    Case("sort-returns-none", 'nums = [3, 1, 2]\nordered = nums.sort()\nprint(ordered[0])\n',
         "TypeError", 3, 2, ("sorted",)),
    Case("missing-return", 'def add(a, b):\n    a + b\n\ntotal = add(2, 3) + 1\nprint(total)\n',
         "TypeError", 4, 2, ("return",)),
    Case("assign-in-if", 'x = 5\nif x = 5:\n    print("five")\n',
         "SyntaxError", 2, 2, ("==",)),
    Case("missing-colon", 'def greet(name)\n    print("Hi", name)\n\ngreet("Ana")\n',
         "SyntaxError", 1, 1, ("colon", ":")),
    Case("bad-indent", 'def greet(name):\nprint("Hi", name)\n\ngreet("Ana")\n',
         "IndentationError", 2, 2, ("indent it", "four spaces")),
    Case("key-case", 'student = {"name": "Li", "mark": 81}\nprint(student["Name"])\n',
         "KeyError", 2, 2, ('"name"', "lowercase", "lower-case")),
    Case("empty-average", 'marks = []\naverage = sum(marks) / len(marks)\nprint(average)\n',
         "ZeroDivisionError", 2, 2, ("if marks", "if len")),
    Case("unbound-counter", 'count = 0\n\ndef bump():\n    count += 1\n\nbump()\nprint(count)\n',
         "UnboundLocalError", 4, 4, ("global", "nonlocal", "parameter", "return")),
    Case("int-of-float-str", 'price = "3.50"\ncents = int(price) * 100\nprint(cents)\n',
         "ValueError", 2, 2, ("float",)),
    Case("list-call", 'nums = [4, 5, 6]\nprint(nums(0))\n',
         "TypeError", 2, 2, ("square bracket", "[0]", "[")),
    Case("math-attr", 'import math\nprint(math.sqroot(16))\n',
         "AttributeError", 2, 2, ("sqrt",)),
    Case("no-base-case", 'def countdown(n):\n    print(n)\n    countdown(n - 1)\n\ncountdown(3)\n',
         "RecursionError", 3, 1, ("base case", "if n")),
    Case("infinite-loop", 'i = 0\nwhile i < 5:\n    print(i)\n',
         "Timeout", None, 2, ("i += 1", "increment", "i = i + 1")),
    Case("used-up-generator",
         'squares = (x * x for x in range(5))\n\nprint("Sum:", sum(squares))\nprint("Max:", max(squares))\n',
         "ValueError", 4, 1, ("list(", "square brackets", "list comprehension")),
]
