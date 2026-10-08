"""Usage:
    python -m app.services.explainability.trainer \
        --seed 42 \
        --data-path app/services/explainability/data/misconceptions.jsonl \
        --output-path app/services/explainability/artifacts/classifier.joblib \
        --test-size 0.2

    run from src/backend
"""
import argparse
import hashlib
import json
from argparse import Namespace
from pathlib import Path

import sklearn

from .classifier import (
    build_feature_frame,
    collision_mask,
    build_pipeline,
    evaluate,
    fit_pipeline,
    load_dataset,
    save_pipeline,
    train_test_split_data
)

DEFAULT_DATA_PATH = Path(__file__).resolve().parent / "data" / "misconceptions.jsonl"
DEFAULT_OUTPUT_PATH = Path(__file__).resolve().parent / "artifacts" / "classifier.joblib"
DEFAULT_EVAL_PATH = Path(__file__).resolve().parent / "artifacts" / "eval_report.json"

def parse_args() -> Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42, 
                        help="Random seed for split and estimator")
    parser.add_argument("--data-path", type=Path, default=DEFAULT_DATA_PATH,
                        help="Path to misconceptions.jsonl")
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH,
                        help="Where to write the joblib artifact")
    parser.add_argument("--eval-path", type=Path, default=DEFAULT_EVAL_PATH,
                        help="Where to write the eval report")
    parser.add_argument("--test-size", type=float, default=0.2,
                        help="Fraction of the data held out for evaluation")
    return parser.parse_args()

def write_eval_report(
    metrics: dict, path: Path, seed: int, test_size: float, data_path: Path
) -> None:
    """Write the metrics alongside enough provenance to detect a stale artifact.

    classifier.joblib is committed, so it can fall out of step with the
    dataset or with scikit-learn silently: joblib loads an old artifact
    without complaint. The hash answers "was this trained on the dataset
    currently in the repo?" and the version answers "will this still
    unpickle?".

    No timestamp on purpose. The report is committed too, and a field that
    changes on every retrain makes a diff nobody reads.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    dataset_bytes = data_path.read_bytes()
    report = {
        "seed": seed,
        "test_size": test_size,
        **metrics,
        "dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest(),
        "dataset_rows": sum(
            1 for line in dataset_bytes.decode().splitlines() if line.strip()
        ),
        "sklearn_version": sklearn.__version__,
    }
    path.write_text(json.dumps(report, indent=2))


def main() -> None:
    args = parse_args()

    df = build_feature_frame(load_dataset(args.data_path))
    df["is_collision"] = collision_mask(df)

    X_train, X_test, y_train, y_test, amb_test = train_test_split_data(
        df, test_size=args.test_size, random_state=args.seed
    )
    collision_test_mask = X_test["is_collision"]

    pipeline = build_pipeline(random_state=args.seed)
    fit_pipeline(pipeline, X_train, y_train)

    metrics = evaluate(pipeline, X_train, y_train, X_test, y_test, amb_test, collision_test_mask, df)
    write_eval_report(metrics, args.eval_path, args.seed, args.test_size, args.data_path)

    save_pipeline(pipeline, args.output_path)

    print(f"headline_accuracy:  {metrics['headline_accuracy']:.3f} (n={metrics['headline_n']})")
    print(f"ambiguous_accuracy: {metrics['ambiguous_accuracy']:.3f} (n={metrics['ambiguous_n']})")
    print(f"artifact saved to:  {args.output_path}")
    print(f"eval report saved:  {args.eval_path}")
    print(f"held_out_lookup_baseline_accuracy: {metrics['held_out_lookup_baseline_accuracy']:.3f}")

if __name__ == "__main__":
    main()