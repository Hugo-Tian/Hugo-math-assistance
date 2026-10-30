"""Course isolation and course-role permissions. 'la' is a second course created through the public API."""
import uuid
import pytest
from backend.ai.tools import execute_tool
from backend.ai.plans import validate_plan
from backend.courses import scope_for
from backend.models import User
from tests.test_assistant import ai, new, send

LA = '/api/courses/la'

def login(c, username, password='Password123!'):
    r = c.post('/api/auth/login', json={'username': username, 'password': password})
    assert r.status_code == 200, r.text
    return {'Authorization': f'Bearer {r.json()["token"]}'}

def register(c, username):
    r = c.post('/api/auth/register', json={'username': username, 'password': 'Password123!'})
    assert r.status_code == 201, r.text
    return {'Authorization': f'Bearer {r.json()["token"]}'}

def la_questions(n=5):
    return [dict(knowledge_id='la.vectors', stem=f'向量题 {i}：设 u=({i},1)，求 2u 的第一个分量。', options=[str(2*i+k) for k in (0, 10, 20, 30)],
                 answer=0, explanation='数乘逐分量相乘。', difficulty=1, source='自编测试题') for i in range(1, n+1)]

def setup_la(c, learner):
    admin = login(c, 'admin')
    assert c.post('/api/courses', headers=admin, json={'id': 'la', 'name': '线性代数', 'subject': 'math', 'level': 'university'}).status_code == 201
    r = c.put(f'{LA}/admin/knowledge/la.vectors', headers=admin, json={'id': 'la.vectors', 'name': '向量', 'chapter': '第一章',
              'description': '向量及其线性运算', 'position': 0, 'prerequisites': []})
    assert r.status_code == 200, r.text
    assert c.post(f'{LA}/admin/questions/import', headers=admin, json=la_questions()).status_code == 200
    r = c.post(f'{LA}/assistant/admin/documents', headers=admin, data={'source': '自编测试资料', 'knowledge_id': 'la.vectors'},
               files={'file': ('vectors.md', '# 向量\n\n向量的线性组合与张成空间。唯一测试短语：蓝色矩阵。'.encode(), 'text/markdown')})
    assert r.status_code == 200 and r.json()['status'] in ('parsed', 'indexed'), r.text
    assert c.post(f'{LA}/members', headers=admin, json={'username': 'learner'}).status_code == 200
    return admin

def test_course_roles_and_membership(env, learner):
    c, _ = env
    assert c.post('/api/courses', headers=learner, json={'id': 'la', 'name': '线性代数', 'subject': 'math', 'level': 'university'}).status_code == 403
    # Not yet a member: the course is invisible, not merely forbidden.
    admin = login(c, 'admin')
    assert c.post('/api/courses', headers=admin, json={'id': 'la', 'name': '线性代数', 'subject': 'math', 'level': 'university'}).status_code == 201
    assert [x['id'] for x in c.get('/api/courses', headers=learner).json()] == ['hs-math']
    assert c.get(f'{LA}/knowledge', headers=learner).status_code == 404
    assert c.post(f'{LA}/join', headers=learner).status_code == 404
    assert c.post(f'{LA}/members', headers=admin, json={'username': 'learner'}).status_code == 200
    assert sorted(x['id'] for x in c.get('/api/courses', headers=learner).json()) == ['hs-math', 'la']
    assert c.get(f'{LA}/knowledge', headers=learner).json()['nodes'] == []
    # Students cannot use staff endpoints; a teacher of one course is only a student elsewhere.
    assert c.get(f'{LA}/admin/questions', headers=learner).status_code == 403
    teacher = register(c, 'teacher_la')
    assert c.post(f'{LA}/members', headers=admin, json={'username': 'teacher_la', 'role': 'teacher'}).status_code == 200
    assert c.get(f'{LA}/admin/questions', headers=teacher).status_code == 200
    assert c.get('/api/admin/questions', headers=teacher).status_code == 403
    assert c.post(f'{LA}/members', headers=learner, json={'username': 'learner', 'role': 'teacher'}).status_code == 403

