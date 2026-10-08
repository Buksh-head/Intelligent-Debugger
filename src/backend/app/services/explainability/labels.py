"""#74: plain-English labels for what the model looks at. Each completes
"this pointed there because of ..." and never names the model's internals.
"""
from .classifier import NUMERIC_FEATURES

# The one-hot error-type block and the TF-IDF message block each collapse
# to a single attribution; the numeric features stay individual.
ERROR_TYPE_FEATURE = "error_type"
MESSAGE_TEXT_FEATURE = "message_text"

AGGREGATE_FEATURES = (ERROR_TYPE_FEATURE, MESSAGE_TEXT_FEATURE, *NUMERIC_FEATURES)

FEATURE_LABELS = {
    ERROR_TYPE_FEATURE: "the kind of error Python reported",
    MESSAGE_TEXT_FEATURE: "the wording of the error message",
    "total_lines": "how long your program is",
    "line_number_ratio": "how far through the program the error happened",
    "num_loops": "how many loops your program has",
    "max_loop_depth": "how deeply your loops are nested",
    "num_conditionals": "how many if statements your program has",
    "num_function_defs": "how many functions your program defines",
    "has_subscript": "your program looks up an item by its position",
    "has_division": "your program divides two values",
    "mutates_during_iteration": "your program changes a list while looping over it",
    "parse_failed": "your code could not be read as valid Python",
}


# Yes/no features whose label states the thing is present. SHAP can credit
# one of these when it is absent (absence differs from the average program),
# and showing the label then would tell the student something false.
PRESENCE_FEATURES = ("has_subscript", "has_division", "mutates_during_iteration", "parse_failed")


def readable(feature: str) -> str:
    """Plain-English label for a feature, or an empty string if there is none.

    Returning nothing rather than the raw name is deliberate: a missing
    label is a bug for the coverage test to catch, not something to paper
    over by leaking ``max_loop_depth`` to a student.
    """
    return FEATURE_LABELS.get(feature, "")
