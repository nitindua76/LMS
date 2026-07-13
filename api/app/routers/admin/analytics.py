import re
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_, or_

from app.database import get_db
from app.dependencies import require_admin
from app.models.user import User
from app.models.course import Course, CourseStatus, Section, ContentItem, CourseTarget, CourseTargetUser, Quiz
from app.models.discipline import Discipline
from app.models.level import Level
from app.models.enrollment import Enrollment, EnrollmentStatus, SectionProgress, QuizAttempt, QuizAttemptStatus, ProgressSource
from app.models.package import LearningPackage, ScormCmiData
from app.services import content_progress

router = APIRouter(prefix="/admin/analytics", tags=["admin-analytics"])

def parse_iso8601_duration(duration_str: str) -> float:
    if not duration_str:
        return 0.0
    pattern = re.compile(
        r'P(?:(?P<years>\d+)Y)?(?:(?P<months>\d+)M)?(?:(?P<days>\d+)D)?'
        r'(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?'
    )
    match = pattern.match(duration_str)
    if not match:
        return 0.0
    gd = match.groupdict()
    seconds = float(gd.get('seconds') or 0.0)
    minutes = float(gd.get('minutes') or 0.0)
    hours = float(gd.get('hours') or 0.0)
    days = float(gd.get('days') or 0.0)
    return seconds + minutes * 60 + hours * 3600 + days * 86400

def get_targeted_user_ids(db: Session, course_id: int) -> set:
    """
    One query per course instead of one query per (course, target) pair — every
    CourseTarget row is a required (discipline_id, level_id) pair (both columns
    are NOT NULL on the model), so all targets can be matched in a single
    query via an OR of per-pair AND conditions. Unioned with anyone
    individually added via CourseTargetUser (models/course.py).
    """
    ids: set = set()

    targets = db.query(CourseTarget).filter(CourseTarget.course_id == course_id).all()
    if targets:
        pairs = {(t.discipline_id, t.level_id) for t in targets}
        conditions = [and_(User.discipline_id == d, User.level_id == l) for d, l in pairs]
        rows = db.query(User.id).filter(User.role == "employee", or_(*conditions)).all()
        ids.update(row[0] for row in rows)

    individual_rows = db.query(CourseTargetUser.user_id).filter(
        CourseTargetUser.course_id == course_id
    ).all()
    ids.update(row[0] for row in individual_rows)

    return ids

def calculate_progress_pct(db: Session, enrollment_id: int, user_id: int, course_id: int) -> float:
    total_sections = db.query(func.count(Section.id)).filter(Section.course_id == course_id).scalar() or 1
    completed_sections = db.query(func.count(SectionProgress.id)).filter(
        SectionProgress.enrollment_id == enrollment_id,
        SectionProgress.content_done == True,
        SectionProgress.completed_at != None
    ).scalar() or 0

    # Add partial credit for in-progress sections — SCORM engagement (existing) or
    # native video watch time (ContentProgress.max_watched_seconds), so a
    # part-way-watched video shows real progress instead of 0% until it's fully done.
    all_sections = db.query(Section).options(joinedload(Section.content_items)).filter(
        Section.course_id == course_id
    ).all()
    partial_credit = 0.0
    for sec in all_sections:
        # Skip sections already counted as fully complete
        sp_check = db.query(SectionProgress).filter(
            SectionProgress.enrollment_id == enrollment_id,
            SectionProgress.section_id == sec.id,
            SectionProgress.completed_at != None,
        ).first()
        if sp_check:
            continue

        scorm_item = next((ci for ci in sec.content_items if ci.type.value == "scorm"), None)
        if scorm_item:
            pkg = db.query(LearningPackage).filter(
                LearningPackage.content_item_id == scorm_item.id
            ).first()
            if pkg:
                cmi_rows = db.query(ScormCmiData).filter(
                    ScormCmiData.user_id == user_id,
                    ScormCmiData.learning_package_id == pkg.id,
                ).all()
                if cmi_rows:
                    vals = []
                    for r in cmi_rows:
                        if r.progress_measure is not None:
                            vals.append(r.progress_measure)
                        elif r.score_scaled is not None:
                            vals.append(r.score_scaled)
                        elif r.completion_status == "completed":
                            vals.append(1.0)
                    if vals:
                        partial_credit += sum(vals) / len(vals)
            continue

        item_ids = [ci.id for ci in sec.content_items]
        progress_map = content_progress.get_progress_map(db, enrollment_id, item_ids)
        native_pct = content_progress.compute_section_native_pct(sec, progress_map)
        if native_pct is not None:
            partial_credit += native_pct / 100.0

    raw_progress = completed_sections + partial_credit
    return min(100.0, round((raw_progress / total_sections) * 100, 1))


