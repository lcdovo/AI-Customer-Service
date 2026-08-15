"""
人机协同服务 - Phase 4 实现
1. 人工客服接管
2. 工单管理与分配
3. 人机协作时机控制
"""
import time
import uuid
import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class HandoffReason:
    """转人工原因"""
    USER_REQUEST = "user_request"
    AGENT_FAILURE = "agent_failure"
    HIGH_PRIORITY = "high_priority"
    COMPLEX_AMOUNT = "complex_amount"
    TECHNICAL_ISSUE = "technical_issue"
    COMPLAINT_ESCALATION = "complaint_escalation"


class HumanAgent:
    """人工客服信息"""

    def __init__(
        self,
        agent_id: str,
        name: str,
        skills: Optional[List[str]] = None,
        current_load: int = 0,
        max_load: int = 5,
        status: str = "online",
    ):
        self.agent_id = agent_id
        self.name = name
        self.skills = skills or ["general"]
        self.current_load = current_load
        self.max_load = max_load
        self.status = status

    def can_take_more(self) -> bool:
        return self.current_load < self.max_load and self.status == "online"

    def assign(self):
        self.current_load += 1

    def release(self):
        self.current_load = max(0, self.current_load - 1)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "skills": self.skills,
            "current_load": self.current_load,
            "max_load": self.max_load,
            "status": self.status,
        }


class HandoffRequest:
    """转人工请求"""

    def __init__(
        self,
        request_id: Optional[str] = None,
        user_id: int = 0,
        session_id: str = "",
        reason: str = "",
        priority: str = "normal",
        context: Optional[Dict[str, Any]] = None,
    ):
        self.request_id = request_id or str(uuid.uuid4())
        self.user_id = user_id
        self.session_id = session_id
        self.reason = reason
        self.priority = priority
        self.context = context or {}
        self.status = "pending"
        self.assigned_to: Optional[str] = None
        self.created_at = datetime.utcnow().isoformat()
        self.assigned_at: Optional[str] = None
        self.resolved_at: Optional[str] = None
        self.sla_deadline: str = ""

        self._set_sla_deadline()

    def _set_sla_deadline(self):
        sla_hours = {
            "urgent": 1,
            "high": 4,
            "normal": 24,
            "low": 48,
        }
        hours = sla_hours.get(self.priority, 24)
        deadline = datetime.utcnow() + timedelta(hours=hours)
        self.sla_deadline = deadline.isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "reason": self.reason,
            "priority": self.priority,
            "context": self.context,
            "status": self.status,
            "assigned_to": self.assigned_to,
            "created_at": self.created_at,
            "assigned_at": self.assigned_at,
            "resolved_at": self.resolved_at,
            "sla_deadline": self.sla_deadline,
        }


