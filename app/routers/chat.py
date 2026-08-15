import time
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.utils.database import get_db, get_redis
from app.models.models import (
    Session, SessionStatus, Message, MessageRole, User
)
from app.schemas.schemas import ChatRequest, ChatResponse, APIResponse
from app.services.llm_service import LLMService

router = APIRouter(prefix="/api/v1/chat", tags=["对话管理"])

llm_service = LLMService()


@router.post("/send", response_model=ChatResponse)
async def send_message(
    chat_data: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, chat_data.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    session_id = chat_data.session_id
    if session_id:
        session = await db.get(Session, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")
        if session.status == SessionStatus.CLOSED:
            raise HTTPException(status_code=400, detail="会话已关闭")
    else:
        session_id = str(uuid.uuid4())
        session = Session(
            id=session_id,
            user_id=chat_data.user_id,
            status=SessionStatus.ACTIVE,
        )
        db.add(session)

    start_time = time.time()

    user_message = Message(
        session_id=session_id,
        role=MessageRole.USER,
        content=chat_data.message,
    )
    db.add(user_message)

    reply, intent, token_count = await llm_service.chat(
        user_id=chat_data.user_id,
        session_id=session_id,
        message=chat_data.message,
    )

    response_time_ms = int((time.time() - start_time) * 1000)

    assistant_message = Message(
        session_id=session_id,
        role=MessageRole.ASSISTANT,
        content=reply,
        token_count=token_count,
        response_time_ms=response_time_ms,
    )
    db.add(assistant_message)

    session.message_count += 2
    session.last_intent = intent
    session.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(assistant_message)

    return ChatResponse(
        message_id=assistant_message.id,
        session_id=session_id,
        reply=reply,
        intent=intent,
        response_time_ms=response_time_ms,
    )


@router.get("/history/{session_id}", response_model=APIResponse)
async def get_chat_history(
    session_id: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    query = select(Message).where(Message.session_id == session_id)
    query = query.order_by(Message.created_at.desc()).limit(limit)
    result = await db.execute(query)
    messages = result.scalars().all()

    return APIResponse(
        code=0,
        message="获取成功",
        data={
            "session_id": session_id,
            "messages": [
                {
                    "id": m.id,
                    "role": m.role.value,
                    "content": m.content,
                    "token_count": m.token_count,
                    "response_time_ms": m.response_time_ms,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in reversed(messages)
            ],
        },
    )


@router.get("/sessions/{user_id}", response_model=APIResponse)
async def get_user_sessions(
    user_id: int,
    page: int = 1,
    page_size: int = 10,
    db: AsyncSession = Depends(get_db),
):
    query = select(Session).where(
        Session.user_id == user_id,
        Session.status == SessionStatus.ACTIVE,
    )
    query = query.order_by(Session.updated_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    sessions = result.scalars().all()

    return APIResponse(
        code=0,
        message="获取成功",
        data=[
            {
                "id": s.id,
                "status": s.status.value,
                "message_count": s.message_count,
                "last_intent": s.last_intent,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            }
            for s in sessions
        ],
    )
