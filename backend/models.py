from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, Boolean, DateTime, Date, ForeignKey, Text, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def utcnow():
    # Naive UTC, matching the existing DateTime columns.
    return datetime.now(timezone.utc).replace(tzinfo=None)

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default='student')
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    goal_id: Mapped[str | None] = mapped_column(ForeignKey('knowledge.id'), nullable=True)

class AuthToken(Base):
    __tablename__ = 'auth_tokens'
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    expires_at: Mapped[datetime] = mapped_column(DateTime)

class Knowledge(Base):
    __tablename__ = 'knowledge'
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    subject: Mapped[str] = mapped_column(String(30), default='math')
    chapter: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer)

class Prerequisite(Base):
    __tablename__ = 'prerequisites'
    knowledge_id: Mapped[str] = mapped_column(ForeignKey('knowledge.id'), primary_key=True)
    prerequisite_id: Mapped[str] = mapped_column(ForeignKey('knowledge.id'), primary_key=True)

class Question(Base):
    __tablename__ = 'questions'
    id: Mapped[int] = mapped_column(primary_key=True)
    knowledge_id: Mapped[str] = mapped_column(ForeignKey('knowledge.id'), index=True)
    auxiliary_ids: Mapped[list] = mapped_column(JSON, default=list)
    stem: Mapped[str] = mapped_column(Text)
    options: Mapped[list] = mapped_column(JSON)
    answer: Mapped[int] = mapped_column(Integer)
    explanation: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class PracticeSession(Base):
    __tablename__ = 'practice_sessions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    mode: Mapped[str] = mapped_column(String(20))
    knowledge_id: Mapped[str | None] = mapped_column(ForeignKey('knowledge.id'), nullable=True)
    difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_count: Mapped[int] = mapped_column(Integer)
    question_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ended: Mapped[bool] = mapped_column(Boolean, default=False)
    notice: Mapped[str] = mapped_column(Text, default='')

class Attempt(Base):
    __tablename__ = 'attempts'
    __table_args__ = (UniqueConstraint('user_id', 'idempotency_key'), UniqueConstraint('session_id', 'question_id'), UniqueConstraint('user_id', 'question_id', 'effective_day'))
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey('practice_sessions.id'))
    question_id: Mapped[int] = mapped_column(ForeignKey('questions.id'))
    knowledge_id: Mapped[str] = mapped_column(ForeignKey('knowledge.id'))
    selected: Mapped[int] = mapped_column(Integer)
    correct: Mapped[bool] = mapped_column(Boolean)
    effective_day: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    exclusion_reason: Mapped[str] = mapped_column(String(150), default='')
    idempotency_key: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    result: Mapped[dict] = mapped_column(JSON, default=dict)

class Exposure(Base):
    __tablename__ = 'answer_exposures'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey('questions.id'), primary_key=True)
    first_shown_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class Mastery(Base):
    __tablename__ = 'mastery'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    knowledge_id: Mapped[str] = mapped_column(ForeignKey('knowledge.id'), primary_key=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    samples: Mapped[int] = mapped_column(Integer, default=0)
    distinct_count: Mapped[int] = mapped_column(Integer, default=0)
    last_effective_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    passed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    difficulty_level: Mapped[int] = mapped_column(Integer, default=1)
    last_adjusted_count: Mapped[int] = mapped_column(Integer, default=0)

class Mistake(Base):
    __tablename__ = 'mistakes'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey('questions.id'), primary_key=True)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error_at: Mapped[datetime] = mapped_column(DateTime)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class Recommendation(Base):
    __tablename__ = 'recommendations'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    version: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
