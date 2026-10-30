"""Static checks of course data packages under data/courses and of the import script's helpers."""
import json
import re
import sys
from pathlib import Path
import pytest
from backend.schemas import QuestionInput, CourseInput
from backend.algorithms import validate_dag
from backend.ai.drafts import DraftPayload

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import import_course  # noqa: E402

COURSES = sorted(p for p in (ROOT / 'data' / 'courses').iterdir() if (p / 'course.json').exists())

@pytest.mark.parametrize('course', COURSES, ids=lambda p: p.name)
def test_course_package_is_consistent(course):
    meta = CourseInput.model_validate(json.loads((course / 'course.json').read_text('utf-8')))
    graph = json.loads((course / 'graph.json').read_text('utf-8'))
    slugs = [n['slug'] for n in graph['nodes']]
    assert len(set(slugs)) == len(slugs) and all(len(f'{meta.id}.{s}') <= 50 for s in slugs)
    validate_dag({s: [e['from'] for e in graph['edges'] if e['to'] == s] for s in slugs})
    headings = {h.strip() for f in (course / 'notes').glob('*.md') for h in re.findall(r'^# (.+)$', f.read_text('utf-8'), re.M)}
    assert {h for n in graph['nodes'] for h in n['evidence']} <= headings
    # The reference graph must also pass the same validation a model draft goes through (evidence as placeholder ids).
    DraftPayload.model_validate({'nodes': [n | {'evidence': ['x']} for n in graph['nodes']], 'edges': graph['edges']})
    questions = json.loads((course / 'questions.json').read_text('utf-8'))
    per = {s: 0 for s in slugs}
    for q in questions:
        per[q['knowledge']] += 1
        QuestionInput.model_validate({k: v for k, v in q.items() if k != 'knowledge'} | {'knowledge_id': f'{meta.id}.{q["knowledge"]}'})
    # Passing needs >= pass_distinct distinct questions per node (default 5).
    assert min(per.values()) >= 5, per
    for case in json.loads((course / 'eval_cases.json').read_text('utf-8')):
        assert set(case['expected_headings']) <= headings

def test_linalg_questions_are_reproducible():
    import build_linalg_questions
    assert build_linalg_questions.build() == json.loads((ROOT / 'data/courses/linalg/questions.json').read_text('utf-8'))

def test_draft_scoring_matches_by_evidence():
    graph = {'nodes': [{'slug': 'a', 'evidence': ['A']}, {'slug': 'b', 'evidence': ['B']}, {'slug': 'c', 'evidence': ['C']}],
             'edges': [{'from': 'a', 'to': 'b'}, {'from': 'b', 'to': 'c'}]}
    by_title = {'A': ['a1', 'a2'], 'B': ['b1'], 'C': ['c1']}
    draft = {'nodes': [{'slug': 'x1', 'evidence': ['a1']}, {'slug': 'x2', 'evidence': ['a2']}, {'slug': 'y', 'evidence': ['b1']},
                       {'slug': 'z', 'evidence': ['c1']}, {'slug': 'junk', 'evidence': ['zz']}],
             'edges': [{'from': 'x1', 'to': 'x2'}, {'from': 'x2', 'to': 'z'}, {'from': 'z', 'to': 'y'}]}
    s = import_course.score(draft, graph, by_title)
    # x1/x2 both map to a (finer granularity), junk maps to nothing; z->y is the reversed reference edge b->c.
    assert s['node_recall'] == 1.0 and s['node_precision'] == 0.8
    assert s['reversed_edges'] == 1 and s['edge_recall'] == 0.0 and s['edge_precision'] == 0.0
    payload = import_course.reference_payload({'nodes': [{'slug': 'a', 'name': 'n', 'chapter': 'c', 'description': 'd', 'evidence': ['A']}], 'edges': []}, by_title)
    assert payload['nodes'][0]['evidence'] == ['a1', 'a2']
