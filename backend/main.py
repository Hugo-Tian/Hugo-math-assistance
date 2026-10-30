import logging
import os
from collections import defaultdict
from datetime import timezone
from fastapi import APIRouter, FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from .db import get_db
from .models import User, AuthToken, Course, Enrollment, Knowledge, Prerequisite, Question, Attempt, Mistake, PracticeSession
from .security import current_user, administrator, passwords, issue_token, bearer, token_digest, login_throttle
from .schemas import Credentials, SessionInput, AnswerInput, KnowledgeInput, QuestionInput, GoalInput, CourseInput, MemberInput
from .algorithms import graph, validate_dag, knowledge_view, recompute, rebuild_mistakes
from .service import public_question, start_session, session_view, owned_session, submit_answer, record_recommendation, lock_user
from .courses import DEFAULT_COURSE, STAFF_ROLES, course_context, course_staff, course_knowledge_ids, in_course, auto_enroll, enroll, rules_for, scope_for
from .config import VERSION, TIMEZONE

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'), format='%(asctime)s %(levelname)s %(name)s %(message)s')
app = FastAPI(title='知序 · 课程 AI 助教', version='3.0.0')
app.add_middleware(CORSMiddleware, allow_origins=os.getenv('CORS_ORIGINS', 'http://127.0.0.1:5173,http://localhost:5173').split(','), allow_methods=['*'], allow_headers=['Authorization', 'Content-Type'])
# Learning routes are mounted twice (see bottom): under /api/courses/{cid} and, for the legacy frontend, under /api (= DEFAULT_COURSE).
learning = APIRouter()

@app.get('/api/health')
def health(db=Depends(get_db)):
    db.execute(select(1))
    return {'status': 'ok', 'algorithm': VERSION}

def user_info(u, db, course_id=DEFAULT_COURSE):
    e = db.get(Enrollment, (course_id, u.id))
    return dict(id=u.id, username=u.username, role=u.role, is_demo=u.is_demo, goal_id=e.goal_id if e else None)

@app.post('/api/auth/register', status_code=201)
def register(data: Credentials, db=Depends(get_db)):
    u = User(username=data.username, password_hash=passwords.hash(data.password), role='student', is_demo=False)
    db.add(u)
    try:
        db.flush()
        auto_enroll(db, u)
        token = issue_token(db, u)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, '用户名已存在')
    return dict(token=token, user=user_info(u, db))

@app.post('/api/auth/login')
def login(data: Credentials, db=Depends(get_db)):
    login_throttle.check(data.username)
    u = db.scalar(select(User).where(User.username == data.username))
    if not u or not passwords.verify(data.password, u.password_hash):
        login_throttle.failed(data.username)
        raise HTTPException(401, '用户名或密码错误')
    login_throttle.succeeded(data.username)
    token = issue_token(db, u)
    db.commit()
    return dict(token=token, user=user_info(u, db))

@app.get('/api/me')
def me(user=Depends(current_user), db=Depends(get_db)):
    return user_info(user, db)

@app.post('/api/auth/logout')
def logout(credentials=Depends(bearer), user=Depends(current_user), db=Depends(get_db)):
    db.execute(delete(AuthToken).where(AuthToken.digest == token_digest(credentials.credentials)))
    db.commit()
    return {'ok': True}

# ---- Courses and membership ----

def course_info(c, role):
    return dict(id=c.id, name=c.name, subject=c.subject, level=c.level, language=c.language, status=c.status, role=role)

@app.get('/api/courses')
def my_courses(user=Depends(current_user), db=Depends(get_db)):
    roles = {e.course_id: e.role for e in db.scalars(select(Enrollment).where(Enrollment.user_id == user.id))}
    courses = db.scalars(select(Course).where(Course.status != 'archived').order_by(Course.id))
    return [course_info(c, roles.get(c.id, 'admin')) for c in courses if c.id in roles or user.role == 'admin']

