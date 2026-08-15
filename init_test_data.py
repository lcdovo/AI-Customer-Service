"""
使用 SQLAlchemy 初始化测试数据库并插入测试数据
"""
import os
import sys
import asyncio

os.environ["DATABASE_URL_OVERRIDE"] = "sqlite+aiosqlite:///./test.db"
os.environ["MYSQL_HOST"] = "localhost"
os.environ["MYSQL_PORT"] = "9999"
os.environ["MYSQL_USER"] = "root"
os.environ["MYSQL_PASSWORD"] = ""
os.environ["MYSQL_DATABASE"] = "customer_service"
os.environ["REDIS_HOST"] = "localhost"
os.environ["REDIS_PORT"] = "9999"
os.environ["REDIS_PASSWORD"] = ""
os.environ["REDIS_DB"] = "0"
os.environ["LLM_API_KEY"] = "test-key"

from app.utils.database import engine, init_database, async_session
from app.models.models import User, UserLevel, Session, SessionStatus, Ticket, TicketStatus, TicketPriority
from sqlalchemy import select


async def init_test_data():
    """插入测试数据"""
    async with async_session() as session:
        # 检查是否已有用户
        result = await session.execute(select(User).where(User.id == 1))
        user = result.scalar_one_or_none()
        
        if not user:
            # 创建测试用户
            user = User(
                id=1,
                username="testuser",
                nickname="测试用户",
                level=UserLevel.NORMAL,
                status=True,
            )
            session.add(user)
            await session.commit()
            print("✅ 创建测试用户: testuser (ID: 1)")
        else:
            print("ℹ️ 测试用户已存在")

        # 检查是否已有测试会话
        result = await session.execute(
            select(Session).where(Session.user_id == 1, Session.status == SessionStatus.ACTIVE)
        )
        existing_sessions = result.scalars().all()
        
        if not existing_sessions:
            print("ℹ️ 暂无活跃会话")


async def main():
    # 删除旧数据库
    if os.path.exists("test.db"):
        os.remove("test.db")
        print("🗑️ 已删除旧数据库")

    # 创建表
    print("🔨 创建数据库表...")
    await init_database()
    print("✅ 数据库表创建完成")

    # 插入测试数据
    print("📝 插入测试数据...")
    await init_test_data()
    print("✅ 测试数据初始化完成")

    print("\n" + "=" * 50)
    print("测试数据库初始化完成!")
    print("=" * 50)
    print("测试账号: testuser (ID: 1)")
    print("数据库: SQLite (test.db)")


if __name__ == "__main__":
    asyncio.run(main())
