"""Bounded, reproducible evaluation. Real, Mock and local retrieval results never mixed."""
import argparse
import asyncio
import csv
import hashlib
import json
import os
import statistics
import sys
import time
import uuid
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from backend.db import Base,make_engine
from backend.seed import seed
from backend.models import User,Question
from backend.ai.models import Conversation,ChatTurn,ToolTrace
from backend.ai.materials import seed_materials
from backend.ai.settings import settings
from backend.ai.knowledge_base import retrieve
from backend.ai.agent import run_assistant,PROMPT_VERSION
from backend.ai.provider import make_provider,ModelError
from backend.ai.schemas import SendMessage
from backend.schemas import SessionInput,AnswerInput
from backend.service import start_session,submit_answer

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--suite',choices=['retrieval','mock','real'],default='retrieval');parser.add_argument('--split',choices=['dev','test','all'],default='test');parser.add_argument('--max-calls',type=int,default=8);parser.add_argument('--limit',type=int,default=60);parser.add_argument('--threshold',type=float);parser.add_argument('--output',default='evals/results');parser.add_argument('--ids',default='');args=parser.parse_args()
    if not 1<=args.max_calls<=40:parser.error('--max-calls must be 1..40')
    config=settings();config.retries=0
    if args.threshold is not None:config.vector_threshold=args.threshold
    if args.suite=='mock':config.mode='mock';config.allow_mock=True
    if args.suite=='real':config.mode='real'
    cases=json.loads((ROOT/'evals/cases.json').read_text(encoding='utf-8'));cases=[c for c in cases if args.split=='all' or c['split']==args.split][:args.limit]
    if args.ids:cases=[c for c in cases if c['id'] in args.ids.split(',')]
    out=ROOT/args.output;out.mkdir(parents=True,exist_ok=True)
    temp=ROOT/'tmp'/f'eval-{uuid.uuid4().hex[:8]}.db';temp.parent.mkdir(exist_ok=True)
    engine=make_engine(f'sqlite:///{temp.as_posix()}');Base.metadata.create_all(engine);factory=sessionmaker(engine,expire_on_commit=False)
    with factory() as db:seed(db);seed_materials(db)
    manifest_path=Path(config.index_dir)/'manifest.json';manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    output=[];count=0;raw_outputs=[]
    provider=make_provider(config)
    class Bounded:
        async def complete(self,*params):
            nonlocal count
            if count>=args.max_calls and args.suite=='real':raise ModelError('evaluation_call_cap','本次评测已达到真实调用量上限。')
            count+=1;result=await provider.complete(*params);raw_outputs.append(result);return result
    for case in cases:
        variants=['keyword','vector'] if args.suite=='retrieval' else (['direct','rag'] if case['category']=='knowledge' else ['agent' if case['expected_tools'] or case['category'] in ('security','plans') else 'rag'])
        for variant in variants:
            row=dict(id=case['id'],category=case['category'],split=case['split'],variant=variant,input=case['input'],expected_evidence=case['expected_evidence'],expected_tools=case['expected_tools'],rubric=case['rubric'])
            if args.suite=='real' and (not config.key or count>=args.max_calls):
                row.update(status='skipped',reason='missing_api_key' if not config.key else 'call_cap',elapsed_ms=None);output.append(row);continue
            with factory() as db:
                user=db.scalar(select(User).where(User.username=='demo_foundation'))
                t0=time.perf_counter();raw_start=len(raw_outputs)
                try:
                    if args.suite=='retrieval':
                        # No topic filter: query-only benchmark, avoids leaking expected topic labels into retrieval.
                        r=retrieve(db,user.id,case['input'],config,mode=variant)
                        recalled=[e['chunk_id'] for e in r['evidence']];expected=set(case['expected_evidence']);hits=len(expected&set(recalled))
                        row.update(status='completed',recalled=recalled,hit_at_k=int(hits>0) if expected else None,recall_at_k=hits/len(expected) if expected else None,
                            insufficient_retrieval=int(not recalled) if case['category']=='insufficient' else None,threshold=r.get('threshold'))
                    else:
                        context=case['context'];qid=None;sid=None
                        if context.get('active_assessment') or context.get('submitted_question'):
                            s=start_session(db,user,SessionInput(mode='custom',knowledge_id='sets',count=1));qid=s.question_ids[0];sid=s.id
                            if context.get('submitted_question'):
                                q=db.get(Question,qid);submit_answer(db,user,s.id,AnswerInput(question_id=qid,selected=(q.answer+1)%4,idempotency_key=str(uuid.uuid4())))
                            db.commit()
                        c=Conversation(id=str(uuid.uuid4()),user_id=user.id,title=case['id'],knowledge_id=context.get('knowledge_id'),question_id=qid);db.add(c);db.flush()
                        turn=ChatTurn(id=str(uuid.uuid4()),conversation_id=c.id,request_key=str(uuid.uuid4()),question=case['input'],mode='agent' if variant=='agent' else 'rag',answer='',citations=[],metadata_json={});db.add(turn);db.commit()
                        data=SendMessage(message=case['input'],request_key=turn.request_key,mode=turn.mode)
                        asyncio.run(run_assistant(db,user,c,turn,data,config,Bounded(),direct=variant=='direct'));db.commit()
                        traces=list(db.scalars(select(ToolTrace).where(ToolTrace.turn_id==turn.id)));called={t.name for t in traces}
                        row.update(status=turn.status,answer=turn.answer,citations=turn.citations,plan=turn.plan,metadata=turn.metadata_json,
                            tool_traces=[dict(name=t.name,status=t.status,elapsed_ms=t.elapsed_ms,args=t.arguments) for t in traces],
                            tool_selection_success=int(set(case['expected_tools']).issubset(called)) if case['expected_tools'] else None,
                            parameter_validity=sum(t.status=='success' for t in traces)/len(traces) if traces else None,
                            citation_id_validity=1 if turn.citations and turn.status=='completed' else (0 if turn.metadata_json.get('error') in ('invalid_citation','missing_citation') else None),
                            expected_refusal=int(turn.status=='insufficient_evidence') if case['category']=='insufficient' else None,
                            assessment_guard=int(turn.status=='assessment_hint' and not turn.citations and turn.metadata_json['model_calls']==0) if context.get('active_assessment') else None,
                            automated_plan_completion=int(turn.status=='completed' and bool(turn.plan)) if case['expected_behavior']=='plan' else None,
                            correctness_review=None,citation_support_review=None,task_completion_review=None,review_status='pending_human_review')
                        if sid:db.get(__import__('backend.models',fromlist=['PracticeSession']).PracticeSession,sid).ended=True;db.commit()
                except Exception as exc:row.update(status='error',error=exc.code if isinstance(exc,ModelError) else type(exc).__name__)
                if args.suite!='retrieval':row['raw_model_outputs']=raw_outputs[raw_start:]
                row['elapsed_ms']=round((time.perf_counter()-t0)*1000,3)
            output.append(row)
    metrics={}
    for variant in sorted({r['variant'] for r in output}):
        rows=[r for r in output if r['variant']==variant];active=[r for r in rows if r['status']!='skipped'];m={'rows':len(rows),'executed':len(active),'skipped':len(rows)-len(active),'error_rate':sum(r['status'] in ['failed','error'] for r in active)/len(active) if active else None}
        for key in ['hit_at_k','recall_at_k','insufficient_retrieval','tool_selection_success','parameter_validity','citation_id_validity','expected_refusal','assessment_guard','automated_plan_completion']:
            values=[r[key] for r in rows if r.get(key) is not None];m[key]=sum(values)/len(values) if values else None;m[key+'_n']=len(values)
        latencies=[r['elapsed_ms'] for r in active if r.get('elapsed_ms') is not None];m['latency_mean_ms']=statistics.mean(latencies) if latencies else None
        m['latency_p95_ms']=sorted(latencies)[max(0,__import__('math').ceil(.95*len(latencies))-1)] if latencies else None
        metrics[variant]=m
    meta=dict(executed_at=datetime.now(timezone.utc).isoformat(),suite=args.suite,split=args.split,provider_mode=config.mode,model=config.model,embedding=config.embedding_model,prompt_version=PROMPT_VERSION,
        index_version=manifest.get('version'),embedding_fingerprint=manifest.get('model_fingerprint'),top_k=config.top_k,threshold=config.vector_threshold,cases_sha256=hashlib.sha256((ROOT/'evals/cases.json').read_bytes()).hexdigest(),
        actual_provider_calls=count if args.suite=='real' else 0,mock_calls=count if args.suite=='mock' else 0,max_real_calls=args.max_calls,metrics=metrics)
    prefix=f'{args.suite}-{args.split}'
    (out/f'{prefix}.json').write_text(json.dumps({'metadata':meta,'results':output},ensure_ascii=False,indent=2),encoding='utf-8')
    columns=sorted({k for r in output for k in r})
    with (out/f'{prefix}.csv').open('w',encoding='utf-8-sig',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=columns);writer.writeheader();writer.writerows({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in r.items()} for r in output)
    report=f'# {args.suite} / {args.split} 实际评测\n\n执行时间：{meta["executed_at"]}\n\n模型：{config.model}；Embedding：{config.embedding_model}；Prompt：{PROMPT_VERSION}；索引：{meta["index_version"]}\n\n真实 API 调用：{meta["actual_provider_calls"]}；Mock 调用：{meta["mock_calls"]}。\n\n```json\n'+json.dumps(metrics,ensure_ascii=False,indent=2)+'\n```\n\nHit/Recall 仅对有相关证据标注的案例计算；拒答指标与安全指标使用各自适用分母。检索延迟包含本地模型首次加载，回答延迟包含检索、工具、模型和校验。Token 未返回时为未知。\n\n引用 ID 合法不代表支持结论；开放回答正确性、引用支持和任务完成需在 CSV 人工填写评分。Mock 仅验证应用流程，不代表真实模型效果。未配置 Key 的 direct/RAG 行标记 skipped，不生成伪造分数。\n'
    (out/f'{prefix}.md').write_text(report,encoding='utf-8');print(json.dumps(meta,ensure_ascii=True,indent=2))
    engine.dispose()

if __name__=='__main__':main()
