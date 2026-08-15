"""
多轮对话状态管理 - Phase 3 增强版
基于 Redis 的会话状态追踪
支持会话中断恢复、多设备同步、上下文压缩、智能摘要
Redis 不可用时降级为内存存储
"""
import json
import time
import uuid
import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from app.agent.state import AgentState
from app.utils.database import get_redis

logger = logging.getLogger(__name__)

SESSION_TTL_SECONDS = 86400
MAX_MESSAGES_BEFORE_COMPRESSION = 40
MIN_MESSAGES_AFTER_COMPRESSION = 10
SUMMARY_MAX_LENGTH = 500


class ConversationSummary:
    """对话摘要"""

    def __init__(self):
        self.summary_text: str = ""
        self.key_topics: List[str] = []
        self.entities: List[str] = []
        self.intent_history: List[str] = []
        self.message_count: int = 0
        self.created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary_text": self.summary_text,
            "key_topics": self.key_topics,
            "entities": self.entities,
            "intent_history": self.intent_history,
            "message_count": self.message_count,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationSummary":
        summary = cls()
        summary.summary_text = data.get("summary_text", "")
        summary.key_topics = data.get("key_topics", [])
        summary.entities = data.get("entities", [])
        summary.intent_history = data.get("intent_history", [])
        summary.message_count = data.get("message_count", 0)
        summary.created_at = data.get("created_at", "")
        return summary


