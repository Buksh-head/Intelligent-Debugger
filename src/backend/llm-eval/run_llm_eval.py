"""run_llm_eval.py - Generate hints for error logs and append results to JSON"""
from dotenv import load_dotenv
load_dotenv()

import os
from datetime import datetime
import json

from sqlmodel import Session, select
from app.db_models import ErrorLog, Submission
from app.services.db import engine  
from app.services.hint_generator import generate_hint


def get_error_with_submission(error_id: int) -> dict:
    """Get error with its submission code"""
    with Session(engine) as session:
        error = session.get(ErrorLog, error_id)

        if not error:
            return None

        submission = session.get(Submission, error.submission_id)

        return {
            "error_id": error.id,
            "error_type": error.error_type,
            "message": error.message,
            "code_snippet": error.code_snippet,
            "code": submission.code if submission else None,
            "expected_behaviour": submission.expected_behaviour if submission else None,
        }


def evaluate_errors(
    error_ids: list = None,
    stage: int = 1,
    model: str = "gpt2",
    output_file: str = "eval_results.json",
    limit: int = 10,
):
    results = []

    with Session(engine) as session:
        if error_ids:
            statement = select(ErrorLog).where(ErrorLog.id.in_(error_ids))
        else:
            statement = select(ErrorLog).order_by(ErrorLog.created_at.desc())
            if limit:
                statement = statement.limit(limit)

        errors = session.exec(statement).all()

        fetched = []
        for error in errors:
            error_data = get_error_with_submission(error.id)
            fetched.append((error, error_data))

    # Phase 2: run slow LLM generation with NO open DB session
    for error, error_data in fetched:
        eval_doc = generate_hint(error_data, stage, model)

        result = {
            "log_no": eval_doc.log_no,
            "error_id": error.id,
            "error_type": error.error_type,
            "stage": stage,
            "model": model,
            "error_data": error_data,
            "hint": eval_doc.response,
            "timestamp": eval_doc.time.isoformat(),
        }
        results.append(result)
        print(f"✓ Error {error.id}: Generated hint (log_no: {eval_doc.log_no})")

    # Load existing data and append
    if os.path.exists(output_file):
        with open(output_file, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = []
    else:
        data = []

    data.extend(results)

    with open(output_file, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\n✅ Appended {len(results)} hints to {output_file}")


if __name__ == "__main__":
    evaluate_errors(limit=10, model="Qwen/Qwen2.5-1.5B-Instruct")
    # evaluate_errors(error_ids=[1, 2, 5], stage=1)  # or target specific rows instead