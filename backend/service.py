import uuid
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select, update
from .models import User, Question, PracticeSession, Attempt, Exposure, Recommendation, Knowledge
from .algorithms import recompute, rebuild_mistakes, recommend
from .config import TIMEZONE, VERSION

def lock_user(db, user_id):
    # A write lock serializes all mutations for one learner on MySQL; SQLite serializes writes.
    db.execute(update(User).where(User.id == user_id).values(username=User.username))

def public_question(q):
    return dict(id=q.id, knowledge_id=q.knowledge_id, auxiliary_ids=q.auxiliary_ids, stem=q.stem,
                options=q.options, difficulty=q.difficulty, source=q.source)

def record_recommendation(db, user):
    payload = recommend(db, user)
    db.add(Recommendation(user_id=user.id, version=VERSION, payload=payload))
    return payload

def choose_next(db, user, session):
    recommendations = record_recommendation(db, user)['recommendations']
    used = set(session.question_ids)
    for rec in recommendations:
        qs = list(db.scalars(select(Question).where(Question.active.is_(True), Question.knowledge_id == rec['knowledge_id']).order_by(Question.id)))
        exposed = set(db.scalars(select(Exposure.question_id).where(Exposure.user_id == user.id)))
        qs = [q for q in qs if q.id not in used]
        # Prefer unseen questions, then target difficulty. Never silently duplicate a question.
        qs.sort(key=lambda q: (q.id in exposed, abs(q.difficulty - rec['difficulty']), q.difficulty, q.id))
        if qs:
            q = qs[0]
            session.question_ids = session.question_ids + [q.id]
            session.notice = ('当前可选题已展示过答案，本题只计复习记录。' if q.id in exposed else '')
            if q.difficulty != rec['difficulty']:
                session.notice += '目标难度题量不足，已选择最近难度。'
            return
    session.ended = True
    session.notice = '当前可学习知识点的题量不足，已结束；没有重复填充题目。'

def start_session(db, user, data):
    if data.knowledge_id and not db.get(Knowledge, data.knowledge_id):
        raise HTTPException(422, '知识点不存在')
    lock_user(db, user.id)
    s = PracticeSession(id=str(uuid.uuid4()), user_id=user.id, mode=data.mode, knowledge_id=data.knowledge_id,
                        difficulty=data.difficulty, requested_count=data.count, question_ids=[], notice='', ended=False)
    db.add(s)
    if data.mode == 'adaptive':
        choose_next(db, user, s)
    else:
        query = select(Question).where(Question.active.is_(True))
        if data.mode == 'review' and data.question_id is None:
            raise HTTPException(422, '请选择要复习的题目')
        if data.question_id:
            query = query.where(Question.id == data.question_id)
        if data.knowledge_id:
            query = query.where(Question.knowledge_id == data.knowledge_id)
        if data.difficulty:
            query = query.where(Question.difficulty == data.difficulty)
        candidates = list(db.scalars(query.order_by(Question.id)))
        exposed = set(db.scalars(select(Exposure.question_id).where(Exposure.user_id == user.id)))
        candidates.sort(key=lambda q: (q.id in exposed, q.id))
        s.question_ids = [q.id for q in candidates[:data.count]]
        if len(s.question_ids) < data.count:
            s.notice = f'符合条件的题目只有 {len(s.question_ids)} 道，少于所选 {data.count} 道。'
        if not s.question_ids:
            raise HTTPException(422, '没有符合条件的题目，请调整筛选')
    db.flush()
    return s

def owned_session(db, user_id, sid):
    s = db.get(PracticeSession, sid)
    if not s:
        raise HTTPException(404, '练习不存在')
    if s.user_id != user_id:
        raise HTTPException(403, '不能访问其他学生的练习')
    return s

def session_view(db, s):
    attempts = list(db.scalars(select(Attempt).where(Attempt.session_id == s.id).order_by(Attempt.id)))
    answered = {a.question_id for a in attempts}
    pending = next((qid for qid in s.question_ids if qid not in answered), None)
    return dict(id=s.id, mode=s.mode, requested_count=s.requested_count, actual_count=len(s.question_ids),
                answered=len(attempts), correct=sum(a.correct for a in attempts), effective=sum(a.effective_day is not None for a in attempts),
                ended=s.ended, notice=s.notice, question=public_question(db.get(Question, pending)) if pending else None,
                results=[a.result for a in attempts])

def submit_answer(db, user, sid, data, at=None, simulated=False):
    lock_user(db, user.id)
    s = owned_session(db, user.id, sid)
    previous = db.scalar(select(Attempt).where(Attempt.user_id == user.id, Attempt.idempotency_key == data.idempotency_key))
    if previous:
        if (previous.session_id, previous.question_id, previous.selected) != (sid, data.question_id, data.selected):
            raise HTTPException(409, '幂等键已经用于不同的答案')
        return previous.result
    already = db.scalar(select(Attempt).where(Attempt.session_id == sid, Attempt.question_id == data.question_id))
    if already:
        if already.selected != data.selected:
            raise HTTPException(409, '本题已提交，不能修改答案')
        return already.result
    pending = session_view(db, s)['question']
    if s.ended or not pending or pending['id'] != data.question_id:
        raise HTTPException(409, '请按练习顺序提交当前题目')
    q = db.get(Question, data.question_id)
    now = at or datetime.utcnow()
    day = now.replace(tzinfo=timezone.utc).astimezone(TIMEZONE).date()
    exposure = db.get(Exposure, (user.id, q.id))
    duplicate_day = db.scalar(select(Attempt.id).where(Attempt.user_id == user.id, Attempt.question_id == q.id, Attempt.effective_day == day))
    reason = '已展示答案，重复练习不计入掌握度' if exposure else ('同题当天已计分' if duplicate_day else '')
    a = Attempt(user_id=user.id, session_id=sid, question_id=q.id, knowledge_id=q.knowledge_id,
                selected=data.selected, correct=data.selected == q.answer, effective_day=None if reason else day,
                exclusion_reason=reason, idempotency_key=data.idempotency_key, created_at=now, simulated=simulated)
    db.add(a)
    if not exposure:
        db.add(Exposure(user_id=user.id, question_id=q.id, first_shown_at=now))
    db.flush()
    states = recompute(db, user.id)
    rebuild_mistakes(db, user.id)
    answered = list(db.scalars(select(Attempt).where(Attempt.session_id == sid)))
    if len(answered) >= s.requested_count or (s.mode != 'adaptive' and len(answered) >= len(s.question_ids)):
        s.ended = True
    elif s.mode == 'adaptive':
        choose_next(db, user, s)
    m = states[q.knowledge_id]
    rec = record_recommendation(db, user)
    a.result = dict(attempt_id=a.id, question_id=q.id, selected=a.selected, correct=a.correct, answer=q.answer,
                    explanation=q.explanation, effective=a.effective_day is not None, exclusion_reason=reason,
                    mastery=m.value, samples=m.samples, knowledge_id=q.knowledge_id,
                    recommendation=rec['recommendations'][0] if rec['recommendations'] else None)
    db.flush()
    return a.result
