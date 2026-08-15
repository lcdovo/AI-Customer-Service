"""
LLM 服务 - Phase 3 增强版
支持多模型切换、降级策略、重试机制、调用统计
"""
import json
import time
import logging
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime

import httpx

from app.config.config import settings

logger = logging.getLogger(__name__)

INTENT_KEYWORDS = {
    "query_order": ["订单", "物流", "发货", "快递", "查询", "单号"],
    "refund": ["退款", "退货", "退换", "售后", "拒收"],
    "complaint": ["投诉", "差评", "不满", "气愤", "骗子"],
    "technical": ["怎么用", "如何", "设置", "安装", "教程", "问题", "报错"],
    "promotion": ["优惠", "活动", "折扣", "券", "促销", "便宜"],
    "human": ["人工", "客服", "转人工", "找客服"],
}


class ModelConfig:
    """模型配置"""

    def __init__(
        self,
        name: str,
        api_base: str = "",
        api_key: str = "",
        model: str = "",
        is_local: bool = False,
        priority: int = 0,
    ):
        self.name = name
        self.api_base = api_base
        self.api_key = api_key
        self.model = model
        self.is_local = is_local
        self.priority = priority
        self.failure_count = 0
        self.last_failure_time: float = 0
        self.circuit_open: bool = False


class CircuitBreaker:
    """熔断器 - 防止故障模型被反复调用"""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 300,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.states: Dict[str, Dict[str, Any]] = {}

    def can_execute(self, model_name: str) -> bool:
        state = self.states.get(model_name, {})

        if not state.get("open", False):
            return True

        last_failure = state.get("last_failure", 0)
        if time.time() - last_failure > self.recovery_timeout:
            self.reset(model_name)
            return True

        return False

    def record_failure(self, model_name: str):
        state = self.states.setdefault(model_name, {"failures": 0, "open": False, "last_failure": 0})
        state["failures"] = state.get("failures", 0) + 1
        state["last_failure"] = time.time()

        if state["failures"] >= self.failure_threshold:
            state["open"] = True
            logger.warning(f"模型 {model_name} 熔断器打开")

    def record_success(self, model_name: str):
        self.reset(model_name)

    def reset(self, model_name: str):
        self.states[model_name] = {"failures": 0, "open": False, "last_failure": 0}


