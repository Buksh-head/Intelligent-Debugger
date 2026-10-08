"""#76: builds the explanation object the API returns.

Built lazily and once. Any failure returns None so the answer still ships;
nothing here may raise into the request path.
"""
import logging
import threading
from pathlib import Path

from app.models import Attribution, Explanation

from .classifier import MisconceptionClassifier, build_feature_frame, load_dataset, load_pipeline
from .explainer import AttributionExplainer

logger = logging.getLogger(__name__)

ARTIFACT_PATH = Path(__file__).resolve().parent / "artifacts" / "classifier.joblib"

_service: "ExplanationService | None" = None
_lock = threading.Lock()
_load_failed = False


class ExplanationService:
    """Holds the fitted pipeline and the three explainers."""

    def __init__(self, pipeline, background):
        self._pipeline = pipeline
        self._background = background
        self._counterfactuals = None
        self.classifier = MisconceptionClassifier(pipeline)
        self.attributions = AttributionExplainer(
            pipeline, background=background.drop(columns=["misconception_label"])
        )

    @property
    def counterfactuals(self):
        """Built on first use: DiCE (dice-ml, ~430MB with xgboost) is a dev
        dependency, and the served Socratic path never asks for it."""
        if self._counterfactuals is None:
            from .counterfactual import CounterfactualExplainer

            self._counterfactuals = CounterfactualExplainer(self._pipeline, background=self._background)
        return self._counterfactuals

    def explain(
        self,
        code: str,
        error_type: str,
        message: str,
        timed_out: bool,
        reasoning: str = "",
        include_counterfactual: bool = True,
    ) -> Explanation:
        probabilities = self.classifier.predict_proba(
            code=code, error_type=error_type, message=message, timed_out=timed_out
        )
        misconception = max(probabilities, key=probabilities.get)
        confidence = probabilities[misconception]

        # Code features only: SHAP ranks the error type and message wording
        # top almost every time, and the student just read both on screen.
        attributions = self.attributions.attributions(
            code=code,
            error_type=error_type,
            message=message,
            timed_out=timed_out,
            code_features_only=True,
        )

        return Explanation(
            reasoning=reasoning or None,
            misconception=misconception,
            confidence=confidence,
            attributions=[
                Attribution(feature=a.feature, label=a.label, weight=a.weight)
                for a in attributions
            ]
            or None,
            # Measured at 88ms of the 91ms an explanation costs, against
            # 1.6ms for the classifier and 3ms for SHAP. Socratic mode hides
            # the question, so generating it there would spend 97% of the
            # budget on output nobody sees and put a field on the response
            # that the client is committed to ignoring.
            counterfactual_question=(
                self.counterfactuals.question(
                    code=code,
                    error_type=error_type,
                    message=message,
                    timed_out=timed_out,
                    confidence=confidence,
                )
                if include_counterfactual
                else None
            ),
        )


def _get_service() -> ExplanationService | None:
    """Build the service once, or give up permanently and say so once.

    ``_load_failed`` latches so a missing or unreadable artifact does not
    retry on every hint request, and does not repeat the same error line
    in the log for every student who asks for a hint.
    """
    global _service, _load_failed

    if _service is not None or _load_failed:
        return _service

    with _lock:
        if _service is not None or _load_failed:
            return _service
        try:
            pipeline = load_pipeline(ARTIFACT_PATH)
            background = build_feature_frame(load_dataset())
            _service = ExplanationService(pipeline, background)
            logger.info("Explanation service ready")
        except Exception as e:
            _load_failed = True
            logger.error(
                f"Explanation service unavailable, hints will ship without one: {e}"
            )
    return _service


def build_explanation(
    code: str,
    error_type: str,
    message: str,
    timed_out: bool,
    reasoning: str = "",
    include_counterfactual: bool = True,
) -> Explanation | None:
    """The API's entry point. Returns None rather than raising, always."""
    service = _get_service()
    if service is None:
        return None
    try:
        return service.explain(
            code=code,
            error_type=error_type,
            message=message,
            timed_out=timed_out,
            reasoning=reasoning,
            include_counterfactual=include_counterfactual,
        )
    except Exception as e:
        logger.error(f"Explanation failed for error_type={error_type}: {e}")
        return None
