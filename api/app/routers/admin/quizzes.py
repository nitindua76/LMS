from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.dependencies import require_admin, verify_csrf
from app.models.user import User
from app.models.course import Section, Quiz, Question, Option
from app.schemas.quiz import (
    QuizCreate, QuizUpdate, QuizReadAdmin,
    QuestionCreateAdmin, QuestionUpdateAdmin, QuestionReadAdmin,
    OptionCreateAdmin, OptionUpdateAdmin, OptionReadAdmin,
    validate_question_options,
)
from app.services.audit import audit

router = APIRouter(
    prefix="/admin/courses/{course_id}/sections/{section_id}/quiz",
    tags=["admin-quizzes"],
)


def _get_section(db: Session, course_id: int, section_id: int) -> Section:
    section = db.query(Section).filter(
        Section.id == section_id, Section.course_id == course_id
    ).first()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    return section


def _get_quiz(db: Session, course_id: int, section_id: int) -> Quiz:
    _get_section(db, course_id, section_id)
    quiz = (
        db.query(Quiz)
        .options(joinedload(Quiz.questions).joinedload(Question.options))
        .filter(Quiz.section_id == section_id)
        .first()
    )
    if not quiz:
        raise HTTPException(status_code=404, detail="No quiz on this section")
    return quiz


