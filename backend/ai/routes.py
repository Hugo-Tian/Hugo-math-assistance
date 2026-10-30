import asyncio
import json
import time
import uuid
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import select, delete, func
from .settings import settings
from .models import Conversation, ChatTurn, ToolTrace, Document, Chunk, SavedPlan, PlanPractice
from .schemas import NewConversation, SendMessage, SavePlanInput, StartPlanInput
from .agent import run_assistant
from .plans import validate_plan
from .knowledge_base import import_document, allowed_chunks, chunk_payload, rebuild_index, assessment_open, MAX_FILE_BYTES
from ..security import administrator
from ..db import get_db
from ..models import Question, PracticeSession, utcnow
from ..schemas import SessionInput
from ..service import lock_user, start_session, session_view
from ..algorithms import knowledge_view
from ..courses import course_context, course_staff, in_course

# Mounted under /api/courses/{cid} and the legacy /api (default course) by backend.main.
# Conversation ids use {conv_id}: {cid} is reserved for the course in the prefix.
router=APIRouter(prefix='/assistant',tags=['学习助手'])

def owned(db,ctx,conv_id):
    c=db.get(Conversation,conv_id)
    if not c or c.deleted or c.course_id!=ctx.course.id:raise HTTPException(404,'对话不存在')
    if c.user_id!=ctx.user.id:raise HTTPException(403,'无权访问其他用户的对话')
    return c

def trace_map(db,turn_ids):
    by_turn={i:[] for i in turn_ids}
    for x in db.scalars(select(ToolTrace).where(ToolTrace.turn_id.in_(turn_ids)).order_by(ToolTrace.id)) if turn_ids else []:by_turn[x.turn_id].append(x)
    return by_turn

def allowed_ids(db,ctx):
    return {c.id for c,d in allowed_chunks(db,ctx.user.id,course_id=ctx.course.id)}

def turn_view(t,db,ctx,allowed=None,traces=None):
    # Callers rendering many turns pass the permission set and traces once, avoiding per-turn queries.
    if allowed is None:allowed=allowed_ids(db,ctx)
    if traces is None:traces=trace_map(db,[t.id])[t.id]
    citations=[c for c in t.citations if c['chunk_id'] in allowed]
    unavailable=len(citations)!=len(t.citations)
    return dict(id=t.id,question=t.question,answer=t.answer if not unavailable else '此历史回答引用的资料已停用、删除或当前不可访问，暂不展示原回答。',status=t.status,mode=t.mode,citations=[{k:v for k,v in c.items() if k!='content'} for c in citations],
        sources_unavailable=unavailable,
        diagnostics={k:t.metadata_json.get(k) for k in ('elapsed_ms','model_calls','provider_attempts','usage')},
        tools=[dict(name=x.name,status=x.status,elapsed_ms=x.elapsed_ms) for x in traces],
        plan=t.plan,created_at=t.created_at,provider_mode=t.metadata_json.get('provider_mode'),error=t.metadata_json.get('error'),origin=t.metadata_json.get('answer_origin'))

@router.get('/status')
def status(ctx=Depends(course_context),db=Depends(get_db),config=Depends(settings)):
    return dict(configured=bool(config.key) if config.mode=='real' else config.allow_mock,mode=config.mode,
        assessment_open=bool(assessment_open(db,ctx.user.id,ctx.course.id)),retrieval_mode=config.retrieval_mode)

@router.post('/assessment/end')
def end_assessment(ctx=Depends(course_context),db=Depends(get_db)):
    lock_user(db,ctx.user.id)
    ids=assessment_open(db,ctx.user.id,ctx.course.id)
    for sid in ids:db.get(PracticeSession,sid).ended=True
    db.commit();return {'ended':len(ids)}

@router.get('/conversations')
def conversations(ctx=Depends(course_context),db=Depends(get_db)):
    return [dict(id=c.id,title=c.title,knowledge_id=c.knowledge_id,question_id=c.question_id,created_at=c.created_at) for c in db.scalars(select(Conversation).where(
        Conversation.user_id==ctx.user.id,Conversation.course_id==ctx.course.id,Conversation.deleted.is_(False)).order_by(Conversation.created_at.desc()))]

@router.post('/conversations',status_code=201)
def create(data:NewConversation,ctx=Depends(course_context),db=Depends(get_db)):
    if data.knowledge_id and not in_course(db,data.knowledge_id,ctx.course.id):raise HTTPException(422,'知识点不存在')
    if data.question_id:
        q=db.get(Question,data.question_id)
        if not q or not in_course(db,q.knowledge_id,ctx.course.id):raise HTTPException(422,'题目不存在')
    c=Conversation(id=str(uuid.uuid4()),user_id=ctx.user.id,course_id=ctx.course.id,**data.model_dump());db.add(c);db.commit()
    return {'id':c.id}

