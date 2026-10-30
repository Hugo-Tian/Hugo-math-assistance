from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
class AssistantOutput(Strict):
    answer:str=Field(min_length=1,max_length=16000)
    citations:list[str]=Field(max_length=40)
    # Plan semantics are validated separately so the one-repair/fallback flow remains available.
    plan:dict|None
class NewConversation(Strict):
    title:str=Field(default='新的学习对话',min_length=1,max_length=120)
    knowledge_id:str|None=None
    question_id:int|None=Field(default=None,ge=1)
class SendMessage(Strict):
    message:str=Field(min_length=1,max_length=2000)
    request_key:str=Field(min_length=8,max_length=100)
    mode:Literal['rag','agent']='rag'
class EmptyArgs(Strict):pass
class TopicArgs(Strict):
    knowledge_id:str=Field(min_length=2,max_length=50)
class WrongArgs(Strict):
    limit:int=Field(default=5,ge=1,le=10)
class SearchArgs(Strict):
    query:str=Field(min_length=2,max_length=300)
    knowledge_id:str|None=None
class PlanTask(Strict):
    knowledge_id:str
    question_count:int=Field(ge=1,le=10)
    estimated_minutes:int=Field(ge=5,le=90)
    reason:str=Field(min_length=3,max_length=500)
    question_ids:list[int]=Field(default_factory=list,max_length=10)
    conditional_on_pass:bool=False
class PlanDay(Strict):
    day:int=Field(ge=1,le=3)
    tasks:list[PlanTask]=Field(min_length=1,max_length=3)
class StudyPlan(Strict):
    goal:str=Field(min_length=2,max_length=200)
    days:list[PlanDay]=Field(min_length=3,max_length=3)
    basis:list[str]=Field(min_length=1,max_length=8)
class SavePlanInput(Strict):
    turn_id:str
    request_key:str=Field(min_length=8,max_length=100)
class StartPlanInput(Strict):
    day:int=Field(ge=1,le=3)
    task:int=Field(ge=0,le=2)