def test_knowledge_graph_stays_inside_course(env, learner):
    c, _ = env
    admin = setup_la(c, learner)
    body = lambda kid, pre: {'id': kid, 'name': '张成', 'chapter': '第一章', 'description': '张成空间', 'position': 1, 'prerequisites': pre}
    assert c.put(f'{LA}/admin/knowledge/span', headers=admin, json=body('span', [])).status_code == 422
    assert c.put(f'{LA}/admin/knowledge/la.span', headers=admin, json=body('la.span', ['sets'])).status_code == 422
    assert c.put(f'{LA}/admin/knowledge/sets', headers=admin, json=body('sets', [])).status_code == 409
    assert c.put(f'{LA}/admin/knowledge/la.span', headers=admin, json=body('la.span', ['la.vectors'])).status_code == 200
    nodes = c.get(f'{LA}/knowledge', headers=learner).json()['nodes']
    assert [n['id'] for n in nodes] == ['la.vectors', 'la.span'] and nodes[1]['prerequisites'] == ['la.vectors']
    assert all(n['id'] not in ('la.vectors', 'la.span') for n in c.get('/api/knowledge', headers=learner).json()['nodes'])
    bad = la_questions(1)[0] | {'auxiliary_ids': ['sets']}
    assert c.post(f'{LA}/admin/questions/import', headers=admin, json=[bad]).status_code == 422

def test_practice_report_and_goal_isolation(env, learner):
    c, _ = env
    setup_la(c, learner)
    la_ids = {q['id'] for q in c.get(f'{LA}/questions', headers=learner).json()['items']}
    assert len(la_ids) == 5
    assert not la_ids & {q['id'] for q in c.get('/api/questions', headers=learner).json()['items']}
    assert c.post(f'{LA}/sessions', headers=learner, json={'mode': 'custom', 'knowledge_id': 'sets', 'count': 1}).status_code == 422
    hs = c.post('/api/sessions', headers=learner, json={'mode': 'custom', 'knowledge_id': 'sets', 'count': 1}).json()
    assert c.get(f'{LA}/sessions/{hs["id"]}', headers=learner).status_code == 404
    s = c.post(f'{LA}/sessions', headers=learner, json={'mode': 'custom', 'knowledge_id': 'la.vectors', 'count': 1}).json()
    q = s['question']
    assert q['id'] in la_ids
    wrong = {'question_id': q['id'], 'selected': 1, 'idempotency_key': str(uuid.uuid4())}
    assert c.post(f'/api/sessions/{s["id"]}/answers', headers=learner, json=wrong).status_code == 404
    assert c.post(f'{LA}/sessions/{s["id"]}/answers', headers=learner, json=wrong).json()['correct'] is False
    assert c.get(f'{LA}/report', headers=learner).json()['total'] == 1
    assert c.get('/api/report', headers=learner).json()['total'] == 0
    assert [m['question']['id'] for m in c.get(f'{LA}/mistakes', headers=learner).json()] == [q['id']]
    assert c.get('/api/mistakes', headers=learner).json() == []
    assert c.put(f'{LA}/me/goal', headers=learner, json={'knowledge_id': 'sets'}).status_code == 422
    assert c.put(f'{LA}/me/goal', headers=learner, json={'knowledge_id': 'la.vectors'}).json()['goal_id'] == 'la.vectors'
    assert c.get('/api/me', headers=learner).json()['goal_id'] is None
    assert all(r['knowledge_id'].startswith('la.') for r in c.get(f'{LA}/recommendations', headers=learner).json()['recommendations'])

