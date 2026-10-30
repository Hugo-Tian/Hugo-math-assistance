"""Teacher dashboard: rule-computed class views for one course. No model calls, so every number is reproducible."""
from collections import defaultdict
from datetime import timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from .db import get_db
from .models import User, Enrollment, Attempt, Mistake, Question, utcnow
from .algorithms import knowledge_view, recommend
from .courses import course_staff, course_knowledge_ids, scope_for

router = APIRouter()
LOW_MASTERY = 0.5

def students_of(db, course_id):
    return list(db.scalars(select(User).join(Enrollment, Enrollment.user_id == User.id)
                           .where(Enrollment.course_id == course_id, Enrollment.role == 'student').order_by(User.username)))

@router.get('/teacher/dashboard')
def dashboard(ctx=Depends(course_staff), db=Depends(get_db)):
    cid = ctx.course.id
    ids = course_knowledge_ids(db, cid)
    students = students_of(db, cid)
    now = utcnow()
    attempts = defaultdict(list)
    if students and ids:
        for a in db.scalars(select(Attempt).where(Attempt.user_id.in_([s.id for s in students]), Attempt.knowledge_id.in_(ids))):
            attempts[a.user_id].append(a)
    rows, views, stuck = [], {}, defaultdict(lambda: {'students': [], 'blocks': set()})
    for s in students:
        scope = scope_for(db, s.id, cid)
        nodes = knowledge_view(db, s.id, scope)
        views[s.id] = {n['id']: n for n in nodes}
        mine = attempts[s.id]
        rows.append(dict(user_id=s.id, username=s.username, is_demo=s.is_demo, goal_id=scope.goal_id,
                         attempts=len(mine), effective=sum(a.effective_day is not None for a in mine),
                         simulated=sum(a.simulated for a in mine),
                         accuracy=sum(a.correct for a in mine) / len(mine) if mine else None,
                         last_active=max((a.created_at for a in mine), default=None),
                         cells={n['id']: dict(mastery=n['mastery'], samples=n['samples'], status=n['status']) for n in nodes}))
        # Shared sticking point = the node the existing recommender sends this student to next (read-only, nothing recorded).
        recs = recommend(db, s, scope, now=now)['recommendations']
        if recs and mine:
            top = recs[0]['knowledge_id']
            stuck[top]['students'].append(s.username)
            stuck[top]['blocks'] |= {n['id'] for n in nodes if top in n['missing_prerequisites']}
    graph_nodes = knowledge_view(db, ctx.user.id, scope_for(db, ctx.user.id, cid)) if ids else []
    names = {n['id']: n['name'] for n in graph_nodes}
    week = now - timedelta(days=7)
    summary = []
    for n in graph_nodes:
        cells = [views[s.id][n['id']] for s in students]
        assessed = [c for c in cells if c['samples']]
        summary.append(dict(knowledge_id=n['id'], name=n['name'], chapter=n['chapter'], prerequisites=n['prerequisites'],
                            assessed=len(assessed), passed=sum(c['status'] == '已通过' for c in cells),
                            low=sum(c['mastery'] is not None and c['samples'] >= 3 and c['mastery'] < LOW_MASTERY for c in cells),
                            average_mastery=sum(c['mastery'] for c in assessed) / len(assessed) if assessed else None,
                            attempts_7d=sum(1 for s in students for a in attempts[s.id] if a.knowledge_id == n['id'] and a.created_at >= week)))
    sticking = sorted(({'knowledge_id': k, 'name': names.get(k, k), 'count': len(v['students']), 'students': sorted(v['students']),
                        'blocks': [names[b] for b in sorted(v['blocks']) if b in names]} for k, v in stuck.items()),
                      key=lambda x: (-x['count'], x['knowledge_id']))
    mistakes = []
    if students and ids:
        rows_m = db.execute(select(Question, func.sum(Mistake.error_count), func.count(Mistake.user_id))
                            .join(Mistake, Mistake.question_id == Question.id)
                            .where(Mistake.user_id.in_([s.id for s in students]), Question.knowledge_id.in_(ids))
                            .group_by(Question.id).order_by(func.sum(Mistake.error_count).desc(), Question.id).limit(10)).all()
        mistakes = [dict(question_id=q.id, knowledge_id=q.knowledge_id, knowledge=names.get(q.knowledge_id, q.knowledge_id),
                         stem=q.stem[:160], errors=int(errors), students=int(learners)) for q, errors, learners in rows_m]
    return dict(course=dict(id=cid, name=ctx.course.name), generated_at=now, low_mastery_threshold=LOW_MASTERY,
                knowledge=[dict(id=n['id'], name=n['name'], chapter=n['chapter']) for n in graph_nodes],
                students=rows, summary=summary, sticking_points=sticking, frequent_mistakes=mistakes,
                simulated_students=sum(r['simulated'] > 0 for r in rows))
