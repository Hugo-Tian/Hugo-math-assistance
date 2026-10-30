import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from sqlalchemy import select, func
from backend.models import Question, Attempt, Mastery, User, Prerequisite, PracticeSession
from backend.algorithms import recommend, recompute
from backend.schemas import SessionInput, AnswerInput
from backend.service import start_session, submit_answer

def start(client, headers, kid='sets', count=5, difficulty=1, mode='custom'):
    r=client.post('/api/sessions',headers=headers,json=dict(mode=mode,knowledge_id=kid,count=count,difficulty=difficulty))
    assert r.status_code == 201, r.text
    return r.json()

def solve(env, headers, kid, correct=True, count=5, difficulty=1):
    c,factory=env
    s=start(c,headers,kid,count,difficulty)
    while s['question']:
        q=s['question']
        with factory() as db:
            answer=db.get(Question,q['id']).answer
        r=c.post(f'/api/sessions/{s["id"]}/answers',headers=headers,json=dict(question_id=q['id'],selected=answer if correct else (answer+1)%4,idempotency_key=str(uuid.uuid4())))
        assert r.status_code==200,r.text
        s=c.get(f'/api/sessions/{s["id"]}',headers=headers).json()
    return s

def test_cold_start_and_no_answer_leak(env,learner):
    c,_=env
    k=c.get('/api/knowledge',headers=learner).json()['nodes']
    assert all(n['mastery'] is None and n['samples']==0 and n['status']=='未评估' for n in k)
    rec=c.get('/api/recommendations',headers=learner).json()
    assert rec['recommendations'][0]['knowledge_id']=='sets'
    assert rec['recommendations'][0]['cold_start']
    s=start(c,learner)
    assert 'answer' not in s['question'] and 'explanation' not in s['question']
    for q in c.get('/api/questions',headers=learner).json()['items']:
        assert 'answer' not in q and 'explanation' not in q

def test_passing_requires_distinct_samples_and_prerequisites(env,learner):
    c,_=env
    solve(env,learner,'domain')
    nodes={n['id']:n for n in c.get('/api/knowledge',headers=learner).json()['nodes']}
    assert nodes['domain']['mastery']==6/7 and not nodes['domain']['passed_at']
    solve(env,learner,'sets',count=4)
    nodes={n['id']:n for n in c.get('/api/knowledge',headers=learner).json()['nodes']}
    assert not nodes['sets']['passed_at']
    solve(env,learner,'sets',count=1)
    nodes={n['id']:n for n in c.get('/api/knowledge',headers=learner).json()['nodes']}
    assert nodes['sets']['status']=='已通过' and nodes['domain']['status']=='已通过'

def test_wrong_answers_recommend_prerequisite_and_shared_views(env,learner):
    c,factory=env
    c.put('/api/me/goal',headers=learner,json={'knowledge_id':'optimization'})
    solve(env,learner,'sets',correct=False)
    r=c.get('/api/report',headers=learner).json()
    m=c.get('/api/mistakes',headers=learner).json()
    k=c.get('/api/knowledge',headers=learner).json()['nodes'][0]
    rec=c.get('/api/recommendations',headers=learner).json()['recommendations'][0]
    assert (r['total'],r['correct'],r['effective'],len(m))==(5,0,5,5)
    assert k['mastery']==r['knowledge'][0]['mastery']==1/7
    assert rec['knowledge_id']=='sets' and '先修' in rec['reason']
    assert abs(rec['score']-sum(rec['contributions'].values()))<1e-6
    assert len(r['trend'])==5
    with factory() as db:
        uid=db.scalar(select(User.id).where(User.username=='learner'))
        recompute(db,uid);db.commit()
    assert c.get('/api/knowledge',headers=learner).json()['nodes'][0]['mastery']==1/7

def test_idempotency_and_conflicting_key(env,learner):
    c,factory=env;s=start(c,learner,count=1)
    body={'question_id':s['question']['id'],'selected':0,'idempotency_key':str(uuid.uuid4())}
    url=f'/api/sessions/{s["id"]}/answers'
    a=c.post(url,headers=learner,json=body);b=c.post(url,headers=learner,json=body)
    assert a.status_code==b.status_code==200 and a.json()==b.json()
    b2=c.post(url,headers=learner,json={**body,'idempotency_key':str(uuid.uuid4())})
    assert b2.json()==a.json()
    assert c.post(url,headers=learner,json={**body,'selected':1}).status_code==409
    assert c.get('/api/report',headers=learner).json()['total']==1

