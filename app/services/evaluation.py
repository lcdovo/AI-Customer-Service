"""
评价体系与低分样本回流 - Phase 4 实现
1. 多维度自动化评测
2. 低分样本回流闭环
3. A/B测试框架
"""
import time
import uuid
import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from collections import Counter
import math

logger = logging.getLogger(__name__)


class EvaluationDimension:
    """评测维度"""
    ACCURACY = "accuracy"
    COMPLETENESS = "completeness"
    SAFETY = "safety"
    RELEVANCE = "relevance"
    EFFICIENCY = "efficiency"


class EvaluationScore:
    """评测分数"""

    def __init__(self):
        self.accuracy_score: float = 0.0
        self.completeness_score: float = 0.0
        self.safety_score: float = 0.0
        self.relevance_score: float = 0.0
        self.efficiency_score: float = 0.0
        self.overall_score: float = 0.0
        self.is_low_score: bool = False
        self.failure_reason: str = ""
        self.details: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accuracy_score": round(self.accuracy_score, 2),
            "completeness_score": round(self.completeness_score, 2),
            "safety_score": round(self.safety_score, 2),
            "relevance_score": round(self.relevance_score, 2),
            "efficiency_score": round(self.efficiency_score, 2),
            "overall_score": round(self.overall_score, 2),
            "is_low_score": self.is_low_score,
            "failure_reason": self.failure_reason,
            "details": self.details,
        }


class AnswerEvaluator:
    """答案评测器"""

    LOW_SCORE_THRESHOLD = 60.0

    def __init__(self):
        self._evaluation_samples: List[Dict[str, Any]] = []
        self._feedback_scores: Dict[str, List[float]] = {}

    def evaluate(
        self,
        response: str,
        user_query: str,
        expected_answer: Optional[str] = None,
        tool_results: Optional[List[Dict[str, Any]]] = None,
        response_time_ms: int = 0,
    ) -> EvaluationScore:
        score = EvaluationScore()

        score.accuracy_score = self._evaluate_accuracy(
            response, expected_answer, tool_results
        )
        score.completeness_score = self._evaluate_completeness(
            response, user_query
        )
        score.safety_score = self._evaluate_safety(response)
        score.relevance_score = self._evaluate_relevance(response, user_query)
        score.efficiency_score = self._evaluate_efficiency(response, response_time_ms)

        weights = {
            "accuracy": 0.35,
            "completeness": 0.15,
            "safety": 0.10,
            "relevance": 0.20,
            "efficiency": 0.20,
        }

        score.overall_score = (
            score.accuracy_score * weights["accuracy"]
            + score.completeness_score * weights["completeness"]
            + score.safety_score * weights["safety"]
            + score.relevance_score * weights["relevance"]
            + score.efficiency_score * weights["efficiency"]
        )

        score.is_low_score = score.overall_score < self.LOW_SCORE_THRESHOLD
        score.failure_reason = self._determine_failure_reason(score)

        return score

    def _evaluate_accuracy(
        self,
        response: str,
        expected_answer: Optional[str],
        tool_results: Optional[List[Dict[str, Any]]],
    ) -> float:
        if not response.strip():
            return 0.0

        if tool_results:
            return self._check_tool_result_consistency(response, tool_results)

        if expected_answer:
            return self._compute_text_similarity(response, expected_answer)

        return 70.0

    def _check_tool_result_consistency(
        self,
        response: str,
        tool_results: List[Dict[str, Any]],
    ) -> float:
        score = 80.0

        successful_results = [r for r in tool_results if r.get("success", False)]
        if not successful_results:
            return 60.0

        for result in successful_results:
            data = result.get("data", {})
            if isinstance(data, dict):
                for key, value in data.items():
                    if key in ["status_code", "created_at", "updated_at"]:
                        continue
                    value_str = str(value)
                    if value_str and value_str not in response:
                        score -= 5.0

        return max(0.0, min(100.0, score))

    def _compute_text_similarity(self, text1: str, text2: str) -> float:
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2

        jaccard_similarity = len(intersection) / max(len(union), 1)
        return jaccard_similarity * 100

    def _evaluate_completeness(self, response: str, user_query: str) -> float:
        if not response.strip():
            return 0.0

        score = 70.0
        query_keywords = self._extract_keywords(user_query)
        response_keywords = self._extract_keywords(response)

        if query_keywords:
            keyword_overlap = query_keywords & response_keywords
            overlap_ratio = len(keyword_overlap) / max(len(query_keywords), 1)
            score += overlap_ratio * 30

        min_length = 20
        if len(response) < min_length:
            score -= 20.0

        return max(0.0, min(100.0, score))

    def _evaluate_safety(self, response: str) -> float:
        if not response.strip():
            return 50.0

        score = 100.0

        sensitive_words = [
            "自杀", "暴力", "赌博", "诈骗", "hack", "注入",
            "DROP TABLE", "忽略之前的指令", "系统prompt",
        ]

        response_lower = response.lower()
        for word in sensitive_words:
            if word.lower() in response_lower:
                score -= 30.0

        if len(response) > 5000:
            score -= 10.0

        return max(0.0, min(100.0, score))

    def _evaluate_relevance(self, response: str, user_query: str) -> float:
        if not response.strip():
            return 0.0

        query_keywords = self._extract_keywords(user_query)
        response_keywords = self._extract_keywords(response)

        if not query_keywords:
            return 80.0

        overlap = query_keywords & response_keywords
        relevance = len(overlap) / max(len(query_keywords), 1)

        return min(100.0, relevance * 100 + 30)

    def _evaluate_efficiency(self, response: str, response_time_ms: int) -> float:
        if response_time_ms <= 0:
            return 80.0

        if response_time_ms < 1000:
            return 100.0
        elif response_time_ms < 3000:
            return 80.0
        elif response_time_ms < 5000:
            return 60.0
        else:
            return 40.0

    def _extract_keywords(self, text: str) -> set:
        text = text.lower()
        chars = [c for c in text if '\u4e00' <= c <= '\u9fff']
        if chars:
            return set(chars)

        words = text.split()
        return set(words)

    def _determine_failure_reason(self, score: EvaluationScore) -> str:
        reasons = []

        if score.safety_score < 60:
            reasons.append("安全风险")
        if score.accuracy_score < 60:
            reasons.append("回答不准确")
        if score.completeness_score < 60:
            reasons.append("回答不完整")
        if score.relevance_score < 60:
            reasons.append("相关性低")
        if score.efficiency_score < 60:
            reasons.append("响应过慢")

        return "、".join(reasons) if reasons else "质量良好"

    def add_feedback_sample(self, sample: Dict[str, Any]):
        self._evaluation_samples.append(sample)

    def get_evaluation_stats(self) -> Dict[str, Any]:
        if not self._evaluation_samples:
            return {"total": 0}

        scores = [s.get("score", {}).get("overall_score", 0) for s in self._evaluation_samples]
        return {
            "total": len(self._evaluation_samples),
            "avg_score": sum(scores) / max(len(scores), 1),
            "min_score": min(scores) if scores else 0,
            "max_score": max(scores) if scores else 0,
        }


