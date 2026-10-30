"""Set up a course through the public HTTP API only: no application code changes are needed to add a course.

Course directory layout (see data/courses/linalg): course.json, notes/*.md, graph.json (teacher-reviewed reference
graph; node evidence = note headings), questions.json (knowledge referenced by slug).

  --graph reference : write the reference graph through the staff knowledge API (no model call)
  --graph draft     : let the model draft the graph from the notes N times, score each draft against the reference,
                      then act as the reviewing teacher: replace the draft with the reference graph and approve it,
                      so the draft endpoint records how much the teacher had to change.

Example:
  python scripts/import_course.py data/courses/linalg --api http://127.0.0.1:8013 --graph draft --draft-runs 3 \
      --students alice,bob --out evals/linalg-acceptance
"""
import argparse
import json
import os
import sys
from pathlib import Path
import httpx

def main():
    p = argparse.ArgumentParser()
    p.add_argument('course_dir'); p.add_argument('--api', default='http://127.0.0.1:8000')
    p.add_argument('--username', default='demo_admin'); p.add_argument('--password', default=os.getenv('COURSE_ADMIN_PASSWORD', 'DemoMath2026!'))
    p.add_argument('--graph', choices=['reference', 'draft'], default='reference'); p.add_argument('--draft-runs', type=int, default=1)
    p.add_argument('--students', default=''); p.add_argument('--rebuild-index', action='store_true'); p.add_argument('--out', default='')
    a = p.parse_args()
    root = Path(a.course_dir)
    course, graph = json.loads((root / 'course.json').read_text('utf-8')), json.loads((root / 'graph.json').read_text('utf-8'))
    questions = json.loads((root / 'questions.json').read_text('utf-8'))
    c = httpx.Client(base_url=a.api, timeout=180)
    token = c.post('/api/auth/login', json={'username': a.username, 'password': a.password}).raise_for_status().json()['token']
    c.headers['Authorization'] = f'Bearer {token}'
    cid = course['id']; base = f'/api/courses/{cid}'; report = {'course': cid}

    r = c.post('/api/courses', json=course)
    if r.status_code not in (201, 409):
        sys.exit(f'create course failed: {r.text}')
    report['course_created'] = r.status_code == 201

    uploaded = []
    for f in sorted((root / 'notes').glob('*.md')):
        r = c.post(f'{base}/assistant/admin/documents', data={'source': f'{course["name"]} 自编讲义'}, files={'file': (f.name, f.read_bytes(), 'text/markdown')})
        if r.status_code == 422 and '已经导入' in r.text:
            continue
        r.raise_for_status()
        if r.json()['status'] == 'failed':
            sys.exit(f'{f.name}: {r.json()["error"]}')
        uploaded.append(f.name)
    report['notes_uploaded'] = uploaded
    if a.rebuild_index:
        report['index'] = c.post(f'{base}/assistant/admin/index/rebuild').raise_for_status().json()

    if a.graph == 'reference':
        ids = apply_reference(c, base, cid, graph)
    else:
        runs = []
        for _ in range(a.draft_runs):
            d = c.post(f'{base}/teacher/drafts')
            if d.status_code != 201:
                runs.append({'error': d.status_code, 'detail': d.text[:300]}); continue
            detail = c.get(f'{base}/teacher/drafts/{d.json()["id"]}').json()
            runs.append({'draft_id': detail['id'], 'meta': detail['model_meta'], 'payload': detail['payload'],
                         'quality': score(detail['payload'], graph, chunk_ids(detail['chunks']))})
        report['drafts'] = runs
        last = next((x for x in reversed(runs) if 'draft_id' in x), None)
        if not last:
            sys.exit('no valid draft: ' + json.dumps(runs, ensure_ascii=False)[:600])
        detail = c.get(f'{base}/teacher/drafts/{last["draft_id"]}').json()
        reviewed = reference_payload(graph, chunk_ids(detail['chunks']))
        c.put(f'{base}/teacher/drafts/{last["draft_id"]}', json=reviewed).raise_for_status()
        approved = c.post(f'{base}/teacher/drafts/{last["draft_id"]}/approve').raise_for_status().json()
        report['review_diff'] = c.get(f'{base}/teacher/drafts/{last["draft_id"]}').json()['review_diff']
        ids = approved['ids']
    report['knowledge_ids'] = ids

    items = [{k: v for k, v in q.items() if k != 'knowledge'} | {'knowledge_id': ids[q['knowledge']]} for q in questions]
    existing = c.get(f'{base}/admin/questions').raise_for_status().json()
    if not existing:
        report['questions_imported'] = c.post(f'{base}/admin/questions/import', json=items).raise_for_status().json()['imported']
    for name in filter(None, a.students.split(',')):
        c.post(f'{base}/members', json={'username': name}).raise_for_status()
    report['students'] = [x for x in a.students.split(',') if x]
    text = json.dumps(report, ensure_ascii=False, indent=1, default=str)
    if a.out:
        Path(a.out).mkdir(parents=True, exist_ok=True); (Path(a.out) / 'import.json').write_text(text, 'utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('drafts', 'knowledge_ids')} |
                     {'draft_quality': [r.get('quality') or r for r in report.get('drafts', [])]}, ensure_ascii=False, indent=1, default=str))