def test_concurrent_retries_count_once(env,learner):
    c,_=env;s=start(c,learner,count=1)
    body=dict(question_id=s['question']['id'],selected=0,idempotency_key=str(uuid.uuid4()))
    def post(_):return c.post(f'/api/sessions/{s["id"]}/answers',headers=learner,json=body)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(post,range(4)))
    assert all(r.status_code==200 for r in results)
    assert len({r.json()['attempt_id'] for r in results})==1
    assert c.get('/api/report',headers=learner).json()['effective']==1

def test_cross_user_and_student_admin_access(env,learner):
    c,_=env;s=start(c,learner)
    other=c.post('/api/auth/register',json={'username':'other','password':'Password123!'}).json()
    h={'Authorization':f'Bearer {other["token"]}'}
    assert c.get(f'/api/sessions/{s["id"]}',headers=h).status_code==403
    assert c.post(f'/api/sessions/{s["id"]}/answers',headers=h,json=dict(question_id=s['question']['id'],selected=0,idempotency_key=str(uuid.uuid4()))).status_code==403
    assert c.get('/api/admin/overview',headers=learner).status_code==403
    assert c.get('/api/report',headers=h).json()['total']==0
    assert c.get('/api/report').status_code==401

def test_custom_filters_search_and_shortage(env,learner):
    c,_=env;s=start(c,learner,'tangent',count=20,difficulty=2)
    assert s['actual_count']==3 and '只有 3 道' in s['notice']
    assert s['question']['knowledge_id']=='tangent' and s['question']['difficulty']==2
    matches=c.get('/api/questions',headers=learner,params={'keyword':'切线','difficulty':2,'knowledge_id':'tangent'}).json()
    assert matches['total']==3
    assert c.get('/api/questions',headers=learner,params={'keyword':'不存在的题目'}).json()['total']==0
    assert c.get('/api/questions',headers=learner,params={'keyword':'%'}).json()['total']==0

def test_repeat_after_exposure_saved_but_not_scored_even_next_day(env,learner):
    c,factory=env
    s=solve(env,learner,'sets',correct=False,count=1)
    qid=s['results'][0]['question_id']
    with factory() as db:
        u=db.scalar(select(User).where(User.username=='learner'));q=db.get(Question,qid)
        session=start_session(db,u,SessionInput(mode='review',question_id=qid,count=1))
        result=submit_answer(db,u,session.id,AnswerInput(question_id=qid,selected=q.answer,idempotency_key=str(uuid.uuid4())),at=datetime.utcnow()+timedelta(days=1))
        assert not result['effective'];db.commit()
    r=c.get('/api/report',headers=learner).json()
    assert (r['total'],r['effective'],r['correct'])==(2,1,1)
    assert c.get('/api/mistakes',headers=learner).json()[0]['status']=='已复习'

def test_history_achievement_survives_regression(env,learner):
    c,_=env;solve(env,learner,'sets')
    old=c.get('/api/knowledge',headers=learner).json()['nodes'][0]['passed_at']
    solve(env,learner,'sets',correct=False,count=3,difficulty=2)
    n=c.get('/api/knowledge',headers=learner).json()['nodes'][0]
    assert n['passed_at']==old and n['status']=='建议复习' and n['available']
    assert n['mastery']==.6

def test_cycle_and_atomic_import_validation(env,learner):
    c,factory=env
    token=c.post('/api/auth/login',json={'username':'admin','password':'Password123!'}).json()['token'];h={'Authorization':f'Bearer {token}'}
    data=dict(id='sets',name='集合运算',chapter='集合',position=0,description='集合基础',prerequisites=['domain'])
    assert c.put('/api/admin/knowledge/sets',headers=h,json=data).status_code==422
    with factory() as db:assert not list(db.scalars(select(Prerequisite).where(Prerequisite.knowledge_id=='sets')))
    payload=dict(knowledge_id='sets',stem='测试题干',options=['1','2','3','4'],answer=0,explanation='答案为1',difficulty=1,source='测试演示题')
    assert c.post('/api/admin/questions/import',headers=h,json=[payload,{**payload,'answer':4}]).status_code==422
    assert c.post('/api/admin/questions/import',headers=h,json=[payload,{**payload,'knowledge_id':'missing'}]).status_code==422
    with factory() as db:assert db.scalar(select(func.count()).select_from(Question))==140

def test_adaptive_next_selected_after_answer_and_difficulty_hysteresis(env,learner):
    c,factory=env;s=start(c,learner,mode='adaptive',count=10)
    assert s['actual_count']==1
    q=s['question']
    with factory() as db:answer=db.get(Question,q['id']).answer
    c.post(f'/api/sessions/{s["id"]}/answers',headers=learner,json=dict(question_id=q['id'],selected=answer,idempotency_key=str(uuid.uuid4())))
    s2=c.get(f'/api/sessions/{s["id"]}',headers=learner).json()
    assert s2['actual_count']==2 and s2['question']['id']!=q['id'] and s2['question']['difficulty']==1
    assert c.get('/api/knowledge',headers=learner).json()['nodes'][0]['difficulty']==1

