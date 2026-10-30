import json
import os
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from sqlalchemy import select, func
from .db import SessionLocal
from .models import Course, Knowledge, Prerequisite, Question, User, utcnow
from .courses import DEFAULT_COURSE, enroll
from .question_bank import KNOWLEDGE, items
from .schemas import SessionInput, AnswerInput
from .security import passwords
from .service import start_session, submit_answer
from .config import PASS_DISTINCT, PASS_MASTERY, WINDOW

# Kept in sync with the course row the courses migration inserts for pre-existing databases.
DEFAULT_COURSE_ROW = dict(id=DEFAULT_COURSE, name='高中数学（函数与导数）', subject='math', level='high', language='zh',
                          settings={'open_enrollment': True, 'assistant': {'persona': '高中数学智能学习助手', 'formula': 'katex',
                                    'scope_note': '本库目前仅覆盖高中数学函数与导数路径'}})

def ensure_default_course(db):
    if not db.get(Course, DEFAULT_COURSE):
        db.add(Course(**DEFAULT_COURSE_ROW))
        db.flush()

def seed(db, demos=True):
    if db.scalar(select(func.count()).select_from(Knowledge)):
        return False
    ensure_default_course(db)
    for pos, (kid, chapter, name, prerequisites, description) in enumerate(KNOWLEDGE):
        db.add(Knowledge(id=kid, course_id=DEFAULT_COURSE, subject='math', chapter=chapter, name=name, description=description, position=pos))
    db.flush()
    for kid, _, _, prerequisites, _ in KNOWLEDGE:
        for p in prerequisites:
            db.add(Prerequisite(knowledge_id=kid, prerequisite_id=p))
    bank = items()
    for q in bank:
        db.add(Question(**q))
    db.flush()
    for kid, *_ in KNOWLEDGE:
        count = sum(q['knowledge_id'] == kid for q in bank)
        n = min(count, WINDOW)
        if count < PASS_DISTINCT or (n+1)/(n+2) < PASS_MASTERY:
            raise ValueError(f'{kid}: 题库规模无法满足当前通关阈值')
    if demos:
        password = os.getenv('DEMO_PASSWORD', 'DemoMath2026!')
        for username, role in [('demo_foundation', 'student'), ('demo_advanced', 'student'), ('demo_admin', 'admin')]:
            u = User(username=username, password_hash=passwords.hash(password), role=role, is_demo=True)
            db.add(u)
            db.flush()
            e = enroll(db, u.id, DEFAULT_COURSE, 'teacher' if role == 'admin' else 'student')
            e.goal_id = 'optimization' if role == 'student' else None
        db.flush()
        # All synthetic histories pass through the same service as real submissions.
        for username, strong_nodes, weak in [('demo_foundation', ['sets','domain','evaluation'], 'monotonicity'),
                                             ('demo_advanced', [k[0] for k in KNOWLEDGE[:9]], 'derivative_rules')]:
            u = db.scalar(select(User).where(User.username == username))
            for kid in strong_nodes + [weak]:
                qs = list(db.scalars(select(Question).where(Question.knowledge_id == kid, Question.difficulty == 1).order_by(Question.id)))
                s = start_session(db, u, SessionInput(mode='custom', knowledge_id=kid, difficulty=1, count=5))
                for i, q in enumerate(qs[:5]):
                    correct = kid in strong_nodes
                    submit_answer(db, u, s.id, AnswerInput(question_id=q.id, selected=q.answer if correct else (q.answer+1)%4,
                                  idempotency_key=str(uuid.uuid4())), at=utcnow()-timedelta(days=2, minutes=5-i), simulated=True)
    db.commit()
    return True

if __name__ == '__main__':
    with SessionLocal() as db:
        created = seed(db)
    target = Path('data')
    target.mkdir(exist_ok=True)
    (target/'demo_questions.json').write_text(json.dumps(items(), ensure_ascii=False, indent=2), encoding='utf-8')
    print('Initialized 14 knowledge nodes, 140 demo questions and 3 marked demo accounts.' if created else 'Already initialized; no data changed.')
