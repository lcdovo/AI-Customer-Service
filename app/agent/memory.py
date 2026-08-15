"""
多轮对话状态管理 - 基于 Redis 的会话状态追踪
支持会话中断恢复、多设备同步、上下文压缩
Redis 不可用时降级为内存存储
"""
import json
import time
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime

from app.agent.state import AgentState
from app.utils.database import get_redis


SESSION_TTL_SECONDS = 86400  # 24小时


class SessionManager:
    """会话状态管理器"""

    def __init__(self):
        self._state_cache: Dict[str, AgentState] = {}
        self._redis_available: Optional[bool] = None

    async def _is_redis_available(self) -> bool:
        """检查 Redis 是否可用"""
        if self._redis_available is not None:
            return self._redis_available
        
        redis = await get_redis()
        if redis is None:
            self._redis_available = False
            return False
        
        try:
            await redis.ping()
            self._redis_available = True
            return True
        except Exception:
            self._redis_available = False
            return False

    async def create_session(self, user_id: int, session_id: Optional[str] = None) -> str:
        """创建新会话"""
        if not session_id:
            session_id = str(uuid.uuid4())

        state = AgentState(
            session_id=session_id,
            user_id=user_id,
            user_message="",
        )

        # 先保存到内存
        self._state_cache[session_id] = state

        # 如果 Redis 可用，同时存储
        if await self._is_redis_available():
            try:
                redis = await get_redis()
                await redis.setex(
                    f"session:{session_id}",
                    SESSION_TTL_SECONDS,
                    json.dumps(self._serialize_state(state)),
                )
                user_sessions_key = f"user_sessions:{user_id}"
                await redis.sadd(user_sessions_key, session_id)
                await redis.expire(user_sessions_key, SESSION_TTL_SECONDS)
            except Exception:
                pass

        return session_id

    async def get_state(self, session_id: str) -> Optional[AgentState]:
        """获取会话状态"""
        # 先从内存缓存获取
        if session_id in self._state_cache:
            return self._state_cache[session_id]

        # 从 Redis 获取
        if await self._is_redis_available():
            try:
                redis = await get_redis()
                data = await redis.get(f"session:{session_id}")
                if data:
                    state = self._deserialize_state(json.loads(data))
                    self._state_cache[session_id] = state
                    return state
            except Exception:
                pass

        return None

    async def save_state(self, state: AgentState):
        """保存会话状态"""
        # 更新内存缓存
        self._state_cache[state.session_id] = state

        # 更新 Redis
        if await self._is_redis_available():
            try:
                redis = await get_redis()
                await redis.setex(
                    f"session:{state.session_id}",
                    SESSION_TTL_SECONDS,
                    json.dumps(self._serialize_state(state)),
                )
            except Exception:
                pass

    async def append_message(self, session_id: str, message: Dict[str, Any]):
        """追加消息到会话"""
        state = await self.get_state(session_id)
        if state:
            state.messages.append(message)

            # 检查是否需要压缩上下文
            if len(state.messages) > 40:
                await self._compress_context(state)

            await self.save_state(state)

    async def get_messages(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """获取会话消息"""
        state = await self.get_state(session_id)
        if state:
            return state.messages[-limit:]
        return []

    async def close_session(self, session_id: str):
        """关闭会话"""
        state = await self.get_state(session_id)
        if state:
            state.current_node = "end"
            await self.save_state(state)

        if await self._is_redis_available():
            try:
                redis = await get_redis()
                await redis.delete(f"session:{session_id}")
            except Exception:
                pass

        if session_id in self._state_cache:
            del self._state_cache[session_id]

    async def get_user_sessions(self, user_id: int, limit: int = 10) -> List[str]:
        """获取用户的活跃会话列表"""
        if await self._is_redis_available():
            try:
                redis = await get_redis()
                user_sessions_key = f"user_sessions:{user_id}"
                session_ids = await redis.smembers(user_sessions_key)

                active_sessions = []
                for sid in session_ids:
                    state = await self.get_state(sid)
                    if state and state.current_node != "end":
                        active_sessions.append(sid)
                return active_sessions[:limit]
            except Exception:
                pass

        # 内存降级
        return [
            sid for sid, state in self._state_cache.items()
            if state.user_id == user_id and state.current_node != "end"
        ][:limit]

    async def _compress_context(self, state: AgentState):
        """压缩上下文 - 当消息过多时生成摘要"""
        if len(state.messages) <= 20:
            return

        recent_messages = state.messages[-10:]
        older_messages = state.messages[:-10]
        summary_parts = []
        for msg in older_messages:
            if msg["role"] == "user":
                summary_parts.append(f"用户: {msg['content'][:50]}")
            elif msg["role"] == "assistant":
                summary_parts.append(f"助手: {msg['content'][:50]}")

        state.messages = [
            {
                "role": "system",
                "content": f"[对话摘要] {' | '.join(summary_parts[-5:])}",
                "type": "summary",
            }
        ] + recent_messages

    def _serialize_state(self, state: AgentState) -> Dict[str, Any]:
        """序列化状态"""
        return {
            "session_id": state.session_id,
            "user_id": state.user_id,
            "user_message": state.user_message,
            "detected_intent": state.detected_intent,
            "intent_confidence": state.intent_confidence,
            "current_node": state.current_node,
            "messages": state.messages,
            "collected_info": state.collected_info,
            "reply": state.reply,
            "need_human": state.need_human,
            "user_emotion": state.user_emotion,
            "total_tokens": state.total_tokens,
            "created_at": datetime.now().isoformat(),
        }

    def _deserialize_state(self, data: Dict[str, Any]) -> AgentState:
        """反序列化状态"""
        return AgentState(
            session_id=data.get("session_id", ""),
            user_id=data.get("user_id", 0),
            user_message=data.get("user_message", ""),
            detected_intent=data.get("detected_intent", "general"),
            intent_confidence=data.get("intent_confidence", 0.0),
            current_node=data.get("current_node", "start"),
            messages=data.get("messages", []),
            collected_info=data.get("collected_info", {}),
            reply=data.get("reply", ""),
            need_human=data.get("need_human", False),
            user_emotion=data.get("user_emotion", "neutral"),
            total_tokens=data.get("total_tokens", 0),
        )


# 全局会话管理器实例
session_manager = SessionManager()
