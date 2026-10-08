"""#75: DiCE counterfactuals rendered as Socratic questions, or nothing.

Only some features may vary, booleans are categorical, and templates exist
only for removing a trait, never adding one, so a question can't suggest
introducing a bug. Below the confidence gate nothing renders.
"""
import contextlib
import io
import logging

import dice_ml
import numpy as np
import pandas as pd
from dice_ml import Dice

# dice-ml raises this via raiutils, not from its own exception module.
from raiutils.exceptions import UserConfigValidationException

from .features import extract_features

logger = logging.getLogger(__name__)

# Below this the prediction is not solid enough to build a question on.
# The model's own collision accuracy is 0.538, so anything at or under a
# coin flip must stay silent.
CONFIDENCE_GATE = 0.55

# Yes/no facts about the code. Categorical, so DiCE proposes flips rather
# than fractions.
BOOLEAN_FEATURES = ["has_subscript", "has_division", "mutates_during_iteration", "parse_failed"]

COUNT_FEATURES = [
    "total_lines", "num_loops", "max_loop_depth", "num_conditionals", "num_function_defs",
]

CONTINUOUS_FEATURES = [*COUNT_FEATURES, "line_number_ratio"]

# The only features worth asking a student about. Everything else is
# arbitrary, a consequence rather than a cause, or not a choice.
#
# Order is deliberate and is the order _render considers them in: most
# diagnostic first. Mutating a list mid-loop names one specific mistake;
# "how many loops" could describe almost any program. DiCE frequently
# changes several at once, so without this the question would be decided
# by list position rather than by which change means anything.
FEATURES_TO_VARY = [
    "mutates_during_iteration",
    "has_division",
    "has_subscript",
    "max_loop_depth",
    "num_conditionals",
    "num_loops",
]

# Some templates only make sense for certain starting values. Without this
# a program with one flat loop gets asked about "the inner loop", which
# describes a program the student is not looking at.
TEMPLATE_PRECONDITIONS = {
    ("max_loop_depth", "decrease"): lambda before: float(before) >= 2,
    ("num_loops", "decrease"): lambda before: float(before) >= 2,
    ("num_conditionals", "decrease"): lambda before: float(before) >= 2,
}

ALL_FEATURES = [*CONTINUOUS_FEATURES, *BOOLEAN_FEATURES]

# (feature, direction) -> question. Only "decrease" exists: these describe
# a program with *less* of a trait, never one with more.
QUESTION_TEMPLATES = {
    ("mutates_during_iteration", "decrease"):
        "What would be different about this loop if the list stayed the same "
        "length the whole way through it?",
    ("max_loop_depth", "decrease"):
        "What would have to be true for the inner loop to finish on its own?",
    ("num_loops", "decrease"):
        "Which part of this repetition is doing work that has already been done?",
    ("has_subscript", "decrease"):
        "What would change if you reached each item directly, rather than by "
        "its position?",
    ("has_division", "decrease"):
        "What would you want to know about the number you are dividing by, "
        "before dividing by it?",
    ("num_conditionals", "decrease"):
        "Which of these conditions can already be ruled out by the time the "
        "program reaches them?",
}

TOTAL_CANDIDATES = 5
SEED = 42