def test_rollback_leaves_no_partial_attempt(env,learner,monkeypatch):
    c,factory=env;s=start(c,learner,count=1)
    import backend.service as service
    def fail(*args):raise RuntimeError('injected failure')
    monkeypatch.setattr(service,'recompute',fail)
    with factory() as db:
        u=db.scalar(select(User).where(User.username=='learner'))
        try:submit_answer(db,u,s['id'],AnswerInput(question_id=s['question']['id'],selected=0,idempotency_key=str(uuid.uuid4())))
        except RuntimeError:db.rollback()
    assert c.get('/api/report',headers=learner).json()['total']==0

def test_recommendation_returns_to_failed_prerequisite(env,learner):
    c,_=env
    c.put('/api/me/goal',headers=learner,json={'knowledge_id':'optimization'})
    solve(env,learner,'sets')
    assert c.get('/api/recommendations',headers=learner).json()['recommendations'][0]['knowledge_id']=='domain'
    solve(env,learner,'sets',correct=False,count=3,difficulty=2)
    payload=c.get('/api/recommendations',headers=learner).json()
    rec=payload['recommendations']
    assert rec[0]['knowledge_id']=='sets'
    assert payload['fixed_order_next']=='domain'
    assert 'domain' not in [r['knowledge_id'] for r in rec]

def test_window_twenty_and_difficulty_changes_slowly(env,learner):
    c,factory=env
    with factory() as db:
        u=db.scalar(select(User).where(User.username=='learner'))
        base=db.scalar(select(Question).where(Question.knowledge_id=='sets'))
        for i in range(26):
            q=Question(knowledge_id='sets',stem=f'窗口测试题 {i}',options=['1','2','3','4'],answer=0,explanation='测试',difficulty=1,source='测试专用')
            db.add(q);db.flush()
            s=start_session(db,u,SessionInput(mode='review',question_id=q.id,count=1))
            result=submit_answer(db,u,s.id,AnswerInput(question_id=q.id,selected=0 if i<10 else 1,idempotency_key=str(uuid.uuid4())))
            m=db.get(Mastery,(u.id,'sets'))
            if i==0:assert m.difficulty_level==1
            if i==4:assert m.difficulty_level==2
            if i==7:assert m.difficulty_level==3
        assert result['samples']==20 and result['mastery']==5/22
        assert m.difficulty_level==1
        db.commit()

def test_question_versioning_preserves_historical_judgment(env,learner):
    c,factory=env;s=solve(env,learner,'sets',count=1)
    qid=s['results'][0]['question_id'];old_result=s['results'][0]
    token=c.post('/api/auth/login',json={'username':'admin','password':'Password123!'}).json()['token'];h={'Authorization':f'Bearer {token}'}
    old=next(q for q in c.get('/api/admin/questions',headers=h).json() if q['id']==qid)
    payload={k:v for k,v in old.items() if k!='id'};payload['answer']=(old['answer']+1)%4
    r=c.put(f'/api/admin/questions/{qid}',headers=h,json=payload)
    assert r.status_code==200 and r.json()['versioned']
    assert c.get(f'/api/sessions/{s["id"]}',headers=learner).json()['results'][0]==old_result
    with factory() as db:assert not db.get(Question,qid).active

def test_goal_relevance_stable_ties_and_multi_prerequisite(env,learner):
    c,_=env
    for kid in ['sets','domain','evaluation','monotonicity','exponential']:
        solve(env,learner,kid)
    nodes={n['id']:n for n in c.get('/api/knowledge',headers=learner).json()['nodes']}
    assert nodes['logarithm']['prerequisites']==['domain','exponential']
    assert nodes['logarithm']['available']
    rec=c.get('/api/recommendations',headers=learner).json()
    assert all(0<=r['score']<=1 for r in rec['recommendations'])
    assert all(r['factors']['goal']==.5 for r in rec['recommendations'])

def test_login_failures_throttled_and_reset_on_success(env):
    c, _ = env
    c.post('/api/auth/register', json={'username': 'throttle', 'password': 'Password123!'})
    for _ in range(4):
        assert c.post('/api/auth/login', json={'username': 'throttle', 'password': 'Wrong12345!'}).status_code == 401
    assert c.post('/api/auth/login', json={'username': 'throttle', 'password': 'Password123!'}).status_code == 200
    for _ in range(5):
        assert c.post('/api/auth/login', json={'username': 'Throttle', 'password': 'Wrong12345!'}).status_code == 401
    # Locked even with the right password until the window passes.
    assert c.post('/api/auth/login', json={'username': 'throttle', 'password': 'Password123!'}).status_code == 429
