"""Real process restart check against a fresh, isolated SQLite database."""
import os
import sys
import uuid
import time
import subprocess
from pathlib import Path
import httpx

root=Path(__file__).resolve().parents[1]
root.joinpath('tmp').mkdir(exist_ok=True)
database=root/'tmp'/f'restart-{uuid.uuid4().hex[:8]}.db'
env={**os.environ,'DATABASE_URL':f'sqlite:///{database.as_posix()}','PYTHONUTF8':'1',
     'LLM_MODE':'mock','ALLOW_TEST_MOCK':'true','RAG_MODE':'keyword'}
for args in [['-m','alembic','upgrade','head'],['-m','backend.seed']]:
    subprocess.run([sys.executable,*args],cwd=root,env=env,check=True,capture_output=True)
subprocess.run([sys.executable,'-c','from backend.db import SessionLocal; from backend.ai.materials import seed_materials; db=SessionLocal(); seed_materials(db); db.close()'],cwd=root,env=env,check=True,capture_output=True)
url='http://127.0.0.1:8011'
def launch():
    process=subprocess.Popen([sys.executable,'-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8011'],cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    for _ in range(60):
        if process.poll() is not None:raise RuntimeError('Backend failed to start')
        try:
            if httpx.get(url+'/api/health').status_code==200:return process
        except httpx.ConnectError:pass
        time.sleep(.1)
    process.terminate()
    raise RuntimeError('Backend startup timed out')
process=launch()
try:
    login=httpx.post(url+'/api/auth/register',json={'username':'restart_check','password':'Password123!'}).json()
    h={'Authorization':'Bearer '+login['token']}
    s=httpx.post(url+'/api/sessions',headers=h,json={'mode':'custom','knowledge_id':'sets','difficulty':1,'count':1}).json()
    response=httpx.post(url+f'/api/sessions/{s["id"]}/answers',headers=h,json={'question_id':s['question']['id'],'selected':0,'idempotency_key':str(uuid.uuid4())})
    assert response.status_code==200,response.text
    before=httpx.get(url+'/api/report',headers=h).json()
    conversation=httpx.post(url+'/api/assistant/conversations',headers=h,json={}).json()['id']
    turn=httpx.post(url+f'/api/assistant/conversations/{conversation}/messages',headers=h,
        json={'message':'根据学习记录安排三天复习','mode':'agent','request_key':str(uuid.uuid4())},timeout=30).json()
    assert turn['status']=='completed' and turn['provider_mode']=='mock' and turn['plan']
    saved=httpx.post(url+'/api/assistant/plans',headers=h,json={'turn_id':turn['id'],'request_key':str(uuid.uuid4())})
    assert saved.status_code==200
    chat_before=httpx.get(url+f'/api/assistant/conversations/{conversation}',headers=h).json()
    plans_before=httpx.get(url+'/api/assistant/plans',headers=h).json()
    process.terminate();process.wait(timeout=10)
    process=launch()
    after=httpx.get(url+'/api/report',headers=h).json()
    assert before==after and after['total']==1
    assert httpx.get(url+f'/api/sessions/{s["id"]}',headers=h).json()['ended']
    assert len(httpx.get(url+'/api/mistakes',headers=h).json())==1
    assert httpx.get(url+f'/api/assistant/conversations/{conversation}',headers=h).json()==chat_before
    assert httpx.get(url+'/api/assistant/plans',headers=h).json()==plans_before
    print('PROCESS RESTART VERIFIED: login token, session, attempt, mastery, report and mistake persisted unchanged')
    print('MOCK ASSISTANT RESTART VERIFIED: conversation, citations, tool diagnostics and confirmed plan persisted unchanged')
finally:
    process.terminate();process.wait(timeout=10)
