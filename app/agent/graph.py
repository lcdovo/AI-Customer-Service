"""
状态机 Agent 编排 - 核心流程控制
实现类似 LangGraph 的节点式 Agent 编排
支持条件分支、工具调用、状态追踪
"""
import time
import json
import asyncio
from typing import AsyncGenerator, Dict, List, Optional, Any, Callable
from datetime import datetime

from app.agent.state import AgentState, AgentNode, IntentType, ToolCall
from app.agent.intent import EnhancedIntentRecognizer, IntentResult
from app.agent.tools import get_tool
from app.services.llm_service import LLMService


class AgentGraph:
    """Agent 状态机 - 核心编排器"""

    def __init__(self):
        self.llm_service = LLMService()
        self.intent_recognizer = EnhancedIntentRecognizer()
        self.nodes: Dict[str, Callable] = {}
        self._register_nodes()

    def _register_nodes(self):
        """注册所有节点"""
        self.nodes[AgentNode.START] = self._node_start
        self.nodes[AgentNode.INTENT_RECOGNITION] = self._node_intent_recognition
        self.nodes[AgentNode.CLARIFICATION] = self._node_clarification
        self.nodes[AgentNode.RAG_RETRIEVAL] = self._node_rag_retrieval
        self.nodes[AgentNode.TOOL_EXECUTION] = self._node_tool_execution
        self.nodes[AgentNode.RESULT_VERIFICATION] = self._node_result_verification
        self.nodes[AgentNode.RESPONSE_GENERATION] = self._node_response_generation
        self.nodes[AgentNode.HUMAN_HANDOFF] = self._node_human_handoff
        self.nodes[AgentNode.END] = self._node_end

    async def run(self, state: AgentState) -> AgentState:
        """
        运行 Agent 状态机
        Args:
            state: 初始状态
        Returns:
            处理完成的状态
        """
        start_time = time.time()
        current_node = state.current_node
        visited_nodes = set()

        max_iterations = 10
        iteration = 0

        while current_node != AgentNode.END and iteration < max_iterations:
            iteration += 1

            # 防止循环
            node_key = f"{current_node}_{state.detected_intent}"
            if node_key in visited_nodes:
                break
            visited_nodes.add(node_key)

            # 执行当前节点
            if current_node in self.nodes:
                node_func = self.nodes[current_node]
                state.current_node = current_node

                node_start = time.time()
                next_node = await node_func(state)
                node_duration = int((time.time() - node_start) * 1000)

                # 记录轨迹
                state.add_trace(
                    node_name=current_node,
                    input_data={"message": state.user_message, "intent": state.detected_intent},
                    output_data={"next_node": next_node, "reply": state.reply[:100] if state.reply else ""},
                    duration_ms=node_duration,
                )

                current_node = next_node
            else:
                # 未知节点，直接结束
                break

        state.execution_time_ms = int((time.time() - start_time) * 1000)
        state.response_ready = True

        return state

    async def _node_start(self, state: AgentState) -> str:
        """起始节点 -> 意图识别"""
        return AgentNode.INTENT_RECOGNITION

    async def _node_intent_recognition(self, state: AgentState) -> str:
        """意图识别节点"""
        intent_result = self.intent_recognizer.recognize(
            message=state.user_message,
            context=state.messages,
            history_intent=state.detected_intent if state.current_node != AgentNode.START else None,
        )

        state.detected_intent = intent_result.intent
        state.intent_confidence = intent_result.confidence
        state.needs_clarification = intent_result.needs_clarification

        # 根据置信度决定下一步
        if intent_result.needs_clarification:
            return AgentNode.CLARIFICATION

        # 根据意图类型选择路径
        return self._route_by_intent(state.detected_intent)

    def _route_by_intent(self, intent: str) -> str:
        """根据意图路由到对应节点"""
        intent_routes = {
            IntentType.QUERY_ORDER: AgentNode.TOOL_EXECUTION,
            IntentType.REFUND: AgentNode.TOOL_EXECUTION,
            IntentType.COMPLAINT: AgentNode.TOOL_EXECUTION,
            IntentType.TECHNICAL: AgentNode.RAG_RETRIEVAL,
            IntentType.PROMOTION: AgentNode.RAG_RETRIEVAL,
            IntentType.HUMAN: AgentNode.HUMAN_HANDOFF,
            IntentType.GENERAL: AgentNode.RESPONSE_GENERATION,
        }
        return intent_routes.get(intent, AgentNode.RESPONSE_GENERATION)

    async def _node_clarification(self, state: AgentState) -> str:
        """澄清节点 - 当意图不明确时追问"""
        question = self.intent_recognizer.get_clarification_question(state.detected_intent)
        state.reply = question
        state.needs_clarification = True

        # 记录消息
        state.messages.append({
            "role": "assistant",
            "content": question,
            "type": "clarification",
        })

        return AgentNode.RESPONSE_GENERATION

    async def _node_rag_retrieval(self, state: AgentState) -> str:
        """RAG 检索节点 - 从知识库检索答案"""
        tool = get_tool("search_kb")
        if tool:
            result = await tool.execute(query=state.user_message, top_k=3)
            state.add_tool_call(
                tool_name="search_kb",
                arguments={"query": state.user_message, "top_k": 3},
                result=result,
                success=result.get("success", False),
            )
            state.collected_info["kb_results"] = result.get("data", [])

        return AgentNode.RESPONSE_GENERATION

    async def _node_tool_execution(self, state: AgentState) -> str:
        """工具执行节点"""
        # 从用户消息中提取关键信息
        extracted_info = self._extract_info_from_message(state.user_message)
        
        # 合并已收集的信息和提取的信息
        for key, value in extracted_info.items():
            if key not in state.collected_info or not state.collected_info[key]:
                state.collected_info[key] = value

        # 根据意图选择要执行的工具
        tools_to_execute = self._select_tools_for_intent(state.detected_intent, state.collected_info)

        for tool_name, tool_args in tools_to_execute:
            tool = get_tool(tool_name)
            if tool:
                try:
                    result = await tool.execute(**tool_args)
                    state.add_tool_call(
                        tool_name=tool_name,
                        arguments=tool_args,
                        result=result,
                        success=result.get("success", False),
                        error_message=result.get("error"),
                    )

                    # 收集信息
                    if result.get("success"):
                        data = result.get("data", {})
                        if isinstance(data, dict):
                            state.collected_info.update(data)

                    # 如果需要人工介入
                    if not result.get("success") and result.get("hint", "").find("人工") >= 0:
                        state.need_human = True
                        state.human_reason = result.get("error", "未知错误")
                        return AgentNode.HUMAN_HANDOFF

                except Exception as e:
                    state.add_tool_call(
                        tool_name=tool_name,
                        arguments=tool_args,
                        result=None,
                        success=False,
                        error_message=str(e),
                    )

        return AgentNode.RESULT_VERIFICATION

    def _extract_info_from_message(self, message: str) -> Dict[str, Any]:
        """从用户消息中提取关键信息"""
        import re
        info = {}

        # 提取订单号 (ORD + 数字)
        order_patterns = [
            r'ORD\d{8,}',
            r'订单[：:]\s*(\w+)',
            r'订单号[：:]\s*(\w+)',
        ]
        for pattern in order_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                order_id = match.group(0) if len(match.groups()) == 0 else match.group(1)
                info["order_id"] = order_id
                break

        # 提取用户ID (如果是从数据库获取的)
        # 这里主要依赖 state 中的 user_id

        # 提取投诉内容
        if any(word in message for word in ["投诉", "垃圾", "骗子", "气愤"]):
            info["complaint_content"] = message

        # 提取退款原因
        if any(word in message for word in ["退款", "退货", "退换"]):
            info["reason"] = message
            # 判断退款类型
            if "换" in message:
                info["refund_type"] = "exchange"
            else:
                info["refund_type"] = "refund"

        return info

    def _select_tools_for_intent(
        self, intent: str, collected_info: Dict[str, Any]
    ) -> List[tuple]:
        """根据意图选择工具"""
        tool_plan = []

        if intent == IntentType.QUERY_ORDER:
            # 如果已经有订单号，直接查询
            order_id = collected_info.get("order_id")
            if order_id:
                tool_plan.append(("query_order", {"order_id": order_id}))
            # 没有订单号时不添加工具，回复默认提示

        elif intent == IntentType.REFUND:
            order_id = collected_info.get("order_id", "")
            reason = collected_info.get("reason", "")
            refund_type = collected_info.get("refund_type", "refund")
            
            if order_id:
                tool_plan.append((
                    "apply_refund",
                    {
                        "order_id": order_id,
                        "reason": reason,
                        "type": refund_type,
                    },
                ))

        elif intent == IntentType.COMPLAINT:
            complaint_content = collected_info.get("complaint_content", "")
            tool_plan.append((
                "create_ticket",
                {
                    "user_id": collected_info.get("user_id", 1),
                    "category": "投诉建议",
                    "content": complaint_content or "用户投诉",
                    "priority": "high",
                },
            ))

        return tool_plan

    async def _node_result_verification(self, state: AgentState) -> str:
        """结果校验节点"""
        # 检查最后一个工具调用的结果
        if state.tool_calls:
            last_call = state.tool_calls[-1]

            if not last_call.success:
                # 工具调用失败
                if len(state.tool_calls) < 3:
                    # 重试次数不够，给用户提示
                    state.reply = f"抱歉，操作遇到问题：{last_call.error_message or '未知错误'}"
                else:
                    # 重试次数过多，转人工
                    state.need_human = True
                    state.human_reason = "工具调用连续失败"
                    return AgentNode.HUMAN_HANDOFF

        return AgentNode.RESPONSE_GENERATION

    async def _node_response_generation(self, state: AgentState) -> str:
        """响应生成节点"""
        # 如果已经有回复（如澄清问题），直接使用
        if state.reply:
            pass
        # 如果需要人工，给出转接提示
        elif state.need_human:
            state.reply = f"非常抱歉，正在为您转接人工客服。{state.human_reason or ''}"
        else:
            # 基于收集的信息生成回复
            state.reply = self._generate_response(state)

        # 记录消息
        state.messages.append({
            "role": "assistant",
            "content": state.reply,
            "intent": state.detected_intent,
            "tool_calls": [tc.tool_name for tc in state.tool_calls],
        })

        return AgentNode.END

    def _generate_response(self, state: AgentState) -> str:
        """根据状态生成回复"""
        intent = state.detected_intent
        collected = state.collected_info
        tool_results = [tc for tc in state.tool_calls if tc.success]

        # 如果有工具调用结果，基于结果生成回复
        if tool_results:
            last_result = tool_results[-1]

            if intent == IntentType.QUERY_ORDER:
                order_data = last_result.result.get("data", {}) if last_result.result else {}
                if order_data:
                    shipping = order_data.get("shipping", {})
                    return (
                        f"您的订单 {order_data.get('order_id', '')} 当前状态：{order_data.get('status', '未知')}\n"
                        f"物流信息：{shipping.get('carrier', '')} - {shipping.get('tracking_no', '')}\n"
                        f"配送状态：{shipping.get('status', '')}\n"
                        f"订单金额：¥{order_data.get('total_amount', 0)}"
                    )

            elif intent == IntentType.REFUND:
                refund_data = last_result.result.get("data", {}) if last_result.result else {}
                if refund_data:
                    steps = refund_data.get("next_steps", [])
                    return (
                        f"退款申请已提交（退款单号：{refund_data.get('refund_id', '')}）\n"
                        f"接下来的步骤：\n"
                        + "\n".join(f"• {step}" for step in steps)
                    )

            elif intent == IntentType.COMPLAINT:
                ticket_data = last_result.result.get("data", {}) if last_result.result else {}
                if ticket_data:
                    return (
                        f"您的投诉工单已创建（工单号：{ticket_data.get('ticket_id', '')}）\n"
                        f"我们将在 {ticket_data.get('sla_deadline', '')} 前处理您的问题，请保持电话畅通。"
                    )

            # 通用工具成功回复
            if last_result.result and last_result.result.get("success"):
                data = last_result.result.get('data')
                if isinstance(data, dict):
                    return f"操作成功：{data.get('message', '已完成')}"
                elif isinstance(data, list) and data:
                    if isinstance(data[0], dict):
                        return f"已找到 {len(data)} 条相关信息：{data[0].get('content', '')[:100]}"
                    return f"已找到 {len(data)} 条相关信息"
                return "操作成功"

        # 如果有 RAG 检索结果
        kb_results = collected.get("kb_results", [])
        if kb_results:
            best_match = kb_results[0] if kb_results else {}
            return f"根据您的问题，我们找到以下信息：\n\n{best_match.get('content', '')}"

        # 基于意图的默认回复
        return self._get_default_reply(intent, state.user_message)

    def _get_default_reply(self, intent: str, message: str) -> str:
        """获取默认回复"""
        default_replies = {
            IntentType.QUERY_ORDER: "请提供您的订单号，我可以帮您查询最新的订单状态和物流信息。",
            IntentType.REFUND: "关于退换货问题，请提供订单号和退换货原因，我将为您处理。",
            IntentType.COMPLAINT: "非常抱歉给您带来不好的体验。请详细描述您遇到的问题，我们会尽快为您解决。",
            IntentType.TECHNICAL: "我来帮您解决这个问题。请详细描述遇到的情况，包括操作步骤和报错信息。",
            IntentType.PROMOTION: "我们目前有多种优惠活动。您可以在官网或 APP 首页查看最新的促销信息。",
            IntentType.GENERAL: "感谢您的咨询。我可以帮助您查询订单、处理退换货、解答产品问题等。请问有什么可以帮您的？",
        }
        return default_replies.get(intent, default_replies[IntentType.GENERAL])

    async def _node_human_handoff(self, state: AgentState) -> str:
        """人工转接节点"""
        tool = get_tool("escalate_to_human")
        if tool:
            result = await tool.execute(
                reason=state.human_reason or "用户要求转人工",
                priority="urgent" if state.need_human else "normal",
            )
            state.add_tool_call(
                tool_name="escalate_to_human",
                arguments={"reason": state.human_reason},
                result=result,
                success=result.get("success", False),
            )
            state.reply = result.get("data", {}).get("message", "正在为您转接人工客服...")
        else:
            state.reply = "正在为您转接人工客服，请稍候..."

        return AgentNode.RESPONSE_GENERATION

    async def _node_end(self, state: AgentState) -> str:
        """结束节点"""
        return AgentNode.END


# Agent 执行流程图（文档用）:
#
#                  ┌─────────────┐
#                  │    START    │
#                  └──────┬──────┘
#                         │
#                  ┌──────▼──────┐
#                  │ INTENT_REC  │
#                  └──────┬──────┘
#                         │
#              ┌──────────┼──────────┐
#              │          │          │
#       confidence<0.4   不同意图   │
#              │          │          │
#       ┌──────▼──┐  ┌───▼────┐  ┌──▼─────┐
#       │CLARIFY  │  │TOOL_EXE│  │RAG_RETR│
#       └──────┬──┘  └───┬────┘  └──┬─────┘
#              │         │          │
#              │    ┌────▼────┐     │
#              │    │RESULT_V │     │
#              │    └────┬────┘     │
#              │         │          │
#              │    ┌────▼──────────▼────┐
#              │    │  RESPONSE_GEN      │
#              │    └────┬──────────┬────┘
#              │         │          │
#              │    need_human   正常流程
#              │         │          │
#              │    ┌────▼────┐     │
#              │    │HUMAN_HD │     │
#              │    └────┬────┘     │
#              │         │          │
#              └─────────┴──────────┘
#                        │
#                 ┌──────▼──────┐
#                 │     END     │
#                 └─────────────┘
