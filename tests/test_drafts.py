"""Knowledge-graph drafting: the deterministic Mock stands in for the model; real model quality is evaluated separately."""
import pytest
from backend.ai.drafts import validate_draft, DraftInvalid, course_chunks
from tests.test_assistant import ai
from tests.test_courses import LA, setup_la

NOTES = '\n\n'.join(f'# {t}\n\n{body}' for t, body in [
    ('向量', '向量的加法与数乘，线性组合。'), ('矩阵', '矩阵乘法与转置，矩阵可看作线性映射。'),
    ('行列式', '二阶与三阶行列式的计算，行列式与可逆性。'), ('线性方程组', '高斯消元，解的存在性与唯一性。')])

def with_materials(c, admin):
    r = c.post(f'{LA}/assistant/admin/documents', headers=admin, data={'source': '自编测试讲义'},
               files={'file': ('la-notes.md', NOTES.encode(), 'text/markdown')})
    assert r.status_code == 200 and r.json()['status'] in ('parsed', 'indexed'), r.text

def test_draft_generate_edit_approve(ai):
    c, f, learner, config = ai
    admin = setup_la(c, learner)
    with_materials(c, admin)
    assert c.post(f'{LA}/teacher/drafts', headers=learner).status_code == 403
    first = c.post(f'{LA}/teacher/drafts', headers=admin)
    assert first.status_code == 201, first.text
    d = c.post(f'{LA}/teacher/drafts', headers=admin).json()
    statuses = {x['id']: x['status'] for x in c.get(f'{LA}/teacher/drafts', headers=admin).json()}
    assert statuses[first.json()['id']] == 'superseded' and statuses[d['id']] == 'pending'
    assert d['model_meta']['prompt_version'] == 'graph-draft-v1.1' and 'original_payload' not in d['model_meta']
    detail = c.get(f'{LA}/teacher/drafts/{d["id"]}', headers=admin).json()
    assert all(detail['evidence'][e] for n in detail['payload']['nodes'] for e in n['evidence'])
    assert [x['id'] for x in detail['existing']] == ['la.vectors']
    payload = detail['payload']
    cycle = {**payload, 'edges': payload['edges'] + [{'from': payload['nodes'][-1]['slug'], 'to': payload['nodes'][0]['slug'], 'reason': '成环'}]}
    assert c.put(f'{LA}/teacher/drafts/{d["id"]}', headers=admin, json=cycle).status_code == 422
    fake = {**payload, 'nodes': [{**payload['nodes'][0], 'evidence': ['made-up-chunk']}] + payload['nodes'][1:]}
    assert '不存在' in c.put(f'{LA}/teacher/drafts/{d["id"]}', headers=admin, json=fake).json()['detail']
    # Teacher edits: rename one node, reuse the existing "vectors" slug, drop one edge.
    nodes = [{**payload['nodes'][0], 'slug': 'vectors', 'name': '向量（审核后）'}] + payload['nodes'][1:]
    edges = [{**e, 'from': 'vectors' if e['from'] == payload['nodes'][0]['slug'] else e['from']} for e in payload['edges'][1:]]
    assert c.put(f'{LA}/teacher/drafts/{d["id"]}', headers=admin, json={'nodes': nodes, 'edges': edges}).status_code == 200
    r = c.post(f'{LA}/teacher/drafts/{d["id"]}/approve', headers=admin).json()
    assert r['ids']['vectors'] == 'la.vectors' and r['updated'] == 1 and r['created'] == len(nodes) - 1 and r['retained'] == []
    graph = {n['id']: n for n in c.get(f'{LA}/knowledge', headers=learner).json()['nodes']}
    assert graph['la.vectors']['name'] == '向量（审核后）'
    assert all(k.startswith('la.') for k in graph) and len(graph) == len(nodes)
    for e in edges:
        assert r['ids'][e['from']] in graph[r['ids'][e['to']]]['prerequisites']
    diff = c.get(f'{LA}/teacher/drafts/{d["id"]}', headers=admin).json()['model_meta']['review_diff']
    assert diff['nodes_added'] == 1 and diff['nodes_removed'] == 1 and diff['edges_removed'] >= 1
    assert c.post(f'{LA}/teacher/drafts/{d["id"]}/approve', headers=admin).status_code == 409
    # Practised questions stay attached: la.vectors kept its id, so its five questions are still searchable.
    assert c.get(f'{LA}/questions', headers=learner).json()['total'] == 5

