"""Routes for hint generation (see issue #9)"""
from fastapi import APIRouter, HTTPException

from sqlmodel import Session
from app.services.hint_generator import generate_hint, generate_socratic_answer
from app.services.stage_classifier import classify_student_message, resolve_next_stage, Stage
from app.services.learning_resources import detect_concept, get_resource
from app.services.db import get_engine
from app.services.explainability.service import build_explanation
from app.db_models import ErrorLog, Submission
from app.models import HintRequest, HintResponse, HintStage, SocraticAnswer

router = APIRouter(prefix="/api",tags=["generation"])

@router.post("/hints", response_model=HintResponse)
def create_hint(request: HintRequest) -> HintResponse:
    """Generates hint for the corresponding findings to return a hint to correct the error.
    
        error_id is fetched from ErrorLog to generate hint for the corresponding error
    """
    with Session(get_engine()) as session:
        error_log = session.get(ErrorLog, request.error_id)
        if not error_log:
            raise HTTPException(status_code=404, detail="Error not found")
        if request.mode == "socratic":
            # One turn, so no stage classification and nothing written back.
            message = error_log.message or ""
            eval_doc = generate_socratic_answer(
                findings={**request.finding.model_dump(), "message": message},
            )
            answer = None
            explanation = None
            if eval_doc.success:
                answer = SocraticAnswer(diagnosis=eval_doc.diagnosis or None, fix=eval_doc.fix or None)
                # The classifier parses the whole program, not the failing line.
                submission = session.get(Submission, error_log.submission_id)
                if submission is not None:
                    # build_explanation returns None rather than raising, so the
                    # answer always ships. No counterfactual: the fix is already given.
                    explanation = build_explanation(
                        code=submission.code,
                        error_type=request.finding.error_type,
                        message=message,
                        timed_out=request.execution.timed_out,
                        reasoning=eval_doc.reasoning,
                        include_counterfactual=False,
                    )
            return HintResponse(
                status="success" if eval_doc.success else "error",
                execution=request.execution,
                finding=request.finding,
                hints=[],
                answer=answer,
                explanation=explanation,
            )

        current_stage = min(error_log.hint_stage_reached or 1, Stage.REDIRECT)
        vague_attempts = error_log.vague_attempts_this_stage or 0

        # No previous_hint means the student hasn't been given a task to
        # respond to yet for this error aka this is turn one.
        is_first_turn = not request.previous_hint

        pending_concept = error_log.pending_resource_concept
        pending_resource = get_resource(pending_concept)

        classification = classify_student_message(
            student_message=request.student_message,
            stage_task=request.previous_hint,
            pending_check_prompt=pending_resource.check_prompt if pending_resource else None,
        )

        intent = classification.intent

        next_stage, next_vague_attempts, advanced, advanced_softly, clear_gate = resolve_next_stage(
            current_stage=current_stage,
            vague_attempts_this_stage=vague_attempts,
            intent=intent,
            has_pending_resource=pending_resource is not None,
        )

        # Only a genuine "repeat" if we didn't advance AND there was an
        # actual previous attempt to be repeating. First turn is never a repeat.
        is_repeat = (not advanced) and not is_first_turn

        # Open a NEW gate at Stage 2 (UNDERSTAND), at most once per
        # error, and only when a concept actually matches. Earlier would
        # interrupt "look here"; later stalls them mid-fix.
        offer_concept = None
        if pending_concept is None and next_stage == Stage.UNDERSTAND and not error_log.resource_offered:
            offer_concept = detect_concept(
                request.finding.error_type,
                request.finding.failing_code_snippet,
            )
        offer_resource = get_resource(offer_concept)

        active = offer_resource or (None if clear_gate else pending_resource)

        eval_doc = generate_hint(
            findings={**request.finding.model_dump(), "message": error_log.message or ""},
            stage=next_stage,
            student_message=request.student_message,
            intent=intent,
            advanced_softly=advanced_softly,
            is_repeat_of_current_stage=is_repeat,
            is_first_turn=is_first_turn,
            resource_label=active.label if active else "",
            resource_url=active.url if active else "",
            resource_blurb=active.blurb if active else "",
            resource_check=active.check_prompt if active else "",
            is_new_resource=offer_resource is not None,
            gate_cleared=clear_gate,
        )

        new_hint = HintStage(
            stage=next_stage,
            text=eval_doc.response if eval_doc.success else None,
            intent=intent,
            advanced_softly=advanced_softly,
            resource_url=active.url if active else None,
            resource_label=active.label if active else None,
            gate_on_url=active is not None,
        )

        if eval_doc.success:
            error_log.hint_stage_reached = next_stage
            error_log.vague_attempts_this_stage = next_vague_attempts
            if offer_concept:
                error_log.pending_resource_concept = offer_concept
                error_log.resource_offered = True
            elif clear_gate:
                error_log.pending_resource_concept = None
            session.add(error_log)
            session.commit()

    return HintResponse(
        status="success" if eval_doc.success else "error",
        execution=request.execution,
        finding=request.finding,
        hints=[new_hint],
    )