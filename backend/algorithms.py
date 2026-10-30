"""Deterministic, auditable heuristics. No learned parameters or ML claims."""
from datetime import datetime, timezone
from sqlalchemy import select
from .models import Knowledge, Prerequisite, Mastery, Attempt, Mistake, utcnow
from .config import PASS_MASTERY, PASS_DISTINCT, WINDOW, VERSION

def graph(db):
    nodes = list(db.scalars(select(Knowledge).order_by(Knowledge.position, Knowledge.id)))
    edges = {n.id: [] for n in nodes}
    for e in db.scalars(select(Prerequisite)):
        edges[e.knowledge_id].append(e.prerequisite_id)
    for p in edges.values():
        p.sort()
    return nodes, edges

def validate_dag(edges):
    visiting, visited = set(), set()
    def visit(k):
        if k in visiting:
            raise ValueError('先修关系存在环路')
        if k in visited:
            return
        if k not in edges:
            raise ValueError('先修知识点不存在')
        visiting.add(k)
        for p in edges[k]:
            visit(p)
        visiting.remove(k)
        visited.add(k)
    for k in edges:
        visit(k)

def own_pass(m):
    return bool(m and m.samples >= PASS_DISTINCT and m.distinct_count >= PASS_DISTINCT and m.value >= PASS_MASTERY)

def current_pass(k, states, edges, memo=None):
    memo = {} if memo is None else memo
    if k not in memo:
        memo[k] = own_pass(states.get(k)) and all(current_pass(p, states, edges, memo) for p in edges[k])
    return memo[k]

def recompute(db, user_id):
    """Rebuild caches AND historical achievements by replaying effective attempts."""
    nodes, edges = graph(db)
    states = {}
    for n in nodes:
        m = db.get(Mastery, (user_id, n.id))
        if m is None:
            m = Mastery(user_id=user_id, knowledge_id=n.id)
            db.add(m)
        m.value, m.samples, m.distinct_count, m.last_effective_at = None, 0, 0, None
        # Preserve awarded achievements if an administrator later changes a prerequisite.
        m.difficulty_level, m.last_adjusted_count = 1, 0
        states[n.id] = m
    windows = {n.id: [] for n in nodes}
    totals = {n.id: 0 for n in nodes}
    attempts = list(db.scalars(select(Attempt).where(Attempt.user_id == user_id).order_by(Attempt.created_at, Attempt.id)))
    for a in attempts:
        if a.effective_day is None:
            continue
        rows = windows[a.knowledge_id]
        rows.append(a)
        del rows[:-WINDOW]
        totals[a.knowledge_id] += 1
        m = states[a.knowledge_id]
        m.samples = len(rows)
        m.distinct_count = len({r.question_id for r in rows})
        m.value = (sum(r.correct for r in rows) + 1) / (len(rows) + 2)
        m.last_effective_at = a.created_at
        total = totals[a.knowledge_id]
        if total >= 5 and total - m.last_adjusted_count >= 3:
            recent = rows[-8:]
            rate = sum(r.correct for r in recent) / len(recent)
            desired = 3 if len(recent) >= 8 and rate >= .85 and m.value >= .8 else (2 if rate >= .7 else 1)
            m.difficulty_level += (desired > m.difficulty_level) - (desired < m.difficulty_level)
            m.last_adjusted_count = total
        # Multi-prerequisite nodes may earn their award when another prerequisite passes.
        for n in nodes:
            if states[n.id].passed_at is None and current_pass(n.id, states, edges):
                states[n.id].passed_at = a.created_at
    db.flush()
    return states

