from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool
from redis import asyncio as aioredis
from redis.asyncio import Redis

from app.config.config import settings
from app.models.models import Base


# 根据数据库类型选择引擎配置
if settings.DATABASE_URL.startswith("sqlite"):
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
else:
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        poolclass=AsyncAdaptedQueuePool,
        pool_size=20,
        max_overflow=10,
        pool_pre_ping=True,
    )

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

redis_client: Optional[Redis] = None


async def get_redis() -> Optional[Redis]:
    global redis_client
    if redis_client is None:
        try:
            redis_client = aioredis.Redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
        except Exception:
            redis_client = None
    return redis_client


async def close_redis():
    global redis_client
    if redis_client:
        try:
            await redis_client.close()
        except Exception:
            pass
        redis_client = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with get_db() as session:
        yield session


async def init_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 创建默认用户（如果不存在）
    from app.models.models import User
    async with async_session() as session:
        from sqlalchemy import select
        result = await session.execute(select(User).limit(1))
        existing = result.first()
        if not existing:
            default_users = [
                User(id=1, username='user001', nickname='普通用户', level='normal'),
                User(id=2, username='user002', nickname='VIP用户', level='vip'),
                User(id=999, username='admin', nickname='管理员', level='admin'),
            ]
            session.add_all(default_users)
            await session.commit()