@app.post('/api/courses', status_code=201)
def create_course(data: CourseInput, admin=Depends(administrator), db=Depends(get_db)):
    if db.get(Course, data.id):
        raise HTTPException(409, '课程 ID 已存在')
    c = Course(**data.model_dump(), created_by=admin.id)
    try:
        rules_for(c)
    except ValueError as e:
        raise HTTPException(422, str(e))
    db.add(c)
    db.flush()
    enroll(db, admin.id, c.id, 'teacher')
    db.commit()
    return course_info(c, 'teacher')

@app.post('/api/courses/{cid}/members')
def add_member(cid: str, data: MemberInput, ctx=Depends(course_staff), db=Depends(get_db)):
    if data.role in STAFF_ROLES and ctx.role != 'teacher' and ctx.user.role != 'admin':
        raise HTTPException(403, '只有任课老师可以添加老师或助教')
    u = db.scalar(select(User).where(User.username == data.username))
    if not u:
        raise HTTPException(404, '用户不存在')
    e = enroll(db, u.id, cid, data.role)
    e.role = data.role
    db.commit()
    return {'user_id': u.id, 'role': e.role}

@app.post('/api/courses/{cid}/join')
def join(cid: str, user=Depends(current_user), db=Depends(get_db)):
    c = db.get(Course, cid)
    if not c or c.status != 'active' or not (c.settings or {}).get('open_enrollment'):
        raise HTTPException(404, '课程不存在或不开放自主加入')
    e = enroll(db, user.id, cid)
    db.commit()
    return {'course_id': cid, 'role': e.role}

# ---- Learning (course scoped) ----

@learning.put('/me/goal')
def goal(data: GoalInput, ctx=Depends(course_context), db=Depends(get_db)):
    if not ctx.enrollment:
        raise HTTPException(409, '尚未加入本课程，不能设置学习目标')
    if data.knowledge_id and not in_course(db, data.knowledge_id, ctx.course.id):
        raise HTTPException(422, '学习目标不存在')
    lock_user(db, ctx.user.id)
    ctx.enrollment.goal_id = data.knowledge_id
    db.flush()
    result = record_recommendation(db, ctx.user, scope_for(db, ctx.user.id, ctx.course.id))
    db.commit()
    return result

@learning.get('/knowledge')
def knowledge(ctx=Depends(course_context), db=Depends(get_db)):
    r = ctx.scope.rules
    return dict(nodes=knowledge_view(db, ctx.user.id, ctx.scope), course=course_info(ctx.course, ctx.role),
                rules=dict(pass_mastery=r.pass_mastery, pass_distinct=r.pass_distinct, window=r.window, timezone=str(TIMEZONE)))

@learning.get('/recommendations')
def recommendations(ctx=Depends(course_context), db=Depends(get_db)):
    result = record_recommendation(db, ctx.user, ctx.scope)
    db.commit()
    return result

@learning.get('/questions')
def search(keyword: str = Query('', max_length=200), knowledge_id: str | None = None, difficulty: int | None = Query(None, ge=1, le=3), ctx=Depends(course_context), db=Depends(get_db)):
    query = select(Question).where(Question.active.is_(True), Question.knowledge_id.in_(course_knowledge_ids(db, ctx.course.id)))
    if keyword:
        query = query.where(Question.stem.contains(keyword, autoescape=True))
    if difficulty:
        query = query.where(Question.difficulty == difficulty)
    qs = list(db.scalars(query.order_by(Question.id)))
    if knowledge_id:
        qs = [q for q in qs if q.knowledge_id == knowledge_id or knowledge_id in q.auxiliary_ids]
    return {'total': len(qs), 'items': [public_question(q) for q in qs[:200]]}

def course_session(db, ctx, sid):
    s = owned_session(db, ctx.user.id, sid)
    if s.course_id != ctx.course.id:
        raise HTTPException(404, '练习不存在')
    return s

@learning.post('/sessions', status_code=201)
def sessions(data: SessionInput, ctx=Depends(course_context), db=Depends(get_db)):
    s = start_session(db, ctx.user, data, ctx.scope)
    result = session_view(db, s)
    db.commit()
    return result

