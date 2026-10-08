"""#74: per-feature attributions for one prediction, via SHAP and LIME.

The 244 transformed columns are summed back into readable features: one for
the error type, one for the message wording, and one per code feature.
SHAP is served, computed directly as coef x (x - mean), which equals
shap.LinearExplainer for this model (checked in test_attribution_explainer.py)
so shap is not a runtime dependency. LIME is an offline cross-check, imported
only when called.
"""
import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .features import extract_features
from .labels import ERROR_TYPE_FEATURE, FEATURE_LABELS, MESSAGE_TEXT_FEATURE, PRESENCE_FEATURES

logger = logging.getLogger(__name__)

DEFAULT_TOP_N = 3

# The error the student can already read on screen. Honest attributions,
# but not an explanation of anything they did not already know.
CONTEXT_FEATURES = frozenset({ERROR_TYPE_FEATURE, MESSAGE_TEXT_FEATURE})

# LIME's default is 5000. The surrogate is fitting a linear function, so it
# converges long before then, and LIME is a cross-check rather than served.
LIME_SAMPLES = 1000

SEED = 42


@dataclass(frozen=True)
class Attribution:
    """One thing that pushed the prediction towards the label it chose."""

    feature: str
    label: str
    weight: float


class AttributionExplainer:
    """Explains one prediction. Never raises; returns [] when it cannot."""

    def __init__(self, pipeline, background: pd.DataFrame):
        self.pipeline = pipeline
        self.classes = list(pipeline.classes_)
        self._preprocess = pipeline.named_steps["preprocess"]
        self._model = pipeline.named_steps["clf"]

        transformed_background = self._transform(background)
        self._column_blocks = self._build_column_blocks()

        # Linear SHAP against the whole background: coef x (x - mean).
        self._background_mean = transformed_background.mean(axis=0)
        self._lime_background = transformed_background

    # ----------------------------------------------------------------- setup

    def _build_column_blocks(self) -> dict[str, list[int]]:
        """Map each reported feature to the transformed columns it covers."""
        blocks: dict[str, list[int]] = {}
        for index, name in enumerate(self._preprocess.get_feature_names_out()):
            if name.startswith("cat__"):
                key = ERROR_TYPE_FEATURE
            elif name.startswith("text__"):
                key = MESSAGE_TEXT_FEATURE
            else:
                key = name.removeprefix("num__")
            blocks.setdefault(key, []).append(index)
        return blocks

    def _transform(self, frame: pd.DataFrame) -> np.ndarray:
        transformed = self._preprocess.transform(frame)
        return transformed.toarray() if hasattr(transformed, "toarray") else transformed

    @staticmethod
    def _frame(code: str, error_type: str, message: str, timed_out: bool) -> pd.DataFrame:
        features = extract_features(code, error_type, timed_out)
        features["message"] = message
        return pd.DataFrame([features])

    # ------------------------------------------------------------ attribution

    def _aggregate(
        self,
        per_column: np.ndarray,
        top_n: int,
        code_features_only: bool = False,
        absent: frozenset[str] = frozenset(),
    ) -> list[Attribution]:
        """Sum column weights into reported features, strongest first.

        Only positive contributions survive. The panel presents these as
        "what pointed there", and a feature that pushed the prediction away
        from the chosen label did not point there.
        """
        totals = {
            feature: float(per_column[columns].sum())
            for feature, columns in self._column_blocks.items()
            if not (code_features_only and feature in CONTEXT_FEATURES) and feature not in absent
        }
        return [
            Attribution(feature=feature, label=FEATURE_LABELS[feature], weight=weight)
            for feature, weight in sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
            if weight > 0
        ][:top_n]

    def _class_index(self, frame: pd.DataFrame) -> int:
        return self.classes.index(self.pipeline.predict(frame)[0])

    def attributions(
        self,
        code: str,
        error_type: str,
        message: str,
        timed_out: bool,
        top_n: int = DEFAULT_TOP_N,
        code_features_only: bool = False,
    ) -> list[Attribution]:
        """SHAP attributions towards the predicted label. The served path."""
        try:
            frame = self._frame(code, error_type, message, timed_out)
            transformed = self._transform(frame)
            class_index = self._class_index(frame)

            values = self.shap_values(transformed[0], class_index)
            absent = frozenset(f for f in PRESENCE_FEATURES if not frame[f].iloc[0])
            return self._aggregate(values, top_n, code_features_only, absent)
        except Exception as e:
            logger.error(f"SHAP attribution failed for error_type={error_type}: {e}")
            return []

    def shap_values(self, row: np.ndarray, class_index: int) -> np.ndarray:
        """Exact linear SHAP values of one transformed row towards one class."""
        return self._model.coef_[class_index] * (row - self._background_mean)

    def lime_attributions(
        self,
        code: str,
        error_type: str,
        message: str,
        timed_out: bool,
        top_n: int = DEFAULT_TOP_N,
    ) -> list[Attribution]:
        """LIME attributions, as a cross-check on SHAP rather than a second opinion.

        Built per call rather than once at construction: LIME keeps the
        instance being explained in its own state, so a shared explainer
        would not be safe across concurrent requests. It is off the request
        path, so the cost does not matter.
        """
        try:
            from lime.lime_tabular import LimeTabularExplainer

            frame = self._frame(code, error_type, message, timed_out)
            transformed = self._transform(frame)
            class_index = self._class_index(frame)

            explainer = LimeTabularExplainer(
                self._lime_background,
                mode="classification",
                feature_names=list(self._preprocess.get_feature_names_out()),
                class_names=self.classes,
                # The transformed space holds TF-IDF weights and counts, not
                # quantiles; discretising them invents bins that mean nothing.
                discretize_continuous=False,
                random_state=SEED,
            )
            explanation = explainer.explain_instance(
                transformed[0],
                self._model.predict_proba,
                labels=(class_index,),
                num_features=transformed.shape[1],
                num_samples=LIME_SAMPLES,
            )

            per_column = np.zeros(transformed.shape[1])
            for column, weight in explanation.as_map()[class_index]:
                per_column[column] = weight
            return self._aggregate(per_column, top_n)
        except Exception as e:
            logger.error(f"LIME attribution failed for error_type={error_type}: {e}")
            return []
