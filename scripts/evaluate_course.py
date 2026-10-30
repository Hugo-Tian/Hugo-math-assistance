"""Retrieval evaluation for an imported course (no model calls).

Builds a throw-away database holding the default course (with its notes, as cross-course distractors) and the target
course from its data directory, builds a vector index in a temporary directory, then runs the course's eval cases in
keyword / vector / hybrid modes, always scoped to the target course.

  python scripts/evaluate_course.py data/courses/linalg --out evals/linalg-retrieval
"""
import argparse
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def main():
    p = argparse.ArgumentParser(); p.add_argument('course_dir'); p.add_argument('--out', default=''); a = p.parse_args()
    root = Path(a.course_dir)
    work = Path(tempfile.mkdtemp(prefix='course-eval-', dir=ROOT / 'tmp'))
    os.environ['DATABASE_URL'] = f'sqlite:///{(work / "eval.db").as_posix()}'
    from sqlalchemy.orm import sessionmaker
    from backend.db import Base, make_engine
    from backend.seed import seed
    from backend.models import Course, Knowledge, Prerequisite, User
    from backend.courses import enroll
    from backend.security import passwords
    from backend.ai.materials import seed_materials
    from backend.ai.knowledge_base import import_document, rebuild_index, retrieve
    from backend.ai.drafts import course_chunks
    from backend.ai.settings import settings

    course, graph = json.loads((root / 'course.json').read_text('utf-8')), json.loads((root / 'graph.json').read_text('utf-8'))
    cases = json.loads((root / 'eval_cases.json').read_text('utf-8'))
    cid = course['id']
    engine = make_engine(os.environ['DATABASE_URL']); Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)
    # FAISS on Windows cannot open non-ASCII absolute paths (this repo lives under a Chinese folder); use a relative one.
    os.chdir(ROOT)
    config = settings(); config.index_dir = os.path.relpath(work / 'index', ROOT)
    with Session() as db:
        seed(db, demos=False); seed_materials(db)
        db.add(Course(**course)); db.flush()
        for f in sorted((root / 'notes').glob('*.md')):
            # Deterministic ids keep chunk ids stable across runs.
            import_document(db, f.name, f.read_bytes(), None, course['name'] + ' 自编讲义', document_id=f'{cid}-{f.stem}', course_id=cid)
        for pos, n in enumerate(graph['nodes']):
            db.add(Knowledge(id=f'{cid}.{n["slug"]}', course_id=cid, subject=course['subject'], chapter=n['chapter'], name=n['name'], description=n['description'], position=pos))
        db.flush()
        for e in graph['edges']:
            db.add(Prerequisite(knowledge_id=f'{cid}.{e["to"]}', prerequisite_id=f'{cid}.{e["from"]}'))
        u = User(username='course_eval', password_hash=passwords.hash(uuid.uuid4().hex), role='student'); db.add(u); db.flush()
        enroll(db, u.id, cid); db.commit()
        index = rebuild_index(db, config)
        by_title = {}
        for ch, d in course_chunks(db, cid):
            by_title.setdefault(ch.title, set()).add(ch.id)
        rows = []
        for case in cases:
            expected = set().union(*(by_title[t] for t in case['expected_headings'])) if case['expected_headings'] else set()
            for mode in ('keyword', 'vector', 'hybrid'):
                t0 = time.perf_counter()
                r = retrieve(db, u.id, case['input'], config, mode=mode, course_id=cid)
                recalled = [e['chunk_id'] for e in r['evidence']]
                rows.append(dict(id=case['id'], category=case['category'], mode=mode, recalled=recalled,
                                 foreign=[x for x in recalled if not x.startswith(cid + '-')],
                                 hit=int(bool(expected & set(recalled))) if expected else None,
                                 refused=int(not recalled) if not expected else None,
                                 ms=round((time.perf_counter() - t0) * 1000, 3)))
    engine.dispose()
    summary = {}
    for mode in ('keyword', 'vector', 'hybrid'):
        m = [r for r in rows if r['mode'] == mode]
        k = [r for r in m if r['hit'] is not None]; o = [r for r in m if r['category'] == 'insufficient']; x = [r for r in m if r['category'] == 'other_course']
        summary[mode] = dict(hit_at_k=f'{sum(r["hit"] for r in k)}/{len(k)}', refused_out_of_scope=f'{sum(r["refused"] for r in o)}/{len(o)}',
                             refused_other_course=f'{sum(r["refused"] for r in x)}/{len(x)}', foreign_chunks=sum(len(r['foreign']) for r in m),
                             mean_ms=round(sum(r['ms'] for r in m) / len(m), 2))
    result = dict(course=cid, cases=len(cases), index=index, top_k=config.top_k, thresholds=dict(vector=config.vector_threshold,
                  keyword=config.keyword_threshold, hybrid_keyword=config.hybrid_keyword, hybrid_vector_floor=config.hybrid_vector_floor),
                  summary=summary, rows=rows)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if a.out:
        Path(a.out).mkdir(parents=True, exist_ok=True); (Path(a.out) / 'retrieval.json').write_text(json.dumps(result, ensure_ascii=False, indent=1), 'utf-8')

if __name__ == '__main__':
    main()
