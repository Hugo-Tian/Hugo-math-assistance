from typing import Literal
from pydantic import BaseModel, Field, model_validator

class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=60, pattern=r'^[a-zA-Z0-9_-]+$')
    password: str = Field(min_length=8, max_length=128)

class SessionInput(BaseModel):
    mode: Literal['custom', 'adaptive', 'review'] = 'adaptive'
    knowledge_id: str | None = None
    difficulty: int | None = Field(default=None, ge=1, le=3)
    count: int = Field(default=5, ge=1, le=30)
    question_id: int | None = None

class AnswerInput(BaseModel):
    question_id: int
    selected: int = Field(ge=0, le=3)
    idempotency_key: str = Field(min_length=8, max_length=100)

class KnowledgeInput(BaseModel):
    # New courses namespace ids as "<course>.<slug>"; subject always comes from the course.
    id: str = Field(pattern=r'^[a-z0-9_.-]{2,50}$')
    name: str = Field(min_length=1, max_length=100)
    chapter: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=3000)
    position: int = Field(ge=0, le=10000)
    prerequisites: list[str] = Field(default_factory=list, max_length=30)

class QuestionInput(BaseModel):
    knowledge_id: str
    auxiliary_ids: list[str] = Field(default_factory=list, max_length=10)
    stem: str = Field(min_length=3, max_length=5000)
    options: list[str] = Field(min_length=4, max_length=4)
    answer: int = Field(ge=0, le=3)
    explanation: str = Field(min_length=3, max_length=5000)
    difficulty: int = Field(ge=1, le=3)
    source: str = Field(min_length=3, max_length=255)
    active: bool = True

    @model_validator(mode='after')
    def valid_options(self):
        if any(not o.strip() or len(o) > 2000 for o in self.options) or len(set(self.options)) != 4:
            raise ValueError('选项必须是四个不同的非空文本')
        return self

class GoalInput(BaseModel):
    knowledge_id: str | None = None

class CourseInput(BaseModel):
    id: str = Field(pattern=r'^[a-z0-9-]{2,40}$')
    name: str = Field(min_length=2, max_length=100)
    subject: str = Field(pattern=r'^[a-z_]{2,30}$')
    level: Literal['middle', 'high', 'university']
    language: str = Field(default='zh', pattern=r'^[a-z]{2}(-[A-Z]{2})?$')
    settings: dict = Field(default_factory=dict)

class MemberInput(BaseModel):
    username: str = Field(min_length=3, max_length=60)
    role: Literal['teacher', 'ta', 'student'] = 'student'
