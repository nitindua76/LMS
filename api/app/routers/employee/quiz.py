"""
M5 Native quiz engine — server owns the clock.

Per-question timers are enforced by comparing served_at against now().
The SCO is forward-only (one question at a time). Resume correctly
detects a timed-out current question and auto-advances.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import require_employee, verify_csrf
from app.models.user import User
from app.models.course import Section, Quiz, Question, Option, QuestionType
from app.models.enrollment import (
    Enrollment, EnrollmentStatus,
    QuizAttempt, QuizAttemptStatus,
    AttemptAnswer, SectionProgress,
)
from app.standards import bridge, xapi as xapi_svc

router = APIRouter(prefix="/my", tags=["employee-quiz"])

TIMER_GRACE_SECONDS = 5


# ── Shared helpers ────────────────────────────────────────────────────────────

def _get_enrollment_section_quiz(
    enrollment_id: int, section_id: int, user: User, db: Session
) -> tuple[Enrollment, Section, Quiz]:
    enrollment = db.query(Enrollment).filter(
        Enrollment.id == enrollment_id,
        Enrollment.user_id == user.id,
    ).first()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    if enrollment.deadline_at and datetime.now(timezone.utc) > enrollment.deadline_at:
        raise HTTPException(status_code=403, detail="Course deadline has passed")

    section = db.query(Section).options(
        joinedload(Section.quiz).joinedload(Quiz.questions).joinedload(Question.options)
    ).filter(
        Section.id == section_id,
        Section.course_id == enrollment.course_id,
    ).first()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    if not bridge.is_section_unlocked(db, enrollment, section):
        raise HTTPException(status_code=403, detail="Section is locked")

    # Must have consumed content first
    sp = db.query(SectionProgress).filter(
        SectionProgress.enrollment_id == enrollment_id,
        SectionProgress.section_id == section_id,
    ).first()
    if sp and sp.content_done is False and len(section.content_items) > 0:
        raise HTTPException(status_code=403, detail="Complete the section content before taking the quiz")

    if not section.quiz:
        raise HTTPException(status_code=404, detail="This section has no quiz")

    return enrollment, section, section.quiz


def _question_employee_view(q: Question) -> dict:
    """Employee-safe question: no is_correct."""
    return {
        "id": q.id,
        "order_index": q.order_index,
        "type": q.type.value,
        "text": q.text,
        "timer_sec": q.timer_sec,
        "options": [
            {"id": o.id, "order_index": o.order_index, "text": o.text}
            for o in sorted(q.options, key=lambda x: x.order_index)
        ],
    }


def _serve_question(
    db: Session,
    attempt: QuizAttempt,
    question: Question,
) -> AttemptAnswer:
    """Create an AttemptAnswer with served_at = now."""
    aa = AttemptAnswer(
        attempt_id=attempt.id,
        question_id=question.id,
        served_at=datetime.now(timezone.utc),
    )
    db.add(aa)
    db.flush()
    return aa


def _check_timed_out(aa: AttemptAnswer, question: Question) -> bool:
    elapsed = (datetime.now(timezone.utc) - aa.served_at).total_seconds()
    return elapsed > (question.timer_sec + TIMER_GRACE_SECONDS)


def _grade_attempt(
    attempt: QuizAttempt,
    quiz: Quiz,
    questions: list[Question],
    answers: list[AttemptAnswer],
) -> tuple[int, bool]:
    """
    Grade all submitted answers. Returns (score_pct, passed).
    Timed-out answers count as 0 marks.
    """
    answer_map = {aa.question_id: aa for aa in answers}
    total_marks = 0
    earned_marks = 0

    for q in questions:
        total_marks += q.marks
        aa = answer_map.get(q.id)
        if not aa or aa.timed_out or aa.answer is None:
            continue

        correct_ids = {o.id for o in q.options if o.is_correct}
        submitted = aa.answer  # stored as {"option_ids": [...]} or {"value": bool}

        if q.type == QuestionType.true_false:
            # submitted: {"value": true/false}
            correct_bool = True if (True in [o.is_correct for o in q.options if o.text.lower() == "true"]) else False
            if isinstance(submitted.get("value"), bool) and submitted["value"] == correct_bool:
                earned_marks += q.marks
        elif q.type == QuestionType.mcq_single:
            selected = set(submitted.get("option_ids", []))
            if selected == correct_ids:
                earned_marks += q.marks
        elif q.type == QuestionType.mcq_multi:
            selected = set(submitted.get("option_ids", []))
            if selected == correct_ids:
                earned_marks += q.marks

    score_pct = int((earned_marks / total_marks * 100)) if total_marks > 0 else 0
    passed = score_pct >= quiz.passing_pct
    return score_pct, passed


# ── Start attempt ─────────────────────────────────────────────────────────────

class _EmptyBody(BaseModel):
    pass


@router.post(
    "/enrollments/{enrollment_id}/sections/{section_id}/quiz/attempts",
    dependencies=[Depends(verify_csrf)],
)
def start_attempt(
    enrollment_id: int,
    section_id: int,
    _body: _EmptyBody,    # forces Content-Type: application/json → non-simple request → preflight required
    db: Session = Depends(get_db),
    user: User = Depends(require_employee),
):
    enrollment, section, quiz = _get_enrollment_section_quiz(enrollment_id, section_id, user, db)

    # Count existing completed attempts
    completed_attempts = db.query(QuizAttempt).filter(
        QuizAttempt.quiz_id == quiz.id,
        QuizAttempt.enrollment_id == enrollment_id,
        QuizAttempt.status == QuizAttemptStatus.submitted,
    ).count()

    if completed_attempts >= quiz.max_attempts:
        raise HTTPException(
            status_code=403,
            detail=f"Maximum attempts ({quiz.max_attempts}) reached. Contact an administrator to reset.",
        )

    # Abandon any lingering in-progress attempt
    old = db.query(QuizAttempt).filter(
        QuizAttempt.quiz_id == quiz.id,
        QuizAttempt.enrollment_id == enrollment_id,
        QuizAttempt.status == QuizAttemptStatus.in_progress,
    ).first()
    if old:
        old.status = QuizAttemptStatus.submitted
        db.flush()

    questions = sorted(quiz.questions, key=lambda q: q.order_index)
    if not questions:
        raise HTTPException(status_code=422, detail="Quiz has no questions")

    attempt = QuizAttempt(
        user_id=user.id,
        quiz_id=quiz.id,
        enrollment_id=enrollment_id,
        attempt_no=completed_attempts + 1,
        status=QuizAttemptStatus.in_progress,
        current_question_index=0,
    )
    db.add(attempt)
    db.flush()

    first_q = questions[0]
    _serve_question(db, attempt, first_q)
    db.commit()

    iri = f"http://lms.internal/courses/{enrollment.course_id}/sections/{section_id}/quiz/{quiz.id}"
    xapi_svc.emit(db, user, "initialized", iri, f"Quiz: {section.title}",
                  activity_type="http://adlnet.gov/expapi/activities/assessment",
                  enrollment_id=enrollment_id)
    db.commit()

    return {
        "attempt_id": attempt.id,
        "attempt_no": attempt.attempt_no,
        "total_questions": len(questions),
        "question": _question_employee_view(first_q),
    }


# ── Answer question ───────────────────────────────────────────────────────────

class AnswerBody(BaseModel):
    option_ids: Optional[list[int]] = None
    value: Optional[bool] = None          # for true/false


@router.post(
    "/enrollments/{enrollment_id}/sections/{section_id}/quiz/attempts/{attempt_id}/answer",
    dependencies=[Depends(verify_csrf)],
)
def answer_question(
    enrollment_id: int,
    section_id: int,
    attempt_id: int,
    body: AnswerBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_employee),
):
    enrollment, section, quiz = _get_enrollment_section_quiz(enrollment_id, section_id, user, db)

    attempt = db.query(QuizAttempt).filter(
        QuizAttempt.id == attempt_id,
        QuizAttempt.user_id == user.id,
        QuizAttempt.status == QuizAttemptStatus.in_progress,
    ).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Active attempt not found")

    questions = sorted(quiz.questions, key=lambda q: q.order_index)
    if attempt.current_question_index >= len(questions):
        raise HTTPException(status_code=409, detail="All questions already answered")

    current_q = questions[attempt.current_question_index]

    # Get the AttemptAnswer row that was created when we served this question
    aa = db.query(AttemptAnswer).filter(
        AttemptAnswer.attempt_id == attempt_id,
        AttemptAnswer.question_id == current_q.id,
    ).first()
    if not aa:
        raise HTTPException(status_code=500, detail="Answer record missing (internal error)")

    now = datetime.now(timezone.utc)
    elapsed = (now - aa.served_at).total_seconds()
    timed_out = elapsed > (current_q.timer_sec + TIMER_GRACE_SECONDS)

    if timed_out:
        aa.timed_out = True
        aa.answer = None
        aa.time_taken_sec = int(elapsed)
    else:
        if current_q.type == QuestionType.true_false:
            aa.answer = {"value": body.value}
        else:
            aa.answer = {"option_ids": body.option_ids or []}
        aa.time_taken_sec = int(elapsed)
        aa.timed_out = False

    attempt.current_question_index += 1
    db.flush()

    # Emit xAPI answered
    iri = f"http://lms.internal/questions/{current_q.id}"
    xapi_svc.emit(db, user, "answered", iri, current_q.text,
                  activity_type="http://adlnet.gov/expapi/activities/cmi.interaction",
                  result={"success": False, "completion": True},
                  enrollment_id=enrollment_id)

    # Last question → grade
    if attempt.current_question_index >= len(questions):
        all_answers = db.query(AttemptAnswer).filter(
            AttemptAnswer.attempt_id == attempt_id
        ).all()

        score_pct, passed = _grade_attempt(attempt, quiz, questions, all_answers)

        attempt.status = QuizAttemptStatus.submitted
        attempt.score_pct = score_pct
        attempt.passed = passed
        attempt.submitted_at = datetime.now(timezone.utc)
        db.flush()

        # Emit xAPI scored/passed/failed
        quiz_iri = f"http://lms.internal/courses/{enrollment.course_id}/sections/{section_id}/quiz/{quiz.id}"
        xapi_svc.emit(db, user, "scored", quiz_iri, f"Quiz: {section.title}",
                      activity_type="http://adlnet.gov/expapi/activities/assessment",
                      result={"score": {"scaled": score_pct / 100.0, "raw": score_pct,
                                        "min": 0, "max": 100}},
                      enrollment_id=enrollment_id)
        xapi_svc.emit(db, user, "passed" if passed else "failed", quiz_iri,
                      f"Quiz: {section.title}",
                      activity_type="http://adlnet.gov/expapi/activities/assessment",
                      result={"success": passed, "completion": True,
                              "score": {"scaled": score_pct / 100.0}},
                      enrollment_id=enrollment_id)

        section_complete = False
        if passed:
            section_complete = bridge.native_content_to_progress(
                db, enrollment, section, user,
                content_done=True, quiz_passed=True,
            )
        else:
            # Check if all attempts exhausted
            submitted_count = db.query(QuizAttempt).filter(
                QuizAttempt.quiz_id == quiz.id,
                QuizAttempt.enrollment_id == enrollment_id,
                QuizAttempt.status == QuizAttemptStatus.submitted,
            ).count()
            if submitted_count >= quiz.max_attempts:
                enrollment.status = EnrollmentStatus.failed
                db.flush()

        db.commit()
        return {
            "complete": True,
            "passed": passed,
            "score_pct": score_pct,
            "section_complete": section_complete,
            "attempts_used": attempt.attempt_no,
            "max_attempts": quiz.max_attempts,
        }

    # Not last — serve next question
    next_q = questions[attempt.current_question_index]
    _serve_question(db, attempt, next_q)
    db.commit()

    return {
        "complete": False,
        "question": _question_employee_view(next_q),
        "question_number": attempt.current_question_index + 1,
        "total_questions": len(questions),
        "timed_out": timed_out,
    }


# ── Resume / current question ─────────────────────────────────────────────────

@router.get(
    "/enrollments/{enrollment_id}/sections/{section_id}/quiz/attempts/{attempt_id}/current",
)
def current_question(
    enrollment_id: int,
    section_id: int,
    attempt_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_employee),
):
    """Resume: returns current question, auto-advancing timed-out questions."""
    enrollment, section, quiz = _get_enrollment_section_quiz(enrollment_id, section_id, user, db)

    attempt = db.query(QuizAttempt).filter(
        QuizAttempt.id == attempt_id,
        QuizAttempt.user_id == user.id,
        QuizAttempt.status == QuizAttemptStatus.in_progress,
    ).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Active attempt not found")

    questions = sorted(quiz.questions, key=lambda q: q.order_index)

    # Auto-advance questions that timed out during disconnect
    while attempt.current_question_index < len(questions):
        q = questions[attempt.current_question_index]
        aa = db.query(AttemptAnswer).filter(
            AttemptAnswer.attempt_id == attempt_id,
            AttemptAnswer.question_id == q.id,
        ).first()

        if aa and not aa.timed_out and _check_timed_out(aa, q):
            aa.timed_out = True
            aa.answer = None
            aa.time_taken_sec = int((datetime.now(timezone.utc) - aa.served_at).total_seconds())
            attempt.current_question_index += 1
            db.flush()
            # Serve next if available
            if attempt.current_question_index < len(questions):
                next_q = questions[attempt.current_question_index]
                _serve_question(db, attempt, next_q)
            continue
        break

    db.commit()

    if attempt.current_question_index >= len(questions):
        return {"complete": True, "attempt_id": attempt_id}

    q = questions[attempt.current_question_index]
    aa = db.query(AttemptAnswer).filter(
        AttemptAnswer.attempt_id == attempt_id,
        AttemptAnswer.question_id == q.id,
    ).first()

    elapsed = int((datetime.now(timezone.utc) - aa.served_at).total_seconds()) if aa else 0
    remaining = max(0, q.timer_sec - elapsed)

    return {
        "complete": False,
        "question": _question_employee_view(q),
        "question_number": attempt.current_question_index + 1,
        "total_questions": len(questions),
        "seconds_remaining": remaining,
        "elapsed_seconds": elapsed,
    }


# ── Admin: reset attempts ─────────────────────────────────────────────────────

@router.delete(
    "/enrollments/{enrollment_id}/sections/{section_id}/quiz/attempts",
    dependencies=[Depends(verify_csrf)],
    tags=["admin-quiz"],
)
def admin_reset_attempts(
    enrollment_id: int,
    section_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_employee),  # will be overridden in admin router
):
    """Reset quiz attempts for an enrollment (admin action, separate admin router calls this)."""
    raise HTTPException(status_code=403, detail="Use admin endpoint to reset attempts")
