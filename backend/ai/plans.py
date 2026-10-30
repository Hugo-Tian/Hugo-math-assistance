from sqlalchemy import select
from .schemas import StudyPlan
from ..algorithms import knowledge_view, recommend
from ..models import Question
from ..courses import scope_for

def validate_plan(db,user,raw,scope=None):
    plan=StudyPlan.model_validate(raw)
    if [d.day for d in plan.days]!=[1,2,3]:raise ValueError('计划必须按第 1、2、3 天顺序排列')
    # Only this course's knowledge points are valid plan targets.
    nodes={n['id']:n for n in knowledge_view(db,user.id,scope or scope_for(db,user.id))}
    earlier=set()
    for day in plan.days:
        if sum(t.estimated_minutes for t in day.tasks)>180:raise ValueError('每日估算总时间不能超过 180 分钟')
        for task in day.tasks:
            if task.knowledge_id not in nodes:raise ValueError('计划引用不存在的知识点')
            node=nodes[task.knowledge_id]
            missing=set(node['missing_prerequisites'])
            if missing and (not task.conditional_on_pass or not missing.issubset(earlier)):
                raise ValueError('先修顺序不足：请先安排 '+','.join(sorted(missing))+'，并标记后续任务需先修通过后开始')
            questions=list(db.scalars(select(Question).where(Question.active.is_(True),Question.knowledge_id==task.knowledge_id)))
            ids={q.id for q in questions}
            if task.question_count>len(ids):raise ValueError('题量超过当前可用题库')
            if task.question_ids and (len(task.question_ids)!=task.question_count or len(set(task.question_ids))!=len(task.question_ids) or not set(task.question_ids).issubset(ids)):
                raise ValueError('计划题目 ID、所属知识点或题量不合法')
            earlier.add(task.knowledge_id)
    return plan.model_dump()

def fallback_plan(db,user,scope=None):
    recs=recommend(db,user,scope)['recommendations']
    for rec in recs:
        ids=list(db.scalars(select(Question.id).where(Question.active.is_(True),Question.knowledge_id==rec['knowledge_id'])))
        if ids:
            count=min(5,len(ids))
            return {'goal':'三天巩固当前可学习的薄弱知识点','days':[{'day':i,'tasks':[{'knowledge_id':rec['knowledge_id'],'question_count':count,'estimated_minutes':20,
                'reason':rec['reason']+' 后续天可复习同类题；已曝光题不重复计分。','question_ids':[],'conditional_on_pass':False}]} for i in [1,2,3]],
                'basis':['已有确定性推荐 rules-v1.0','当前掌握度、有效样本与先修关系；时间为估算']}
    raise ValueError('当前没有足够题目生成计划')
