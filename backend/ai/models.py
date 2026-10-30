from datetime import datetime
from sqlalchemy import String, Text, JSON, DateTime, Boolean, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from ..db import Base
from ..models import utcnow

class Document(Base):
    __tablename__='kb_documents'
    id: Mapped[str]=mapped_column(String(36),primary_key=True)
    title: Mapped[str]=mapped_column(String(200))
    filename: Mapped[str]=mapped_column(String(200))
    checksum: Mapped[str]=mapped_column(String(64),unique=True)
    source: Mapped[str]=mapped_column(String(255))
    course_id: Mapped[str]=mapped_column(ForeignKey('courses.id'),index=True)
    # Course-wide material may not belong to a single knowledge point.
    knowledge_id: Mapped[str|None]=mapped_column(ForeignKey('knowledge.id'),nullable=True)
    version: Mapped[str]=mapped_column(String(30),default='1')
    scope: Mapped[str]=mapped_column(String(20),default='public')
    question_id: Mapped[int|None]=mapped_column(ForeignKey('questions.id'),nullable=True)
    status: Mapped[str]=mapped_column(String(30),default='parsed')
    error: Mapped[str|None]=mapped_column(String(300),nullable=True)
    active: Mapped[bool]=mapped_column(Boolean,default=True)
    created_at: Mapped[datetime]=mapped_column(DateTime,default=utcnow)

class Chunk(Base):
    __tablename__='kb_chunks'
    id: Mapped[str]=mapped_column(String(64),primary_key=True)
    document_id: Mapped[str]=mapped_column(ForeignKey('kb_documents.id'),index=True)
    title: Mapped[str]=mapped_column(String(200))
    chapter: Mapped[str]=mapped_column(String(100))
    page: Mapped[int|None]=mapped_column(Integer,nullable=True)
    content: Mapped[str]=mapped_column(Text)
    position: Mapped[int]=mapped_column(Integer)

class Conversation(Base):
    __tablename__='ai_conversations'
    id: Mapped[str]=mapped_column(String(36),primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    course_id: Mapped[str]=mapped_column(ForeignKey('courses.id'),index=True)
    title: Mapped[str]=mapped_column(String(120))
    knowledge_id: Mapped[str|None]=mapped_column(ForeignKey('knowledge.id'),nullable=True)
    question_id: Mapped[int|None]=mapped_column(ForeignKey('questions.id'),nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    deleted: Mapped[bool]=mapped_column(Boolean,default=False)

class ChatTurn(Base):
    __tablename__='ai_turns'
    __table_args__=(UniqueConstraint('conversation_id','request_key'),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True)
    conversation_id: Mapped[str]=mapped_column(ForeignKey('ai_conversations.id'),index=True)
    request_key: Mapped[str]=mapped_column(String(100))
    question: Mapped[str]=mapped_column(Text)
    answer: Mapped[str]=mapped_column(Text,default='')
    status: Mapped[str]=mapped_column(String(30),default='pending')
    mode: Mapped[str]=mapped_column(String(20))
    citations: Mapped[list]=mapped_column(JSON,default=list)
    plan: Mapped[dict|None]=mapped_column(JSON,nullable=True)
    metadata_json: Mapped[dict]=mapped_column(JSON,default=dict)
    created_at: Mapped[datetime]=mapped_column(DateTime,default=utcnow)

class ToolTrace(Base):
    __tablename__='ai_tool_traces'
    id: Mapped[int]=mapped_column(primary_key=True)
    turn_id: Mapped[str]=mapped_column(ForeignKey('ai_turns.id'),index=True)
    name: Mapped[str]=mapped_column(String(100))
    arguments: Mapped[dict]=mapped_column(JSON)
    status: Mapped[str]=mapped_column(String(40))
    elapsed_ms: Mapped[int]=mapped_column(Integer)

class SavedPlan(Base):
    __tablename__='ai_saved_plans'
    __table_args__=(UniqueConstraint('user_id','request_key'),UniqueConstraint('user_id','turn_id'))
    id: Mapped[str]=mapped_column(String(36),primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    turn_id: Mapped[str]=mapped_column(ForeignKey('ai_turns.id'))
    request_key: Mapped[str]=mapped_column(String(100))
    payload: Mapped[dict]=mapped_column(JSON)
    created_at: Mapped[datetime]=mapped_column(DateTime,default=utcnow)

class PlanPractice(Base):
    __tablename__='ai_plan_practices'
    __table_args__=(UniqueConstraint('plan_id','day','task'),)
    id: Mapped[int]=mapped_column(primary_key=True)
    plan_id: Mapped[str]=mapped_column(ForeignKey('ai_saved_plans.id'))
    day: Mapped[int]=mapped_column(Integer)
    task: Mapped[int]=mapped_column(Integer)
    session_id: Mapped[str]=mapped_column(ForeignKey('practice_sessions.id'))
