"""
核心工具实现 - Function Calling (Phase 3 增强版)
实现订单查询、工单创建、退换货申请等8个结构化工具
支持重试机制、参数校验、错误处理、执行追踪
"""
import uuid
import asyncio
import time
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, List, Callable, Tuple
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ToolParameter(BaseModel):
    """工具参数定义"""
    name: str
    type: str
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


class ToolExecutionResult(BaseModel):
    """工具执行结果"""
    success: bool
    data: Any = None
    error: Optional[str] = None
    hint: Optional[str] = None
    execution_time_ms: int = 0
    retry_count: int = 0


class BaseTool:
    """工具基类 - 支持重试、超时、错误处理"""
    name: str = ""
    description: str = ""
    parameters: List[Dict[str, Any]] = []
    max_retries: int = 3
    retry_delay_ms: int = 100
    timeout_ms: int = 5000

    def validate_params(self, **kwargs) -> Tuple[bool, List[str]]:
        """参数验证，返回 (是否有效, 错误信息列表)"""
        errors = []
        for param in self.parameters:
            name = param["name"]
            if param.get("required", True) and name not in kwargs:
                errors.append(f"缺少必要参数: {name}")
            elif name in kwargs and kwargs[name] is None:
                errors.append(f"参数 {name} 不能为 None")

            if name in kwargs and name in [p["name"] for p in self.parameters if p.get("enum")]:
                param_def = next(p for p in self.parameters if p["name"] == name)
                if param_def.get("enum") and kwargs[name] not in param_def["enum"]:
                    errors.append(
                        f"参数 {name} 值无效: {kwargs[name]}, "
                        f"有效值为: {param_def['enum']}"
                    )

        return len(errors) == 0, errors

    async def execute_with_retry(self, **kwargs) -> ToolExecutionResult:
        """带重试的执行"""
        start_time = time.time()
        last_error = None

        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    delay = self.retry_delay_ms * (2 ** (attempt - 1)) / 1000
                    await asyncio.sleep(delay)
                    logger.info(f"工具 {self.name} 第 {attempt + 1} 次重试")

                result = await self.execute(**kwargs)
                execution_time = int((time.time() - start_time) * 1000)

                if result.get("success", False):
                    return ToolExecutionResult(
                        success=True,
                        data=result.get("data"),
                        execution_time_ms=execution_time,
                        retry_count=attempt,
                    )
                else:
                    last_error = result.get("error", "未知错误")
                    if attempt < self.max_retries - 1:
                        continue
                    return ToolExecutionResult(
                        success=False,
                        error=last_error,
                        hint=result.get("hint"),
                        execution_time_ms=execution_time,
                        retry_count=attempt,
                    )

            except asyncio.TimeoutError:
                last_error = f"执行超时 (>{self.timeout_ms}ms)"
                if attempt < self.max_retries - 1:
                    continue

            except Exception as e:
                last_error = str(e)
                logger.error(f"工具 {self.name} 执行异常: {e}")
                if attempt < self.max_retries - 1:
                    continue

        execution_time = int((time.time() - start_time) * 1000)
        return ToolExecutionResult(
            success=False,
            error=last_error or "未知错误",
            hint="请稍后重试或联系人工客服",
            execution_time_ms=execution_time,
            retry_count=self.max_retries,
        )

    async def execute(self, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError


class QueryOrderTool(BaseTool):
    """查询订单状态与物流"""
    name = "query_order"
    description = "根据订单号查询订单状态、物流信息、订单详情"
    parameters = [
        {"name": "order_id", "type": "string", "description": "订单号 (如 ORD20260801)", "required": True},
    ]

    async def execute(self, **kwargs) -> Dict[str, Any]:
        order_id = kwargs.get("order_id", "").strip().upper()

        if not order_id:
            return {
                "success": False,
                "error": "订单号不能为空",
                "hint": "请提供有效的订单号，如 ORD20260801",
            }

        mock_orders = {
            "ORD20260801": {
                "order_id": "ORD20260801",
                "status": "已发货",
                "status_code": "shipped",
                "items": [{"name": "无线耳机", "qty": 1, "price": 299.0, "image": "🎧"}],
                "total_amount": 299.0,
                "shipping": {
                    "carrier": "顺丰快递",
                    "carrier_code": "SF",
                    "tracking_no": "SF1234567890",
                    "status": "运输中",
                    "status_code": "in_transit",
                    "updated_at": "2026-08-15 14:30:00",
                    "estimated_delivery": "2026-08-17",
                },
                "created_at": "2026-08-10 10:00:00",
                "pay_method": "微信支付",
                "address": "北京市朝阳区建国路88号",
            },
            "ORD20260802": {
                "order_id": "ORD20260802",
                "status": "已完成",
                "status_code": "completed",
                "items": [{"name": "智能手表", "qty": 1, "price": 1299.0, "image": "⌚"}],
                "total_amount": 1299.0,
                "shipping": {
                    "carrier": "京东物流",
                    "carrier_code": "JD",
                    "tracking_no": "JD9876543210",
                    "status": "已签收",
                    "status_code": "delivered",
                    "updated_at": "2026-08-14 09:00:00",
                    "delivered_at": "2026-08-14 16:30:00",
                },
                "created_at": "2026-08-05 16:00:00",
                "pay_method": "支付宝",
                "address": "上海市浦东新区陆家嘴金融中心",
            },
            "ORD20260803": {
                "order_id": "ORD20260803",
                "status": "待付款",
                "status_code": "pending_payment",
                "items": [{"name": "机械键盘", "qty": 1, "price": 599.0, "image": "⌨️"}],
                "total_amount": 599.0,
                "shipping": None,
                "created_at": "2026-08-15 18:00:00",
                "pay_method": "待选择",
                "expire_at": "2026-08-16 18:00:00",
            },
            "ORD20260804": {
                "order_id": "ORD20260804",
                "status": "已取消",
                "status_code": "cancelled",
                "items": [{"name": "显示器", "qty": 1, "price": 2499.0, "image": "🖥️"}],
                "total_amount": 2499.0,
                "shipping": None,
                "created_at": "2026-08-12 11:00:00",
                "cancelled_at": "2026-08-12 12:00:00",
                "cancel_reason": "用户主动取消",
            },
        }

        if order_id in mock_orders:
            order = mock_orders[order_id]
            can_refund = order["status_code"] in ["shipped", "delivered", "completed"]
            return {
                "success": True,
                "data": order,
                "can_refund": can_refund,
                "refund_deadline": (
                    (datetime.now() + timedelta(days=7)).isoformat()
                    if can_refund
                    else None
                ),
            }
        else:
            return {
                "success": False,
                "error": f"未找到订单 {order_id}",
                "hint": "请确认订单号是否正确，或提供订单关联的手机号查询。也可以尝试提供订单创建时间帮助定位。",
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
        user_id = kwargs.get("user_id", 0)
        category = kwargs.get("category", "")
        content = kwargs.get("content", "")
        priority = kwargs.get("priority", "medium")

        if not category:
            return {"success": False, "error": "请选择工单分类", "hint": "可选分类: 产品咨询、订单问题、退换货、投诉建议、技术支持"}

        if not content or len(content.strip()) < 5:
            return {"success": False, "error": "工单内容过于简短", "hint": "请详细描述您的问题（至少5个字符），以便我们更好地为您服务"}

        ticket_id = str(uuid.uuid4())
        sla_hours = {"low": 48, "medium": 24, "high": 12, "urgent": 4}
        sla = sla_hours.get(priority, 24)
        priority_labels = {"low": "低", "medium": "中", "high": "高", "urgent": "紧急"}

        assignee_map = {
            "产品咨询": "产品组-李专员",
            "订单问题": "订单组-王专员",
            "退换货": "售后组-张专员",
            "投诉建议": "客服主管-赵经理",
            "技术支持": "技术组-刘工程师",
        }
        assignee = assignee_map.get(category, "客服组")

        return {
            "success": True,
            "data": {
                "ticket_id": ticket_id,
                "category": category,
                "priority": priority,
                "priority_label": priority_labels.get(priority, "中"),
                "content": content,
                "assignee": assignee,
                "sla_hours": sla,
                "sla_deadline": (datetime.now() + timedelta(hours=sla)).isoformat(),
                "status": "pending",
                "created_at": datetime.now().isoformat(),
                "message": f"工单创建成功（{ticket_id[:8]}...），已分配给{assignee}，将在 {sla} 小时内处理",
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
        order_id = kwargs.get("order_id", "").strip().upper()
        reason = kwargs.get("reason", "").strip()
        refund_type = kwargs.get("type", "refund")

        if not order_id:
            return {"success": False, "error": "请提供订单号", "hint": "订单号格式：ORD + 数字，如 ORD20260801"}

        if not reason or len(reason) < 3:
            return {"success": False, "error": "请说明退换货原因", "hint": "请详细描述退换货原因，便于我们为您处理"}

        if refund_type not in ["refund", "return"]:
            return {"success": False, "error": f"无效的退换货类型: {refund_type}", "hint": "支持的类型：refund(仅退款)、return(退货退款)"}

        valid_orders = ["ORD20260801", "ORD20260802"]
        if order_id not in valid_orders:
            return {
                "success": False,
                "error": f"订单 {order_id} 不支持退换货",
                "hint": "仅已发货/已完成的订单可申请退换货。待付款或已取消的订单无法申请。",
            }

        refund_type_labels = {"refund": "仅退款", "return": "退货退款"}

        return {
            "success": True,
            "data": {
                "refund_id": str(uuid.uuid4()),
                "order_id": order_id,
                "type": refund_type,
                "type_label": refund_type_labels.get(refund_type, "退款"),
                "reason": reason,
                "status": "pending_review",
                "status_label": "待审核",
                "amount": 299.0,
                "currency": "CNY",
                "apply_time": datetime.now().isoformat(),
                "next_steps": [
                    "1. 退款审核将在 1 个工作日内完成",
                    "2. 审核通过后，退款将原路返回至您的支付账户",
                    "3. 如有需要，我们会安排快递员上门取件",
                ] if refund_type == "refund" else [
                    "1. 请将商品寄回指定地址（我们会通过短信发送）",
                    "2. 请确保商品完好无损、配件齐全",
                    "3. 我们将在收到商品后 3 个工作日内处理",
                    "4. 退款将原路返回至您的支付账户",
                ],
                "shipping_address": {
                    "province": "广东省",
                    "city": "深圳市",
                    "district": "南山区",
                    "detail": "科技园路10号创新大厦A座",
                    "contact": "售后部",
                    "phone": "400-888-9999",
                } if refund_type == "return" else None,
            },
        }


class SearchKBTool(BaseTool):
    """知识库检索 - 支持关键词匹配 + 评分排序"""
    name = "search_kb"
    description = "从知识库中检索相关问题的答案，支持关键词匹配和语义搜索"
    parameters = [
        {"name": "query", "type": "string", "description": "查询内容", "required": True},
        {"name": "top_k", "type": "integer", "description": "返回结果数量", "required": False, "default": 3},
    ]

    KNOWLEDGE_BASE = {
        "退换货政策": {
            "content": "我们支持 7 天无理由退换货。商品需保持原包装、未经使用。退款将在收到商品后 3-7 个工作日内到账。",
            "keywords": ["退换货", "退货", "退款", "7天", "无理由", "售后"],
            "category": "售后政策",
        },
        "订单查询": {
            "content": "您可以通过订单号或手机号查询订单状态。物流信息在发货后 24 小时内更新。支持按时间段查询历史订单。",
            "keywords": ["订单", "物流", "查询", "发货", "快递", "状态"],
            "category": "订单服务",
        },
        "会员权益": {
            "content": "VIP 会员享受 95 折优惠、专属客服优先接入、免费包邮等权益。年度会员费 199 元，开通后立即生效。",
            "keywords": ["会员", "VIP", "权益", "优惠", "包邮", "折扣"],
            "category": "会员服务",
        },
        "支付方式": {
            "content": "我们支持支付宝、微信支付、银联、信用卡分期（3/6/12期）等多种支付方式。大额订单支持企业对公转账。",
            "keywords": ["支付", "付款", "支付宝", "微信", "银行卡", "分期"],
            "category": "支付服务",
        },
        "发票开具": {
            "content": "购买后 180 天内可申请开具电子发票。请在订单详情页点击'申请发票'按钮填写抬头信息。增值税专用发票需额外提交资质材料。",
            "keywords": ["发票", "开票", "抬头", "电子发票", "增值税"],
            "category": "财务服务",
        },
        "物流配送": {
            "content": "全国大部分地区 1-3 个工作日送达，偏远地区可能需要 3-5 个工作日。提供顺丰、京东、中通等多家快递公司选择。",
            "keywords": ["物流", "配送", "快递", "送达", "发货", "时效"],
            "category": "物流服务",
        },
        "账号安全": {
            "content": "建议使用强密码（至少8位，包含大小写字母和数字）。如怀疑账号被盗，请立即通过'忘记密码'功能重置密码，并联系客服冻结账号。",
            "keywords": ["密码", "账号", "安全", "登录", "被盗", "冻结"],
            "category": "账号服务",
        },
        "产品使用": {
            "content": "产品首次使用请先充电 2 小时。长按电源键 3 秒开机。详细使用说明请参考产品包装盒内的《快速上手指南》。",
            "keywords": ["使用", "开机", "充电", "设置", "安装", "教程"],
            "category": "产品支持",
        },
        "售后服务": {
            "content": "所有产品享受 1 年免费质保。非人为损坏可享受免费维修或更换。质保期外提供有偿维修服务，费用按故障类型评估。",
            "keywords": ["保修", "质保", "维修", "售后", "故障", "损坏"],
            "category": "售后服务",
        },
        "活动规则": {
            "content": "新用户首单立减 20 元。满 199 减 30，满 399 减 80。促销活动不与其他优惠同享，具体以结算页为准。",
            "keywords": ["优惠", "活动", "促销", "折扣", "满减", "券"],
            "category": "营销活动",
        },
    }

    async def execute(self, **kwargs) -> Dict[str, Any]:
        query = kwargs.get("query", "").lower().strip()
        top_k = kwargs.get("top_k", 3)

        if not query:
            return {
                "success": True,
                "data": [],
                "hint": "请输入搜索关键词",
            }

        query_chars = set(query)
        results = []

        for title, info in self.KNOWLEDGE_BASE.items():
            score = 0
            title_lower = title.lower()
            content_lower = info["content"].lower()

            if query in title_lower:
                score += 10
            if query in content_lower:
                score += 5

            for keyword in info["keywords"]:
                keyword_lower = keyword.lower()
                if keyword_lower in query or query in keyword_lower:
                    score += 3
                overlap = len(query_chars & set(keyword_lower))
                score += overlap * 0.5

            if score > 0:
                results.append({
                    "title": title,
                    "content": info["content"],
                    "category": info.get("category", "通用"),
                    "relevance_score": round(score, 2),
                })

        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        results = results[:top_k]

        if results:
            return {"success": True, "data": results}
        else:
            return {
                "success": True,
                "data": [],
                "hint": "未找到相关内容，请尝试其他关键词，或联系人工客服咨询",
            }


class EscalateToHumanTool(BaseTool):
    """转接人工客服"""
    name = "escalate_to_human"
    description = "将用户转接至人工客服处理，支持选择优先级和转接原因"
    parameters = [
        {"name": "reason", "type": "string", "description": "转接原因", "required": True},
        {"name": "priority", "type": "string", "description": "优先级", "required": False,
         "enum": ["normal", "urgent"], "default": "normal"},
        {"name": "context", "type": "string", "description": "上下文信息（可选）", "required": False, "default": ""},
    ]

    async def execute(self, **kwargs) -> Dict[str, Any]:
        reason = kwargs.get("reason", "")
        priority = kwargs.get("priority", "normal")
        context = kwargs.get("context", "")

        if not reason:
            return {"success": False, "error": "请提供转接原因", "hint": "请简要说明需要人工客服处理的原因"}

        priority_config = {
            "normal": {"wait_time": "3-5分钟", "position": 5, "label": "普通"},
            "urgent": {"wait_time": "立即", "position": 1, "label": "紧急"},
        }
        config = priority_config.get(priority, priority_config["normal"])

        return {
            "success": True,
            "data": {
                "escalation_id": str(uuid.uuid4()),
                "status": "queued",
                "priority": priority,
                "priority_label": config["label"],
                "queue_position": config["position"],
                "estimated_wait_time": config["wait_time"],
                "reason": reason,
                "context": context,
                "message": f"正在为您转接人工客服（{config['label']}优先级），预计等待{config['wait_time']}，请稍候...",
                "callback": "如等待时间过长，系统将自动回拨您的预留手机号",
            },
        }


class SendNotificationTool(BaseTool):
    """发送通知 - 支持多渠道"""
    name = "send_notification"
    description = "向用户发送短信或站内信通知"
    parameters = [
        {"name": "channel", "type": "string", "description": "通知渠道", "required": True,
         "enum": ["sms", "email", "inapp"]},
        {"name": "content", "type": "string", "description": "通知内容", "required": True},
        {"name": "user_id", "type": "integer", "description": "用户ID", "required": False, "default": 0},
    ]

    async def execute(self, **kwargs) -> Dict[str, Any]:
        channel = kwargs.get("channel", "")
        content = kwargs.get("content", "")
        user_id = kwargs.get("user_id", 0)

        if channel not in ["sms", "email", "inapp"]:
            return {"success": False, "error": f"不支持的通知渠道: {channel}", "hint": "支持的渠道：sms(短信)、email(邮件)、inapp(站内信)"}

        if not content or len(content.strip()) < 5:
            return {"success": False, "error": "通知内容过短", "hint": "请提供至少5个字符的通知内容"}

        channel_labels = {"sms": "短信", "email": "邮件", "inapp": "站内信"}

        return {
            "success": True,
            "data": {
                "notification_id": str(uuid.uuid4()),
                "channel": channel,
                "channel_label": channel_labels.get(channel, channel),
                "user_id": user_id,
                "content": content,
                "status": "sent",
                "sent_at": datetime.now().isoformat(),
                "message": f"{channel_labels.get(channel, channel)}通知已发送",
            },
        }


class UpdateTicketStatusTool(BaseTool):
    """更新工单状态"""
    name = "update_ticket_status"
    description = "更新工单的处理状态，用于工单流转和状态同步"
    parameters = [
        {"name": "ticket_id", "type": "string", "description": "工单ID", "required": True},
        {"name": "status", "type": "string", "description": "新状态", "required": True,
         "enum": ["pending", "processing", "resolved", "closed", "escalated"]},
        {"name": "note", "type": "string", "description": "状态变更备注", "required": False, "default": ""},
    ]

    async def execute(self, **kwargs) -> Dict[str, Any]:
        ticket_id = kwargs.get("ticket_id", "")
        status = kwargs.get("status", "")
        note = kwargs.get("note", "")

        if not ticket_id:
            return {"success": False, "error": "请提供工单ID", "hint": "工单ID格式：UUID"}

        if status not in ["pending", "processing", "resolved", "closed", "escalated"]:
            return {
                "success": False,
                "error": f"无效的工单状态: {status}",
                "hint": "有效状态：pending(待处理)、processing(处理中)、resolved(已解决)、closed(已关闭)、escalated(已升级)",
            }

        status_labels = {
            "pending": "待处理",
            "processing": "处理中",
            "resolved": "已解决",
            "closed": "已关闭",
            "escalated": "已升级",
        }

        return {
            "success": True,
            "data": {
                "ticket_id": ticket_id,
                "old_status": "pending",
                "new_status": status,
                "new_status_label": status_labels.get(status, status),
                "note": note,
                "updated_at": datetime.now().isoformat(),
                "message": f"工单状态已更新为：{status_labels.get(status, status)}",
            },
        }


class GetUserHistoryTool(BaseTool):
    """获取用户历史咨询记录"""
    name = "get_user_history"
    description = "获取用户的历史咨询记录、工单历史、偏好标签等"
    parameters = [
        {"name": "user_id", "type": "integer", "description": "用户ID", "required": True},
        {"name": "limit", "type": "integer", "description": "返回条数", "required": False, "default": 10},
    ]

    async def execute(self, **kwargs) -> Dict[str, Any]:
        user_id = kwargs.get("user_id", 0)
        limit = kwargs.get("limit", 10)

        if not user_id or user_id <= 0:
            return {"success": False, "error": "请提供有效的用户ID", "hint": "用户ID应为正整数"}

        mock_history = {
            1: {
                "user_id": 1,
                "user_level": "VIP",
                "total_orders": 15,
                "total_tickets": 3,
                "tags": ["高价值用户", "电子产品爱好者"],
                "history": [
                    {"date": "2026-08-10", "type": "订单咨询", "summary": "查询订单 ORD20260801 物流状态", "resolved": True},
                    {"date": "2026-07-25", "type": "退换货", "summary": "申请退货 ORD20260720（商品质量问题）", "resolved": True},
                    {"date": "2026-07-15", "type": "产品咨询", "summary": "询问产品使用方法和保修政策", "resolved": True},
                    {"date": "2026-06-20", "type": "投诉建议", "summary": "物流配送延迟投诉", "resolved": True},
                    {"date": "2026-05-10", "type": "订单咨询", "summary": "批量订单查询", "resolved": True},
                ],
            },
        }

        user_data = mock_history.get(user_id, {
            "user_id": user_id,
            "user_level": "普通用户",
            "total_orders": 0,
            "total_tickets": 0,
            "tags": [],
            "history": [],
        })

        return {
            "success": True,
            "data": {
                "user_id": user_id,
                "user_level": user_data.get("user_level", "普通用户"),
                "total_orders": user_data.get("total_orders", 0),
                "total_tickets": user_data.get("total_tickets", 0),
                "tags": user_data.get("tags", []),
                "history": user_data.get("history", [])[:limit],
            },
        }


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
    return TOOL_REGISTRY.get(name)


def get_all_tools() -> List[BaseTool]:
    return list(TOOL_REGISTRY.values())


def get_tool_schemas() -> List[Dict[str, Any]]:
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


async def execute_tool_with_fallback(
    tool_name: str,
    fallback_tool_name: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    带降级的工具执行
    主工具失败时，自动切换到备用工具
    """
    tool = get_tool(tool_name)
    if not tool:
        return {
            "success": False,
            "error": f"工具 {tool_name} 不存在",
            "hint": "请确认工具名称是否正确",
        }

    result = await tool.execute_with_retry(**kwargs)

    if not result.success and fallback_tool_name:
        fallback_tool = get_tool(fallback_tool_name)
        if fallback_tool:
            logger.warning(
                f"工具 {tool_name} 执行失败，降级到 {fallback_tool_name}"
            )
            fallback_result = await fallback_tool.execute_with_retry(**kwargs)
            return {
                "success": fallback_result.success,
                "data": fallback_result.data,
                "error": fallback_result.error,
                "hint": result.hint or fallback_result.hint,
                "fallback_used": True,
            }

    return {
        "success": result.success,
        "data": result.data,
        "error": result.error,
        "hint": result.hint,
        "execution_time_ms": result.execution_time_ms,
        "retry_count": result.retry_count,
    }