@router.get('/conversations/{conv_id}')
def read(conv_id:str,ctx=Depends(course_context),db=Depends(get_db)):
    c=owned(db,ctx,conv_id)
    turns=list(db.scalars(select(ChatTurn).where(ChatTurn.conversation_id==conv_id).order_by(ChatTurn.created_at)))
    allowed=allowed_ids(db,ctx);traces=trace_map(db,[t.id for t in turns])
    return dict(id=c.id,title=c.title,knowledge_id=c.knowledge_id,question_id=c.question_id,
        turns=[turn_view(t,db,ctx,allowed,traces[t.id]) for t in turns])

@router.delete('/conversations/{conv_id}')
def remove(conv_id:str,ctx=Depends(course_context),db=Depends(get_db)):
    lock_user(db,ctx.user.id);c=owned(db,ctx,conv_id)
    if db.scalar(select(ChatTurn.id).where(ChatTurn.conversation_id==conv_id,ChatTurn.status=='pending')):raise HTTPException(409,'对话正在生成，请等待后再删除')
    c.deleted=True
    # Retain ids needed by saved plans, but erase textual conversation content and traces.
    for t in db.scalars(select(ChatTurn).where(ChatTurn.conversation_id==conv_id)):
        db.execute(delete(ToolTrace).where(ToolTrace.turn_id==t.id));t.question='';t.answer='';t.citations=[];t.metadata_json={};t.plan=None;t.status='deleted'
    db.commit();return {'ok':True}

@router.post('/conversations/{conv_id}/messages')
def send(conv_id:str,data:SendMessage,ctx=Depends(course_context),db=Depends(get_db),config=Depends(settings)):
    # Sync route: FastAPI runs it in a worker thread, so the agent's synchronous DB work never blocks the event loop.
    user=ctx.user
    lock_user(db,user.id);c=owned(db,ctx,conv_id)
    previous=db.scalar(select(ChatTurn).where(ChatTurn.conversation_id==conv_id,ChatTurn.request_key==data.request_key))
    if previous:
        if previous.question!=data.message or previous.mode!=data.mode:raise HTTPException(409,'请求键已用于不同问题')
        return turn_view(previous,db,ctx)
    pending=db.scalar(select(ChatTurn).where(ChatTurn.conversation_id==conv_id,ChatTurn.status=='pending'))
    if pending:
        if pending.created_at < utcnow()-timedelta(seconds=config.request_seconds+30):
            pending.status='failed';pending.answer='服务曾中断，本次回答未完成。'
        else:raise HTTPException(409,'此对话仍在生成，请等待完成')
    t=ChatTurn(id=str(uuid.uuid4()),conversation_id=conv_id,request_key=data.request_key,question=data.message,mode=data.mode,answer='',citations=[],metadata_json={})
    # Name an untitled conversation after its first question.
    if c.title=='新的学习对话' and not db.scalar(select(ChatTurn.id).where(ChatTurn.conversation_id==conv_id).limit(1)):
        first=' '.join(data.message.split());c.title=first[:30]+('…' if len(first)>30 else '')
    db.add(t);db.commit()
    asyncio.run(run_assistant(db,user,c,t,data,config))
    db.commit()
    return turn_view(t,db,ctx)

@router.get('/sources/{chunk_id}')
def source(chunk_id:str,ctx=Depends(course_context),db=Depends(get_db)):
    for c,d in allowed_chunks(db,ctx.user.id,course_id=ctx.course.id):
        if c.id==chunk_id:return chunk_payload(c,d)
    raise HTTPException(404,'来源不存在、已停用或当前不可访问')

def plan_conversation(db,plan_or_turn_id):
    t=db.get(ChatTurn,plan_or_turn_id)
    return db.get(Conversation,t.conversation_id) if t else None

@router.post('/plans')
def save_plan(data:SavePlanInput,ctx=Depends(course_context),db=Depends(get_db)):
    user=ctx.user
    lock_user(db,user.id)
    old=db.scalar(select(SavedPlan).where(SavedPlan.user_id==user.id,SavedPlan.request_key==data.request_key))
    if old:
        if old.turn_id!=data.turn_id:raise HTTPException(409,'请求键已使用')
        return {'id':old.id,'payload':old.payload}
    t=db.get(ChatTurn,data.turn_id)
    if not t:raise HTTPException(404,'草稿不存在')
    owned(db,ctx,t.conversation_id)
    old=db.scalar(select(SavedPlan).where(SavedPlan.user_id==user.id,SavedPlan.turn_id==t.id))
    if old:return {'id':old.id,'payload':old.payload}
    if t.status!='completed' or not t.plan:raise HTTPException(422,'没有可保存的有效草稿')
    try:payload=validate_plan(db,user,t.plan['content'],ctx.scope)
    except ValueError as exc:raise HTTPException(422,str(exc))
    p=SavedPlan(id=str(uuid.uuid4()),user_id=user.id,turn_id=t.id,request_key=data.request_key,payload={**payload,'origin':t.plan['origin']});db.add(p);db.commit()
    return {'id':p.id,'payload':p.payload}

@router.get('/plans')
def plans(ctx=Depends(course_context),db=Depends(get_db)):
    # A plan belongs to the course of the conversation that drafted it.
    rows=db.scalars(select(SavedPlan).join(ChatTurn,ChatTurn.id==SavedPlan.turn_id).join(Conversation,Conversation.id==ChatTurn.conversation_id)
        .where(SavedPlan.user_id==ctx.user.id,Conversation.course_id==ctx.course.id).order_by(SavedPlan.created_at.desc()))
    return [dict(id=p.id,payload=p.payload) for p in rows]

