import os
from collections import defaultdict
from datetime import timezone
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, delete, func, or_
from sqlalchemy.exc import IntegrityError
from .db import get_db
from .models import User, AuthToken, Knowledge, Prerequisite, Question, Attempt, Mastery, Mistake, Recommendation, PracticeSession
from .security import current_user, administrator, passwords, issue_token, bearer, token_digest
from .schemas import Credentials, SessionInput, AnswerInput, KnowledgeInput, QuestionInput, GoalInput
from .algorithms import graph, validate_dag, knowledge_view, recompute, rebuild_mistakes
from .service import public_question, start_session, session_view, owned_session, submit_answer, record_recommendation, lock_user
from .config import PASS_MASTERY, PASS_DISTINCT, WINDOW, VERSION, TIMEZONE

app = FastAPI(title='知序 · 高中数学智能学习助手', version='2.0.0')
from .ai.routes import router as assistant_router
app.include_router(assistant_router)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv('CORS_ORIGINS', 'http://127.0.0.1:5173,http://localhost:5173').split(','), allow_methods=['*'], allow_headers=['Authorization', 'Content-Type'])

@app.get('/api/health')
def health(db=Depends(get_db)):
    db.execute(select(1))
    return {'status': 'ok', 'algorithm': VERSION}

def user_info(u):
    return dict(id=u.id, username=u.username, role=u.role, is_demo=u.is_demo, goal_id=u.goal_id)

@app.post('/api/auth/register', status_code=201)
def register(data: Credentials, db=Depends(get_db)):
    u = User(username=data.username, password_hash=passwords.hash(data.password), role='student', is_demo=False)
    db.add(u)
    try:
        db.flush()
        token = issue_token(db, u)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, '用户名已存在')
    return dict(token=token, user=user_info(u))

@app.post('/api/auth/login')
def login(data: Credentials, db=Depends(get_db)):
    u = db.scalar(select(User).where(User.username == data.username))
    if not u or not passwords.verify(data.password, u.password_hash):
        raise HTTPException(401, '用户名或密码错误')
    token = issue_token(db, u)
    db.commit()
    return dict(token=token, user=user_info(u))

@app.get('/api/me')
def me(user=Depends(current_user)):
    return user_info(user)

@app.post('/api/auth/logout')
def logout(credentials=Depends(bearer), user=Depends(current_user), db=Depends(get_db)):
    db.execute(delete(AuthToken).where(AuthToken.digest == token_digest(credentials.credentials)))
    db.commit()
    return {'ok': True}

@app.put('/api/me/goal')
def goal(data: GoalInput, user=Depends(current_user), db=Depends(get_db)):
    if data.knowledge_id and not db.get(Knowledge, data.knowledge_id):
        raise HTTPException(422, '学习目标不存在')
    lock_user(db, user.id)
    user.goal_id = data.knowledge_id
    db.flush()
    result = record_recommendation(db, user)
    db.commit()
    return result

@app.get('/api/knowledge')
def knowledge(user=Depends(current_user), db=Depends(get_db)):
    return dict(nodes=knowledge_view(db, user.id), rules=dict(pass_mastery=PASS_MASTERY, pass_distinct=PASS_DISTINCT, window=WINDOW, timezone=str(TIMEZONE)))

@app.get('/api/recommendations')
def recommendations(user=Depends(current_user), db=Depends(get_db)):
    result = record_recommendation(db, user)
    db.commit()
    return result

@app.get('/api/questions')
def search(keyword: str = Query('', max_length=200), knowledge_id: str | None = None, difficulty: int | None = Query(None, ge=1, le=3), user=Depends(current_user), db=Depends(get_db)):
    query = select(Question).where(Question.active.is_(True))
    if keyword:
        query = query.where(Question.stem.contains(keyword, autoescape=True))
    if difficulty:
        query = query.where(Question.difficulty == difficulty)
    qs = list(db.scalars(query.order_by(Question.id)))
    if knowledge_id:
        qs = [q for q in qs if q.knowledge_id == knowledge_id or knowledge_id in q.auxiliary_ids]
    return {'total': len(qs), 'items': [public_question(q) for q in qs[:200]]}

@app.post('/api/sessions', status_code=201)
def sessions(data: SessionInput, user=Depends(current_user), db=Depends(get_db)):
    s = start_session(db, user, data)
    result = session_view(db, s)
    db.commit()
    return result

@app.get('/api/sessions/{sid}')
def get_session(sid: str, user=Depends(current_user), db=Depends(get_db)):
    return session_view(db, owned_session(db, user.id, sid))