class LLMService:
    """LLM 服务 - 支持多模型降级"""

    MAX_RETRIES = 2
    RETRY_DELAY = 1.0
    TIMEOUT = 30.0

    def __init__(self):
        self.models: List[ModelConfig] = []
        self.current_model_index: int = 0
        self.circuit_breaker = CircuitBreaker()
        self._client: Optional[httpx.AsyncClient] = None
        self.call_stats: Dict[str, Dict[str, int]] = {}

        self._init_models()

    def _init_models(self):
        primary = ModelConfig(
            name="primary",
            api_base=settings.LLM_API_BASE,
            api_key=settings.LLM_API_KEY,
            model=settings.LLM_MODEL,
            is_local=False,
            priority=0,
        )
        self.models.append(primary)

        if hasattr(settings, "LLM_BACKUP_BASE") and settings.LLM_BACKUP_BASE:
            backup = ModelConfig(
                name="backup",
                api_base=settings.LLM_BACKUP_BASE,
                api_key=getattr(settings, "LLM_BACKUP_KEY", ""),
                model=getattr(settings, "LLM_BACKUP_MODEL", "gpt-4o-mini"),
                is_local=False,
                priority=1,
            )
            self.models.append(backup)

        local = ModelConfig(
            name="local_fallback",
            api_base="",
            api_key="",
            model="local_mock",
            is_local=True,
            priority=2,
        )
        self.models.append(local)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.TIMEOUT,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.close()

    def detect_intent(self, message: str) -> str:
        message_lower = message.lower()
        scores = {}
        for intent, keywords in INTENT_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw.lower() in message_lower)
            if score > 0:
                scores[intent] = score

        if scores:
            return max(scores, key=scores.get)
        return "general"

    async def chat(
        self,
        user_id: int,
        session_id: str,
        message: str,
        context: Optional[list] = None,
    ) -> Tuple[str, str, int]:
        intent = self.detect_intent(message)

        for attempt in range(len(self.models)):
            model = self.models[attempt]

            if not self.circuit_breaker.can_execute(model.name):
                logger.info(f"模型 {model.name} 熔断器开启，跳过")
                continue

            try:
                if model.is_local:
                    reply = self._get_mock_reply(intent, message)
                    self.circuit_breaker.record_success(model.name)
                    self._record_stats(model.name, True)
                    return reply, intent, len(message)

                if model.api_key and model.api_key != "your-api-key-here":
                    reply, token_count = await self._call_model_api(
                        model, user_id, session_id, message, context
                    )
                    self.circuit_breaker.record_success(model.name)
                    self._record_stats(model.name, True)
                    return reply, intent, token_count

            except Exception as e:
                logger.warning(f"模型 {model.name} 调用失败: {e}")
                self.circuit_breaker.record_failure(model.name)
                self._record_stats(model.name, False)

                if attempt < len(self.models) - 1:
                    logger.info(f"降级到下一个模型")
                    continue

        reply = self._get_mock_reply(intent, message)
        return reply, intent, len(message)

    async def _call_model_api(
        self,
        model: ModelConfig,
        user_id: int,
        session_id: str,
        message: str,
        context: Optional[list] = None,
    ) -> Tuple[str, int]:
        client = self._get_client()

        system_prompt = self._get_system_prompt()
        messages = [{"role": "system", "content": system_prompt}]

        if context:
            messages.extend(context[-10:])

        messages.append({"role": "user", "content": message})

        payload = {
            "model": model.model,
            "messages": messages,
            "max_tokens": 1024,
            "temperature": 0.7,
        }

        headers = {
            "Authorization": f"Bearer {model.api_key}",
            "Content-Type": "application/json",
        }

        response = await client.post(
            f"{model.api_base}/chat/completions",
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()

        reply = data["choices"][0]["message"]["content"]
        token_count = data.get("usage", {}).get("total_tokens", len(message))

        return reply, token_count

    def _get_system_prompt(self) -> str:
        return """你是一个专业的智能客服助手。你的职责是：
1. 友好、专业地回应用户问题
2. 准确理解用户意图，提供准确的答案
3. 对于订单查询、退换货等操作，引导用户提供必要信息
4. 当无法解决时，主动建议转接人工客服
5. 回答要简洁明了，避免冗长"""

    def _get_mock_reply(self, intent: str, message: str) -> str:
        replies = {
            "query_order": "好的，我来帮您查询订单信息。请提供您的订单号，我会为您查询最新的物流状态和订单详情。",
            "refund": "关于退换货的问题，我可以帮您处理。请问您的订单号是多少？另外，请说明退换货的原因，我会为您指引相应的流程。",
            "complaint": "非常抱歉给您带来不好的体验。我已经记录了您的反馈，会有专门的客服团队尽快与您联系处理。",
            "technical": "我来帮您解决这个问题。请详细描述一下您遇到的情况，包括具体的操作步骤和报错信息，这样我能更准确地为您提供解决方案。",
            "promotion": "目前我们有以下优惠活动：\n1. 新用户首单立减20元\n2. 满199减30\n3. VIP会员享受95折优惠\n您可以在结算时自动享受相应优惠。",
            "human": "好的，正在为您转接人工客服。预计等待时间约1-3分钟，请稍候...",
            "general": "感谢您的咨询。我已经收到您的消息，会尽快为您处理。如果您有订单相关的问题，可以提供订单号；如果是其他问题，请详细描述，我会尽力帮助您。",
        }
        return replies.get(intent, replies["general"])

    def _record_stats(self, model_name: str, success: bool):
        stats = self.call_stats.setdefault(model_name, {"success": 0, "failure": 0, "total": 0})
        stats["total"] += 1
        if success:
            stats["success"] += 1
        else:
            stats["failure"] += 1

    def get_stats(self) -> Dict[str, Any]:
        return {
            "models": [
                {
                    "name": m.name,
                    "is_local": m.is_local,
                    "failure_count": m.failure_count,
                    "circuit_open": self.circuit_breaker.states.get(m.name, {}).get("open", False),
                    "stats": self.call_stats.get(m.name, {"success": 0, "failure": 0, "total": 0}),
                }
                for m in self.models
            ],
            "current_model": self.current_model_index,
            "timestamp": datetime.now().isoformat(),
        }

    def reset_circuit(self, model_name: Optional[str] = None):
        if model_name:
            self.circuit_breaker.reset(model_name)
        else:
            for m in self.models:
                self.circuit_breaker.reset(m.name)