class HumanAgentService:
    """人工客服管理服务"""

    def __init__(self):
        self._agents: Dict[str, HumanAgent] = {}
        self._handoff_requests: Dict[str, HandoffRequest] = {}
        self._initialize_default_agents()

    def _initialize_default_agents(self):
        default_agents = [
            HumanAgent(
                agent_id="agent_001",
                name="客服主管-赵经理",
                skills=["complaint", "escalation", "general"],
                max_load=3,
            ),
            HumanAgent(
                agent_id="agent_002",
                name="客服专员-李小明",
                skills=["general", "order_query", "refund"],
                max_load=5,
            ),
            HumanAgent(
                agent_id="agent_003",
                name="技术支持-王工程师",
                skills=["technical", "product_support"],
                max_load=3,
            ),
            HumanAgent(
                agent_id="agent_004",
                name="售后专员-陈小丽",
                skills=["refund", "return", "exchange"],
                max_load=4,
            ),
        ]

        for agent in default_agents:
            self._agents[agent.agent_id] = agent

    def get_agent(self, agent_id: str) -> Optional[HumanAgent]:
        return self._agents.get(agent_id)

    def list_agents(
        self,
        skill: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        agents = list(self._agents.values())

        if skill:
            agents = [a for a in agents if skill in a.skills]
        if status:
            agents = [a for a in agents if a.status == status]

        return [a.to_dict() for a in agents]

    def find_best_agent(
        self,
        required_skills: List[str],
        priority: str = "normal",
    ) -> Optional[HumanAgent]:
        candidates = []

        for agent in self._agents.values():
            if not agent.can_take_more():
                continue

            skill_match = any(skill in agent.skills for skill in required_skills)
            if not skill_match:
                continue

            load_score = 1 - (agent.current_load / agent.max_load)
            candidates.append((agent, load_score))

        if not candidates:
            for agent in self._agents.values():
                if agent.can_take_more():
                    candidates.append((agent, 0.5))

        if not candidates:
            return None

        if priority == "urgent":
            candidates.sort(key=lambda x: x[1], reverse=True)
            return candidates[0][0]

        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    def create_handoff_request(
        self,
        user_id: int,
        session_id: str,
        reason: str,
        priority: str = "normal",
        context: Optional[Dict[str, Any]] = None,
    ) -> HandoffRequest:
        request = HandoffRequest(
            user_id=user_id,
            session_id=session_id,
            reason=reason,
            priority=priority,
            context=context,
        )

        self._handoff_requests[request.request_id] = request
        logger.info(
            f"创建转人工请求: request_id={request.request_id}, "
            f"user_id={user_id}, reason={reason}, priority={priority}"
        )

        return request

    def assign_handoff_request(self, request_id: str, agent_id: str) -> bool:
        request = self._handoff_requests.get(request_id)
        agent = self._agents.get(agent_id)

        if not request or not agent:
            return False

        if not agent.can_take_more():
            return False

        agent.assign()
        request.assigned_to = agent_id
        request.assigned_at = datetime.utcnow().isoformat()
        request.status = "assigned"

        return True

    def get_handoff_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        request = self._handoff_requests.get(request_id)
        return request.to_dict() if request else None

    def list_handoff_requests(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        requests = list(self._handoff_requests.values())

        if status:
            requests = [r for r in requests if r.status == status]
        if priority:
            requests = [r for r in requests if r.priority == priority]

        requests.sort(key=lambda x: x.created_at, reverse=True)
        return [r.to_dict() for r in requests[:limit]]

    def resolve_handoff_request(
        self,
        request_id: str,
        resolution: str,
        agent_id: Optional[str] = None,
    ) -> bool:
        request = self._handoff_requests.get(request_id)
        if not request:
            return False

        request.status = "resolved"
        request.resolved_at = datetime.utcnow().isoformat()
        request.resolution = resolution

        if agent_id and agent_id in self._agents:
            self._agents[agent_id].release()

        return True


class TicketManager:
    """工单管理器"""

    def __init__(self):
        self._tickets: Dict[str, Dict[str, Any]] = {}
        self._ticket_counter = 0

    def create_ticket(
        self,
        user_id: int,
        category: str,
        content: str,
        priority: str = "medium",
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        ticket_id = f"TKT{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        self._ticket_counter += 1

        sla_deadline = self._calculate_sla_deadline(priority)

        ticket = {
            "ticket_id": ticket_id,
            "user_id": user_id,
            "category": category,
            "content": content,
            "priority": priority,
            "status": "pending",
            "assigned_to": None,
            "session_id": session_id,
            "sla_deadline": sla_deadline,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "resolution": None,
        }

        self._tickets[ticket_id] = ticket
        logger.info(f"创建工单: ticket_id={ticket_id}, category={category}")

        return ticket

    def _calculate_sla_deadline(self, priority: str) -> str:
        sla_hours = {
            "urgent": 1,
            "high": 4,
            "medium": 24,
            "low": 48,
        }
        hours = sla_hours.get(priority, 24)
        deadline = datetime.utcnow() + timedelta(hours=hours)
        return deadline.isoformat()

    def get_ticket(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        return self._tickets.get(ticket_id)

    def update_ticket_status(
        self,
        ticket_id: str,
        status: str,
        assigned_to: Optional[str] = None,
        resolution: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        ticket = self._tickets.get(ticket_id)
        if not ticket:
            return None

        ticket["status"] = status
        ticket["updated_at"] = datetime.utcnow().isoformat()

        if assigned_to:
            ticket["assigned_to"] = assigned_to

        if resolution:
            ticket["resolution"] = resolution
            ticket["resolved_at"] = datetime.utcnow().isoformat()

        return ticket

    def list_tickets(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        category: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        tickets = list(self._tickets.values())

        if status:
            tickets = [t for t in tickets if t["status"] == status]
        if priority:
            tickets = [t for t in tickets if t["priority"] == priority]
        if category:
            tickets = [t for t in tickets if t["category"] == category]

        total = len(tickets)
        start = (page - 1) * page_size
        end = start + page_size

        tickets.sort(key=lambda x: x["created_at"], reverse=True)

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "tickets": tickets[start:end],
        }

    def get_ticket_stats(self) -> Dict[str, Any]:
        tickets = list(self._tickets.values())

        status_counts = {}
        priority_counts = {}
        overdue_count = 0

        now = datetime.utcnow()

        for ticket in tickets:
            status = ticket["status"]
            status_counts[status] = status_counts.get(status, 0) + 1

            priority = ticket["priority"]
            priority_counts[priority] = priority_counts.get(priority, 0) + 1

            if ticket["status"] not in ["resolved", "closed"]:
                sla_deadline = ticket.get("sla_deadline", "")
                if sla_deadline:
                    try:
                        deadline = datetime.fromisoformat(sla_deadline)
                        if now > deadline:
                            overdue_count += 1
                    except ValueError:
                        pass

        total = len(tickets)
        resolved = status_counts.get("resolved", 0) + status_counts.get("closed", 0)

        return {
            "total_tickets": total,
            "status_distribution": status_counts,
            "priority_distribution": priority_counts,
            "resolved_count": resolved,
            "resolution_rate": round(resolved / max(total, 1) * 100, 2),
            "overdue_count": overdue_count,
        }


class CollaborationService:
    """人机协同服务"""

    def __init__(self):
        self.human_agent_service = HumanAgentService()
        self.ticket_manager = TicketManager()
        self._collaboration_rules = self._default_rules()

    def _default_rules(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": "rule_1",
                "trigger": "agent_failure_threshold",
                "condition": "consecutive_failures >= 3",
                "action": "handoff_to_human",
                "priority": "high",
            },
            {
                "id": "rule_2",
                "trigger": "user_request_human",
                "condition": "user_says_human_keywords",
                "action": "immediate_handoff",
                "priority": "urgent",
            },
            {
                "id": "rule_3",
                "trigger": "high_value_order",
                "condition": "order_amount > 500",
                "action": "human_review",
                "priority": "medium",
            },
            {
                "id": "rule_4",
                "trigger": "complaint_escalation",
                "condition": "complaint_priority = urgent",
                "action": "create_urgent_ticket",
                "priority": "urgent",
            },
        ]

    def check_handoff_needed(
        self,
        agent_state: Dict[str, Any],
    ) -> Tuple[bool, str, str]:
        consecutive_failures = agent_state.get("consecutive_failures", 0)
        user_message = agent_state.get("user_message", "").lower()
        order_amount = agent_state.get("order_amount", 0)
        intent = agent_state.get("intent", "")

        human_keywords = ["人工", "客服", "转人工", "找客服", "真人"]
        if any(kw in user_message for kw in human_keywords):
            return True, "user_request_human", "urgent"

        if consecutive_failures >= 3:
            return True, "agent_failure_threshold", "high"

        if intent == "complaint" and consecutive_failures >= 1:
            return True, "complaint_escalation", "urgent"

        if order_amount > 500 and intent in ["refund", "complaint"]:
            return True, "high_value_order", "medium"

        return False, "", ""

    def execute_handoff(
        self,
        user_id: int,
        session_id: str,
        reason: str,
        priority: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        request = self.human_agent_service.create_handoff_request(
            user_id=user_id,
            session_id=session_id,
            reason=reason,
            priority=priority,
            context=context,
        )

        handoff_result = {
            "request_id": request.request_id,
            "status": request.status,
            "message": self._get_handoff_message(priority),
            "sla_deadline": request.sla_deadline,
        }

        if priority in ["urgent", "high"]:
            required_skills = ["complaint", "escalation"] if priority == "urgent" else ["general"]
            agent = self.human_agent_service.find_best_agent(required_skills, priority)

            if agent:
                self.human_agent_service.assign_handoff_request(
                    request.request_id, agent.agent_id
                )
                handoff_result["assigned_to"] = agent.name
                handoff_result["status"] = "assigned"

        return handoff_result

    def _get_handoff_message(self, priority: str) -> str:
        messages = {
            "urgent": "非常抱歉给您带来不好的体验，我们的客服主管将立即为您处理，请稍候...",
            "high": "您的问题已升级处理，我们将尽快安排专员为您服务，预计1小时内响应。",
            "normal": "正在为您转接人工客服，预计等待时间3-5分钟，请稍候...",
            "low": "已为您创建服务请求，我们的客服将在24小时内与您联系。",
        }
        return messages.get(priority, messages["normal"])

    def create_ticket_from_request(
        self,
        handoff_request_id: str,
        category: str,
        content: str,
        priority: str = "medium",
    ) -> Dict[str, Any]:
        request = self.human_agent_service.get_handoff_request(handoff_request_id)
        if not request:
            return {}

        ticket = self.ticket_manager.create_ticket(
            user_id=request["user_id"],
            category=category,
            content=content,
            priority=priority,
            session_id=request["session_id"],
        )

        return ticket

    def get_collaboration_stats(self) -> Dict[str, Any]:
        agent_stats = []
        for agent in self.human_agent_service._agents.values():
            agent_stats.append({
                "agent_id": agent.agent_id,
                "name": agent.name,
                "load": agent.current_load,
                "max_load": agent.max_load,
                "availability": "在线" if agent.can_take_more() else "忙碌",
            })

        handoff_stats = {
            "pending": len([
                r for r in self.human_agent_service._handoff_requests.values()
                if r.status == "pending"
            ]),
            "assigned": len([
                r for r in self.human_agent_service._handoff_requests.values()
                if r.status == "assigned"
            ]),
            "resolved": len([
                r for r in self.human_agent_service._handoff_requests.values()
                if r.status == "resolved"
            ]),
        }

        ticket_stats = self.ticket_manager.get_ticket_stats()

        return {
            "human_agents": agent_stats,
            "handoff_requests": handoff_stats,
            "tickets": ticket_stats,
        }


collaboration_service = CollaborationService()


def get_collaboration_service() -> CollaborationService:
    return collaboration_service