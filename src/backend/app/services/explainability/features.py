"""AST and execution feature extraction for the misconception classifier (#72).

Submitted code is parsed, never executed, same rule as the static analysis
processor in #7. Runtime behaviour comes from the sandbox, not from here.

Feature order in ``FEATURE_NAMES`` is part of the contract: SHAP and DiCE both
index features by position, so appending is safe but reordering is not.
"""
import ast

FEATURE_NAMES = (
    "error_type",
    "timed_out",
    "total_lines",
    "line_number_ratio",
    "num_loops",
    "max_loop_depth",
    "num_conditionals",
    "num_function_defs",
    "has_subscript",
    "has_division",
    "mutates_during_iteration",
    "parse_failed",
)

# Methods that change a collection in place. Covers list, dict and set.
_MUTATING_METHODS = frozenset({
    "append", "extend", "insert", "remove", "pop", "clear",
    "add", "discard", "update", "popitem", "setdefault",
})

# Modulo is included because it raises ZeroDivisionError just as division does.
_DIVISION_OPS = (ast.Div, ast.FloorDiv, ast.Mod)


def _iterated_name(node: ast.For) -> str | None:
    """Name of the collection a ``for`` loop walks over, if it is a plain name.

    Recognises the shapes that can go wrong: ``for x in nums``,
    ``for i in range(len(nums))``, ``for i, x in enumerate(nums)``,
    ``for x in reversed(nums)``, and ``for k in d.keys()``.

    Deliberately returns None for ``for x in list(nums)`` and
    ``sorted(nums)``, which iterate a copy and are the correct way to mutate
    while looping. Flagging those would punish working code.
    """
    iterated = node.iter

    if isinstance(iterated, ast.Name):
        return iterated.id

    if isinstance(iterated, ast.Call):
        func = iterated.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            return func.value.id
        # enumerate() and reversed() walk the original, unlike list()/sorted().
        if (
            isinstance(func, ast.Name)
            and func.id in ("enumerate", "reversed")
            and iterated.args
            and isinstance(iterated.args[0], ast.Name)
        ):
            return iterated.args[0].id
        if isinstance(func, ast.Name) and func.id == "range":
            for inner in ast.walk(iterated):
                if (
                    isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Name)
                    and inner.func.id == "len"
                    and inner.args
                    and isinstance(inner.args[0], ast.Name)
                ):
                    return inner.args[0].id

    return None


def _targets_name(targets, name: str) -> bool:
    return any(
        isinstance(target, ast.Subscript)
        and isinstance(target.value, ast.Name)
        and target.value.id == name
        for target in targets
    )


def _mutates(name: str, body: list) -> bool:
    """Whether ``body`` changes the collection called ``name`` in place."""
    for statement in body:
        for node in ast.walk(statement):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in _MUTATING_METHODS
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == name
            ):
                return True
            if isinstance(node, ast.Delete) and _targets_name(node.targets, name):
                return True
            if isinstance(node, ast.Assign) and _targets_name(node.targets, name):
                return True
    return False


class _Analyser(ast.NodeVisitor):
    def __init__(self):
        self.num_loops = 0
        self.max_loop_depth = 0
        self.num_conditionals = 0
        self.num_function_defs = 0
        self.has_subscript = False
        self.has_division = False
        self.mutates_during_iteration = False
        self._depth = 0

    def _visit_loop(self, node):
        self.num_loops += 1
        self._depth += 1
        self.max_loop_depth = max(self.max_loop_depth, self._depth)

        if isinstance(node, (ast.For, ast.AsyncFor)):
            name = _iterated_name(node)
            if name and _mutates(name, node.body):
                self.mutates_during_iteration = True

        self.generic_visit(node)
        self._depth -= 1

    visit_For = _visit_loop
    visit_AsyncFor = _visit_loop
    visit_While = _visit_loop

    def visit_If(self, node):
        self.num_conditionals += 1
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self.num_function_defs += 1
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Subscript(self, node):
        self.has_subscript = True
        self.generic_visit(node)

    def visit_BinOp(self, node):
        if isinstance(node.op, _DIVISION_OPS):
            self.has_division = True
        self.generic_visit(node)

    def visit_AugAssign(self, node):
        if isinstance(node.op, _DIVISION_OPS):
            self.has_division = True
        self.generic_visit(node)


def extract_features(
    code: str,
    error_type: str,
    timed_out: bool = False,
    line_number: int | None = None,
) -> dict:
    """Turn a submission into the classifier's feature record.

    Unparseable code returns a valid record flagged ``parse_failed`` rather than
    raising: a syntax error is itself a misconception worth classifying, so it
    must not take the pipeline down.
    """
    total_lines = len(code.splitlines())
    ratio = line_number / total_lines if line_number and total_lines else 0.0

    analyser = _Analyser()
    try:
        tree = ast.parse(code)
    except SyntaxError:
        parse_failed = True
    else:
        parse_failed = False
        analyser.visit(tree)

    return {
        "error_type": error_type,
        "timed_out": timed_out,
        "total_lines": total_lines,
        "line_number_ratio": ratio,
        "num_loops": analyser.num_loops,
        "max_loop_depth": analyser.max_loop_depth,
        "num_conditionals": analyser.num_conditionals,
        "num_function_defs": analyser.num_function_defs,
        "has_subscript": analyser.has_subscript,
        "has_division": analyser.has_division,
        "mutates_during_iteration": analyser.mutates_during_iteration,
        "parse_failed": parse_failed,
    }
