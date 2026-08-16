import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete

from app.utils.database import get_db
from app.models.models import User, UserLevel
from app.schemas.schemas import UserCreate, UserResponse, UserUpdate, APIResponse

router = APIRouter(prefix="/api/v1/users", tags=["用户管理"])


@router.post("/login", response_model=APIResponse)
async def login(username: str, role: str = "user", db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.username == username))
    user = existing.scalar_one_or_none()

    if user:
        return APIResponse(
            code=0,
            message="登录成功",
            data={
                "id": user.id,
                "username": user.username,
                "nickname": user.nickname or user.username,
                "level": user.level.value,
                "role": role,
            },
        )

    user = User(
        username=username,
        nickname=username,
        level=UserLevel.VIP if role == "admin" else UserLevel.NORMAL,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return APIResponse(
        code=0,
        message="登录成功（新用户已自动创建）",
        data={
            "id": user.id,
            "username": user.username,
            "nickname": user.nickname or user.username,
            "level": user.level.value,
            "role": role,
        },
    )


@router.post("/", response_model=APIResponse)
async def create_user(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.username == user_data.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名已存在")

    user = User(
        username=user_data.username,
        nickname=user_data.nickname,
        level=UserLevel(user_data.level),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return APIResponse(
        code=0,
        message="创建成功",
        data={
            "id": user.id,
            "username": user.username,
            "nickname": user.nickname,
            "level": user.level.value,
        },
    )


@router.get("/", response_model=APIResponse)
async def list_users(
    page: int = 1,
    page_size: int = 20,
    level: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(User)
    if level:
        query = query.where(User.level == UserLevel(level))

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    users = result.scalars().all()

    return APIResponse(
        code=0,
        message="获取成功",
        data=[
            {
                "id": u.id,
                "username": u.username,
                "nickname": u.nickname,
                "level": u.level.value,
                "status": u.status,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ],
    )


@router.get("/{user_id}", response_model=APIResponse)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    return APIResponse(
        code=0,
        message="获取成功",
        data={
            "id": user.id,
            "username": user.username,
            "nickname": user.nickname,
            "level": user.level.value,
            "avatar_url": user.avatar_url,
            "tags": user.tags,
            "status": user.status,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
    )


@router.put("/{user_id}", response_model=APIResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    update_data = user_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if hasattr(user, key) and value is not None:
            if key == "level":
                value = UserLevel(value)
            setattr(user, key, value)

    user.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(user)

    return APIResponse(code=0, message="更新成功", data={"id": user.id})


@router.delete("/{user_id}", response_model=APIResponse)
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    user.status = False
    user.updated_at = datetime.utcnow()
    await db.commit()

    return APIResponse(code=0, message="删除成功", data=None)
