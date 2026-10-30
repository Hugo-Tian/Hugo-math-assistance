"""Regression checks: deterministic model fixtures are not real model quality evidence."""
import asyncio
import json
import time
import httpx
import pytest
from sqlalchemy import select
from tests.test_assistant import ai, new, send
from backend.ai.models import Document, ChatTurn
from backend.ai.provider import DeepSeekProvider, ModelError
from backend.ai.settings import Settings


@pytest.mark.parametrize('payload', [[], {'answer': 'x'},
    {'answer': 'x', 'citations': [], 'plan': None, 'user_id': 1},
    {'answer': 123, 'citations': [], 'plan': None},
    {'answer': 'x', 'citations': 'fake', 'plan': None}])
def test_complete_output_schema(ai, monkeypatch, payload):
    c,f,h,config=ai
    class Invalid:
        async def complete(self,*args):
            return {'message':{'content':json.dumps(payload)},'usage':None}
    monkeypatch.setattr('backend.ai.agent.make_provider',lambda _:Invalid())
    result=send(c,h,new(c,h)).json()
    assert result['status']=='failed' and result['error']=='invalid_response'
    assert not result['citations']


def test_hybrid_admits_only_strong_or_agreeing_signals(ai,monkeypatch):
    from backend.ai import knowledge_base as kb
    c,f,h,config=ai
    with f() as db:
        rows=kb.allowed_chunks(db,1)[:3]
        a,b,d=(x[0] for x in rows)
        # a: vector alone clears threshold; b: weak vector but keyword agrees; d: weak on both.
        monkeypatch.setattr(kb,'vector_scores',lambda rows,q,cfg:([(.7,a,rows[0][1]),(.62,b,rows[1][1]),(.62,d,rows[2][1])],'v1'))
        monkeypatch.setattr(kb,'lexical_score',lambda q,text:.5 if text.startswith(b.title+' '+b.content) else 0)
        admitted=[x[1].id for x in kb.hybrid_scores(rows,'q',config)[0]]
    assert admitted==[a.id,b.id]


def test_first_question_names_untitled_conversation(ai):
    c,f,h,config=ai;cid=new(c,h)
    send(c,h,cid,key='title-key-1')
    title=next(x['title'] for x in c.get('/api/assistant/conversations',headers=h).json() if x['id']==cid)
    assert title!='新的学习对话' and len(title)<=31
    send(c,h,cid,key='title-key-2',message='另一个完全不同的问题')
    assert next(x['title'] for x in c.get('/api/assistant/conversations',headers=h).json() if x['id']==cid)==title


def test_malformed_json_repaired_once(ai,monkeypatch):
    c,f,h,config=ai
    replies=[]
    class Broken:
        async def complete(self,messages,*args):
            replies.append(messages[-1]['content'])
            pack=next(json.loads(m['content'][4:]) for m in messages if m.get('content','').startswith('资料包：'))
            good=json.dumps({'answer':'修正后的回答','citations':[pack['evidence'][0]['chunk_id']],'plan':None})
            return {'message':{'content':good[:-2] if len(replies)==1 else good},'usage':None}
    monkeypatch.setattr('backend.ai.agent.make_provider',lambda _:Broken())
    result=send(c,h,new(c,h)).json()
    assert result['status']=='completed' and result['answer']=='修正后的回答'
    assert len(replies)==2 and '只允许修正一次' in replies[1]
    with f() as db:
        assert db.get(ChatTurn,result['id']).metadata_json['repair_reason']=='invalid_json'


def test_revoked_source_hidden_from_history_retry_and_next_context(ai,monkeypatch):
    c,f,h,config=ai;cid=new(c,h)
    result=send(c,h,cid,key='history-key').json()
    citation=result['citations'][0]
    with f() as db:
        db.get(Document,citation['document_id']).active=False;db.commit()
    assert c.get('/api/assistant/sources/'+citation['chunk_id'],headers=h).status_code==404
    history=c.get('/api/assistant/conversations/'+cid,headers=h).json()['turns'][0]
    assert history['sources_unavailable'] and citation not in history['citations']
    assert '暂不展示' in history['answer']
    assert send(c,h,cid,key='history-key').json()['sources_unavailable']
    captured=[]
    class Inspect:
        async def complete(self,messages,*args):
            captured.extend(messages)
            return {'message':{'content':json.dumps({'answer':'无资料','citations':[],'plan':None})}}
    monkeypatch.setattr('backend.ai.agent.make_provider',lambda _:Inspect())
    send(c,h,cid)
    assert not any(m['role']=='assistant' and m['content']==result['answer'] for m in captured)