class CounterfactualExplainer:
    """Produces one Socratic question, or None. Never raises."""

    def __init__(self, pipeline, background: pd.DataFrame):
        self.pipeline = pipeline
        self.classes = list(pipeline.classes_)
        self._background = self._as_dice_frame(background)

    @staticmethod
    def _as_dice_frame(frame: pd.DataFrame) -> pd.DataFrame:
        """DiCE wants ints and strings, not numpy bools."""
        out = frame[ALL_FEATURES].copy()
        for column in BOOLEAN_FEATURES:
            out[column] = out[column].astype(int).astype(str)
        for column in COUNT_FEATURES:
            out[column] = out[column].astype(int)
        out["line_number_ratio"] = out["line_number_ratio"].astype(float)
        return out

    @staticmethod
    def _restore_context(frame: pd.DataFrame, error_type: str, message: str) -> pd.DataFrame:
        restored = frame[ALL_FEATURES].copy()
        for column in BOOLEAN_FEATURES:
            restored[column] = restored[column].astype(int).astype(bool)
        restored["error_type"] = error_type
        restored["message"] = message
        return restored

    def _wrapped_model(self, error_type: str, message: str, class_index: int):
        """A binary "is it still this class" view of the multiclass pipeline.

        DiCE works over the structured features only, so the error type and
        message are pinned to the submission being explained and reinserted
        on every call. The counterfactual therefore asks what would have to
        change about the *code*, which is the only thing the student
        controls anyway.
        """
        pipeline = self.pipeline

        class Wrapped:
            def predict_proba(self, rows):
                frame = pd.DataFrame(rows, columns=ALL_FEATURES).copy()
                for column in BOOLEAN_FEATURES:
                    frame[column] = frame[column].astype(int).astype(bool)
                frame["error_type"] = error_type
                frame["message"] = message
                towards = pipeline.predict_proba(frame)[:, class_index]
                return np.column_stack([1 - towards, towards])

        return Wrapped()

    @staticmethod
    def _direction(before, after) -> str | None:
        try:
            return "decrease" if float(after) < float(before) else "increase"
        except (TypeError, ValueError):
            return None

    def _render(self, original: pd.Series, counterfactual: pd.Series) -> str | None:
        """Turn the first safe change into a question, or return nothing.

        Only one change is rendered even when DiCE returns several. Two
        questions at once reads as a checklist, which is the imperative
        framing this ticket exists to avoid.
        """
        for feature in FEATURES_TO_VARY:
            before, after = original[feature], counterfactual[feature]
            if str(before) == str(after):
                continue

            key = (feature, self._direction(before, after))
            question = QUESTION_TEMPLATES.get(key)
            if not question:
                continue

            precondition = TEMPLATE_PRECONDITIONS.get(key)
            if precondition is not None and not precondition(before):
                continue

            return question
        return None

    def question(
        self,
        code: str,
        error_type: str,
        message: str,
        timed_out: bool,
        confidence: float,
    ) -> str | None:
        if confidence < CONFIDENCE_GATE:
            return None

        try:
            features = extract_features(code, error_type, timed_out)
            features["message"] = message
            row = pd.DataFrame([features])
            predicted = self.pipeline.predict(row)[0]
            class_index = self.classes.index(predicted)

            data = self._background.copy()
            data["outcome"] = (
                self.pipeline.predict(self._restore_context(data, error_type, message))
                == predicted
            ).astype(int)

            dice_data = dice_ml.Data(
                dataframe=data,
                continuous_features=CONTINUOUS_FEATURES,
                outcome_name="outcome",
            )
            dice_model = dice_ml.Model(
                model=self._wrapped_model(error_type, message, class_index),
                backend="sklearn",
                model_type="classifier",
            )

            query = self._as_dice_frame(row)
            # DiCE writes "no counterfactuals found" to stdout and a tqdm
            # progress bar to stderr, neither through logging, and
            # verbose=False stops neither. Unredirected, an ordinary outcome
            # becomes a wall of server log noise.
            #
            # Safe to silence both: this suppresses only what those streams
            # are *printed* to. Exceptions still propagate to the handlers
            # below, and anything we actually want recorded goes via logger.
            with (
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                results = Dice(dice_data, dice_model, method="random").generate_counterfactuals(
                    query,
                    total_CFs=TOTAL_CANDIDATES,
                    desired_class="opposite",
                    features_to_vary=FEATURES_TO_VARY,
                    random_seed=SEED,
                    verbose=False,
                )
            candidates = results.cf_examples_list[0].final_cfs_df
            if candidates is None or not len(candidates):
                return None

            original = query.iloc[0]
            # Sparsest first: the fewest changed features is the closest
            # thing DiCE gives us to a single reason.
            ordered = sorted(
                (candidates.iloc[i] for i in range(len(candidates))),
                key=lambda cf: sum(str(original[f]) != str(cf[f]) for f in FEATURES_TO_VARY),
            )
            for candidate in ordered:
                if question := self._render(original, candidate):
                    return question
            return None
        except UserConfigValidationException:
            # DiCE raises this when the search finds nothing within the
            # allowed feature ranges. That is an ordinary outcome for a
            # prediction with no nearby boundary, not a fault, and the
            # student simply gets no question.
            logger.debug(f"No counterfactual within range for error_type={error_type}")
            return None
        except Exception as e:
            logger.error(f"Counterfactual generation failed for error_type={error_type}: {e}")
            return None