@router.post('/plans/{pid}/practice')
def plan_practice(pid:str,data:StartPlanInput,ctx=Depends(course_context),db=Depends(get_db)):
    user=ctx.user
    lock_user(db,user.id);p=db.get(SavedPlan,pid)
    conversation=plan_conversation(db,p.turn_id) if p else None
    if not p or p.user_id!=user.id or not conversation or conversation.course_id!=ctx.course.id:raise HTTPException(403,'计划不可访问')
    old=db.scalar(select(PlanPractice).where(PlanPractice.plan_id==pid,PlanPractice.day==data.day,PlanPractice.task==data.task))
    if old:return {'session_id':old.session_id}
    try:task=p.payload['days'][data.day-1]['tasks'][data.task]
    except IndexError:raise HTTPException(422,'任务不存在')
    n=next((n for n in knowledge_view(db,user.id,ctx.scope) if n['id']==task['knowledge_id']),None)
    if not n:raise HTTPException(409,'计划中的知识点已不在本课程，请重新生成计划')
    if n['missing_prerequisites']:raise HTTPException(409,'当前先修条件尚未满足，请先完成先修练习')
    s=start_session(db,user,SessionInput(mode='custom',knowledge_id=task['knowledge_id'],count=task['question_count']),ctx.scope)
    if task['question_ids']:
        ids=list(db.scalars(select(Question.id).where(Question.active.is_(True),Question.id.in_(task['question_ids']),Question.knowledge_id==task['knowledge_id'])))
        if len(ids)!=task['question_count']:raise HTTPException(409,'计划中的题目已变更，请重新生成计划')
        s.question_ids=task['question_ids']
    if len(s.question_ids)<task['question_count']:raise HTTPException(409,'当前题量不足，请重新生成计划')
    db.add(PlanPractice(plan_id=pid,day=data.day,task=data.task,session_id=s.id));db.commit();return {'session_id':s.id}

def course_document(db,ctx,did):
    d=db.get(Document,did)
    if not d or d.course_id!=ctx.course.id:raise HTTPException(404,'文档不存在')
    return d

@router.get('/admin/documents')
def documents(ctx=Depends(course_staff),db=Depends(get_db)):
    counts=dict(db.execute(select(Chunk.document_id,func.count(Chunk.id)).group_by(Chunk.document_id)).all())
    return [dict(id=d.id,title=d.title,filename=d.filename,source=d.source,knowledge_id=d.knowledge_id,scope=d.scope,status=d.status,error=d.error,active=d.active,
        chunks=counts.get(d.id,0)) for d in db.scalars(select(Document).where(Document.course_id==ctx.course.id).order_by(Document.created_at.desc()))]

@router.post('/admin/documents')
def upload(file:UploadFile=File(...),source:str=Form(...),knowledge_id:str|None=Form(None),question_id:int|None=Form(None),ctx=Depends(course_staff),db=Depends(get_db)):
    if not 3<=len(source)<=255:raise HTTPException(422,'请提供 3～255 字符的来源说明')
    data=file.file.read(MAX_FILE_BYTES+1)
    try:d=import_document(db,file.filename or '',data,knowledge_id or None,source,question_id,course_id=ctx.course.id)
    except ValueError as exc:raise HTTPException(422,str(exc))
    db.commit();return {'id':d.id,'status':d.status,'error':d.error}

@router.post('/admin/documents/{did}/toggle')
def toggle(did:str,ctx=Depends(course_staff),db=Depends(get_db)):
    d=course_document(db,ctx,did)
    d.active=not d.active;db.commit();return {'active':d.active}

@router.delete('/admin/documents/{did}')
def delete_doc(did:str,ctx=Depends(course_staff),db=Depends(get_db)):
    d=course_document(db,ctx,did)
    db.execute(delete(Chunk).where(Chunk.document_id==did));db.delete(d);db.commit()
    return {'ok':True,'index_note':'检索即时过滤；重建索引可清理旧向量文件中的内容。'}

# Platform-wide operations: one shared vector index and cross-course traces stay with the platform admin.
@router.post('/admin/index/rebuild')
def index(admin=Depends(administrator),db=Depends(get_db),config=Depends(settings)):
    try:return rebuild_index(db,config)
    except Exception:raise HTTPException(503,'索引重建失败；已解析文本保留，可使用关键词检索或检查模型缓存后重试。')

@router.get('/admin/traces')
def traces(admin=Depends(administrator),db=Depends(get_db)):
    turns=list(db.scalars(select(ChatTurn).where(ChatTurn.status!='deleted').order_by(ChatTurn.created_at.desc()).limit(30)));by_turn=trace_map(db,[t.id for t in turns])
    return [dict(id=t.id,status=t.status,metadata=t.metadata_json,tools=[dict(name=x.name,arguments=x.arguments,status=x.status,elapsed_ms=x.elapsed_ms) for x in by_turn[t.id]])
        for t in turns]
