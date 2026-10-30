"""Course scoping: membership, per-course rules, and the scope every learning algorithm runs in."""
from dataclasses import dataclass, field
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from .db import get_db
from .models import Course, Enrollment, Knowledge, User
from .security import current_user
from .config import PASS_MASTERY, PASS_DISTINCT, WINDOW, ASSESSMENT_TIMEOUT_MINUTES

# Legacy routes without /courses/{cid} and pre-course data resolve to this course.
DEFAULT_COURSE = 'hs-math'
STAFF_ROLES = ('teacher', 'ta')
# courses.settings key -> Rules field
RULE_KEYS = {'pass_mastery': 'pass_mastery', 'pass_distinct': 'pass_distinct', 'mastery_window': 'window',
             'assessment_timeout_minutes': 'assessment_timeout_minutes'}

@dataclass(frozen=True)
class Rules:
    pass_mastery: float = PASS_MASTERY
    pass_distinct: int = PASS_DISTINCT
    window: int = WINDOW
    assessment_timeout_minutes: int = ASSESSMENT_TIMEOUT_MINUTES

def rules_for(course):
    settings = course.settings or {}
    rules = Rules(**{field: settings[key] for key, field in RULE_KEYS.items() if key in settings})
    if not 0 < rules.pass_mastery < 1 or not 1 <= rules.pass_distinct <= rules.window <= 100 or rules.assessment_timeout_minutes < 1:
        raise ValueError(f'课程 {course.id} 的通过标准配置无效')
    return rules

@dataclass(frozen=True)
class Scope:
    course_id: str
    rules: Rules = field(default_factory=Rules)
    goal_id: str | None = None

def scope_for(db, user_id, course_id=DEFAULT_COURSE):
    course = db.get(Course, course_id)
    if not course:
        raise ValueError('课程不存在')
    enrollment = db.get(Enrollment, (course_id, user_id))
    return Scope(course_id, rules_for(course), enrollment.goal_id if enrollment else None)

def course_knowledge_ids(db, course_id):
    return set(db.scalars(select(Knowledge.id).where(Knowledge.course_id == course_id)))

def in_course(db, knowledge_id, course_id):
    k = db.get(Knowledge, knowledge_id)
    return bool(k and k.course_id == course_id)

def enroll(db, user_id, course_id, role='student'):
    e = db.get(Enrollment, (course_id, user_id))
    if e is None:
        e = Enrollment(course_id=course_id, user_id=user_id, role=role)
        db.add(e)
    return e

def auto_enroll(db, user):
    # Courses that opt in with settings.open_enrollment accept every new student automatically.
    for c in db.scalars(select(Course).where(Course.status == 'active')):
        if (c.settings or {}).get('open_enrollment'):
            enroll(db, user.id, c.id)

@dataclass
class CourseContext:
    course: Course
    user: User
    role: str
    enrollment: Enrollment | None
    scope: Scope

    @property
    def staff(self):
        return self.role in STAFF_ROLES or self.user.role == 'admin'

def course_context(request: Request, user=Depends(current_user), db=Depends(get_db)):
    cid = request.path_params.get('cid', DEFAULT_COURSE)
    course = db.get(Course, cid)
    enrollment = db.get(Enrollment, (cid, user.id)) if course else None
    # 404 rather than 403 so non-members cannot probe which courses exist.
    if not course or course.status == 'archived' or (enrollment is None and user.role != 'admin'):
        raise HTTPException(404, '课程不存在或尚未加入')
    role = enrollment.role if enrollment else 'admin'
    return CourseContext(course, user, role, enrollment, Scope(cid, rules_for(course), enrollment.goal_id if enrollment else None))

def course_staff(ctx=Depends(course_context)):
    if not ctx.staff:
        raise HTTPException(403, '需要本课程老师或助教权限')
    return ctx