def chunk_ids(chunks):
    by_title = {}
    for ch in chunks:
        by_title.setdefault(ch['title'], []).append(ch['id'])
    return by_title

def reference_payload(graph, by_title):
    nodes = [{k: n[k] for k in ('slug', 'name', 'chapter', 'description')} | {'evidence': [i for t in n['evidence'] for i in by_title[t]][:10]}
             for n in graph['nodes']]
    return {'nodes': nodes, 'edges': graph['edges']}

def apply_reference(c, base, cid, graph):
    # Parents first, so every prerequisite exists when its dependant is saved.
    done, ids, edges = set(), {}, {n['slug']: [e['from'] for e in graph['edges'] if e['to'] == n['slug']] for n in graph['nodes']}
    order = []
    while len(order) < len(graph['nodes']):
        for n in graph['nodes']:
            if n['slug'] not in done and all(p in done for p in edges[n['slug']]):
                done.add(n['slug']); order.append(n)
    for pos, n in enumerate(order):
        kid = ids[n['slug']] = f'{cid}.{n["slug"]}'
        body = {'id': kid, 'name': n['name'], 'chapter': n['chapter'], 'description': n['description'], 'position': pos,
                'prerequisites': [f'{cid}.{p}' for p in edges[n['slug']]]}
        c.put(f'{base}/admin/knowledge/{kid}', json=body).raise_for_status()
    return ids

def score(draft, graph, by_title):
    """Match each draft node to the reference node whose evidence chunks it overlaps most, then compare edges."""
    ref_chunks = {n['slug']: {i for t in n['evidence'] for i in by_title.get(t, [])} for n in graph['nodes']}
    match = {}
    for d in draft['nodes']:
        overlaps = sorted(((len(set(d['evidence']) & chunks), slug) for slug, chunks in ref_chunks.items()), reverse=True)
        if overlaps and overlaps[0][0] and (len(overlaps) == 1 or overlaps[0][0] > overlaps[1][0]):
            match[d['slug']] = overlaps[0][1]
    ref_edges = {(e['from'], e['to']) for e in graph['edges']}
    mapped = {(match[e['from']], match[e['to']]) for e in draft['edges'] if e['from'] in match and e['to'] in match and match[e['from']] != match[e['to']]}
    # Reachability: a reference edge also counts when the draft implies it through a longer chain.
    reach = {s: set() for s in ref_chunks}
    for f, t in mapped: reach[t].add(f)
    def ancestors(s, seen=None):
        seen = set() if seen is None else seen
        for p in reach[s]:
            if p not in seen: seen.add(p); ancestors(p, seen)
        return seen
    covered = set(match.values())
    return dict(draft_nodes=len(draft['nodes']), draft_edges=len(draft['edges']), reference_nodes=len(ref_chunks), reference_edges=len(ref_edges),
                node_recall=round(len(covered) / len(ref_chunks), 3), node_precision=round(len(match) / max(1, len(draft['nodes'])), 3),
                edge_precision=round(len(mapped & ref_edges) / max(1, len(mapped)), 3), edge_recall=round(len(mapped & ref_edges) / len(ref_edges), 3),
                edge_reachability_recall=round(sum(f in ancestors(t) for f, t in ref_edges) / len(ref_edges), 3),
                reversed_edges=len({(t, f) for f, t in mapped} & ref_edges))

if __name__ == '__main__':
    main()