@learning.get('/sessions/{sid}')
def get_session(sid: str, ctx=Depends(course_context), db=Depends(get_db)):
    return session_view(db, course_session(db, ctx, sid))

@learning.post('/sessions/{sid}/answers')
def answer(sid: str, data: AnswerInput, ctx=Depends(course_context), db=Depends(get_db)):
    course_session(db, ctx, sid)
    result = submit_answer(db, ctx.user, sid, data)
    db.commit()
    return result

@learning.get('/mistakes')
def mistakes(ctx=Depends(course_context), db=Depends(get_db)):
    ids = course_knowledge_ids(db, ctx.course.id)
    records = db.execute(select(Mistake, Question).join(Question, Question.id == Mistake.question_id)
                         .where(Mistake.user_id == ctx.user.id, Question.knowledge_id.in_(ids))
                         .order_by(Mistake.last_error_at.desc(), Mistake.question_id)).all()
    return [dict(question=public_question(q), error_count=m.error_count,
                 last_error_at=m.last_error_at, reviewed_at=m.reviewed_at, status='已复习' if m.reviewed_at else '待复习') for m, q in records]

def report_data(db, user_id, scope):
    ids = course_knowledge_ids(db, scope.course_id)
    attempts = list(db.scalars(select(Attempt).where(Attempt.user_id == user_id, Attempt.knowledge_id.in_(ids)).order_by(Attempt.created_at, Attempt.id)))
    daily = defaultdict(lambda: {'attempts': 0, 'correct': 0, 'effective': 0})
    windows, trend = defaultdict(list), []
    for a in attempts:
        day = a.created_at.replace(tzinfo=timezone.utc).astimezone(TIMEZONE).date().isoformat()
        daily[day]['attempts'] += 1
        daily[day]['correct'] += int(a.correct)
        daily[day]['effective'] += int(a.effective_day is not None)
        if a.effective_day is not None:
            w = windows[a.knowledge_id]
            w.append(a.correct)
            del w[:-scope.rules.window]
            trend.append(dict(attempt_id=a.id, date=day, knowledge_id=a.knowledge_id, mastery=(sum(w)+1)/(len(w)+2), samples=len(w)))
    return dict(total=len(attempts), correct=sum(a.correct for a in attempts),
                accuracy=sum(a.correct for a in attempts)/len(attempts) if attempts else None,
                effective=sum(a.effective_day is not None for a in attempts), simulated=sum(a.simulated for a in attempts),
                daily=[dict(date=k, **v) for k,v in sorted(daily.items())], trend=trend,
                knowledge=knowledge_view(db, user_id, scope), timezone=str(TIMEZONE))

@learning.get('/report')
def report(ctx=Depends(course_context), db=Depends(get_db)):
    return report_data(db, ctx.user.id, ctx.scope)

# ---- Course staff ----

@learning.get('/admin/overview')
def overview(ctx=Depends(course_staff), db=Depends(get_db)):
    students = db.scalars(select(User).join(Enrollment, Enrollment.user_id == User.id)
                          .where(Enrollment.course_id == ctx.course.id, Enrollment.role == 'student', User.is_demo.is_(True)).order_by(User.id))
    return [dict(user=user_info(u, db, ctx.course.id), report=report_data(db, u.id, scope_for(db, u.id, ctx.course.id))) for u in students]

def lock_staff(db, course_id):
    # Serialize graph edits among everyone who may edit this course, avoiding concurrent cycle insertion.
    staff = set(db.scalars(select(User.id).where(User.role == 'admin')))
    staff |= set(db.scalars(select(Enrollment.user_id).where(Enrollment.course_id == course_id, Enrollment.role.in_(STAFF_ROLES))))
    for uid in sorted(staff):
        lock_user(db, uid)

