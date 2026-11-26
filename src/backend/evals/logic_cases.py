"""Sample programs with logic errors, one per known mistake. Each ran without crashing,
but prints something other than `expected`. Used by the unit tests and the live eval
(python -m evals.run_logic_eval)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LogicCase:
    id: str
    category: str      # off_by_one | recursion_base_case | calculation | missing_return
    code: str
    expected: str      # what the student expected the program to print
    stdin: str = ""
    cause_lines: tuple[int, ...] = ()  # the line(s) a student would change


CASES: list[LogicCase] = [
    LogicCase('sum-range', 'off_by_one', 'total = 0\nfor i in range(1, 5):\n    total = total + i\nprint(total)\n',
              '15\n', cause_lines=(2,)),
    LogicCase('countdown', 'off_by_one', 'n = 5\nwhile n > 1:\n    print(n)\n    n = n - 1\nprint("Liftoff!")\n',
              '5\n4\n3\n2\n1\nLiftoff!\n', cause_lines=(2,)),
    LogicCase('last-item', 'off_by_one', 'names = ["Ann", "Bo", "Cy"]\nfor i in range(len(names) - 1):\n    print(names[i])\n',
              'Ann\nBo\nCy\n', cause_lines=(2,)),
    LogicCase('evens-start', 'off_by_one', 'for i in range(2, 11, 2):\n    print(i)\n',
              '0\n2\n4\n6\n8\n10\n', cause_lines=(1,)),
    LogicCase('factorial-base', 'recursion_base_case', 'def factorial(n):\n    if n == 0:\n        return 0\n    return n * factorial(n - 1)\n\nprint(factorial(5))\n',
              '120\n', cause_lines=(2, 3)),
    LogicCase('sum-digits-base', 'recursion_base_case', 'def total(nums):\n    if len(nums) == 1:\n        return 0\n    return nums[0] + total(nums[1:])\n\nprint(total([4, 5, 6]))\n',
              '15\n', cause_lines=(2, 3)),
    LogicCase('fib-base', 'recursion_base_case', 'def fib(n):\n    if n <= 1:\n        return 1\n    return fib(n - 1) + fib(n - 2)\n\nfor i in range(6):\n    print(fib(i))\n',
              '0\n1\n1\n2\n3\n5\n', cause_lines=(2, 3)),
    LogicCase('average-precedence', 'calculation', 'a = 4\nb = 8\naverage = a + b / 2\nprint(average)\n',
              '6.0\n', cause_lines=(3,)),
    LogicCase('int-division', 'calculation', 'marks = [7, 8, 8]\naverage = sum(marks) // len(marks)\nprint("Average:", average)\n',
              'Average: 7.666666666666667\n', cause_lines=(2,)),
    LogicCase('fahrenheit', 'calculation', 'c = float(input("Celsius: "))\nf = c * 9 / 5 + 23\nprint(f)\n',
              '212.0\n', stdin='100\n', cause_lines=(2,)),
    LogicCase('no-return', 'missing_return', 'def area(w, h):\n    result = w * h\n\nprint(area(3, 4))\n',
              '12\n', cause_lines=(1, 2)),
    LogicCase('squares', 'off_by_one', 'n = 4\nfor i in range(1, n):\n    print(i * i)\n',
              '1\n4\n9\n16\n', cause_lines=(2,)),
    LogicCase('last-letter', 'off_by_one', 'word = "hello"\nprint(word[len(word) - 2])\n',
              'o\n', cause_lines=(2,)),
    LogicCase('while-sum', 'off_by_one', 'total = 0\ni = 1\nwhile i < 10:\n    total += i\n    i += 1\nprint("Sum of 1 to 10 is", total)\n',
              'Sum of 1 to 10 is 55\n', cause_lines=(3,)),
    LogicCase('power-base', 'recursion_base_case', 'def power(b, e):\n    if e == 1:\n        return 1\n    return b * power(b, e - 1)\n\nprint(power(2, 3))\n',
              '8\n', cause_lines=(2, 3)),
    LogicCase('rec-countdown', 'recursion_base_case', 'def countdown(n):\n    if n == 1:\n        return\n    print(n)\n    countdown(n - 1)\n\ncountdown(3)\n',
              '3\n2\n1\n', cause_lines=(2, 3)),
    LogicCase('count-down-list', 'recursion_base_case', 'def length(items):\n    if items == []:\n        return 1\n    return 1 + length(items[1:])\n\nprint(length([3, 1, 4]))\n',
              '3\n', cause_lines=(2, 3)),
    LogicCase('percent', 'calculation', 'score = 17\ntotal = 20\nprint(score / total * 10)\n',
              '85.0\n', cause_lines=(3,)),
    LogicCase('circle-area', 'calculation', 'r = float(input("Radius: "))\narea = 2 * 3.14 * r\nprint("Area:", area)\n',
              'Area: 78.5\n', stdin='5\n', cause_lines=(2,)),
    LogicCase('discount', 'calculation', 'price = 80\ndiscount = 25\nprint(price - price * discount / 10)\n',
              '60.0\n', cause_lines=(3,)),
    LogicCase('double-return', 'missing_return', 'def double(x):\n    print(x * 2)\n\nresult = double(7)\nprint("Result:", result)\n',
              'Result: 14\n', cause_lines=(1, 2)),
    LogicCase('table', 'off_by_one', 'for i in range(1, 10):\n    print(3, "x", i, "=", 3 * i)\n',
              '3 x 1 = 3\n3 x 2 = 6\n3 x 3 = 9\n3 x 4 = 12\n3 x 5 = 15\n3 x 6 = 18\n3 x 7 = 21\n3 x 8 = 24\n3 x 9 = 27\n3 x 10 = 30\n', cause_lines=(1,)),
    LogicCase('first-item', 'off_by_one', 'scores = [9, 7, 5]\nfor i in range(1, len(scores)):\n    print(scores[i])\n',
              '9\n7\n5\n', cause_lines=(2,)),
    LogicCase('sum-list-rec', 'recursion_base_case', 'def add_all(nums):\n    if len(nums) == 0:\n        return nums[0] if nums else 1\n    return nums[0] + add_all(nums[1:])\n\nprint(add_all([1, 2, 3]))\n',
              '6\n', cause_lines=(2, 3)),
    LogicCase('palindrome-rec', 'recursion_base_case', 'def is_pal(s):\n    if len(s) == 0:\n        return False\n    if s[0] != s[-1]:\n        return False\n    return is_pal(s[1:-1])\n\nprint(is_pal("racecar"))\n',
              'True\n', cause_lines=(2, 3)),
    LogicCase('bmi', 'calculation', 'weight = 70\nheight = 1.75\nbmi = weight / height * 2\nprint(round(bmi, 1))\n',
              '22.9\n', cause_lines=(3,)),
    LogicCase('minutes', 'calculation', 'seconds = 150\nminutes = seconds % 60\nprint(minutes, "minutes")\n',
              '2 minutes\n', cause_lines=(2,)),
]