def test_assistant_retrieval_tools_and_guard_isolation(ai):
    c, f, h, config = ai
    setup_la(c, h)
    # Course B's materials answer course B questions only, and the reverse.
    la_conv = c.post(f'{LA}/assistant/conversations', headers=h, json={}).json()['id']
    r = c.post(f'{LA}/assistant/conversations/{la_conv}/messages', headers=h,
               json={'message': '蓝色矩阵 向量', 'mode': 'rag', 'request_key': str(uuid.uuid4())}).json()
    assert r['status'] == 'completed' and r['citations'] and all(x['knowledge_id'] == 'la.vectors' for x in r['citations'])
    r = c.post(f'{LA}/assistant/conversations/{la_conv}/messages', headers=h,
               json={'message': '导数计算 幂函数求导', 'mode': 'rag', 'request_key': str(uuid.uuid4())}).json()
    assert r['status'] == 'insufficient_evidence' and '线性代数' in r['answer']
    assert c.get(f'/api/assistant/conversations/{la_conv}', headers=h).status_code == 404
    hs = send(c, h, new(c, h), message='蓝色矩阵 向量').json()
    assert all(x['knowledge_id'] != 'la.vectors' for x in hs['citations'])
    with f() as db:
        uid = db.query(User).filter_by(username='learner').one().id
        scope = scope_for(db, uid, 'la')
        found = execute_tool(db, uid, 'search_knowledge', {'query': '导数计算 幂函数求导'}, config, scope)
        assert found['evidence'] == []
        with pytest.raises(ValueError):
            execute_tool(db, uid, 'get_mastery', {'knowledge_id': 'sets'}, config, scope)
        plan = {'goal': '巩固', 'basis': ['测试'], 'days': [{'day': d, 'tasks': [{'knowledge_id': 'sets', 'question_count': 1, 'estimated_minutes': 10,
                'reason': '测试计划', 'question_ids': [], 'conditional_on_pass': False}]} for d in (1, 2, 3)]}
        with pytest.raises(ValueError):
            validate_plan(db, db.get(User, uid), plan, scope)
    # An unfinished practice guards only its own course.
    c.post('/api/sessions', headers=h, json={'mode': 'custom', 'knowledge_id': 'sets', 'count': 2})
    assert c.get('/api/assistant/status', headers=h).json()['assessment_open']
    assert not c.get(f'{LA}/assistant/status', headers=h).json()['assessment_open']

def test_teacher_dashboard_permissions_numbers_and_isolation(env, learner):
    c, f = env
    admin = setup_la(c, learner)
    assert c.get('/api/teacher/dashboard', headers=learner).status_code == 403
    s = c.post('/api/sessions', headers=learner, json={'mode': 'custom', 'knowledge_id': 'sets', 'count': 1}).json()
    from backend.models import Question
    with f() as db:
        answer = db.get(Question, s['question']['id']).answer
    c.post(f'/api/sessions/{s["id"]}/answers', headers=learner,
           json={'question_id': s['question']['id'], 'selected': (answer + 1) % 4, 'idempotency_key': str(uuid.uuid4())})
    d = c.get('/api/teacher/dashboard', headers=admin).json()
    row = next(r for r in d['students'] if r['username'] == 'learner')
    assert row['attempts'] == 1 and row['accuracy'] == 0 and row['cells']['sets']['samples'] == 1
    top = c.get('/api/recommendations', headers=learner).json()['recommendations'][0]['knowledge_id']
    assert any(p['knowledge_id'] == top and 'learner' in p['students'] for p in d['sticking_points'])
    assert d['frequent_mistakes'][0]['question_id'] == s['question']['id'] and d['frequent_mistakes'][0]['errors'] == 1
    sets = next(n for n in d['summary'] if n['knowledge_id'] == 'sets')
    assert sets['assessed'] == 1 and sets['attempts_7d'] == 1
    # The other course's dashboard sees the same student but none of the hs-math activity.
    la = c.get(f'{LA}/teacher/dashboard', headers=admin).json()
    assert [k['id'] for k in la['knowledge']] == ['la.vectors']
    assert next(r for r in la['students'] if r['username'] == 'learner')['attempts'] == 0
    assert la['frequent_mistakes'] == [] and la['sticking_points'] == []