@learning.put('/admin/knowledge/{kid}')
def save_knowledge(kid: str, data: KnowledgeInput, ctx=Depends(course_staff), db=Depends(get_db)):
    cid = ctx.course.id
    if kid != data.id:
        raise HTTPException(422, '路径与知识点 ID 必须一致')
    lock_staff(db, cid)
    n = db.get(Knowledge, kid)
    if n is not None and n.course_id != cid:
        raise HTTPException(409, '该知识点 ID 已被其他课程使用')
    # Legacy course keeps its historical ids; every other course namespaces new ids as "<course>.<slug>".
    if n is None and cid != DEFAULT_COURSE and not kid.startswith(cid + '.'):
        raise HTTPException(422, f'新知识点 ID 需以 {cid}. 开头')
    nodes, edges = graph(db, cid)
    edges[kid] = data.prerequisites
    try:
        validate_dag(edges)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if n is None:
        n = Knowledge(id=kid, course_id=cid)
        db.add(n)
    for k, v in data.model_dump(exclude={'prerequisites'}).items():
        setattr(n, k, v)
    n.subject = ctx.course.subject
    db.flush()
    db.execute(delete(Prerequisite).where(Prerequisite.knowledge_id == kid))
    for p in sorted(set(data.prerequisites)):
        db.add(Prerequisite(knowledge_id=kid, prerequisite_id=p))
    db.commit()
    return {'ok': True}

def validate_question_refs(db, data, course_id):
    for kid in [data.knowledge_id] + data.auxiliary_ids:
        if not in_course(db, kid, course_id):
            raise HTTPException(422, f'知识点不存在：{kid}')

@learning.get('/admin/questions')
def admin_questions(ctx=Depends(course_staff), db=Depends(get_db)):
    ids = course_knowledge_ids(db, ctx.course.id)
    return [dict(**public_question(q), answer=q.answer, explanation=q.explanation, active=q.active)
            for q in db.scalars(select(Question).where(Question.knowledge_id.in_(ids)).order_by(Question.id))]

@learning.post('/admin/questions/import')
def import_questions(data: list[QuestionInput], ctx=Depends(course_staff), db=Depends(get_db)):
    if not 1 <= len(data) <= 500:
        raise HTTPException(422, '每次导入 1～500 道题')
    for d in data:
        validate_question_refs(db, d, ctx.course.id)
    for d in data:
        db.add(Question(**d.model_dump()))
    db.commit()
    return {'imported': len(data)}

@learning.put('/admin/questions/{qid}')
def edit_question(qid: int, data: QuestionInput, ctx=Depends(course_staff), db=Depends(get_db)):
    q = db.get(Question, qid)
    if not q or not in_course(db, q.knowledge_id, ctx.course.id):
        raise HTTPException(404, '题目不存在')
    validate_question_refs(db, data, ctx.course.id)
    if db.scalar(select(Attempt.id).where(Attempt.question_id == qid).limit(1)):
        # Preserve the exact historical question; edits become a new version.
        q.active = False
        replacement = Question(**data.model_dump())
        db.add(replacement)
        db.flush()
        new_id = replacement.id
    else:
        # Also disallow edits to a question currently issued to a learner.
        issued = any(qid in s.question_ids for s in db.scalars(select(PracticeSession).where(PracticeSession.ended.is_(False))))
        if issued:
            raise HTTPException(409, '题目正在练习中，请稍后修改或新增版本')
        for k, v in data.model_dump().items():
            setattr(q, k, v)
        new_id = q.id
    db.commit()
    return {'id': new_id, 'versioned': new_id != qid}

@learning.post('/admin/recompute/{uid}')
def rebuild(uid: int, ctx=Depends(course_staff), db=Depends(get_db)):
    if not db.get(Enrollment, (ctx.course.id, uid)):
        raise HTTPException(404, '用户不存在')
    lock_user(db, uid)
    recompute(db, uid, scope_for(db, uid, ctx.course.id))
    rebuild_mistakes(db, uid)
    db.commit()
    return {'ok': True}

from .ai.routes import router as assistant_router
from .teacher import router as teacher_router
from .ai.drafts import router as drafts_router
for prefix in ('/api/courses/{cid}', '/api'):
    app.include_router(learning, prefix=prefix)
    app.include_router(assistant_router, prefix=prefix)
    app.include_router(teacher_router, prefix=prefix)
    app.include_router(drafts_router, prefix=prefix)
