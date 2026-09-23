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
env={**os.environ,'DATABASE_URL':f'sqlite:///{database.as_posix()}','PYTHONUTF8':'1'}
for args in [['-m','alembic','upgrade','head'],['-m','backend.seed']]:
    subprocess.run([sys.executable,*args],cwd=root,env=env,check=True,capture_output=True)
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
    process.terminate();process.wait(timeout=10)
    process=launch()
    after=httpx.get(url+'/api/report',headers=h).json()
    assert before==after and after['total']==1
    assert httpx.get(url+f'/api/sessions/{s["id"]}',headers=h).json()['ended']
    assert len(httpx.get(url+'/api/mistakes',headers=h).json())==1
    print('PROCESS RESTART VERIFIED: login token, session, attempt, mastery, report and mistake persisted unchanged')
finally:
    process.terminate();process.wait(timeout=10)
