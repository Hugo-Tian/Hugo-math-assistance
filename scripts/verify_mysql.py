"""Run ONLY against the dedicated local verification instance on port 3307.
Creates a fresh uniquely named database; never alters existing databases.
"""
import os
import sys
import uuid
import subprocess
from pathlib import Path
import pymysql

root=Path(__file__).resolve().parents[1]
database='zhixu_verify_'+uuid.uuid4().hex[:12]
connection=pymysql.connect(host='127.0.0.1',port=3307,user='root',charset='utf8mb4',autocommit=True)
with connection.cursor() as cursor:
    cursor.execute(f'CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
connection.close()
url=f'mysql+pymysql://root@127.0.0.1:3307/{database}?charset=utf8mb4'
env={**os.environ,'DATABASE_URL':url,'PYTHONUTF8':'1'}
for args in [['-m','alembic','upgrade','head'],['-m','backend.seed'],['-m','alembic','check']]:
    subprocess.run([sys.executable,*args],cwd=root,env=env,check=True)
os.environ['DATABASE_URL']=url
sys.path.insert(0,str(root))
from fastapi.testclient import TestClient
from backend.main import app
from backend.db import SessionLocal
from backend.models import Question
from concurrent.futures import ThreadPoolExecutor
with TestClient(app) as client:
    response=client.post('/api/auth/register',json={'username':'mysql_learner','password':'Password123!'})
    assert response.status_code==201,response.text
    h={'Authorization':'Bearer '+response.json()['token']}
    s=client.post('/api/sessions',headers=h,json={'mode':'custom','knowledge_id':'sets','difficulty':1,'count':5}).json()
    for i in range(5):
        q=s['question']
        with SessionLocal() as db:answer=db.get(Question,q['id']).answer
        body=dict(question_id=q['id'],selected=answer,idempotency_key=str(uuid.uuid4()))
        def post(_):return client.post(f'/api/sessions/{s["id"]}/answers',headers=h,json=body)
        with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(post,range(3)))
        assert all(r.status_code==200 for r in results),[r.text for r in results]
        assert len({r.json()['attempt_id'] for r in results})==1
        s=client.get(f'/api/sessions/{s["id"]}',headers=h).json()
    report=client.get('/api/report',headers=h).json()
    assert report['total']==5 and report['effective']==5
    assert report['knowledge'][0]['status']=='已通过'
    demo=[]
    for name in ['demo_foundation','demo_advanced']:
        login=client.post('/api/auth/login',json={'username':name,'password':'DemoMath2026!'}).json()
        rec=client.get('/api/recommendations',headers={'Authorization':'Bearer '+login['token']}).json()
        demo.append(rec['recommendations'][0]['knowledge_id'])
    assert demo==['monotonicity','derivative_rules'],demo
print('MYSQL VERIFIED: migration + seed + schema diff + concurrent idempotency + passing + distinct demo recommendations')
print('Isolated verification database:',database)
