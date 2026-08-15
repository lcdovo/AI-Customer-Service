import time
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.utils.database import get_db
from app.models.models import (
    Session, SessionStatus, Message, MessageRole, User, AgentTrace
)
from app.schemas.schemas import ChatRequest, ChatResponse, APIResponse
from app.agent.graph import AgentGraph
from app.agent.state import AgentState
from app.agent.memory import session_manager

router = APIRouter(prefix="/api/v1/chat", tags=["对话管理"])

agent_graph = AgentGraph()


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
        await db.commit()

    # 保存用户消息
    user_message = Message(
        session_id=session_id,
        role=MessageRole.USER,
        content=chat_data.message,
    )
    db.add(user_message)

    # 使用 Agent 处理
    agent_state = AgentState(
        session_id=session_id,
        user_id=chat_data.user_id,
        user_message=chat_data.message,
    )

    # 从会话管理器加载历史上下文
    saved_state = await session_manager.get_state(session_id)
    if saved_state:
        agent_state.messages = saved_state.messages
        agent_state.collected_info = saved_state.collected_info

    # 运行 Agent 状态机
    agent_state = await agent_graph.run(agent_state)

    # 保存 Agent 执行轨迹
    if agent_state.trace:
        base_trace_id = str(uuid.uuid4())
        for i, trace_entry in enumerate(agent_state.trace):
            agent_trace = AgentTrace(
                trace_id=f"{base_trace_id}_{i}",
                session_id=session_id,
                intent=agent_state.detected_intent,
                node_name=trace_entry.get("node", "unknown"),
                node_order=i,
                input_data=trace_entry.get("input"),
                output_data=trace_entry.get("output"),
                duration_ms=trace_entry.get("duration_ms", 0),
                success=True,
            )
            db.add(agent_trace)

    # 保存助手回复
    response_time_ms = agent_state.execution_time_ms
    assistant_message = Message(
        session_id=session_id,
        role=MessageRole.ASSISTANT,
        content=agent_state.reply,
        token_count=agent_state.total_tokens,
        response_time_ms=response_time_ms,
        tool_calls=[{"name": tc.tool_name, "success": tc.success} for tc in agent_state.tool_calls],
    )
    db.add(assistant_message)

    session.message_count += 2
    session.last_intent = agent_state.detected_intent
    session.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(assistant_message)

    # 更新会话管理器状态
    await session_manager.save_state(agent_state)

    return ChatResponse(
        message_id=assistant_message.id,
        session_id=session_id,
        reply=agent_state.reply,
        intent=agent_state.detected_intent,
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


@router.get("/tools", response_model=APIResponse)
async def get_available_tools():
    """获取所有可用工具列表"""
    from app.agent.tools import get_all_tools

    tools = get_all_tools()
    return APIResponse(
        code=0,
        message="获取成功",
        data=[
            {
                "name": t.name,
                "description": t.description,
                "parameters": [
                    {
                        "name": p["name"],
                        "type": p["type"],
                        "description": p["description"],
                        "required": p.get("required", True),
                    }
                    for p in t.parameters
                ],
            }
            for t in tools
        ],
    )


@router.get("/intents", response_model=APIResponse)
async def get_intent_types():
    """获取支持的意图类型"""
    intents = [
        {"code": "query_order", "name": "订单查询", "description": "查询订单状态与物流"},
        {"code": "refund", "name": "退换货", "description": "申请退换货"},
        {"code": "complaint", "name": "投诉", "description": "用户投诉处理"},
        {"code": "technical", "name": "技术咨询", "description": "产品使用与技术问题"},
        {"code": "promotion", "name": "活动咨询", "description": "优惠活动咨询"},
        {"code": "human", "name": "转人工", "description": "转接人工客服"},
        {"code": "general", "name": "通用", "description": "普通咨询"},
    ]
    return APIResponse(code=0, message="获取成功", data=intents)