def test_permission_change_during_inference_blocks_citation(ai,monkeypatch):
    c,f,h,config=ai
    class Revoke:
        async def complete(self,messages,*args):
            pack=next(json.loads(m['content'][4:]) for m in messages if m.get('content','').startswith('资料包：'))
            evidence=pack['evidence'][0]
            with f() as db:
                d=db.get(Document,evidence['document_id']);d.scope='question';d.question_id=1;db.commit()
            return {'message':{'content':json.dumps({'answer':'禁止发布','citations':[evidence['chunk_id']],'plan':None})}}
    monkeypatch.setattr('backend.ai.agent.make_provider',lambda _:Revoke())
    result=send(c,h,new(c,h)).json()
    assert result['status']=='failed' and result['error']=='invalid_citation'
    assert not result['citations'] and '禁止发布' not in result['answer']


def test_tool_deadline_and_cold_start(ai,monkeypatch):
    c,f,h,config=ai
    cold=send(c,h,new(c,h),'安排三天复习','agent').json()
    assert '没有作答记录' in cold['answer']
    assert len(cold['tools'])==6 and cold['diagnostics']['usage'] is None
    config.request_seconds=.15
    def slow(*args):time.sleep(.3);return {}
    monkeypatch.setattr('backend.ai.agent.execute_tool',slow)
    result=send(c,h,new(c,h),'安排三天复习','agent').json()
    assert result['status']=='failed' and result['error']=='request_timeout'
    assert result['diagnostics']['elapsed_ms']<290


def test_provider_failed_attempts_and_malformed_envelope():
    p=DeepSeekProvider(Settings(key='fixture',retries=0),httpx.MockTransport(lambda r:httpx.Response(200,json={'choices':None})))
    with pytest.raises(ModelError) as caught:asyncio.run(p.complete([],[],'trace',100))
    assert caught.value.code=='invalid_response' and caught.value.provider_attempts==1


@pytest.mark.parametrize('usage',[None,{'prompt_tokens':None,'completion_tokens':2},{'prompt_tokens':-1,'completion_tokens':2}])
def test_missing_or_invalid_usage_is_unknown(usage):
    response={'choices':[{'finish_reason':'stop','message':{'content':'{}'}}],'usage':usage}
    p=DeepSeekProvider(Settings(key='fixture'),httpx.MockTransport(lambda r:httpx.Response(200,json=response)))
    result=asyncio.run(p.complete([],[],'trace',100))
    assert result['usage'] is None and result['provider_attempts']==1


def test_unknown_citations_and_missing_evidence_agent(ai,monkeypatch):
    c,f,h,config=ai
    class Invented:
        async def complete(self,*args):return {'message':{'content':json.dumps({'answer':'编造','citations':['invented'],'plan':None})}}
    monkeypatch.setattr('backend.ai.agent.make_provider',lambda _:Invented())
    result=send(c,h,new(c,h)).json()
    assert result['error']=='invalid_citation' and not result['citations']
    class Empty:
        async def complete(self,*args):return {'message':{'content':json.dumps({'answer':'编造','citations':[],'plan':None})}}
    monkeypatch.setattr('backend.ai.agent.make_provider',lambda _:Empty())
    result=send(c,h,new(c,h),'火星气候','agent').json()
    assert result['status']=='insufficient_evidence'


def test_saved_plan_cross_user_denied(ai):
    c,f,h,config=ai
    draft=send(c,h,new(c,h),'安排三天复习','agent').json()
    payload={'turn_id':draft['id'],'request_key':'save-plan-key'}
    plan=c.post('/api/assistant/plans',headers=h,json=payload).json()
    other=c.post('/api/auth/register',json={'username':'other_student','password':'Password123!'}).json()
    headers={'Authorization':'Bearer '+other['token']}
    assert c.post('/api/assistant/plans',headers=headers,json=payload).status_code==403
    assert c.get('/api/assistant/plans',headers=headers).json()==[]
    assert c.post('/api/assistant/plans/'+plan['id']+'/practice',headers=headers,json={'day':1,'task':0}).status_code==403
