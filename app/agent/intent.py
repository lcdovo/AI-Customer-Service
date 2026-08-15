"""
增强意图识别 - 多层意图识别策略
第一层：关键词匹配（快速、低成本）
第二层：LLM 二次确认（模糊意图）
第三层：上下文推断（基于历史对话）
"""
import re
from typing import Tuple, Optional, List, Dict, Any
from dataclasses import dataclass


@dataclass
class IntentResult:
    intent: str
    confidence: float
    needs_clarification: bool = False
    sub_intent: Optional[str] = None


# 意图关键词映射 - 带有权重的关键词
INTENT_PATTERNS = {
    "query_order": {
        "high": ["订单号", "物流", "快递", "发货", "运单号", "配送"],
        "medium": ["订单", "查询", "跟踪", "到哪", "状态"],
        "low": ["查一下", "帮我看看", "我的单"],
    },
    "refund": {
        "high": ["退款", "退货", "退换", "退钱", "要钱", "退单"],
        "medium": ["售后", "拒收", "不想要", "不合适", "质量问题"],
        "low": ["退", "换", "不满意"],
    },
    "complaint": {
        "high": ["投诉", "差评", "举报", "骗", "气愤", "垃圾", "骗子"],
        "medium": ["不满", "生气", "失望", "太烂", "太差"],
        "low": ["不好", "差", "糟糕"],
    },
    "technical": {
        "high": ["怎么用", "如何", "安装", "设置", "配置", "教程"],
        "medium": ["问题", "报错", "故障", "坏了", "不工作", "没反应"],
        "low": ["使用", "操作", "功能"],
    },
    "promotion": {
        "high": ["优惠", "活动", "折扣", "券", "促销", "便宜", "减"],
        "medium": ["满减", "赠品", "特价", "限时", "满就送"],
        "low": ["划算", "实惠", "性价比"],
    },
    "human": {
        "high": ["人工", "客服", "转人工", "找客服", "真人", "在线客服"],
        "medium": ["投诉到", "找你们领导", "我要见人"],
        "low": ["help", "真人客服"],
    },
}

# 意图否定词（出现在有争议的关键词附近时降低权重）
NEGATION_WORDS = ["不是", "不要", "不", "非", "没有", "没"]


class EnhancedIntentRecognizer:
    """增强版意图识别器"""

    def __init__(self):
        self.patterns = INTENT_PATTERNS

    def recognize(
        self,
        message: str,
        context: Optional[List[Dict[str, Any]]] = None,
        history_intent: Optional[str] = None,
    ) -> IntentResult:
        """
        识别意图
        Args:
            message: 用户消息
            context: 上下文对话历史
            history_intent: 上一轮识别的意图
        Returns:
            IntentResult 包含意图、置信度、是否需要澄清
        """
        # 第一层：关键词匹配
        keyword_result = self._keyword_matching(message)
        
        # 第二层：检查否定词
        if keyword_result.confidence > 0:
            has_negation = self._check_negation(message, keyword_result.intent)
            if has_negation:
                keyword_result.confidence *= 0.5

        # 第三层：上下文推断
        if context and keyword_result.confidence < 0.3:
            context_intent = self._context_inference(context, message)
            if context_intent:
                keyword_result.intent = context_intent
                keyword_result.confidence = 0.5

        # 第四层：延续性判断
        if history_intent and self._is_continuation(message):
            # 如果消息很短且是追问，保持上一个意图
            if len(message) < 15 and keyword_result.confidence < 0.2:
                keyword_result.intent = history_intent
                keyword_result.confidence = 0.6

        # 判断是否需要澄清
        keyword_result.needs_clarification = keyword_result.confidence < 0.4

        return keyword_result

    def _keyword_matching(self, message: str) -> IntentResult:
        """关键词匹配"""
        message_lower = message.lower()
        scores: Dict[str, float] = {}

        for intent, levels in self.patterns.items():
            score = 0.0
            
            # 高权重关键词
            for keyword in levels.get("high", []):
                if keyword.lower() in message_lower:
                    score += 2.0
            
            # 中权重关键词
            for keyword in levels.get("medium", []):
                if keyword.lower() in message_lower:
                    score += 1.0
            
            # 低权重关键词
            for keyword in levels.get("low", []):
                if keyword.lower() in message_lower:
                    score += 0.3

            if score > 0:
                scores[intent] = score

        if scores:
            best_intent = max(scores, key=scores.get)
            max_score = scores[best_intent]
            
            # 归一化到 0-1 范围
            confidence = min(max_score / 4.0, 1.0)
            
            # 如果有两个意图得分接近，降低置信度
            if len(scores) > 1:
                sorted_scores = sorted(scores.values(), reverse=True)
                if sorted_scores[0] - sorted_scores[1] < 0.5:
                    confidence *= 0.7

            return IntentResult(
                intent=best_intent,
                confidence=round(confidence, 2),
            )

        return IntentResult(intent="general", confidence=0.0)

    def _check_negation(self, message: str, intent: str) -> bool:
        """检查否定词"""
        words = self.patterns.get(intent, {})
        all_keywords = []
        for level_words in words.values():
            all_keywords.extend(level_words)

        for keyword in all_keywords:
            idx = message.find(keyword)
            if idx > 0:
                # 检查关键词前面是否有否定词
                before = message[max(0, idx - 5):idx]
                for neg in NEGATION_WORDS:
                    if neg in before:
                        return True
        return False

    def _context_inference(
        self, context: List[Dict[str, Any]], message: str
    ) -> Optional[str]:
        """基于上下文推断意图"""
        recent_context = context[-3:] if len(context) >= 3 else context
        
        # 检查最近的工具调用
        for msg in reversed(recent_context):
            if msg.get("role") == "tool":
                tool_name = msg.get("tool_name", "")
                if "order" in tool_name.lower():
                    return "query_order"
                if "ticket" in tool_name.lower():
                    return "technical"
                if "refund" in tool_name.lower():
                    return "refund"

        return None

    def _is_continuation(self, message: str) -> bool:
        """判断是否为延续性追问"""
        continuation_patterns = [
            r"^[好的嗯哦啊哦好的]",
            r"^(那|然后|接着|还有)",
            r"^(好|行|可以|明白|知道了)",
            r"^(谢谢|感谢|多谢)",
            r"^\d+$",  # 纯数字，可能是在提供订单号
            r"^(对|是|没错|正确)",
        ]
        
        for pattern in continuation_patterns:
            if re.match(pattern, message):
                return True
        return False

    def get_clarification_question(self, intent: str) -> str:
        """获取澄清问题"""
        questions = {
            "query_order": "您想查询订单的什么信息呢？请提供订单号，我可以帮您查询物流状态和订单详情。",
            "refund": "您是想申请仅退款还是退货退款呢？另外，请提供订单号以便我为您处理。",
            "complaint": "非常抱歉给您带来不好的体验。能否请您详细描述一下遇到的问题？这样我们才能更好地帮助您。",
            "technical": "请问您具体遇到了什么问题呢？能否描述一下操作步骤和出现的情况？",
            "promotion": "我们目前有多种优惠活动，您想了解哪方面的信息呢？",
            "human": "好的，正在为您转接人工客服。请问有什么特别需要备注的信息吗？",
            "general": "我可以帮助您查询订单、处理退换货、解答产品问题等。请问有什么可以帮您的？",
        }
        return questions.get(intent, "请问您需要什么帮助呢？")