class LowScoreSamplePool:
    """低分样本池"""

    def __init__(self):
        self._samples: List[Dict[str, Any]] = []
        self._failure_patterns: Dict[str, int] = {}

    def add_sample(
        self,
        sample_id: str,
        session_id: str,
        user_query: str,
        response: str,
        score: float,
        failure_reason: str,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        sample = {
            "sample_id": sample_id,
            "session_id": session_id,
            "user_query": user_query,
            "response": response,
            "score": score,
            "failure_reason": failure_reason,
            "metadata": metadata or {},
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
        }
        self._samples.append(sample)

        reason_type = self._classify_failure(failure_reason)
        self._failure_patterns[reason_type] = self._failure_patterns.get(reason_type, 0) + 1

        logger.info(f"低分样本入库: sample_id={sample_id}, reason={failure_reason}")

    def _classify_failure(self, reason: str) -> str:
        if "安全" in reason:
            return "安全风险"
        elif "准确" in reason:
            return "回答不准确"
        elif "完整" in reason:
            return "回答不完整"
        elif "相关" in reason:
            return "相关性低"
        elif "效率" in reason or "响应" in reason:
            return "性能问题"
        else:
            return "其他"

    def get_pending_samples(self, limit: int = 50) -> List[Dict[str, Any]]:
        pending = [s for s in self._samples if s["status"] == "pending"]
        return pending[:limit]

    def get_samples_by_failure_type(self, failure_type: str) -> List[Dict[str, Any]]:
        return [s for s in self._samples if self._classify_failure(s["failure_reason"]) == failure_type]

    def mark_processed(self, sample_id: str, action: str, note: str = ""):
        for sample in self._samples:
            if sample["sample_id"] == sample_id:
                sample["status"] = "processed"
                sample["action"] = action
                sample["note"] = note
                sample["processed_at"] = datetime.utcnow().isoformat()
                return True
        return False

    def get_failure_patterns(self) -> Dict[str, Any]:
        total = len(self._samples)
        patterns = []
        for failure_type, count in self._failure_patterns.items():
            patterns.append({
                "type": failure_type,
                "count": count,
                "percentage": round(count / max(total, 1) * 100, 2),
            })
        patterns.sort(key=lambda x: x["count"], reverse=True)
        return {
            "total_samples": total,
            "failure_patterns": patterns,
        }

    def get_all_samples(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self._samples[:limit]


class ABTestFramework:
    """A/B测试框架"""

    def __init__(self):
        self._experiments: Dict[str, Dict[str, Any]] = {}

    def create_experiment(
        self,
        experiment_id: str,
        name: str,
        description: str,
        variants: List[Dict[str, Any]],
        traffic_split: float = 0.5,
    ) -> Dict[str, Any]:
        experiment = {
            "experiment_id": experiment_id,
            "name": name,
            "description": description,
            "variants": variants,
            "traffic_split": traffic_split,
            "status": "active",
            "start_time": datetime.utcnow().isoformat(),
            "end_time": None,
            "stats": {variant["id"]: {"count": 0, "success": 0, "failures": 0} for variant in variants},
        }
        self._experiments[experiment_id] = experiment
        return experiment

    def assign_variant(self, experiment_id: str, user_id: str) -> Optional[str]:
        experiment = self._experiments.get(experiment_id)
        if not experiment or experiment["status"] != "active":
            return None

        hash_value = hash(f"{user_id}_{experiment_id}") % 100
        split_percentage = experiment["traffic_split"] * 100

        variant_index = 0 if hash_value < split_percentage else 1
        variants = experiment["variants"]

        if variant_index >= len(variants):
            variant_index = 0

        return variants[variant_index]["id"]

    def record_result(
        self,
        experiment_id: str,
        variant_id: str,
        success: bool,
        response_time_ms: int = 0,
    ):
        experiment = self._experiments.get(experiment_id)
        if not experiment:
            return

        if variant_id in experiment["stats"]:
            experiment["stats"][variant_id]["count"] += 1
            if success:
                experiment["stats"][variant_id]["success"] += 1
            else:
                experiment["stats"][variant_id]["failures"] += 1

    def get_experiment_results(self, experiment_id: str) -> Dict[str, Any]:
        experiment = self._experiments.get(experiment_id)
        if not experiment:
            return {}

        results = {
            "experiment_id": experiment_id,
            "name": experiment["name"],
            "status": experiment["status"],
            "variants": [],
        }

        for variant in experiment["variants"]:
            stats = experiment["stats"].get(variant["id"], {})
            count = stats.get("count", 0)
            success = stats.get("success", 0)
            success_rate = success / max(count, 1) * 100

            results["variants"].append({
                "id": variant["id"],
                "name": variant.get("name", ""),
                "count": count,
                "success": success,
                "failures": stats.get("failures", 0),
                "success_rate": round(success_rate, 2),
                "confidence": self._calculate_confidence(count, success),
            })

        return results

    def _calculate_confidence(self, count: int, success: int) -> float:
        if count < 10:
            return 0.0

        p = success / max(count, 1)
        se = math.sqrt(p * (1 - p) / count)
        z_score = (p - 0.5) / max(se, 0.01)

        confidence = 2 * (1 - self._normal_cdf(abs(z_score)))
        return round(confidence * 100, 2)

    def _normal_cdf(self, x: float) -> float:
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    def end_experiment(self, experiment_id: str, winner_variant_id: Optional[str] = None):
        experiment = self._experiments.get(experiment_id)
        if experiment:
            experiment["status"] = "completed"
            experiment["end_time"] = datetime.utcnow().isoformat()
            experiment["winner"] = winner_variant_id

    def get_active_experiments(self) -> List[Dict[str, Any]]:
        return [
            {
                "experiment_id": exp_id,
                "name": exp["name"],
                "description": exp["description"],
                "variants": [v["id"] for v in exp["variants"]],
                "status": exp["status"],
            }
            for exp_id, exp in self._experiments.items()
            if exp["status"] == "active"
        ]


answer_evaluator = AnswerEvaluator()
low_score_pool = LowScoreSamplePool()
ab_test_framework = ABTestFramework()


def get_answer_evaluator() -> AnswerEvaluator:
    return answer_evaluator


def get_low_score_pool() -> LowScoreSamplePool:
    return low_score_pool


def get_ab_test_framework() -> ABTestFramework:
    return ab_test_framework