def knowledge_view(db, user_id):
    nodes, edges = graph(db)
    states = {m.knowledge_id: m for m in db.scalars(select(Mastery).where(Mastery.user_id == user_id))}
    result = []
    for n in nodes:
        m = states.get(n.id)
        missing = [p for p in edges[n.id] if not current_pass(p, states, edges)]
        passed = bool(m and m.passed_at)
        status = '未评估' if not m or not m.samples else '学习中'
        if passed:
            status = '已通过' if current_pass(n.id, states, edges) else '建议复习'
        result.append(dict(id=n.id, name=n.name, chapter=n.chapter, subject=n.subject, description=n.description,
                           position=n.position, prerequisites=edges[n.id], missing_prerequisites=missing,
                           mastery=m.value if m else None, samples=m.samples if m else 0,
                           distinct_count=m.distinct_count if m else 0, passed_at=m.passed_at.isoformat() if passed else None,
                           status=status, available=passed or not missing,
                           difficulty=m.difficulty_level if m else 1,
                           last_effective_at=m.last_effective_at.isoformat() if m and m.last_effective_at else None))
    return result

def recommend(db, user, now=None):
    now = now or utcnow()
    nodes = knowledge_view(db, user.id)
    by_id = {n['id']: n for n in nodes}
    goal = user.goal_id
    ancestors = set()
    def collect(k):
        for p in by_id[k]['prerequisites']:
            if p not in ancestors:
                ancestors.add(p)
                collect(p)
    if goal in by_id:
        collect(goal)
    ranked = []
    for n in nodes:
        # Even historical achievements do not bypass prerequisite repair for recommendations.
        if n['missing_prerequisites']:
            continue
        cold = n['mastery'] is None
        weakness = 0.6 if cold else 1 - n['mastery']
        days = 0 if cold else max(0, (now - datetime.fromisoformat(n['last_effective_at'])).total_seconds() / 86400)
        urgency = 0 if cold else min(1, days / 7)
        relevance = 0.5 if not goal else (1 if n['id'] == goal else (.8 if n['id'] in ancestors else .2))
        contributions = dict(weakness=round(.5 * weakness, 6), urgency=round(.3 * urgency, 6), goal=round(.2 * relevance, 6))
        reason = f'尚未评估{n["name"]}，先完成基础诊断，积累有效样本。' if cold else f'{n["name"]}掌握度为 {n["mastery"]:.0%}（{n["samples"]} 条有效样本），距上次有效练习 {days:.1f} 天。'
        if n['id'] in ancestors:
            reason += f'这是学习{by_id[goal]["name"]}的先修知识点，建议先巩固这里。'
        ranked.append(dict(knowledge_id=n['id'], name=n['name'], score=round(sum(contributions.values()), 6),
                           factors=dict(weakness=weakness, urgency=urgency, goal=relevance), contributions=contributions,
                           cold_start=cold, reason=reason, difficulty=n['difficulty'], position=n['position'], version=VERSION))
    ranked.sort(key=lambda r: (-r['score'], r['position'], r['knowledge_id']))
    fixed = next((n for n in nodes if not n['passed_at']), nodes[0] if nodes else None)
    return dict(version=VERSION, goal_id=goal, default_rule='未设置目标时相关度统一为 0.5；冷启动按先修约束和稳定章节顺序诊断。',
                recommendations=ranked, fixed_order_next=fixed['id'] if fixed else None,
                goal_gaps=by_id[goal]['missing_prerequisites'] if goal in by_id else [])

def rebuild_mistakes(db, user_id):
    for m in list(db.scalars(select(Mistake).where(Mistake.user_id == user_id))):
        db.delete(m)
    db.flush()
    cache = {}
    for a in db.scalars(select(Attempt).where(Attempt.user_id == user_id).order_by(Attempt.created_at, Attempt.id)):
        if not a.correct:
            m = cache.get(a.question_id)
            if m is None:
                m = Mistake(user_id=user_id, question_id=a.question_id, error_count=0)
                cache[a.question_id] = m
                db.add(m)
            m.error_count += 1
            m.last_error_at, m.reviewed_at = a.created_at, None
        elif a.question_id in cache:
            cache[a.question_id].reviewed_at = a.created_at
    db.flush()