@router.get("/overview")
def get_overview(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    # 1. Enrolled courses count (Unique courses with at least 1 enrollment)
    enrolled_courses_count = db.query(func.count(func.distinct(Enrollment.course_id))).scalar() or 0
    
    # 2. Sum of target audience size across all courses
    courses = db.query(Course).all()
    total_targeted_instances = 0
    for c in courses:
        targeted_ids = get_targeted_user_ids(db, c.id)
        total_targeted_instances += len(targeted_ids)
        
    # 3. Active courses count
    active_courses_count = db.query(func.count(Course.id)).filter(Course.status == CourseStatus.published).scalar() or 0
    
    # 4. Closed courses count
    closed_courses_count = db.query(func.count(Course.id)).filter(Course.status == CourseStatus.archived).scalar() or 0
    
    # Calculate SCORM study time
    cmi_data = db.query(ScormCmiData.total_time).all()
    scorm_seconds = sum(parse_iso8601_duration(row[0]) for row in cmi_data)
    
    # Calculate PDF watch/read times
    native_count = db.query(func.count(SectionProgress.id)).filter(SectionProgress.source == ProgressSource.native).scalar() or 0
    total_seconds = scorm_seconds + (native_count * 300)
    total_hours = round(total_seconds / 3600.0, 1)
    
    return {
        "enrolled_courses_count": enrolled_courses_count,
        "total_targeted_instances": total_targeted_instances,
        "active_courses_count": active_courses_count,
        "closed_courses_count": closed_courses_count,
        "total_time_spent_hours": total_hours
    }

def _compute_course_analytics(db: Session, course: Course) -> dict:
    # `if True:` keeps this identical to its pre-refactor body indentation —
    # this used to be the per-course loop in get_courses_analytics(), extracted
    # verbatim so the list and single-course detail endpoints share one path.
    if True:
        targeted_ids = get_targeted_user_ids(db, course.id)
        enrollments = db.query(Enrollment).options(joinedload(Enrollment.user)).filter(Enrollment.course_id == course.id).all()

        # Build lookup for enrollments
        enrollment_map = {e.user_id: e for e in enrollments}
        targeted_users = {
            u.id: u for u in db.query(User).filter(User.id.in_(targeted_ids)).all()
        } if targeted_ids else {}

        completed_list = []
        started_list = []
        not_enrolled_list = []

        total_sections = db.query(func.count(Section.id)).filter(Section.course_id == course.id).scalar() or 1

        # Categorize targeted employees
        for user_id in targeted_ids:
            user = targeted_users.get(user_id)
            if not user:
                continue

            e = enrollment_map.get(user_id)
            if e:
                progress_pct = calculate_progress_pct(db, e.id, user_id, course.id)
                
                # Fetch max quiz score — a "submitted" attempt should always carry a
                # score, but don't let a stale/corrupt row (score_pct NULL) crash the
                # whole analytics page; just exclude it from the max.
                attempts = db.query(QuizAttempt.score_pct).filter(
                    QuizAttempt.enrollment_id == e.id,
                    QuizAttempt.status == QuizAttemptStatus.submitted
                ).all()
                scores = [a[0] for a in attempts if a[0] is not None]
                max_score = max(scores) if scores else None

                completed_at = None
                if e.status == EnrollmentStatus.completed:
                    # Enrollment itself has no completed_at column — the course
                    # completes when its last section does, so that's the
                    # latest SectionProgress.completed_at for this enrollment.
                    completed_at = db.query(func.max(SectionProgress.completed_at)).filter(
                        SectionProgress.enrollment_id == e.id
                    ).scalar()

                student_record = {
                    "user_id": user.id,
                    "name": user.name,
                    "email": user.email,
                    "progress": progress_pct,
                    "quiz_score": max_score,
                    "started_at": e.started_at,
                    "completed_at": completed_at,
                }

                if e.status == EnrollmentStatus.completed:
                    completed_list.append(student_record)
                else:
                    started_list.append(student_record)
            else:
                not_enrolled_list.append({
                    "user_id": user.id,
                    "name": user.name,
                    "email": user.email,
                    "progress": 0,
                    "quiz_score": None,
                    "started_at": None
                })
                
        # SCORM statistics for this course
        scorm_stats = []
        scorm_data = db.query(ScormCmiData).join(LearningPackage).join(ContentItem).join(Section).filter(
            Section.course_id == course.id
        ).all()
        
        by_sco = {}
        for sd in scorm_data:
            if sd.sco_identifier not in by_sco:
                by_sco[sd.sco_identifier] = []
            by_sco[sd.sco_identifier].append(sd)
            
        for sco, records in by_sco.items():
            total_records = len(records)
            completed_count = sum(1 for r in records if r.completion_status == "completed")
            in_progress_count = sum(1 for r in records if r.completion_status in ("incomplete", "in_progress", "not attempted"))
            not_attempted_count = max(0, len(targeted_ids) - total_records)
            
            times_sec = [parse_iso8601_duration(r.total_time) for r in records]
            avg_time = (sum(times_sec) / len(times_sec)) if times_sec else 0.0

            # Determine if this SCO is treated as a Quiz / Graded assessment element
            is_quiz = any(r.success_status != "unknown" or r.score_raw is not None for r in records)
            
            passed_count = 0
            failed_count = 0
            avg_score = 0.0
            
            if is_quiz:
                passed_count = sum(1 for r in records if r.success_status == "passed")
                failed_count = sum(1 for r in records if r.success_status == "failed")
                scores = [r.score_raw for r in records if r.score_raw is not None]
                avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0

            scorm_stats.append({
                "sco_identifier": sco,
                "title": sco.split("/")[-1].replace(".html", "").replace("_", " ").title(),
                "avg_time_sec": round(avg_time, 1),
                "completed_count": completed_count,
                "in_progress_count": in_progress_count,
                "not_attempted_count": not_attempted_count,
                "is_quiz": is_quiz,
                "passed_count": passed_count,
                "failed_count": failed_count,
                "avg_score": avg_score
            })
            
        return {
            "id": course.id,
            "title": course.title,
            "status": course.status.value,
            "target_audience_count": len(targeted_ids),
            "completed_count": len(completed_list),
            "started_count": len(started_list),
            "not_enrolled_count": len(not_enrolled_list),
            "students_completed": completed_list,
            "students_started": started_list,
            "students_not_enrolled": not_enrolled_list,
            "scorm_stats": scorm_stats
        }


@router.get("/courses")
def get_courses_analytics(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    courses = db.query(Course).all()
    return [_compute_course_analytics(db, c) for c in courses]


@router.get("/courses/{course_id}/export")
def export_course_report(
    course_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Downloadable .xlsx report — see services/excel_export.py for what's in it."""
    from app.services.excel_export import build_course_report

    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    buf = build_course_report(db, course)
    filename = re.sub(r"[^A-Za-z0-9_-]+", "_", course.title).strip("_") or "course"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}_report.xlsx"'},
    )


@router.get("/courses/{course_id}")
def get_course_analytics_detail(
    course_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Same computation as the list endpoint, scoped to one course, with the
    three completed/started/not-enrolled lists merged into one `students`
    list carrying a `status` tag — the shape the course drill-down modal uses."""
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    detail = _compute_course_analytics(db, course)
    students = (
        [{**s, "status": "completed"} for s in detail["students_completed"]]
        + [{**s, "status": "in_progress"} for s in detail["students_started"]]
        + [{**s, "status": "not_enrolled"} for s in detail["students_not_enrolled"]]
    )
    return {**detail, "students": students}


def _compute_employee_analytics(
    db: Session,
    emp: User,
    courses: List[Course],
    targets_by_course: Dict[int, list],
    timeline_limit: int = 15,
    individual_by_course: Optional[Dict[int, set]] = None,
) -> dict:
    if True:
        enrollments = db.query(Enrollment).filter(Enrollment.user_id == emp.id).all()
        enrollment_map = {e.course_id: e for e in enrollments}
        individual_by_course = individual_by_course or {}

        targeted_courses_list = []
        completed_targeted_count = 0
        enrolled_targeted_count = 0
        not_enrolled_targeted_count = 0

        # Check targets for all courses — targets_by_course is pre-loaded once by
        # the caller (one query total), not re-queried per employee/course pair.
        for course in courses:
            targets = targets_by_course.get(course.id, [])

            matches = emp.id in individual_by_course.get(course.id, set())
            for t in targets:
                match_disc = (t.discipline_id is None) or (emp.discipline_id == t.discipline_id)
                match_lvl = (t.level_id is None) or (emp.level_id == t.level_id)
                if match_disc and match_lvl:
                    matches = True
                    break

            if matches:
                e = enrollment_map.get(course.id)
                status_str = "Not Enrolled"
                progress_pct = 0.0
                quiz_score = None

                if e:
                    progress_pct = calculate_progress_pct(db, e.id, emp.id, course.id)

                    attempts = db.query(QuizAttempt.score_pct).filter(
                        QuizAttempt.enrollment_id == e.id,
                        QuizAttempt.status == QuizAttemptStatus.submitted
                    ).all()
                    scores = [a[0] for a in attempts if a[0] is not None]
                    quiz_score = max(scores) if scores else None

                    if e.status == EnrollmentStatus.completed:
                        status_str = "Completed"
                        completed_targeted_count += 1
                    else:
                        status_str = "Enrolled"
                        enrolled_targeted_count += 1
                else:
                    not_enrolled_targeted_count += 1

                targeted_courses_list.append({
                    "course_id": course.id,
                    "title": course.title,
                    "status": status_str,
                    "is_active": course.status == CourseStatus.published,
                    "progress": progress_pct,
                    "quiz_score": quiz_score
                })

        # Populate timeline history
        timeline = []
        for e in enrollments:
            completed_sections_query = db.query(SectionProgress).options(joinedload(SectionProgress.section)).filter(
                SectionProgress.enrollment_id == e.id,
                SectionProgress.content_done == True
            ).all()
            for sp in completed_sections_query:
                if sp.completed_at:
                    timeline.append({
                        "date": sp.completed_at,
                        "event": f"Completed section '{sp.section.title}' of course '{e.course.title}'",
                        "type": "completion"
                    })
            attempts_query = db.query(QuizAttempt).options(joinedload(QuizAttempt.quiz).joinedload(Quiz.section)).filter(
                QuizAttempt.enrollment_id == e.id,
                QuizAttempt.status == QuizAttemptStatus.submitted
            ).all()
            for qa in attempts_query:
                if qa.submitted_at:
                    passed_str = "passed" if qa.passed else "failed"
                    timeline.append({
                        "date": qa.submitted_at,
                        "event": f"Attempted quiz in '{qa.quiz.section.title}' — Score: {qa.score_pct}% ({passed_str})",
                        "type": "quiz"
                    })

        timeline.sort(key=lambda x: x["date"], reverse=True)

        return {
            "id": emp.id,
            "name": emp.name,
            "email": emp.email,
            "active": emp.active,
            "discipline": emp.discipline.name if emp.discipline else "None",
            "level": emp.level.name if emp.level else "None",
            "completed_targeted_count": completed_targeted_count,
            "enrolled_targeted_count": enrolled_targeted_count,
            "not_enrolled_targeted_count": not_enrolled_targeted_count,
            "targeted_courses": targeted_courses_list,
            "timeline": timeline[:timeline_limit]
        }


def _load_targets_by_course(db: Session) -> Dict[int, list]:
    by_course: Dict[int, list] = {}
    for t in db.query(CourseTarget).all():
        by_course.setdefault(t.course_id, []).append(t)
    return by_course


def _load_individual_targets_by_course(db: Session) -> Dict[int, set]:
    by_course: Dict[int, set] = {}
    for row in db.query(CourseTargetUser).all():
        by_course.setdefault(row.course_id, set()).add(row.user_id)
    return by_course


@router.get("/employees")
def get_employees_analytics(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    employees = db.query(User).options(
        joinedload(User.discipline),
        joinedload(User.level)
    ).filter(User.role == "employee").all()
    courses = db.query(Course).all()
    targets_by_course = _load_targets_by_course(db)
    individual_by_course = _load_individual_targets_by_course(db)

    return [
        _compute_employee_analytics(db, emp, courses, targets_by_course, individual_by_course=individual_by_course)
        for emp in employees
    ]


@router.get("/employees/{employee_id}")
def get_employee_analytics_detail(
    employee_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Same computation as the list endpoint, scoped to one employee, with the
    full (uncapped) timeline and a per-course time-spent figure derived from
    SCORM engagement — the shape the employee drill-down modal uses."""
    emp = db.query(User).options(
        joinedload(User.discipline), joinedload(User.level)
    ).filter(User.id == employee_id, User.role == "employee").first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    courses = db.query(Course).all()
    targets_by_course = _load_targets_by_course(db)
    individual_by_course = _load_individual_targets_by_course(db)
    detail = _compute_employee_analytics(
        db, emp, courses, targets_by_course, timeline_limit=200, individual_by_course=individual_by_course,
    )

    course_titles_by_id = {c.id: c for c in courses}
    courses_with_time: List[dict] = []
    for tc in detail["targeted_courses"]:
        course = course_titles_by_id.get(tc["course_id"])
        time_spent_hours = 0.0
        if course:
            scorm_seconds = sum(
                parse_iso8601_duration(row[0])
                for row in db.query(ScormCmiData.total_time)
                .join(LearningPackage).join(ContentItem).join(Section)
                .filter(Section.course_id == course.id, ScormCmiData.user_id == employee_id)
                .all()
            )
            time_spent_hours = round(scorm_seconds / 3600.0, 2)
        courses_with_time.append({
            "course_id": tc["course_id"],
            "title": tc["title"],
            "status": {"Completed": "completed", "Enrolled": "in_progress", "Not Enrolled": "not_enrolled"}[tc["status"]],
            "progress": tc["progress"],
            "quiz_score": tc["quiz_score"],
            "time_spent_hours": time_spent_hours,
        })

    return {**detail, "courses": courses_with_time}
