"""
结果三层校验机制 - Phase 3 实现
1. 事实校验：回答中的关键信息与工具返回结果一致性检查
2. 安全校验：敏感词过滤、Prompt注入检测、越权操作拦截
3. 完整性校验：是否回答了用户所有问题点
"""
import re
import time
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ValidationResult:
    """校验结果"""

    def __init__(self):
        self.passed: bool = True
        self.fact_score: float = 1.0
        self.safety_score: float = 1.0
        self.completeness_score: float = 1.0
        self.issues: List[Dict[str, Any]] = []
        self.suggestions: List[str] = []
        self.needs_regeneration: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "fact_score": round(self.fact_score, 2),
            "safety_score": round(self.safety_score, 2),
            "completeness_score": round(self.completeness_score, 2),
            "overall_score": round(
                (self.fact_score + self.safety_score + self.completeness_score) / 3, 2
            ),
            "issues": self.issues,
            "suggestions": self.suggestions,
            "needs_regeneration": self.needs_regeneration,
        }


class FactValidator:
    """事实校验器 - 检查回答与工具返回结果的一致性"""

    SENSITIVE_PATTERNS = [
        (r'\d{6}', "6位数字可能是订单号或密码，需确认完整性"),
        (r'\d{3}-\d{4}-\d{4}', "电话号码格式"),
    ]

    def validate(
        self,
        response: str,
        tool_results: List[Dict[str, Any]],
        user_query: str,
    ) -> Tuple[float, List[Dict[str, Any]]]:
        issues = []
        score = 1.0

        if not tool_results:
            return 1.0, []

        successful_results = [r for r in tool_results if r.get("success", False)]
        if not successful_results:
            return 1.0, []

        last_result = successful_results[-1]
        data = last_result.get("data", {})

        if not data:
            return 1.0, []

        response_lower = response.lower()

        def check_field(field_name: str, field_value: Any, min_score: float = 0.8):
            nonlocal score
            if field_value is None:
                return

            if isinstance(field_value, str):
                value_lower = field_value.lower()
                if value_lower and value_lower in response_lower:
                    score = min(score + 0.1, 1.0)
                elif value_lower and value_lower not in response_lower:
                    score -= 0.1
                    issues.append({
                        "type": "fact_missing",
                        "field": field_name,
                        "message": f"字段 '{field_name}' 的值 '{str(field_value)[:30]}' 在回答中缺失",
                        "severity": "warning",
                    })

            elif isinstance(field_value, (int, float)):
                value_str = str(field_value)
                if value_str in response:
                    score = min(score + 0.1, 1.0)
                else:
                    score -= 0.05
                    issues.append({
                        "type": "fact_missing",
                        "field": field_name,
                        "message": f"数值字段 '{field_name}' 的值 {field_value} 在回答中缺失",
                        "severity": "info",
                    })

        if isinstance(data, dict):
            for key, value in data.items():
                if key not in ["status_code", "created_at", "updated_at", "cancel_reason"]:
                    check_field(key, value)

            if "order_id" in data and data["order_id"] not in response:
                score -= 0.2
                issues.append({
                    "type": "fact_critical",
                    "message": "订单号未在回答中明确提及",
                    "severity": "error",
                })

            if "total_amount" in data:
                amount_str = str(data["total_amount"])
                if amount_str not in response:
                    score -= 0.1
                    issues.append({
                        "type": "fact_missing",
                        "message": "订单金额未在回答中体现",
                        "severity": "warning",
                    })

        score = max(0.0, min(1.0, score))
        return score, issues


class SafetyValidator:
    """安全校验器 - 检查敏感内容和安全风险"""

    SENSITIVE_WORDS = [
        ("自杀", "危险内容"),
        ("暴力", "暴力内容"),
        ("赌博", "违法内容"),
        ("诈骗", "违法内容"),
        ("hack", "攻击关键词"),
        ("注入", "安全风险"),
        ("DROP TABLE", "SQL注入尝试"),
    ]

    INJECTION_PATTERNS = [
        r"(忽略|忽视|忘记)(之前|以上|前面)(的)?(指令|提示|prompt)",
        r"system\s*prompt",
        r"你是(一个)?(新的|不同的|另一个)",
        r"role:\s*system",
    ]

    def validate(
        self,
        response: str,
        user_query: str,
    ) -> Tuple[float, List[Dict[str, Any]]]:
        issues = []
        score = 1.0

        response_lower = response.lower()
        query_lower = user_query.lower()

        for word, category in self.SENSITIVE_WORDS:
            if word.lower() in response_lower:
                score -= 0.3
                issues.append({
                    "type": "sensitive_content",
                    "category": category,
                    "word": word,
                    "message": f"回答中包含敏感内容: {word} ({category})",
                    "severity": "error",
                })

        for pattern in self.INJECTION_PATTERNS:
            if re.search(pattern, response_lower, re.IGNORECASE):
                score -= 0.5
                issues.append({
                    "type": "prompt_injection",
                    "pattern": pattern,
                    "message": "检测到潜在的 Prompt 注入风险",
                    "severity": "critical",
                })

        if len(response) > 5000:
            score -= 0.1
            issues.append({
                "type": "response_too_long",
                "message": f"回答过长 ({len(response)} 字符)，可能包含冗余信息",
                "severity": "info",
            })

        if not response.strip():
            score = 0.0
            issues.append({
                "type": "empty_response",
                "message": "回答为空",
                "severity": "critical",
            })

        score = max(0.0, min(1.0, score))
        return score, issues