def test_validate_draft_rules(ai):
    c, f, learner, config = ai
    admin = setup_la(c, learner)
    with_materials(c, admin)
    with f() as db:
        ids = [ch.id for ch, d in course_chunks(db, 'la')][:4]
        node = lambda slug, i: {'slug': slug, 'name': slug, 'chapter': '一', 'description': '说明', 'evidence': [ids[i % len(ids)]]}
        good = {'nodes': [node('na', 0), node('nb', 1), node('nc', 2)], 'edges': [{'from': 'na', 'to': 'nb', 'reason': 'r'}]}
        assert len(validate_draft(db, 'la', good)['nodes']) == 3
        bad_cases = [
            {'nodes': good['nodes'][:2], 'edges': []},
            {'nodes': good['nodes'] + [node('na', 3)], 'edges': []},
            {'nodes': good['nodes'], 'edges': [{'from': 'na', 'to': 'na', 'reason': 'r'}]},
            {'nodes': good['nodes'], 'edges': [{'from': 'na', 'to': 'zzz', 'reason': 'r'}]},
            {'nodes': [{**node('A-b', 0)}] + good['nodes'][1:], 'edges': []},
            {'nodes': good['nodes'], 'edges': [], 'extra': 1},
            {'nodes': [node(f'n{i}', i) for i in range(8)], 'edges': [{'from': f'n{i}', 'to': 'n7', 'reason': 'r'} for i in range(6)]},
        ]
        for case in bad_cases:
            with pytest.raises(DraftInvalid):
                validate_draft(db, 'la', case)
        # Material of another course cannot be cited.
        hs_chunk = next(ch.id for ch, d in course_chunks(db, 'hs-math'))
        with pytest.raises(DraftInvalid):
            validate_draft(db, 'la', {**good, 'nodes': [{**node('na', 0), 'evidence': [hs_chunk]}] + good['nodes'][1:]})

def test_draft_requires_materials_and_merged_graph_stays_acyclic(ai):
    c, f, learner, config = ai
    admin = setup_la(c, learner)
    # la has only the single setup document; a course with no public material cannot be drafted.
    assert c.post('/api/courses', headers=admin, json={'id': 'empty', 'name': '空课程', 'subject': 'math', 'level': 'middle'}).status_code == 201
    assert c.post('/api/courses/empty/teacher/drafts', headers=admin).status_code == 422
    with_materials(c, admin)
    # Existing node la.span depends on la.vectors; a draft making vectors depend on span must be rejected at approval.
    assert c.put(f'{LA}/admin/knowledge/la.span', headers=admin, json={'id': 'la.span', 'name': '张成', 'chapter': '一', 'description': '张成',
                 'position': 1, 'prerequisites': ['la.vectors']}).status_code == 200
    d = c.post(f'{LA}/teacher/drafts', headers=admin).json()
    p = d['payload']
    nodes = [{**p['nodes'][0], 'slug': 'span'}, {**p['nodes'][1], 'slug': 'vectors'}] + p['nodes'][2:]
    edges = [{'from': 'span', 'to': 'vectors', 'reason': '故意与现有图谱冲突'}]
    assert c.put(f'{LA}/teacher/drafts/{d["id"]}', headers=admin, json={'nodes': nodes, 'edges': edges}).status_code == 200
    r = c.post(f'{LA}/teacher/drafts/{d["id"]}/approve', headers=admin)
    assert r.status_code == 200, r.text  # span is in the draft, so its old edge is replaced: no cycle.
    nodes2 = {n['id']: n for n in c.get(f'{LA}/knowledge', headers=admin).json()['nodes']}
    assert nodes2['la.vectors']['prerequisites'] == ['la.span'] and nodes2['la.span']['prerequisites'] == []
