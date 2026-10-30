"""End-to-end acceptance of a second course through the HTTP API, with real model calls for the assistant.

Run after scripts/import_course.py against the same backend. Checks the student loop (practice -> mastery ->
recommendation -> report), the assistant (RAG + Agent plan) and the teacher dashboard, and that nothing leaks between
the new course and the default course. Writes acceptance.json next to import.json.

  python scripts/verify_course_acceptance.py --api http://127.0.0.1:8013 --course linalg --students la_alice,la_bob \
      --student-password ... --out evals/linalg-acceptance
"""
import argparse
import json
import os
import uuid
from pathlib import Path
import httpx

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--api', default='http://127.0.0.1:8000'); p.add_argument('--course', required=True)
    p.add_argument('--students', required=True); p.add_argument('--student-password', default=os.getenv('ACCEPTANCE_STUDENT_PASSWORD', 'LinAlg2026!'))
    p.add_argument('--teacher', default='demo_admin'); p.add_argument('--teacher-password', default=os.getenv('COURSE_ADMIN_PASSWORD', 'DemoMath2026!'))
    p.add_argument('--other-course', default='hs-math'); p.add_argument('--out', default='')
    a = p.parse_args()
    checks, notes = [], {}
    def check(name, ok, detail=None):
        checks.append(dict(name=name, ok=bool(ok), detail=detail)); print(('PASS ' if ok else 'FAIL ') + name, '' if ok else detail)
    def client(user, password):
        c = httpx.Client(base_url=a.api, timeout=180)
        c.headers['Authorization'] = 'Bearer ' + c.post('/api/auth/login', json={'username': user, 'password': password}).raise_for_status().json()['token']
        return c
    base, other = f'/api/courses/{a.course}', f'/api/courses/{a.other_course}'
    teacher = client(a.teacher, a.teacher_password)
    answers = {q['id']: q['answer'] for q in teacher.get(f'{base}/admin/questions').raise_for_status().json()}
    course_docs = {d['id'] for d in teacher.get(f'{base}/assistant/admin/documents').json()}
    alice_name, bob_name = a.students.split(',')[:2]
    alice, bob = client(alice_name, a.student_password), client(bob_name, a.student_password)

    ids = [c['id'] for c in alice.get('/api/courses').json()]
    check('student sees both courses', a.course in ids and a.other_course in ids, ids)
    knowledge = alice.get(f'{base}/knowledge').json()['nodes']
    check('course graph is the reviewed one', len(knowledge) >= 3 and all(n['id'].startswith(a.course + '.') for n in knowledge), len(knowledge))
    first = alice.get(f'{base}/recommendations').json()['recommendations'][0]
    check('cold start recommends a course starting point', first['knowledge_id'].startswith(a.course + '.') and first['cold_start'], first['knowledge_id'])

    def practise(c, correct_pattern):
        s = c.post(f'{base}/sessions', json={'mode': 'adaptive', 'count': len(correct_pattern)}).raise_for_status().json()
        results = []
        for ok in correct_pattern:
            q = s['question']
            if not q:
                break
            right = answers[q['id']]
            r = c.post(f'{base}/sessions/{s["id"]}/answers', json={'question_id': q['id'], 'selected': right if ok else (right + 1) % 4,
                                                                    'idempotency_key': str(uuid.uuid4())}).raise_for_status().json()
            results.append(r); s = c.get(f'{base}/sessions/{s["id"]}').json()
        return results
    ra = practise(alice, [True, True, True, True, False])
    rb = practise(bob, [False, False, True, False, False])
    check('answers are judged by the backend', [r['correct'] for r in ra] == [True, True, True, True, False], [r['correct'] for r in ra])
    check('practice stays inside the course', all(r['knowledge_id'].startswith(a.course + '.') for r in ra + rb))
    report = alice.get(f'{base}/report').json()
    check('course report counts the course attempts', report['total'] == len(ra), report['total'])
    check('other course report unaffected', alice.get(f'{other}/report').json()['total'] == 0)
    mastery = {n['id']: n['mastery'] for n in alice.get(f'{base}/knowledge').json()['nodes'] if n['samples']}
    check('mastery updated from attempts', bool(mastery), mastery)
    notes['alice_mastery'] = mastery
    check('mistake book is course scoped', all(m['question']['knowledge_id'].startswith(a.course + '.') for m in bob.get(f'{base}/mistakes').json())
          and bob.get(f'{other}/mistakes').json() == [])

    def ask(c, message, mode='rag', prefix=base):
        conv = c.post(f'{prefix}/assistant/conversations', json={}).raise_for_status().json()['id']
        return conv, c.post(f'{prefix}/assistant/conversations/{conv}/messages', json={'message': message, 'mode': mode, 'request_key': str(uuid.uuid4())}).json()
    conv, t = ask(alice, '怎样判断一个方阵是否可逆？请给出判断方法。')
    notes['rag_in_course'] = dict(status=t['status'], citations=[x['chunk_id'] for x in t['citations']], answer=t['answer'][:600], diagnostics=t['diagnostics'])
    check('real-model RAG answer cites only this course', t['status'] == 'completed' and t['citations'] and all(x['document_id'] in course_docs for x in t['citations']),
          (t['status'], t.get('error')))
    _, t = ask(alice, '函数的单调区间怎么求？')
    notes['other_subject_question'] = dict(status=t['status'], citations=[x['chunk_id'] for x in t['citations']], answer=t['answer'][:300])
    check('high-school question in this course gets no high-school evidence', all(x['document_id'] in course_docs for x in t['citations']), t['status'])
    check('conversation invisible from the other course', alice.get(f'{other}/assistant/conversations/{conv}').status_code == 404)
    _, t = ask(bob, '根据我最近的错题，帮我安排三天复习。', mode='agent')
    plan = (t.get('plan') or {}).get('content') or {}
    tasks = [x['knowledge_id'] for d in plan.get('days', []) for x in d['tasks']]
    notes['agent_plan'] = dict(status=t['status'], error=t.get('error'), tools=[x['name'] for x in t['tools']], tasks=tasks, origin=(t.get('plan') or {}).get('origin'),
                               diagnostics=t['diagnostics'], answer=t['answer'][:600])
    check('real-model Agent plan uses only this course', t['status'] == 'completed' and tasks and all(k.startswith(a.course + '.') for k in tasks), (t['status'], t.get('error'), tasks))

    dash = teacher.get(f'{base}/teacher/dashboard').json()
    names = {r['username']: r for r in dash['students']}
    check('teacher dashboard shows both students', {alice_name, bob_name} <= names.keys(), list(names))
    check('dashboard attempts match', names[alice_name]['attempts'] == len(ra) and names[bob_name]['attempts'] == len(rb))
    notes['sticking_points'] = dash['sticking_points']; notes['frequent_mistakes'] = dash['frequent_mistakes'][:3]
    check('other course dashboard has no new-course activity', all(r['attempts'] == 0 for r in teacher.get(f'{other}/teacher/dashboard').json()['students']
                                                                   if r['username'] in (alice_name, bob_name)))
    result = dict(passed=sum(c['ok'] for c in checks), total=len(checks), checks=checks, notes=notes)
    if a.out:
        Path(a.out).mkdir(parents=True, exist_ok=True); (Path(a.out) / 'acceptance.json').write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), 'utf-8')
    print(f'{result["passed"]}/{result["total"]} checks passed')

if __name__ == '__main__':
    main()
