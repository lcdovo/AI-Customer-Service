from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, Enum,
    Index, ForeignKey, JSON
)
from sqlalchemy.orm import DeclarativeBase, relationship
import enum


class Base(DeclarativeBase):
    pass


class UserLevel(str, enum.Enum):
    NORMAL = "normal"
    VIP = "vip"
    ENTERPRISE = "enterprise"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    nickname = Column(String(50), nullable=True)
    level = Column(Enum(UserLevel), default=UserLevel.NORMAL)
    avatar_url = Column(String(500), nullable=True)
    tags = Column(JSON, default=list)
    status = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sessions = relationship("Session", back_populates="user")
    tickets = relationship("Ticket", back_populates="user")


class SessionStatus(str, enum.Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    PENDING = "pending"


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(Enum(SessionStatus), default=SessionStatus.ACTIVE, index=True)
    csat_score = Column(Integer, nullable=True)
    message_count = Column(Integer, default=0)
    last_intent = Column(String(50), nullable=True)
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="sessions")
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey("sessions.id"), nullable=False, index=True)
    role = Column(Enum(MessageRole), nullable=False)
    content = Column(Text, nullable=False)
    token_count = Column(Integer, default=0)
    response_time_ms = Column(Integer, nullable=True)
    tool_calls = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    session = relationship("Session", back_populates="messages")


class TicketStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    RESOLVED = "resolved"
    CLOSED = "closed"
    ESCALATED = "escalated"


class TicketPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    category = Column(String(50), nullable=False, index=True)
    status = Column(Enum(TicketStatus), default=TicketStatus.PENDING, index=True)
    priority = Column(Enum(TicketPriority), default=TicketPriority.MEDIUM, index=True)
    content = Column(Text, nullable=False)
    assigned_to = Column(String(50), nullable=True)
    sla_deadline = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="tickets")


class KnowledgeDoc(Base):
    __tablename__ = "knowledge_docs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    category = Column(String(50), nullable=False, index=True)
    content = Column(Text, nullable=False)
    chunk_count = Column(Integer, default=0)
    version = Column(Integer, default=1)
    is_published = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AgentTrace(Base):
    __tablename__ = "agent_traces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trace_id = Column(String(100), unique=True, nullable=False, index=True)
    session_id = Column(String(36), ForeignKey("sessions.id"), nullable=True, index=True)
    intent = Column(String(50), nullable=True, index=True)
    node_name = Column(String(50), nullable=False)
    node_order = Column(Integer, default=0)
    input_data = Column(JSON, nullable=True)
    output_data = Column(JSON, nullable=True)
    tool_calls = Column(JSON, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    token_usage = Column(JSON, nullable=True)
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey("sessions.id"), nullable=True, index=True)
    sample_id = Column(String(50), nullable=True, index=True)
    accuracy_score = Column(Integer, nullable=True)
    completeness_score = Column(Integer, nullable=True)
    safety_score = Column(Integer, nullable=True)
    overall_score = Column(Integer, nullable=True, index=True)
    is_low_score = Column(Boolean, default=False, index=True)
    failure_reason = Column(String(200), nullable=True)
    processed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