class SessionManager:
    """会话状态管理器 - Phase 3 增强版"""

    def __init__(self):
        self._state_cache: Dict[str, AgentState] = {}
        self._redis_available: Optional[bool] = None
        self._summaries: Dict[str, ConversationSummary] = {}

    async def _is_redis_available(self) -> bool:
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

    async def create_session(
        self, user_id: int, session_id: Optional[str] = None
    ) -> str:
        if not session_id:
            session_id = str(uuid.uuid4())

        state = AgentState(
            session_id=session_id,
            user_id=user_id,
            user_message="",
        )

        self._state_cache[session_id] = state

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
            except Exception as e:
                logger.warning(f"Redis 存储失败: {e}")

        return session_id

    async def get_state(self, session_id: str) -> Optional[AgentState]:
        if session_id in self._state_cache:
            return self._state_cache[session_id]

        if await self._is_redis_available():
            try:
                redis = await get_redis()
                data = await redis.get(f"session:{session_id}")
                if data:
                    state = self._deserialize_state(json.loads(data))
                    self._state_cache[session_id] = state
                    return state
            except Exception as e:
                logger.warning(f"Redis 读取失败: {e}")

        return None

    async def save_state(self, state: AgentState):
        self._state_cache[state.session_id] = state

        if await self._is_redis_available():
            try:
                redis = await get_redis()
                await redis.setex(
                    f"session:{state.session_id}",
                    SESSION_TTL_SECONDS,
                    json.dumps(self._serialize_state(state)),
                )
            except Exception as e:
                logger.warning(f"Redis 保存失败: {e}")

    async def append_message(self, session_id: str, message: Dict[str, Any]):
        state = await self.get_state(session_id)
        if not state:
            return

        state.messages.append(message)

        if len(state.messages) > MAX_MESSAGES_BEFORE_COMPRESSION:
            compressed = await self._compress_context(state)
            if compressed:
                summary = self._summarize_messages(state.messages[:-MIN_MESSAGES_AFTER_COMPRESSION])
                self._summaries[session_id] = summary
                state.conversation_summary = summary.summary_text

        await self.save_state(state)

    async def _compress_context(self, state: AgentState) -> bool:
        if len(state.messages) <= MIN_MESSAGES_AFTER_COMPRESSION:
            return False

        recent = state.messages[-MIN_MESSAGES_AFTER_COMPRESSION:]
        older = state.messages[:-MIN_MESSAGES_AFTER_COMPRESSION]

        summary = self._generate_summary(older)
        if not summary:
            return False

        summary_msg = {
            "role": "system",
            "content": f"[对话摘要] {summary}",
            "type": "summary",
            "message_count": len(older),
            "generated_at": datetime.now().isoformat(),
        }

        state.messages = [summary_msg] + recent
        logger.info(
            f"压缩会话上下文: {len(older)} 条消息压缩为摘要, 保留 {len(recent)} 条"
        )
        return True

    def _generate_summary(self, messages: List[Dict[str, Any]]) -> str:
        user_messages = [m for m in messages if m.get("role") == "user"]
        assistant_messages = [m for m in messages if m.get("role") == "assistant"]

        topics = []
        entities = []

        for msg in user_messages:
            content = msg.get("content", "")
            if content:
                topics.append(content[:30])

                import re
                order_ids = re.findall(r'ORD\d{6,}', content.upper())
                entities.extend(order_ids)

        for msg in assistant_messages:
            content = msg.get("content", "")
            if content and any(
                kw in content
                for kw in ["订单", "退款", "工单", "物流", "状态", "金额"]
            ):
                entities.append(content[:50])

        if not topics:
            return ""

        summary_parts = []
        for i, topic in enumerate(topics[-5:]):
            summary_parts.append(f"{i + 1}. 用户询问: {topic}")

        entity_str = ", ".join(set(entities[:5]))
        if entity_str:
            summary_parts.append(f"涉及实体: {entity_str}")

        return " | ".join(summary_parts)[:SUMMARY_MAX_LENGTH]

    def _summarize_messages(self, messages: List[Dict[str, Any]]) -> ConversationSummary:
        summary = ConversationSummary()
        summary.message_count = len(messages)
        summary.created_at = datetime.now().isoformat()

        user_messages = [m for m in messages if m.get("role") == "user"]
        assistant_messages = [m for m in messages if m.get("role") == "assistant"]

        topics = []
        for msg in user_messages:
            content = msg.get("content", "")
            if content:
                topics.append(content[:30])

        summary.key_topics = list(set(topics))[:10]

        import re

        entities = []
        for msg in messages:
            content = msg.get("content", "")
            order_ids = re.findall(r'ORD\d{6,}', content.upper())
            entities.extend(order_ids)

        summary.entities = list(set(entities))[:10]

        summary.intent_history = [
            m.get("intent", "unknown")
            for m in assistant_messages
            if m.get("intent")
        ]

        summary.summary_text = self._generate_summary(messages)

        return summary

    async def get_messages(
        self, session_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        state = await self.get_state(session_id)
        if state:
            return state.messages[-limit:]
        return []

    async def get_summary(self, session_id: str) -> Optional[ConversationSummary]:
        if session_id in self._summaries:
            return self._summaries[session_id]

        state = await self.get_state(session_id)
        if state and state.conversation_summary:
            summary = ConversationSummary()
            summary.summary_text = state.conversation_summary
            summary.message_count = len(state.messages)
            return summary

        return None

    async def close_session(self, session_id: str):
        state = await self.get_state(session_id)
        if state:
            state.current_node = "end"
            await self.save_state(state)

        if await self._is_redis_available():
            try:
                redis = await get_redis()
                await redis.delete(f"session:{session_id}")
            except Exception as e:
                logger.warning(f"Redis 删除失败: {e}")

        if session_id in self._state_cache:
            del self._state_cache[session_id]

    async def get_user_sessions(
        self, user_id: int, limit: int = 10
    ) -> List[str]:
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
            except Exception as e:
                logger.warning(f"Redis 读取用户会话失败: {e}")

        return [
            sid
            for sid, state in self._state_cache.items()
            if state.user_id == user_id and state.current_node != "end"
        ][:limit]

    def get_session_stats(self, session_id: str) -> Dict[str, Any]:
        state = self._state_cache.get(session_id)
        if not state:
            return {"exists": False}

        summary = self._summaries.get(session_id)

        return {
            "exists": True,
            "message_count": len(state.messages),
            "has_summary": state.conversation_summary is not None,
            "summary_preview": (
                state.conversation_summary[:100]
                if state.conversation_summary
                else ""
            ),
            "current_intent": state.detected_intent,
            "last_node": state.current_node,
            "summaries_count": len(self._summaries),
            "total_cached_sessions": len(self._state_cache),
        }

    def _serialize_state(self, state: AgentState) -> Dict[str, Any]:
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
            "conversation_summary": state.conversation_summary,
            "created_at": datetime.now().isoformat(),
        }

    def _deserialize_state(self, data: Dict[str, Any]) -> AgentState:
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
            conversation_summary=data.get("conversation_summary"),
        )


session_manager = SessionManager()
