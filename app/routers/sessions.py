import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.utils.database import get_db, get_redis
from app.models.models import Session, SessionStatus, User
from app.schemas.schemas import SessionCreate, APIResponse

router = APIRouter(prefix="/api/v1/sessions", tags=["会话管理"])

SESSION_TTL_SECONDS = 86400


@router.post("/", response_model=APIResponse)
async def create_session(
    session_data: SessionCreate,
    db: AsyncSession = Depends(get_db),
    redis=None,
):
    user = await db.get(User, session_data.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    session_id = str(uuid.uuid4())
    session = Session(
        id=session_id,
        user_id=session_data.user_id,
        status=SessionStatus.ACTIVE,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    if redis is None:
        redis = await get_redis()
    await redis.setex(
        f"session:{session_id}",
        SESSION_TTL_SECONDS,
        str(session_data.user_id),
    )

    return APIResponse(
        code=0,
        message="创建成功",
        data={
            "id": session.id,
            "user_id": session.user_id,
            "status": session.status.value,
            "created_at": session.created_at.isoformat() if session.created_at else None,
        },
    )


@router.get("/", response_model=APIResponse)
async def list_sessions(
    user_id: Optional[int] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    query = select(Session)
    if user_id:
        query = query.where(Session.user_id == user_id)
    if status:
        query = query.where(Session.status == SessionStatus(status))

    query = query.order_by(Session.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    sessions = result.scalars().all()

    return APIResponse(
        code=0,
        message="获取成功",
        data=[
            {
                "id": s.id,
                "user_id": s.user_id,
                "status": s.status.value,
                "csat_score": s.csat_score,
                "message_count": s.message_count,
                "last_intent": s.last_intent,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "closed_at": s.closed_at.isoformat() if s.closed_at else None,
            }
            for s in sessions
        ],
    )


@router.get("/{session_id}", response_model=APIResponse)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    return APIResponse(
        code=0,
        message="获取成功",
        data={
            "id": session.id,
            "user_id": session.user_id,
            "status": session.status.value,
            "csat_score": session.csat_score,
            "message_count": session.message_count,
            "last_intent": session.last_intent,
            "summary": session.summary,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "closed_at": session.closed_at.isoformat() if session.closed_at else None,
        },
    )


@router.put("/{session_id}/close", response_model=APIResponse)
async def close_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    session.status = SessionStatus.CLOSED
    session.closed_at = datetime.utcnow()
    await db.commit()

    return APIResponse(code=0, message="会话已关闭", data={"id": session_id})


@router.put("/{session_id}/score", response_model=APIResponse)
async def score_session(
    session_id: str,
    score: int,
    db: AsyncSession = Depends(get_db),
):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if score < 1 or score > 5:
        raise HTTPException(status_code=400, detail="评分必须在1-5之间")

    session.csat_score = score
    await db.commit()

    return APIResponse(code=0, message="评分成功", data={"id": session_id, "score": score})
