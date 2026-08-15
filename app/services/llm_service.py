import json
import time
from typing import Optional, Tuple

import httpx

from app.config.config import settings


INTENT_KEYWORDS = {
    "query_order": ["订单", "物流", "发货", "快递", "查询", "单号"],
    "refund": ["退款", "退货", "退换", "售后", "拒收"],
    "complaint": ["投诉", "差评", "不满", "气愤", "骗子"],
    "technical": ["怎么用", "如何", "设置", "安装", "教程", "问题", "报错"],
    "promotion": ["优惠", "活动", "折扣", "券", "促销", "便宜"],
    "human": ["人工", "客服", "转人工", "找客服"],
}


class LLMService:
    def __init__(self):
        self.api_base = settings.LLM_API_BASE
        self.api_key = settings.LLM_API_KEY
        self.model = settings.LLM_MODEL
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.api_base,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
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

        if self.api_key and self.api_key != "your-api-key-here":
            try:
                reply, token_count = await self._call_llm_api(
                    user_id, session_id, message, context
                )
                return reply, intent, token_count
            except Exception:
                pass

        reply = self._get_mock_reply(intent, message)
        return reply, intent, len(message)

    async def _call_llm_api(
        self,
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
            "model": self.model,
            "messages": messages,
            "max_tokens": 1024,
            "temperature": 0.7,
        }

        response = await client.post("/chat/completions", json=payload)
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
            "complaint": "非常抱歉给您带来不好的体验。我已经记录了您的反馈，会有专门的客服团队尽快与您联系处理。请问方便留下您的联系方式吗？",
            "technical": "我来帮您解决这个问题。请详细描述一下您遇到的情况，包括具体的操作步骤和报错信息，这样我能更准确地为您提供解决方案。",
            "promotion": "目前我们有以下优惠活动：\n1. 新用户首单立减20元\n2. 满199减30\n3. VIP会员享受95折优惠\n您可以在结算时自动享受相应优惠。",
            "human": "好的，正在为您转接人工客服。预计等待时间约1-3分钟，请稍候...",
            "general": "感谢您的咨询。我已经收到您的消息，会尽快为您处理。如果您有订单相关的问题，可以提供订单号；如果是其他问题，请详细描述，我会尽力帮助您。",
        }
        return replies.get(intent, replies["general"])
