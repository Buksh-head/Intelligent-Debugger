"""#73: the misconception classifier, training, evaluation and serving.

Trained once by ``trainer.py`` into a joblib artifact and loaded at serving
time, so a request never pays for a fit. The model exists because SHAP,
LIME and DiCE explain models rather than hosted LLM calls; see
docs/decisions/features/explainable-socratic-hints.md.
"""
import json
import logging
import joblib
import pandas as pd
from pathlib import Path
from .features import extract_features
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

logger = logging.getLogger(__name__)

DEFAULT_DATA_PATH = Path(__file__).resolve().parent / "data" / "misconceptions.jsonl"

# The ten numeric columns of features.FEATURE_NAMES. The other two are
# deliberately absent: "error_type" is one-hot encoded separately below, and
# "timed_out" is identical to (error_type == "TimeoutError") on every row of
# the dataset, so it carries no information the encoder does not already have.
NUMERIC_FEATURES = [
    "total_lines", "line_number_ratio", "num_loops", "max_loop_depth",
    "num_conditionals", "num_function_defs", "has_subscript",
    "has_division", "mutates_during_iteration", "parse_failed",
]

def build_feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    records = [
        extract_features(row.code, row.error_type, row.timed_out)
        for row in df.itertuples()
    ]
    engineered = pd.DataFrame(records, index=df.index).drop(columns=["error_type", "timed_out"])
    return pd.concat([df, engineered], axis=1)

def load_dataset(path: Path = DEFAULT_DATA_PATH) -> pd.DataFrame:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f,start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{line_no} is not valid JSON") from e
    return pd.DataFrame(rows)

def build_pipeline(random_state:int) -> Pipeline:
    preprocessor = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore"), ["error_type"]),
            ("text", TfidfVectorizer(), "message"),
            ("num", "passthrough", NUMERIC_FEATURES),
        ],
        remainder="drop"
    )

    return Pipeline(steps=[
        ("preprocess", preprocessor),
        ("clf", LogisticRegression(max_iter=1000, random_state=random_state))
    ])

def train_test_split_data(df, test_size, random_state):
    X = df.drop(columns=["misconception_label"])
    y = df["misconception_label"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=test_size,
        random_state=random_state,
        stratify=y,
    )

    ambiguous_test = X_test["ambiguous"]
    return X_train, X_test, y_train, y_test, ambiguous_test

def fit_pipeline(pipeline, X_train, y_train):
    pipeline.fit(X_train, y_train)
    return pipeline

def evaluate(pipeline : Pipeline, X_train, y_train, X_test, y_test, ambiguous_mask, collision_test_mask, full_df) -> dict:
    headline_preds = pipeline.predict(X_test)
    headline_accuracy = accuracy_score(y_test, headline_preds)

    X_amb = X_test[ambiguous_mask]
    y_amb = y_test[ambiguous_mask]
    amb_preds = pipeline.predict(X_amb)
    ambiguous_correct = int((amb_preds == y_amb).sum())

    X_col = X_test[collision_test_mask]
    y_col = y_test[collision_test_mask]
    col_preds = pipeline.predict(X_col)
    collision_accuracy = accuracy_score(y_col, col_preds) if len(y_col) else None

    return{
        "headline_accuracy": float(headline_accuracy),
        "headline_n": int(len(y_test)),
        "ambiguous_accuracy": ambiguous_correct/len(y_amb) if len(y_amb) else None,
        "ambiguous_n": int(len(y_amb)),
        "collision_accuracy": collision_accuracy,
        "collision_n": int(len(y_col)),
        "held_out_lookup_baseline_accuracy": held_out_lookup_baseline_accuracy(X_train, y_train, X_test, y_test)
    }

def save_pipeline(pipeline, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, path)

def load_pipeline(path: Path) -> Pipeline:
    return joblib.load(path)

def held_out_lookup_baseline_accuracy(X_train, y_train, X_test, y_test) -> float:
    """Accuracy of "predict the most common label for this exact message".

    Fitted on the training rows only and scored on the test rows, so it is
    comparable with the model's own test accuracy. Fitting and scoring the
    lookup on the same rows measures memorisation, not baseline skill, and
    produces a number roughly twice as high.

    A test message never seen in training maps to NaN, which counts as
    wrong, that is the honest outcome, and it is most of the gap between
    this baseline and the model.
    """
    train_df = X_train.copy()
    train_df["misconception_label"] = y_train
    majority_by_message = train_df.groupby("message")["misconception_label"].agg(
        lambda labels: labels.value_counts().idxmax()
    )
    predicted = X_test["message"].map(majority_by_message)
    return float((predicted == y_test).mean())


def collision_mask(df: pd.DataFrame) -> pd.Series:
    label_counts_per_message = df.groupby("message")["misconception_label"].transform("nunique")
    return label_counts_per_message > 1

class MisconceptionClassifier:
    """Serving wrapper around a fitted pipeline.

    Never raises. A hint is still worth delivering when the explanation
    layer fails, so a failed prediction degrades to a uniform distribution
    rather than propagating.
    """

    def __init__(self, pipeline: Pipeline):
        self.pipeline = pipeline
        # Taken from the pipeline rather than the caller. predict_proba
        # returns probabilities in classes_ order, and zipping them against
        # any other ordering mislabels every one of them silently.
        self.labels = list(pipeline.classes_)

    def predict_proba(self, code: str, error_type: str, message: str, timed_out: bool) -> dict:
        try:
            features = extract_features(code, error_type, timed_out)
            features["message"] = message
            X = pd.DataFrame([features])
            probs = self.pipeline.predict_proba(X)[0]
            return dict(zip(self.labels, (float(p) for p in probs)))
        except Exception as e:
            # A uniform distribution is also what a genuinely uncertain
            # prediction looks like, so the fault has to be recorded or it
            # is indistinguishable from normal operation.
            logger.error(f"Misconception prediction failed for error_type={error_type}: {e}")
            return self._unknown_fallback()

    def _unknown_fallback(self) -> dict:
        uniform_p = 1.0 / len(self.labels)
        return {label: uniform_p for label in self.labels}