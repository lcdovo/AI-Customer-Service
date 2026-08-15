"""
全链路追踪与可观测性体系 - Phase 4 实现
1. TraceID 全链路贯穿
2. 指标采集与统计
3. 结构化日志
"""
import time
import uuid
import json
import logging
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class TraceSpan:
    """追踪跨度"""

    def __init__(
        self,
        trace_id: str,
        span_name: str,
        parent_span_id: Optional[str] = None,
    ):
        self.trace_id = trace_id
        self.span_id = str(uuid.uuid4())
        self.span_name = span_name
        self.parent_span_id = parent_span_id
        self.start_time = time.time()
        self.end_time = None
        self.duration_ms = 0
        self.attributes: Dict[str, Any] = {}
        self.events: List[Dict[str, Any]] = []
        self.status = "ok"
        self.error_message = None

    def set_attribute(self, key: str, value: Any):
        self.attributes[key] = value

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        self.events.append({
            "name": name,
            "timestamp": time.time(),
            "attributes": attributes or {},
        })

    def end(self, status: str = "ok", error_message: Optional[str] = None):
        self.end_time = time.time()
        self.duration_ms = int((self.end_time - self.start_time) * 1000)
        self.status = status
        self.error_message = error_message

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "span_name": self.span_name,
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
            "end_time": datetime.fromtimestamp(self.end_time).isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "error_message": self.error_message,
            "attributes": self.attributes,
            "events": self.events,
        }


