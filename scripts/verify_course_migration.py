"""Course migration check: upgrade a COPY of an existing database and prove learning results are unchanged.

Before: a raw-SQL snapshot (mastery, mistakes, goals, latest recommendation per user) of the pre-course schema.
After: the new course-scoped code recomputes everything from the attempts inside a rolled-back transaction,
and every value must match. The source database is never written to.

Usage: python scripts/verify_course_migration.py [path/to/source.db]   (default: adaptive_math.db)
"""
import json
import os
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

root = Path(__file__).resolve().parents[1]
PRE_COURSE_REVISION = '41b7a28e6461'
source = Path(sys.argv[1]) if len(sys.argv) > 1 else root / 'adaptive_math.db'
(root / 'tmp').mkdir(exist_ok=True)
copy = root / 'tmp' / f'course-migration-{uuid.uuid4().hex[:8]}.db'

# The backup API also captures pages still sitting in the WAL file.
with sqlite3.connect(f'file:{source.as_posix()}?mode=ro', uri=True) as src, sqlite3.connect(copy) as dst:
    src.backup(dst)

raw = sqlite3.connect(copy)
version = raw.execute('SELECT version_num FROM alembic_version').fetchone()[0]
if version != PRE_COURSE_REVISION:
    sys.exit(f'Source is at revision {version}, expected {PRE_COURSE_REVISION}; nothing to verify.')
def ts(value):
    return datetime.fromisoformat(str(value)) if value else None
mastery = {(u, k): (v, s, d, ts(p), lvl) for u, k, v, s, d, p, lvl in raw.execute(
    'SELECT user_id, knowledge_id, value, samples, distinct_count, passed_at, difficulty_level FROM mastery')}
mistakes = {(u, q): (n, ts(e), ts(r)) for u, q, n, e, r in raw.execute(
    'SELECT user_id, question_id, error_count, last_error_at, reviewed_at FROM mistakes')}
goals = dict(raw.execute('SELECT id, goal_id FROM users'))
latest = {}
for uid, payload, created in raw.execute('SELECT user_id, payload, created_at FROM recommendations ORDER BY id'):
    latest[uid] = (json.loads(payload), ts(created))
raw.close()

env = {**os.environ, 'DATABASE_URL': f'sqlite:///{copy.as_posix()}', 'PYTHONUTF8': '1'}
for args in (['upgrade', 'head'], ['check']):
    done = subprocess.run([sys.executable, '-m', 'alembic', *args], cwd=root, env=env, capture_output=True, text=True)
    if done.returncode:
        sys.exit(f'alembic {args[0]} failed:\n{done.stderr[-2000:]}')

os.environ['DATABASE_URL'] = env['DATABASE_URL']
sys.path.insert(0, str(root))
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from backend.db import make_engine
from backend.models import User, Mastery, Mistake
from backend.algorithms import recompute, recommend, rebuild_mistakes
from backend.courses import scope_for, course_knowledge_ids, DEFAULT_COURSE

def same(a, b, tolerance=1e-6):
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(a - b) <= tolerance
    return a == b

engine = make_engine(env['DATABASE_URL'])
problems, checked = [], dict(users=0, mastery=0, mistakes=0, recommendations=0)
with sessionmaker(engine)() as db:
    ids = course_knowledge_ids(db, DEFAULT_COURSE)
    for u in db.scalars(select(User).order_by(User.id)):
        checked['users'] += 1
        scope = scope_for(db, u.id)
        if scope.goal_id != goals.get(u.id):
            problems.append(f'user {u.id}: goal {goals.get(u.id)} -> {scope.goal_id}')
        recompute(db, u.id, scope)
        rebuild_mistakes(db, u.id)
        for m in db.scalars(select(Mastery).where(Mastery.user_id == u.id, Mastery.knowledge_id.in_(ids))):
            before = mastery.get((u.id, m.knowledge_id))
            after = (m.value, m.samples, m.distinct_count, m.passed_at, m.difficulty_level)
            # A node never practised may have no stored row before; an empty recomputed row is equivalent.
            if before is None and not m.samples:
                continue
            checked['mastery'] += 1
            if before != after:
                problems.append(f'user {u.id} {m.knowledge_id}: mastery {before} -> {after}')
        for m in db.scalars(select(Mistake).where(Mistake.user_id == u.id)):
            checked['mistakes'] += 1
            if mistakes.get((u.id, m.question_id)) != (m.error_count, m.last_error_at, m.reviewed_at):
                problems.append(f'user {u.id} question {m.question_id}: mistake record changed')
        if u.id in latest:
            payload, created = latest[u.id]
            checked['recommendations'] += 1
            # Replaying at the stored timestamp removes most of the time decay; the original `now` was taken a few
            # microseconds before created_at, so numbers are compared with a small absolute tolerance.
            again = recommend(db, u, scope, now=created)
            if not same(json.loads(json.dumps(again)), payload):
                problems.append(f'user {u.id}: latest recommendation differs when replayed at {created}')
    db.rollback()
engine.dispose()

print(f'source={source} copy={copy}')
print('checked', checked)
if problems:
    print('MISMATCHES:', *problems[:30], sep='\n  ')
    sys.exit(1)
print('COURSE MIGRATION VERIFIED: goals, mastery, mistakes and recommendations unchanged under course-scoped code')
