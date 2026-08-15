"""
核心工具实现 - Function Calling
实现订单查询、工单创建、退换货申请等8个结构化工具
"""
import uuid
import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, List, Callable
from pydantic import BaseModel, Field


class ToolParameter(BaseModel):
    """工具参数定义"""
    name: str
    type: str  # string, integer, boolean, array, object
    description: str
    required: bool = True
    enum: Optional[List[str]] = None
    default: Any = None


class ToolDefinition(BaseModel):
    """工具定义"""
    name: str
    description: str
    parameters: List[ToolParameter]
    async_execute: Optional[Callable] = None
    sync_execute: Optional[Callable] = None


class BaseTool:
    """工具基类"""
    name: str = ""
    description: str = ""
    parameters: List[Dict[str, Any]] = []

    async def execute(self, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError

    def validate_params(self, **kwargs) -> bool:
        """参数验证"""
        return True


class QueryOrderTool(BaseTool):
    """查询订单状态与物流"""
    name = "query_order"
    description = "根据订单号查询订单状态、物流信息、订单详情"
    parameters = [
        {"name": "order_id", "type": "string", "description": "订单号", "required": True},
    ]

    async def execute(self, **kwargs) -> Dict[str, Any]:
        order_id = kwargs.get("order_id", "")
        
        # 模拟订单数据
        mock_orders = {
            "ORD20260801": {
                "order_id": "ORD20260801",
                "status": "已发货",
                "items": [{"name": "无线耳机", "qty": 1, "price": 299.0}],
                "total_amount": 299.0,
                "shipping": {
                    "carrier": "顺丰快递",
                    "tracking_no": "SF1234567890",
                    "status": "运输中",
                    "updated_at": "2026-08-15 14:30:00",
                },
                "created_at": "2026-08-10 10:00:00",
            },
            "ORD20260802": {
                "order_id": "ORD20260802",
                "status": "已完成",
                "items": [{"name": "智能手表", "qty": 1, "price": 1299.0}],
                "total_amount": 1299.0,
                "shipping": {
                    "carrier": "京东物流",
                    "tracking_no": "JD9876543210",
                    "status": "已签收",
                    "updated_at": "2026-08-14 09:00:00",
                },
                "created_at": "2026-08-05 16:00:00",
            },
        }

        if order_id in mock_orders:
            return {"success": True, "data": mock_orders[order_id]}
        else:
            return {
                "success": False,
                "error": f"未找到订单 {order_id}",
                "hint": "请确认订单号是否正确，或提供订单关联的手机号查询",
            }


class CreateTicketTool(BaseTool):
    """创建工单并自动分配"""
    name = "create_ticket"
    description = "创建客服工单，用于处理用户投诉、咨询等问题"
    parameters = [
        {"name": "user_id", "type": "integer", "description": "用户ID", "required": True},
        {"name": "category", "type": "string", "description": "工单分类", "required": True,
         "enum": ["产品咨询", "订单问题", "退换货", "投诉建议", "技术支持"]},
        {"name": "content", "type": "string", "description": "工单内容", "required": True},
        {"name": "priority", "type": "string", "description": "优先级", "required": False,
         "enum": ["low", "medium", "high", "urgent"], "default": "medium"},
    ]

    async def execute(self, **kwargs) -> Dict[str, Any]:
        category = kwargs.get("category", "")
        content = kwargs.get("content", "")
        priority = kwargs.get("priority", "medium")

        ticket_id = str(uuid.uuid4())
        sla_hours = {"low": 48, "medium": 24, "high": 12, "urgent": 4}
        sla = sla_hours.get(priority, 24)

        return {
            "success": True,
            "data": {
                "ticket_id": ticket_id,
                "category": category,
                "priority": priority,
                "content": content,
                "sla_deadline": (datetime.now() + timedelta(hours=sla)).isoformat(),
                "status": "pending",
                "message": f"工单创建成功，将在 {sla} 小时内处理",
            },
        }


class ApplyRefundTool(BaseTool):
    """退换货申请"""
    name = "apply_refund"
    description = "申请退换货，需校验订单状态是否满足退换货条件"
    parameters = [
        {"name": "order_id", "type": "string", "description": "订单号", "required": True},
        {"name": "reason", "type": "string", "description": "退换货原因", "required": True},
        {"name": "type", "type": "string", "description": "类型：refund(仅退款)、return(退货退款)", "required": False,
         "enum": ["refund", "return"], "default": "refund"},
    ]

    async def execute(self, **kwargs) -> Dict[str, Any]:
        order_id = kwargs.get("order_id", "")
        reason = kwargs.get("reason", "")
        refund_type = kwargs.get("type", "refund")

        # 模拟校验
        if not order_id:
            return {"success": False, "error": "请提供订单号"}

        if not reason:
            return {"success": False, "error": "请说明退换货原因"}

        return {
            "success": True,
            "data": {
                "refund_id": str(uuid.uuid4()),
                "order_id": order_id,
                "type": refund_type,
                "reason": reason,
                "status": "pending_review",
                "next_steps": [
                    "1. 请将商品寄回指定地址",
                    "2. 我们将在收到商品后 3 个工作日内处理",
                    "3. 退款将原路返回至您的支付账户",
                ],
            },
        }


class SearchKBTool(BaseTool):
    """知识库检索"""
    name = "search_kb"
    description = "从知识库中检索相关问题的答案"
    parameters = [
        {"name": "query", "type": "string", "description": "查询内容", "required": True},
        {"name": "top_k", "type": "integer", "description": "返回结果数量", "required": False, "default": 3},
    ]

    # 内置知识库
    KNOWLEDGE_BASE = {
        "退换货政策": {
            "content": "我们支持 7 天无理由退换货。商品需保持原包装、未经使用。退款将在收到商品后 3-7 个工作日内到账。",
            "keywords": ["退换货", "退货", "退款", "7天"],
        },
        "订单查询": {
            "content": "您可以通过订单号或手机号查询订单状态。物流信息在发货后 24 小时内更新。",
            "keywords": ["订单", "物流", "查询", "发货"],
        },
        "会员权益": {
            "content": "VIP 会员享受 95 折优惠、专属客服优先接入、免费包邮等权益。年度会员费 199 元。",
            "keywords": ["会员", "VIP", "权益", "优惠"],
        },
        "支付方式": {
            "content": "我们支持支付宝、微信支付、银联、信用卡分期（3/6/12期）等多种支付方式。",
            "keywords": ["支付", "付款", "支付宝", "微信"],
        },
        "发票开具": {
            "content": "购买后 180 天内可申请开具电子发票。请在订单详情页点击'申请发票'按钮填写抬头信息。",
            "keywords": ["发票", "开票", "抬头", "电子发票"],
        },
    }

    async def execute(self, **kwargs) -> Dict[str, Any]:
        query = kwargs.get("query", "").lower()
        top_k = kwargs.get("top_k", 3)

        results = []
        for title, content in self.KNOWLEDGE_BASE.items():
            score = 0
            for keyword in content["keywords"]:
                if keyword in query:
                    score += 1
            if score > 0 or query in title.lower():
                results.append({
                    "title": title,
                    "content": content["content"],
                    "relevance_score": score if score > 0 else 1,
                })

        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        results = results[:top_k]

        if results:
            return {"success": True, "data": results}
        else:
            return {
                "success": True,
                "data": [],
                "hint": "未找到相关内容，请尝试其他关键词",
            }


class EscalateToHumanTool(BaseTool):
    """转接人工客服"""
    name = "escalate_to_human"
    description = "将用户转接至人工客服处理"
    parameters = [
        {"name": "reason", "type": "string", "description": "转接原因", "required": True},
        {"name": "priority", "type": "string", "description": "优先级", "required": False,
         "enum": ["normal", "urgent"], "default": "normal"},
    ]

    async def execute(self, **kwargs) -> Dict[str, Any]:
        reason = kwargs.get("reason", "")
        priority = kwargs.get("priority", "normal")

        return {
            "success": True,
            "data": {
                "escalation_id": str(uuid.uuid4()),
                "status": "queued",
                "position": 1,
                "estimated_wait_time": "3-5分钟" if priority == "normal" else "立即",
                "message": f"正在为您转接人工客服（{reason}），请稍候...",
            },
        }


class SendNotificationTool(BaseTool):
    """发送通知"""
    name = "send_notification"
    description = "向用户发送短信或站内信通知"
    parameters = [
        {"name": "channel", "type": "string", "description": "通知渠道", "required": True,
         "enum": ["sms", "email", "inapp"]},
        {"name": "content", "type": "string", "description": "通知内容", "required": True},
    ]

    async def execute(self, **kwargs) -> Dict[str, Any]:
        channel = kwargs.get("channel", "")
        content = kwargs.get("content", "")

        return {
            "success": True,
            "data": {
                "notification_id": str(uuid.uuid4()),
                "channel": channel,
                "content": content,
                "status": "sent",
                "sent_at": datetime.now().isoformat(),
            },
        }


class UpdateTicketStatusTool(BaseTool):
    """更新工单状态"""
    name = "update_ticket_status"
    description = "更新工单的处理状态"
    parameters = [
        {"name": "ticket_id", "type": "string", "description": "工单ID", "required": True},
        {"name": "status", "type": "string", "description": "新状态", "required": True,
         "enum": ["pending", "processing", "resolved", "closed", "escalated"]},
    ]

    async def execute(self, **kwargs) -> Dict[str, Any]:
        ticket_id = kwargs.get("ticket_id", "")
        status = kwargs.get("status", "")

        return {
            "success": True,
            "data": {
                "ticket_id": ticket_id,
                "old_status": "pending",
                "new_status": status,
                "updated_at": datetime.now().isoformat(),
            },
        }


class GetUserHistoryTool(BaseTool):
    """获取用户历史咨询记录"""
    name = "get_user_history"
    description = "获取用户的历史咨询记录、工单历史等"
    parameters = [
        {"name": "user_id", "type": "integer", "description": "用户ID", "required": True},
        {"name": "limit", "type": "integer", "description": "返回条数", "required": False, "default": 10},
    ]

    async def execute(self, **kwargs) -> Dict[str, Any]:
        user_id = kwargs.get("user_id", 0)
        limit = kwargs.get("limit", 10)

        return {
            "success": True,
            "data": {
                "user_id": user_id,
                "history": [
                    {"date": "2026-08-10", "type": "订单咨询", "summary": "查询订单 ORD20260801"},
                    {"date": "2026-07-25", "type": "退换货", "summary": "申请退货 ORD20260720"},
                    {"date": "2026-07-15", "type": "产品咨询", "summary": "询问产品使用方法"},
                ][:limit],
            },
        }


# 工具注册表
TOOL_REGISTRY: Dict[str, BaseTool] = {
    QueryOrderTool.name: QueryOrderTool(),
    CreateTicketTool.name: CreateTicketTool(),
    ApplyRefundTool.name: ApplyRefundTool(),
    SearchKBTool.name: SearchKBTool(),
    EscalateToHumanTool.name: EscalateToHumanTool(),
    SendNotificationTool.name: SendNotificationTool(),
    UpdateTicketStatusTool.name: UpdateTicketStatusTool(),
    GetUserHistoryTool.name: GetUserHistoryTool(),
}


def get_tool(name: str) -> Optional[BaseTool]:
    """获取工具实例"""
    return TOOL_REGISTRY.get(name)


def get_all_tools() -> List[BaseTool]:
    """获取所有工具"""
    return list(TOOL_REGISTRY.values())


def get_tool_schemas() -> List[Dict[str, Any]]:
    """获取所有工具的 Schema（用于 Function Calling）"""
    schemas = []
    for tool in TOOL_REGISTRY.values():
        schemas.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        p["name"]: {
                            "type": p["type"],
                            "description": p["description"],
                            **({"enum": p["enum"]} if p.get("enum") else {}),
                            **({"default": p["default"]} if p.get("default") is not None else {}),
                        }
                        for p in tool.parameters
                    },
                    "required": [p["name"] for p in tool.parameters if p.get("required", True)],
                },
            },
        })
    return schemas