class CompletenessValidator:
    """完整性校验器 - 检查是否回答了用户的问题"""

    QUESTION_MARKERS = ["？", "?", "吗", "呢", "怎么", "如何", "什么", "多少", "几"]

    def validate(
        self,
        response: str,
        user_query: str,
        intent: str,
    ) -> Tuple[float, List[Dict[str, Any]]]:
        issues = []
        score = 1.0

        query_has_question = any(marker in user_query for marker in self.QUESTION_MARKERS)

        if query_has_question and not response.strip():
            score = 0.0
            issues.append({
                "type": "no_response",
                "message": "用户提出了问题但系统未给出回答",
                "severity": "critical",
            })
            return score, issues

        query_keywords = self._extract_keywords(user_query)
        response_keywords = self._extract_keywords(response)

        if query_keywords:
            keyword_overlap = query_keywords & response_keywords
            overlap_ratio = len(keyword_overlap) / max(len(query_keywords), 1)

            if overlap_ratio < 0.3:
                score -= 0.3
                issues.append({
                    "type": "low_relevance",
                    "message": f"回答与用户问题相关性较低 (关键词重叠率: {overlap_ratio:.1%})",
                    "severity": "warning",
                })

        intent_checks = {
            "query_order": {
                "keywords": ["状态", "物流", "订单"],
                "min_length": 20,
            },
            "refund": {
                "keywords": ["退款", "退货", "步骤", "申请"],
                "min_length": 20,
            },
            "complaint": {
                "keywords": ["工单", "处理", "反馈"],
                "min_length": 20,
            },
            "technical": {
                "keywords": [],
                "min_length": 30,
            },
        }

        if intent in intent_checks:
            check = intent_checks[intent]

            if len(response) < check["min_length"]:
                score -= 0.2
                issues.append({
                    "type": "insufficient_detail",
                    "message": f"回答内容过于简短 ({len(response)} 字符)，建议提供更多详情",
                    "severity": "warning",
                })

            missing_keywords = [kw for kw in check["keywords"] if kw not in response]
            if missing_keywords:
                score -= 0.1
                issues.append({
                    "type": "missing_key_info",
                    "message": f"回答中缺少关键信息: {', '.join(missing_keywords)}",
                    "severity": "info",
                })

        score = max(0.0, min(1.0, score))
        return score, issues

    def _extract_keywords(self, text: str) -> set:
        text = text.lower()
        words = re.findall(r'[\u4e00-\u9fff]+', text)
        if not words:
            words = re.findall(r'[\w]+', text)
        return set(words) if words else set()


class ResponseValidator:
    """响应校验器 - 整合三层校验"""

    FACT_THRESHOLD = 0.6
    SAFETY_THRESHOLD = 0.8
    COMPLETENESS_THRESHOLD = 0.5
    OVERALL_THRESHOLD = 0.6

    MAX_REGENERATION_ATTEMPTS = 2

    def __init__(self):
        self.fact_validator = FactValidator()
        self.safety_validator = SafetyValidator()
        self.completeness_validator = CompletenessValidator()

    def validate(
        self,
        response: str,
        user_query: str,
        intent: str,
        tool_results: Optional[List[Dict[str, Any]]] = None,
    ) -> ValidationResult:
        result = ValidationResult()

        tool_results = tool_results or []

        fact_score, fact_issues = self.fact_validator.validate(
            response, tool_results, user_query
        )
        result.fact_score = fact_score
        result.issues.extend(fact_issues)

        safety_score, safety_issues = self.safety_validator.validate(
            response, user_query
        )
        result.safety_score = safety_score
        result.issues.extend(safety_issues)

        completeness_score, completeness_issues = self.completeness_validator.validate(
            response, user_query, intent
        )
        result.completeness_score = completeness_score
        result.issues.extend(completeness_issues)

        result.passed = self._check_pass(result)
        result.needs_regeneration = self._check_regeneration(result)
        result.suggestions = self._generate_suggestions(result)

        return result

    def _check_pass(self, result: ValidationResult) -> bool:
        if result.safety_score < self.SAFETY_THRESHOLD:
            return False

        if result.fact_score < self.FACT_THRESHOLD:
            return False

        if result.completeness_score < self.COMPLETENESS_THRESHOLD:
            return False

        overall = (result.fact_score + result.safety_score + result.completeness_score) / 3
        return overall >= self.OVERALL_THRESHOLD

    def _check_regeneration(self, result: ValidationResult) -> bool:
        if result.safety_score < 0.5:
            return True

        if result.fact_score < 0.4:
            return True

        if result.completeness_score < 0.3:
            return True

        critical_issues = [i for i in result.issues if i.get("severity") == "critical"]
        return len(critical_issues) > 0

    def _generate_suggestions(self, result: ValidationResult) -> List[str]:
        suggestions = []

        fact_issues = [i for i in result.issues if i.get("type", "").startswith("fact_")]
        if fact_issues:
            suggestions.append("建议在回答中补充工具返回的关键数据信息")

        safety_issues = [i for i in result.issues if i.get("type", "").startswith("sensitive_")]
        if safety_issues:
            suggestions.append("回答中包含敏感内容，需调整措辞")

        injection_issues = [i for i in result.issues if i.get("type") == "prompt_injection"]
        if injection_issues:
            suggestions.append("检测到安全风险，需重新生成回答")

        relevance_issues = [i for i in result.issues if i.get("type") == "low_relevance"]
        if relevance_issues:
            suggestions.append("回答与问题相关性较低，建议重新聚焦用户问题")

        if not suggestions and result.issues:
            suggestions.append("回答基本合格，可考虑优化表达")

        return suggestions


def create_validator() -> ResponseValidator:
    return ResponseValidator()
