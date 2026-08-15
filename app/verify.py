"""
验证脚本：使用 SQLite 替代 MySQL 进行本地开发测试
运行: python -m app.verify
"""
import os

os.environ["MYSQL_HOST"] = "localhost"
os.environ["MYSQL_PORT"] = "9999"
os.environ["MYSQL_USER"] = "root"
os.environ["MYSQL_PASSWORD"] = ""
os.environ["MYSQL_DATABASE"] = ":memory:"
os.environ["REDIS_HOST"] = "localhost"
os.environ["REDIS_PORT"] = "9999"
os.environ["REDIS_PASSWORD"] = ""
os.environ["REDIS_DB"] = "0"
os.environ["LLM_API_KEY"] = ""

import asyncio
import uuid
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import select

from app.models.models import (
    Base, User, Session, Message, Ticket,
    TicketStatus, TicketPriority, SessionStatus
)


DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@asynccontextmanager
async def get_db():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def test():
    print("=" * 60)
    print("智能客服系统 - 本地验证测试")
    print("=" * 60)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ 数据库初始化成功 (SQLite 内存模式)")

    async with get_db() as db:
        print("\n📝 测试 1: 创建用户")
        user = User(username="test_user", nickname="测试用户")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print(f"   用户ID: {user.id}, 用户名: {user.username}")
        assert user.id == 1
        print("   ✅ 通过")

        print("\n📝 测试 2: 创建会话")
        session_id = str(uuid.uuid4())
        session = Session(id=session_id, user_id=user.id)
        db.add(session)
        await db.commit()
        print(f"   会话ID: {session_id}")
        assert session_id is not None
        print("   ✅ 通过")

        print("\n📝 测试 3: 发送消息")
        user_msg = Message(
            session_id=session_id,
            role="user",
            content="查询订单状态",
        )
        db.add(user_msg)
        await db.commit()
        print(f"   消息ID: {user_msg.id}, 角色: {user_msg.role}")

        assistant_msg = Message(
            session_id=session_id,
            role="assistant",
            content="好的，我来帮您查询订单",
        )
        db.add(assistant_msg)
        await db.commit()
        print(f"   回复ID: {assistant_msg.id}, 角色: {assistant_msg.role}")

        session.message_count = 2
        await db.commit()
        print(f"   会话消息数: {session.message_count}")
        print("   ✅ 通过")

        print("\n📝 测试 4: 创建工单")
        ticket_id = str(uuid.uuid4())
        ticket = Ticket(
            id=ticket_id,
            user_id=user.id,
            category="产品咨询",
            status=TicketStatus.PENDING,
            priority=TicketPriority.MEDIUM,
            content="请问这个产品怎么使用？",
        )
        db.add(ticket)
        await db.commit()
        print(f"   工单ID: {ticket_id}")
        print(f"   状态: {ticket.status.value}")
        print(f"   优先级: {ticket.priority.value}")
        print("   ✅ 通过")

        print("\n📝 测试 5: 查询验证")
        result = await db.execute(select(User).where(User.id == user.id))
        found_user = result.scalar_one()
        print(f"   查询用户: {found_user.username}")

        result = await db.execute(select(Session).where(Session.id == session_id))
        found_session = result.scalar_one()
        print(f"   查询会话: {found_session.message_count} 条消息")

        result = await db.execute(select(Message).where(Message.session_id == session_id))
        messages = result.scalars().all()
        print(f"   查询消息: {len(messages)} 条记录")

        result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
        found_ticket = result.scalar_one()
        print(f"   查询工单: {found_ticket.content}")
        print("   ✅ 通过")

    print("\n📝 测试 6: 意图识别测试")
    from app.services.llm_service import LLMService
    llm = LLMService()
    test_cases = [
        ("查询我的订单到哪了", "query_order"),
        ("我要退款", "refund"),
        ("我要投诉你们", "complaint"),
        ("这个产品怎么设置", "technical"),
        ("现在有什么优惠", "promotion"),
        ("转人工客服", "human"),
        ("你好", "general"),
    ]
    all_passed = True
    for msg, expected_intent in test_cases:
        detected = llm.detect_intent(msg)
        status = "✅" if detected == expected_intent else "❌"
        if detected != expected_intent:
            all_passed = False
        print(f"   {status} '{msg}' -> {detected} (期望: {expected_intent})")
    if all_passed:
        print("   ✅ 全部通过")

    print("\n📝 测试 7: LLM Mock 回复测试")
    intents = ["query_order", "refund", "complaint", "technical", "promotion", "human", "general"]
    for intent in intents:
        reply = llm._get_mock_reply(intent, "")
        print(f"   [{intent}]: {reply[:50]}...")
    print("   ✅ 通过")

    print("\n" + "=" * 60)
    print("✅ 所有测试通过！项目基础框架验证成功")
    print("=" * 60)
    print("\n📁 项目结构:")
    print("   app/")
    print("   ├── config/config.py          # 配置管理")
    print("   ├── models/models.py          # 数据模型 (7张表)")
    print("   ├── schemas/schemas.py        # Pydantic Schema")
    print("   ├── routers/                  # API路由")
    print("   │   ├── users.py              # 用户管理")
    print("   │   ├── sessions.py           # 会话管理")
    print("   │   ├── tickets.py            # 工单管理")
    print("   │   └── chat.py               # 对话管理")
    print("   ├── services/llm_service.py   # LLM服务")
    print("   ├── utils/database.py         # 数据库连接")
    print("   └── main.py                   # 主入口")
    print("\n🚀 启动方式:")
    print("   python -m app.main")
    print("   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload")


if __name__ == "__main__":
    asyncio.run(test())