@router.get("", response_model=QuizReadAdmin)
def get_quiz(
    course_id: int,
    section_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return _get_quiz(db, course_id, section_id)


@router.post("", response_model=QuizReadAdmin, status_code=201, dependencies=[Depends(verify_csrf)])
def create_quiz(
    course_id: int,
    section_id: int,
    body: QuizCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    _get_section(db, course_id, section_id)
    existing = db.query(Quiz).filter(Quiz.section_id == section_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="This section already has a quiz")
    quiz = Quiz(section_id=section_id, passing_pct=body.passing_pct, max_attempts=body.max_attempts)
    db.add(quiz)
    db.flush()
    audit(db, actor_id=actor.id, action="create_quiz", target_type="quiz",
          target_id=quiz.id, detail={"section_id": section_id})
    db.commit()
    return _get_quiz(db, course_id, section_id)


@router.put("", response_model=QuizReadAdmin, dependencies=[Depends(verify_csrf)])
def update_quiz(
    course_id: int,
    section_id: int,
    body: QuizUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    quiz = _get_quiz(db, course_id, section_id)
    if body.passing_pct is not None:
        quiz.passing_pct = body.passing_pct
    if body.max_attempts is not None:
        quiz.max_attempts = body.max_attempts
    db.flush()
    audit(db, actor_id=actor.id, action="update_quiz", target_type="quiz", target_id=quiz.id)
    db.commit()
    return _get_quiz(db, course_id, section_id)


@router.delete("", status_code=204, dependencies=[Depends(verify_csrf)])
def delete_quiz(
    course_id: int,
    section_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    quiz = _get_quiz(db, course_id, section_id)
    try:
        db.delete(quiz)
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Cannot delete: quiz has attempt records")
    audit(db, actor_id=actor.id, action="delete_quiz", target_type="quiz", target_id=quiz.id)
    db.commit()


# ── Questions ──────────────────────────────────────────────────────────────────

questions_router = APIRouter(
    prefix="/admin/courses/{course_id}/sections/{section_id}/quiz/questions",
    tags=["admin-questions"],
)


@questions_router.post("", response_model=QuestionReadAdmin, status_code=201,
                       dependencies=[Depends(verify_csrf)])
def create_question(
    course_id: int,
    section_id: int,
    body: QuestionCreateAdmin,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    quiz = _get_quiz(db, course_id, section_id)
    question = Question(
        quiz_id=quiz.id,
        order_index=body.order_index,
        type=body.type,
        text=body.text,
        marks=body.marks,
        timer_sec=body.timer_sec,
    )
    db.add(question)
    db.flush()

    for opt_data in body.options:
        opt = Option(
            question_id=question.id,
            order_index=opt_data.order_index,
            text=opt_data.text,
            is_correct=opt_data.is_correct,
        )
        db.add(opt)
    db.flush()
    audit(db, actor_id=actor.id, action="create_question", target_type="question",
          target_id=question.id, detail={"quiz_id": quiz.id})
    db.commit()

    return (
        db.query(Question)
        .options(joinedload(Question.options))
        .filter(Question.id == question.id)
        .first()
    )


@questions_router.put("/{question_id}", response_model=QuestionReadAdmin,
                      dependencies=[Depends(verify_csrf)])
def update_question(
    course_id: int,
    section_id: int,
    question_id: int,
    body: QuestionUpdateAdmin,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    quiz = _get_quiz(db, course_id, section_id)
    question = db.query(Question).filter(
        Question.id == question_id, Question.quiz_id == quiz.id
    ).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    fields = body.model_dump(exclude_none=True, exclude={"options"})
    new_options = body.options  # kept separate: [] is falsy but a valid "replace with empty" isn't meaningful here

    effective_type = body.type if body.type is not None else question.type
    if new_options is not None:
        try:
            validate_question_options(effective_type, new_options)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    for field, value in fields.items():
        setattr(question, field, value)

    if new_options is not None:
        # Full replace rather than diff/upsert — matches how the create
        # endpoint builds options from scratch, and keeps this simple: an
        # edit from the admin UI always resubmits the complete option set.
        db.query(Option).filter(Option.question_id == question.id).delete()
        db.flush()
        for i, opt_data in enumerate(new_options):
            db.add(Option(
                question_id=question.id,
                order_index=opt_data.order_index if opt_data.order_index else i + 1,
                text=opt_data.text,
                is_correct=opt_data.is_correct,
            ))

    db.flush()
    audit(db, actor_id=actor.id, action="update_question", target_type="question",
          target_id=question_id, detail={"options_replaced": new_options is not None})
    db.commit()
    return (
        db.query(Question)
        .options(joinedload(Question.options))
        .filter(Question.id == question_id)
        .first()
    )


@questions_router.delete("/{question_id}", status_code=204, dependencies=[Depends(verify_csrf)])
def delete_question(
    course_id: int,
    section_id: int,
    question_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    quiz = _get_quiz(db, course_id, section_id)
    question = db.query(Question).filter(
        Question.id == question_id, Question.quiz_id == quiz.id
    ).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    try:
        db.delete(question)
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Cannot delete: question has answer records")
    audit(db, actor_id=actor.id, action="delete_question", target_type="question",
          target_id=question_id)
    db.commit()


# ── Options ────────────────────────────────────────────────────────────────────

options_router = APIRouter(
    prefix="/admin/courses/{course_id}/sections/{section_id}/quiz/questions/{question_id}/options",
    tags=["admin-options"],
)


@options_router.post("", response_model=OptionReadAdmin, status_code=201,
                     dependencies=[Depends(verify_csrf)])
def create_option(
    course_id: int,
    section_id: int,
    question_id: int,
    body: OptionCreateAdmin,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    quiz = _get_quiz(db, course_id, section_id)
    question = db.query(Question).filter(
        Question.id == question_id, Question.quiz_id == quiz.id
    ).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    opt = Option(
        question_id=question_id,
        order_index=body.order_index,
        text=body.text,
        is_correct=body.is_correct,
    )
    db.add(opt)
    db.flush()
    audit(db, actor_id=actor.id, action="create_option", target_type="option", target_id=opt.id)
    db.commit()
    db.refresh(opt)
    return opt


@options_router.put("/{option_id}", response_model=OptionReadAdmin,
                    dependencies=[Depends(verify_csrf)])
def update_option(
    course_id: int,
    section_id: int,
    question_id: int,
    option_id: int,
    body: OptionUpdateAdmin,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    opt = db.query(Option).filter(
        Option.id == option_id, Option.question_id == question_id
    ).first()
    if not opt:
        raise HTTPException(status_code=404, detail="Option not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(opt, field, value)
    db.flush()
    audit(db, actor_id=actor.id, action="update_option", target_type="option", target_id=option_id)
    db.commit()
    db.refresh(opt)
    return opt


@options_router.delete("/{option_id}", status_code=204, dependencies=[Depends(verify_csrf)])
def delete_option(
    course_id: int,
    section_id: int,
    question_id: int,
    option_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    opt = db.query(Option).filter(
        Option.id == option_id, Option.question_id == question_id
    ).first()
    if not opt:
        raise HTTPException(status_code=404, detail="Option not found")
    db.delete(opt)
    audit(db, actor_id=actor.id, action="delete_option", target_type="option", target_id=option_id)
    db.commit()


# ── Quiz attempt reset (admin) ────────────────────────────────────────────────

from app.models.enrollment import QuizAttempt, AttemptAnswer, SectionProgress, EnrollmentStatus


@router.delete(
    "/enrollments/{enrollment_id}/attempts",
    status_code=204,
    dependencies=[Depends(verify_csrf)],
    tags=["admin-quiz-reset"],
)
def admin_reset_quiz_attempts(
    course_id: int,
    section_id: int,
    enrollment_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    """
    Reset quiz attempts for an enrollment so the employee can retake.
    Also clears completed_at on the section_progress row if it was set by a quiz failure.
    """
    quiz = _get_quiz(db, course_id, section_id)
    attempts = db.query(QuizAttempt).filter(
        QuizAttempt.quiz_id == quiz.id,
        QuizAttempt.enrollment_id == enrollment_id,
    ).all()

    for attempt in attempts:
        db.query(AttemptAnswer).filter(AttemptAnswer.attempt_id == attempt.id).delete()
        db.delete(attempt)
    db.flush()

    # If enrollment was failed due to exhausted attempts, reopen it
    from app.models.enrollment import Enrollment
    enrollment = db.get(Enrollment, enrollment_id)
    if enrollment and enrollment.status == EnrollmentStatus.failed:
        enrollment.status = EnrollmentStatus.in_progress
        db.flush()

    audit(
        db, actor_id=actor.id, action="reset_quiz_attempts", target_type="enrollment",
        target_id=enrollment_id, detail={"quiz_id": quiz.id, "attempts_deleted": len(attempts)},
    )
    db.commit()