class Tracer:
    """全链路追踪器"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._active_traces: Dict[str, List[TraceSpan]] = {}
        self._trace_buffer: List[Dict[str, Any]] = []
        self._max_buffer_size = 1000
        self._metrics = MetricsCollector()

    def start_trace(self, trace_id: Optional[str] = None) -> str:
        if trace_id is None:
            trace_id = str(uuid.uuid4())
        self._active_traces[trace_id] = []
        return trace_id

    def start_span(
        self,
        trace_id: str,
        span_name: str,
        parent_span_id: Optional[str] = None,
    ) -> TraceSpan:
        span = TraceSpan(trace_id, span_name, parent_span_id)
        if trace_id in self._active_traces:
            self._active_traces[trace_id].append(span)
        return span

    def end_span(self, span: TraceSpan, status: str = "ok", error_message: Optional[str] = None):
        span.end(status=status, error_message=error_message)
        self._record_span(span)

    def end_trace(self, trace_id: str) -> List[Dict[str, Any]]:
        spans = self._active_traces.pop(trace_id, [])
        return [s.to_dict() for s in spans]

    def _record_span(self, span: TraceSpan):
        span_dict = span.to_dict()
        self._trace_buffer.append(span_dict)

        if len(self._trace_buffer) >= self._max_buffer_size:
            self._flush_buffer()

        self._metrics.record_span(span)

    def _flush_buffer(self):
        if self._trace_buffer:
            logger.debug(f"Flushing {len(self._trace_buffer)} trace spans")
            self._trace_buffer = []

    def get_metrics(self) -> Dict[str, Any]:
        return self._metrics.get_all_metrics()

    def reset_metrics(self):
        self._metrics.reset()


class MetricsCollector:
    """指标采集器"""

    def __init__(self):
        self._counters: Dict[str, int] = {}
        self._timers: Dict[str, List[int]] = {}
        self._gauges: Dict[str, float] = {}
        self._intent_counts: Dict[str, int] = {}
        self._tool_counts: Dict[str, Dict[str, int]] = {}
        self._response_times: List[int] = []
        self._error_counts: Dict[str, int] = {}

    def increment_counter(self, name: str, value: int = 1):
        self._counters[name] = self._counters.get(name, 0) + value

    def record_time(self, name: str, duration_ms: int):
        if name not in self._timers:
            self._timers[name] = []
        self._timers[name].append(duration_ms)

    def record_span(self, span: TraceSpan):
        self.increment_counter(f"span.{span.span_name}.count")
        self.record_time(f"span.{span.span_name}.duration", span.duration_ms)

        if span.status != "ok":
            self.increment_counter(f"span.{span.span_name}.errors")

        if span.span_name == "intent_recognition":
            intent = span.attributes.get("intent", "unknown")
            self._intent_counts[intent] = self._intent_counts.get(intent, 0) + 1

        if span.span_name == "tool_execution":
            tool_name = span.attributes.get("tool_name", "unknown")
            if tool_name not in self._tool_counts:
                self._tool_counts[tool_name] = {"success": 0, "failure": 0}
            if span.status == "ok":
                self._tool_counts[tool_name]["success"] += 1
            else:
                self._tool_counts[tool_name]["failure"] += 1

        if span.span_name == "agent_total":
            self._response_times.append(span.duration_ms)

    def record_intent(self, intent: str, confidence: float):
        self._intent_counts[intent] = self._intent_counts.get(intent, 0) + 1

    def record_tool_call(self, tool_name: str, success: bool, duration_ms: int = 0):
        if tool_name not in self._tool_counts:
            self._tool_counts[tool_name] = {"success": 0, "failure": 0}
        if success:
            self._tool_counts[tool_name]["success"] += 1
        else:
            self._tool_counts[tool_name]["failure"] += 1

        self.increment_counter(f"tool.{tool_name}.total")
        if not success:
            self.increment_counter(f"tool.{tool_name}.failures")

    def record_session(self, session_type: str = "chat"):
        self.increment_counter("session.total")
        self.increment_counter(f"session.{session_type}")

    def record_response(self, response_time_ms: int, is_successful: bool = True):
        self._response_times.append(response_time_ms)
        self.increment_counter("response.total")
        if is_successful:
            self.increment_counter("response.success")
        else:
            self.increment_counter("response.failure")

    def record_error(self, error_type: str, error_message: str = ""):
        self._error_counts[error_type] = self._error_counts.get(error_type, 0) + 1
        self.increment_counter("error.total")

    def get_counter(self, name: str) -> int:
        return self._counters.get(name, 0)

    def get_timer_stats(self, name: str) -> Dict[str, Any]:
        times = self._timers.get(name, [])
        if not times:
            return {"count": 0, "avg_ms": 0, "p50_ms": 0, "p95_ms": 0, "max_ms": 0}

        sorted_times = sorted(times)
        count = len(sorted_times)
        return {
            "count": count,
            "avg_ms": sum(sorted_times) / count,
            "p50_ms": sorted_times[count // 2],
            "p95_ms": sorted_times[int(count * 0.95)],
            "max_ms": sorted_times[-1],
        }

    def get_all_metrics(self) -> Dict[str, Any]:
        response_time_stats = self._compute_response_time_stats()

        tool_stats = {}
        for tool_name, counts in self._tool_counts.items():
            total = counts["success"] + counts["failure"]
            success_rate = counts["success"] / max(total, 1) * 100
            tool_stats[tool_name] = {
                "total": total,
                "success": counts["success"],
                "failure": counts["failure"],
                "success_rate": round(success_rate, 2),
            }

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "counters": dict(self._counters),
            "response_time": response_time_stats,
            "intent_distribution": dict(self._intent_counts),
            "tool_statistics": tool_stats,
            "error_counts": dict(self._error_counts),
            "session_count": self.get_counter("session.total"),
            "total_responses": self.get_counter("response.total"),
            "success_rate": round(
                self.get_counter("response.success") /
                max(self.get_counter("response.total"), 1) * 100, 2
            ),
        }

    def _compute_response_time_stats(self) -> Dict[str, Any]:
        if not self._response_times:
            return {"count": 0, "avg_ms": 0, "p50_ms": 0, "p95_ms": 0}

        sorted_times = sorted(self._response_times)
        count = len(sorted_times)
        return {
            "count": count,
            "avg_ms": round(sum(sorted_times) / count, 2),
            "p50_ms": sorted_times[count // 2],
            "p95_ms": sorted_times[int(count * 0.95)],
            "max_ms": sorted_times[-1],
        }

    def reset(self):
        self._counters.clear()
        self._timers.clear()
        self._gauges.clear()
        self._intent_counts.clear()
        self._tool_counts.clear()
        self._response_times.clear()
        self._error_counts.clear()


tracer = Tracer()


def get_tracer() -> Tracer:
    return tracer


class TraceContext:
    """追踪上下文管理器"""

    def __init__(self, span_name: str, trace_id: Optional[str] = None):
        self.span_name = span_name
        self.trace_id = trace_id or str(uuid.uuid4())
        self.span: Optional[TraceSpan] = None

    async def __aenter__(self):
        self.span = tracer.start_span(self.trace_id, self.span_name)
        return self.span

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            tracer.end_span(self.span, status="error", error_message=str(exc_val))
        else:
            tracer.end_span(self.span)


@asynccontextmanager
async def trace_context(span_name: str, trace_id: Optional[str] = None):
    span = tracer.start_span(trace_id or str(uuid.uuid4()), span_name)
    try:
        yield span
        tracer.end_span(span)
    except Exception as e:
        tracer.end_span(span, status="error", error_message=str(e))
        raise


class StructuredLogger:
    """结构化日志"""

    def __init__(self, name: str = "app"):
        self.logger = logging.getLogger(name)

    def log_request(self, trace_id: str, method: str, path: str, **kwargs):
        self.logger.info(
            json.dumps({
                "type": "request",
                "trace_id": trace_id,
                "method": method,
                "path": path,
                **kwargs,
            })
        )

    def log_response(self, trace_id: str, status_code: int, duration_ms: int, **kwargs):
        self.logger.info(
            json.dumps({
                "type": "response",
                "trace_id": trace_id,
                "status_code": status_code,
                "duration_ms": duration_ms,
                **kwargs,
            })
        )

    def log_agent(self, trace_id: str, node: str, intent: str, **kwargs):
        self.logger.info(
            json.dumps({
                "type": "agent",
                "trace_id": trace_id,
                "node": node,
                "intent": intent,
                **kwargs,
            })
        )

    def log_tool(self, trace_id: str, tool_name: str, success: bool, **kwargs):
        level = logging.INFO if success else logging.WARNING
        self.logger.log(
            level,
            json.dumps({
                "type": "tool",
                "trace_id": trace_id,
                "tool_name": tool_name,
                "success": success,
                **kwargs,
            })
        )

    def log_error(self, trace_id: str, error_type: str, error_message: str, **kwargs):
        self.logger.error(
            json.dumps({
                "type": "error",
                "trace_id": trace_id,
                "error_type": error_type,
                "error_message": error_message,
                **kwargs,
            })
        )


structured_logger = StructuredLogger()


def generate_trace_id() -> str:
    return str(uuid.uuid4())


class AlertManager:
    """告警管理器"""

    ALERT_LEVELS = {
        "P0": {"name": "critical", "channels": ["phone", "sms"]},
        "P1": {"name": "warning", "channels": ["wechat", "email"]},
        "P2": {"name": "info", "channels": ["email"]},
    }

    def __init__(self):
        self._alert_rules: List[Dict[str, Any]] = [
            {
                "level": "P0",
                "rule": "system_error_rate",
                "threshold": 5.0,
                "duration_minutes": 5,
            },
            {
                "level": "P1",
                "rule": "human_handoff_rate",
                "threshold": 30.0,
                "duration_minutes": 10,
            },
            {
                "level": "P1",
                "rule": "avg_response_time",
                "threshold": 5000,
                "duration_minutes": 10,
            },
            {
                "level": "P2",
                "rule": "intent_accuracy",
                "threshold": 70.0,
                "duration_minutes": 30,
            },
        ]
        self._active_alerts: List[Dict[str, Any]] = []

    def check_alerts(self, metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        triggered_alerts = []

        for rule in self._alert_rules:
            alert = self._check_rule(rule, metrics)
            if alert:
                triggered_alerts.append(alert)

        self._active_alerts = triggered_alerts
        return triggered_alerts

    def _check_rule(
        self,
        rule: Dict[str, Any],
        metrics: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        rule_name = rule["rule"]
        threshold = rule["threshold"]

        current_value = self._get_metric_value(metrics, rule_name)
        if current_value is None:
            return None

        if rule_name == "system_error_rate":
            error_rate = metrics.get("error_rate", 0)
            if error_rate > threshold:
                return self._create_alert(rule, current_value, threshold, error_rate)

        elif rule_name == "human_handoff_rate":
            handoff_rate = metrics.get("handoff_rate", 0)
            if handoff_rate > threshold:
                return self._create_alert(rule, current_value, threshold, handoff_rate)

        elif rule_name == "avg_response_time":
            avg_time = metrics.get("avg_response_time", 0)
            if avg_time > threshold:
                return self._create_alert(rule, current_value, threshold, avg_time)

        elif rule_name == "intent_accuracy":
            accuracy = metrics.get("intent_accuracy", 100)
            if accuracy < threshold:
                return self._create_alert(rule, current_value, threshold, accuracy)

        return None

    def _get_metric_value(self, metrics: Dict[str, Any], rule_name: str) -> Optional[float]:
        metric_map = {
            "system_error_rate": metrics.get("error_rate", 0),
            "human_handoff_rate": metrics.get("handoff_rate", 0),
            "avg_response_time": metrics.get("avg_response_time", 0),
            "intent_accuracy": metrics.get("intent_accuracy", 100),
        }
        return metric_map.get(rule_name)

    def _create_alert(
        self,
        rule: Dict[str, Any],
        current_value: float,
        threshold: float,
        actual_value: float,
    ) -> Dict[str, Any]:
        return {
            "level": rule["level"],
            "rule": rule["rule"],
            "current_value": actual_value,
            "threshold": threshold,
            "message": f"告警: {rule['rule']} 当前值 {actual_value:.2f} 超过阈值 {threshold}",
            "timestamp": datetime.utcnow().isoformat(),
            "notification_channels": self.ALERT_LEVELS[rule["level"]]["channels"],
        }

    def get_active_alerts(self) -> List[Dict[str, Any]]:
        return self._active_alerts

    def get_alert_rules(self) -> List[Dict[str, Any]]:
        return self._alert_rules.copy()


alert_manager = AlertManager()