@app.post('/api/sessions/{sid}/answers')
def answer(sid: str, data: AnswerInput, user=Depends(current_user), db=Depends(get_db)):
    result = submit_answer(db, user, sid, data)
    db.commit()
    return result

@app.get('/api/mistakes')
def mistakes(user=Depends(current_user), db=Depends(get_db)):
    records = list(db.scalars(select(Mistake).where(Mistake.user_id == user.id).order_by(Mistake.last_error_at.desc(), Mistake.question_id)))
    return [dict(question=public_question(db.get(Question, m.question_id)), error_count=m.error_count,
                 last_error_at=m.last_error_at, reviewed_at=m.reviewed_at, status='已复习' if m.reviewed_at else '待复习') for m in records]

def report_data(db, user_id):
    attempts = list(db.scalars(select(Attempt).where(Attempt.user_id == user_id).order_by(Attempt.created_at, Attempt.id)))
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
            del w[:-WINDOW]
            trend.append(dict(attempt_id=a.id, date=day, knowledge_id=a.knowledge_id, mastery=(sum(w)+1)/(len(w)+2), samples=len(w)))
    return dict(total=len(attempts), correct=sum(a.correct for a in attempts),
                accuracy=sum(a.correct for a in attempts)/len(attempts) if attempts else None,
                effective=sum(a.effective_day is not None for a in attempts), simulated=sum(a.simulated for a in attempts),
                daily=[dict(date=k, **v) for k,v in sorted(daily.items())], trend=trend,
                knowledge=knowledge_view(db, user_id), timezone=str(TIMEZONE))

@app.get('/api/report')
def report(user=Depends(current_user), db=Depends(get_db)):
    return report_data(db, user.id)

@app.get('/api/admin/overview')
def overview(admin=Depends(administrator), db=Depends(get_db)):
    return [dict(user=user_info(u), report=report_data(db, u.id)) for u in db.scalars(select(User).where(User.is_demo.is_(True), User.role == 'student'))]

@app.put('/api/admin/knowledge/{kid}')
def save_knowledge(kid: str, data: KnowledgeInput, admin=Depends(administrator), db=Depends(get_db)):
    if kid != data.id:
        raise HTTPException(422, '路径与知识点 ID 必须一致')
    # Serialize graph edits with all other admin edits, avoiding concurrent cycle insertion.
    for uid in db.scalars(select(User.id).where(User.role == 'admin').order_by(User.id)):
        lock_user(db, uid)
    nodes, edges = graph(db)
    edges[kid] = data.prerequisites
    try:
        validate_dag(edges)
    except ValueError as e:
        raise HTTPException(422, str(e))
    n = db.get(Knowledge, kid)
    if n is None:
        n = Knowledge(id=kid)
        db.add(n)
    for k, v in data.model_dump(exclude={'prerequisites'}).items():
        setattr(n, k, v)
    db.flush()
    db.execute(delete(Prerequisite).where(Prerequisite.knowledge_id == kid))
    for p in sorted(set(data.prerequisites)):
        db.add(Prerequisite(knowledge_id=kid, prerequisite_id=p))
    db.commit()
    return {'ok': True}

def validate_question_refs(db, data):
    for kid in [data.knowledge_id] + data.auxiliary_ids:
        if not db.get(Knowledge, kid):
            raise HTTPException(422, f'知识点不存在：{kid}')

@app.get('/api/admin/questions')
def admin_questions(admin=Depends(administrator), db=Depends(get_db)):
    return [dict(**public_question(q), answer=q.answer, explanation=q.explanation, active=q.active) for q in db.scalars(select(Question).order_by(Question.id))]

@app.post('/api/admin/questions/import')
def import_questions(data: list[QuestionInput], admin=Depends(administrator), db=Depends(get_db)):
    if not 1 <= len(data) <= 500:
        raise HTTPException(422, '每次导入 1～500 道题')
    for d in data:
        validate_question_refs(db, d)
    for d in data:
        db.add(Question(**d.model_dump()))
    db.commit()
    return {'imported': len(data)}

@app.put('/api/admin/questions/{qid}')
def edit_question(qid: int, data: QuestionInput, admin=Depends(administrator), db=Depends(get_db)):
    q = db.get(Question, qid)
    if not q:
        raise HTTPException(404, '题目不存在')
    validate_question_refs(db, data)
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

@app.post('/api/admin/recompute/{uid}')
def rebuild(uid: int, admin=Depends(administrator), db=Depends(get_db)):
    if not db.get(User, uid):
        raise HTTPException(404, '用户不存在')
    lock_user(db, uid)
    recompute(db, uid)
    rebuild_mistakes(db, uid)
    db.commit()
    return {'ok': True}
