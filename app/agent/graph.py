"""
状态机 Agent 编排 - Phase 3 增强版
实现类似 LangGraph 的节点式 Agent 编排
支持条件分支、工具调用、状态追踪、混合检索、结果校验
"""
import os
import time
import json
import asyncio
import logging
from typing import AsyncGenerator, Dict, List, Optional, Any, Callable
from datetime import datetime

from app.agent.state import AgentState, AgentNode, IntentType, ToolCall
from app.agent.intent import EnhancedIntentRecognizer, IntentResult
from app.agent.tools import get_tool, execute_tool_with_fallback
from app.agent.retrieval import HybridRetriever, create_default_hybrid_retriever
from app.agent.validation import ResponseValidator, create_validator
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)


class AgentGraph:
    """Agent 状态机 - 核心编排器 (Phase 3)"""

    def __init__(self):
        self.llm_service = LLMService()
        self.intent_recognizer = EnhancedIntentRecognizer()

        use_milvus = os.getenv("USE_MILVUS", "false").lower() == "true"
        milvus_host = os.getenv("MILVUS_HOST", "localhost")
        milvus_port = int(os.getenv("MILVUS_PORT", "19530"))
        embedding_dim = int(os.getenv("EMBEDDING_DIM", "1024"))
        self.hybrid_retriever = create_default_hybrid_retriever(
            use_milvus=use_milvus,
            milvus_host=milvus_host,
            milvus_port=milvus_port,
            embedding_dim=embedding_dim,
        )
        self.validator = create_validator()
        self.nodes: Dict[str, Callable] = {}
        self._register_nodes()

    def _register_nodes(self):
        self.nodes[AgentNode.START] = self._node_start
        self.nodes[AgentNode.INTENT_RECOGNITION] = self._node_intent_recognition
        self.nodes[AgentNode.CLARIFICATION] = self._node_clarification
        self.nodes[AgentNode.RAG_RETRIEVAL] = self._node_rag_retrieval
        self.nodes[AgentNode.TOOL_EXECUTION] = self._node_tool_execution
        self.nodes[AgentNode.RESULT_VERIFICATION] = self._node_result_verification
        self.nodes[AgentNode.RESPONSE_GENERATION] = self._node_response_generation
        self.nodes[AgentNode.HUMAN_HANDOFF] = self._node_human_handoff
        self.nodes[AgentNode.END] = self._node_end

    async def run_stream(self, state: AgentState) -> AsyncGenerator[Dict[str, Any], None]:
        """流式执行 Agent 状态机，逐步产出事件供 WebSocket/SSE 推送"""
        start_time = time.time()
        current_node = state.current_node
        visited_nodes = set()

        max_iterations = 15
        iteration = 0
        regeneration_count = 0

        yield {"type": "node_start", "node": current_node, "timestamp": datetime.now().isoformat()}

        while current_node != AgentNode.END and iteration < max_iterations:
            iteration += 1

            node_key = f"{current_node}_{state.detected_intent}"
            if node_key in visited_nodes:
                break
            visited_nodes.add(node_key)

            if current_node in self.nodes:
                node_func = self.nodes[current_node]
                state.current_node = current_node

                node_start = time.time()

                if current_node == AgentNode.INTENT_RECOGNITION:
                    yield {"type": "node_start", "node": "intent_recognition", "timestamp": datetime.now().isoformat()}
                    next_node = await node_func(state)
                    yield {
                        "type": "intent",
                        "intent": state.detected_intent,
                        "confidence": state.intent_confidence,
                        "needs_clarification": state.needs_clarification,
                        "timestamp": datetime.now().isoformat(),
                    }

                elif current_node == AgentNode.RAG_RETRIEVAL:
                    yield {"type": "node_start", "node": "rag_retrieval", "timestamp": datetime.now().isoformat()}
                    next_node = await node_func(state)
                    kb_results = state.collected_info.get("kb_results", [])
                    yield {
                        "type": "rag_result",
                        "results_count": len(kb_results),
                        "top_score": kb_results[0].get("final_score", 0) if kb_results else 0,
                        "timestamp": datetime.now().isoformat(),
                    }

                elif current_node == AgentNode.TOOL_EXECUTION:
                    extracted_info = self._extract_info_from_message(state.user_message)
                    for key, value in extracted_info.items():
                        if key not in state.collected_info or not state.collected_info[key]:
                            state.collected_info[key] = value

                    tools_to_execute = self._select_tools_for_intent(
                        state.detected_intent, state.collected_info
                    )

                    next_node = AgentNode.RESULT_VERIFICATION
                    for tool_name, tool_args in tools_to_execute:
                        yield {
                            "type": "tool_call_start",
                            "tool": tool_name,
                            "args": tool_args,
                            "timestamp": datetime.now().isoformat(),
                        }
                        tool = get_tool(tool_name)
                        if tool:
                            try:
                                result = await tool.execute_with_retry(**tool_args)
                                state.add_tool_call(
                                    tool_name=tool_name,
                                    arguments=tool_args,
                                    result={
                                        "success": result.success,
                                        "data": result.data,
                                        "error": result.error,
                                        "hint": result.hint,
                                        "execution_time_ms": result.execution_time_ms,
                                        "retry_count": result.retry_count,
                                    },
                                    success=result.success,
                                    error_message=result.error,
                                )

                                if result.success and result.data:
                                    if isinstance(result.data, dict):
                                        state.collected_info.update(result.data)
                                    state.collected_info[f"{tool_name}_result"] = result.data

                                yield {
                                    "type": "tool_call_complete",
                                    "tool": tool_name,
                                    "success": result.success,
                                    "execution_time_ms": result.execution_time_ms,
                                    "retry_count": result.retry_count,
                                    "timestamp": datetime.now().isoformat(),
                                }

                                if not result.success:
                                    if result.error and "人工" in result.error:
                                        state.need_human = True
                                        state.human_reason = result.error
                                        next_node = AgentNode.HUMAN_HANDOFF
                                        yield {"type": "handoff", "reason": state.human_reason, "timestamp": datetime.now().isoformat()}
                                        break

                                    if result.retry_count >= 3:
                                        state.need_human = True
                                        state.human_reason = f"工具 {tool_name} 连续 {result.retry_count} 次失败"
                                        next_node = AgentNode.HUMAN_HANDOFF
                                        yield {"type": "handoff", "reason": state.human_reason, "timestamp": datetime.now().isoformat()}
                                        break

                            except Exception as e:
                                logger.error(f"工具 {tool_name} 执行异常: {e}")
                                state.add_tool_call(
                                    tool_name=tool_name,
                                    arguments=tool_args,
                                    result=None,
                                    success=False,
                                    error_message=str(e),
                                )
                                yield {
                                    "type": "tool_call_complete",
                                    "tool": tool_name,
                                    "success": False,
                                    "error": str(e),
                                    "timestamp": datetime.now().isoformat(),
                                }

                elif current_node == AgentNode.CLARIFICATION:
                    yield {"type": "node_start", "node": "clarification", "timestamp": datetime.now().isoformat()}
                    next_node = await node_func(state)

                elif current_node == AgentNode.RESULT_VERIFICATION:
                    yield {"type": "node_start", "node": "result_verification", "timestamp": datetime.now().isoformat()}
                    next_node = await node_func(state)

                    if state.tool_calls:
                        last_call = state.tool_calls[-1]
                        if not last_call.success:
                            tool_count = len(state.tool_calls)
                            if tool_count >= 3:
                                state.need_human = True
                                state.human_reason = "工具调用连续失败"
                                next_node = AgentNode.HUMAN_HANDOFF
                                yield {"type": "handoff", "reason": state.human_reason, "timestamp": datetime.now().isoformat()}

                    if next_node == AgentNode.RESPONSE_GENERATION and state.reply:
                        validation_result = self.validator.validate(
                            response=state.reply,
                            user_query=state.user_message,
                            intent=state.detected_intent,
                            tool_results=[tc.result for tc in state.tool_calls],
                        )
                        state.collected_info["validation"] = validation_result.to_dict()
                        yield {
                            "type": "validation",
                            "passed": validation_result.passed,
                            "overall_score": validation_result.overall_score,
                            "needs_regeneration": validation_result.needs_regeneration,
                            "timestamp": datetime.now().isoformat(),
                        }

                        if validation_result.needs_regeneration and regeneration_count < 2:
                            regeneration_count += 1
                            state.reply = ""
                            yield {"type": "node_start", "node": "result_verification", "regeneration": True, "timestamp": datetime.now().isoformat()}
                            continue

                        if not validation_result.passed and regeneration_count >= 2:
                            state.need_human = True
                            state.human_reason = "回答校验连续不通过，需人工介入"
                            next_node = AgentNode.HUMAN_HANDOFF
                            yield {"type": "handoff", "reason": state.human_reason, "timestamp": datetime.now().isoformat()}

                elif current_node == AgentNode.HUMAN_HANDOFF:
                    yield {"type": "node_start", "node": "human_handoff", "timestamp": datetime.now().isoformat()}
                    next_node = await node_func(state)

                elif current_node == AgentNode.RESPONSE_GENERATION:
                    yield {"type": "node_start", "node": "response_generation", "timestamp": datetime.now().isoformat()}
                    next_node = await node_func(state)

                    full_reply = state.reply
                    chunk_size = max(1, len(full_reply) // 8)
                    for i in range(0, len(full_reply), chunk_size):
                        chunk = full_reply[i:i + chunk_size]
                        yield {"type": "token", "content": chunk, "index": i, "timestamp": datetime.now().isoformat()}
                        await asyncio.sleep(0.02)

                else:
                    next_node = await node_func(state)

                node_duration = int((time.time() - node_start) * 1000)

                state.add_trace(
                    node_name=current_node,
                    input_data={"message": state.user_message, "intent": state.detected_intent},
                    output_data={
                        "next_node": next_node,
                        "reply": state.reply[:100] if state.reply else "",
                    },
                    duration_ms=node_duration,
                )

                yield {
                    "type": "node_complete",
                    "node": current_node,
                    "duration_ms": node_duration,
                    "next_node": next_node,
                    "timestamp": datetime.now().isoformat(),
                }

                current_node = next_node
            else:
                break

        state.execution_time_ms = int((time.time() - start_time) * 1000)
        state.response_ready = True

        yield {
            "type": "done",
            "reply": state.reply,
            "intent": state.detected_intent,
            "execution_time_ms": state.execution_time_ms,
            "tool_calls": [
                {"tool": tc.tool_name, "success": tc.success}
                for tc in state.tool_calls
            ],
            "need_human": state.need_human,
            "timestamp": datetime.now().isoformat(),
        }

    async def run(self, state: AgentState) -> AgentState:
        start_time = time.time()
        current_node = state.current_node
        visited_nodes = set()

        max_iterations = 15
        iteration = 0
        regeneration_count = 0

        while current_node != AgentNode.END and iteration < max_iterations:
            iteration += 1

            node_key = f"{current_node}_{state.detected_intent}"
            if node_key in visited_nodes:
                break
            visited_nodes.add(node_key)

            if current_node in self.nodes:
                node_func = self.nodes[current_node]
                state.current_node = current_node

                node_start = time.time()
                next_node = await node_func(state)
                node_duration = int((time.time() - node_start) * 1000)

                state.add_trace(
                    node_name=current_node,
                    input_data={"message": state.user_message, "intent": state.detected_intent},
                    output_data={
                        "next_node": next_node,
                        "reply": state.reply[:100] if state.reply else "",
                        "need_regeneration": state.current_node == AgentNode.RESULT_VERIFICATION
                        and not state.reply,
                    },
                    duration_ms=node_duration,
                )

                if (
                    current_node == AgentNode.RESULT_VERIFICATION
                    and next_node == AgentNode.RESPONSE_GENERATION
                    and state.reply
                ):
                    validation_result = self.validator.validate(
                        response=state.reply,
                        user_query=state.user_message,
                        intent=state.detected_intent,
                        tool_results=[tc.result for tc in state.tool_calls],
                    )

                    state.collected_info["validation"] = validation_result.to_dict()

                    if validation_result.needs_regeneration and regeneration_count < 2:
                        regeneration_count += 1
                        logger.info(
                            f"回答校验不通过 (第{regeneration_count}次)，重新生成"
                        )
                        state.reply = ""
                        continue

                    if not validation_result.passed and regeneration_count >= 2:
                        state.need_human = True
                        state.human_reason = "回答校验连续不通过，需人工介入"
                        logger.warning(f"回答校验失败，转人工: {state.human_reason}")
                        next_node = AgentNode.HUMAN_HANDOFF

                current_node = next_node
            else:
                break

        state.execution_time_ms = int((time.time() - start_time) * 1000)
        state.response_ready = True

        return state

    async def _node_start(self, state: AgentState) -> str:
        return AgentNode.INTENT_RECOGNITION

    async def _node_intent_recognition(self, state: AgentState) -> str:
        intent_result = self.intent_recognizer.recognize(
            message=state.user_message,
            context=state.messages,
            history_intent=state.detected_intent if state.current_node != AgentNode.START else None,
        )

        state.detected_intent = intent_result.intent
        state.intent_confidence = intent_result.confidence
        state.needs_clarification = intent_result.needs_clarification

        if intent_result.intent == IntentType.HUMAN:
            state.need_human = True
            if not state.human_reason:
                state.human_reason = "用户请求转接人工客服"

        if intent_result.needs_clarification:
            return AgentNode.CLARIFICATION

        return self._route_by_intent(state.detected_intent)

    def _route_by_intent(self, intent: str) -> str:
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
        question = self.intent_recognizer.get_clarification_question(state.detected_intent)
        state.reply = question
        state.needs_clarification = True

        state.messages.append({
            "role": "assistant",
            "content": question,
            "type": "clarification",
        })

        return AgentNode.RESPONSE_GENERATION

    async def _node_rag_retrieval(self, state: AgentState) -> str:
        query = state.user_message
        top_k = 3

        search_result = self.hybrid_retriever.search(query=query, top_k=top_k)

        state.add_tool_call(
            tool_name="hybrid_search",
            arguments={"query": query, "top_k": top_k},
            result=search_result,
            success=search_result.get("success", False),
        )

        state.collected_info["kb_results"] = search_result.get("results", [])
        state.collected_info["kb_search_meta"] = search_result.get("meta", {})

        if state.collected_info["kb_results"]:
            best_match = state.collected_info["kb_results"][0]
            state.collected_info["best_match_score"] = best_match.get(
                "final_score", best_match.get("hybrid_score", 0)
            )

        logger.info(
            f"混合检索完成: {len(search_result.get('results', []))} 条结果, "
            f"耗时 {search_result.get('execution_time_ms', 0)}ms"
        )

        return AgentNode.RESPONSE_GENERATION

    async def _node_tool_execution(self, state: AgentState) -> str:
        extracted_info = self._extract_info_from_message(state.user_message)

        for key, value in extracted_info.items():
            if key not in state.collected_info or not state.collected_info[key]:
                state.collected_info[key] = value

        tools_to_execute = self._select_tools_for_intent(
            state.detected_intent, state.collected_info
        )

        for tool_name, tool_args in tools_to_execute:
            tool = get_tool(tool_name)
            if tool:
                try:
                    result = await tool.execute_with_retry(**tool_args)

                    state.add_tool_call(
                        tool_name=tool_name,
                        arguments=tool_args,
                        result={
                            "success": result.success,
                            "data": result.data,
                            "error": result.error,
                            "hint": result.hint,
                            "execution_time_ms": result.execution_time_ms,
                            "retry_count": result.retry_count,
                        },
                        success=result.success,
                        error_message=result.error,
                    )

                    if result.success and result.data:
                        if isinstance(result.data, dict):
                            state.collected_info.update(result.data)
                        state.collected_info[f"{tool_name}_result"] = result.data

                    if not result.success:
                        if result.error and "人工" in result.error:
                            state.need_human = True
                            state.human_reason = result.error
                            return AgentNode.HUMAN_HANDOFF

                        if result.retry_count >= 3:
                            state.need_human = True
                            state.human_reason = f"工具 {tool_name} 连续 {result.retry_count} 次失败"
                            logger.warning(f"工具连续失败，转人工: {state.human_reason}")
                            return AgentNode.HUMAN_HANDOFF

                except Exception as e:
                    logger.error(f"工具 {tool_name} 执行异常: {e}")
                    state.add_tool_call(
                        tool_name=tool_name,
                        arguments=tool_args,
                        result=None,
                        success=False,
                        error_message=str(e),
                    )

        return AgentNode.RESULT_VERIFICATION

    def _extract_info_from_message(self, message: str) -> Dict[str, Any]:
        import re

        info = {}

        order_patterns = [
            r"ORD\d{6,}",
            r"订单[：:]\s*(\w+)",
            r"订单号[：:]\s*(\w+)",
        ]
        for pattern in order_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                order_id = match.group(0) if len(match.groups()) == 0 else match.group(1)
                info["order_id"] = order_id
                break

        if any(word in message for word in ["投诉", "垃圾", "骗子", "气愤"]):
            info["complaint_content"] = message

        if any(word in message for word in ["退款", "退货", "退换"]):
            info["reason"] = message
            if "换" in message:
                info["refund_type"] = "exchange"
            else:
                info["refund_type"] = "refund"

        return info

    def _select_tools_for_intent(
        self, intent: str, collected_info: Dict[str, Any]
    ) -> List[tuple]:
        tool_plan = []

        if intent == IntentType.QUERY_ORDER:
            order_id = collected_info.get("order_id")
            if order_id:
                tool_plan.append(("query_order", {"order_id": order_id}))

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
        if state.tool_calls:
            last_call = state.tool_calls[-1]

            if not last_call.success:
                tool_count = len(state.tool_calls)
                if tool_count < 3:
                    state.reply = f"抱歉，操作遇到问题：{last_call.error_message or '未知错误'}"
                else:
                    state.need_human = True
                    state.human_reason = "工具调用连续失败"
                    logger.warning(f"工具连续失败 ({tool_count}次)，转人工")
                    return AgentNode.HUMAN_HANDOFF

            if last_call.success and isinstance(last_call.result, dict):
                execution_time = last_call.result.get("execution_time_ms", 0)
                retry_count = last_call.result.get("retry_count", 0)
                if execution_time > 3000:
                    logger.warning(
                        f"工具执行耗时过长: {execution_time}ms"
                    )

                if retry_count > 0:
                    logger.info(
                        f"工具执行重试 {retry_count} 次后成功"
                    )

        return AgentNode.RESPONSE_GENERATION

    async def _node_response_generation(self, state: AgentState) -> str:
        if state.need_human and not state.reply:
            state.reply = f"非常抱歉，正在为您转接人工客服。{state.human_reason or ''}"

        if not state.reply:
            llm_reply = await self._generate_response_with_llm(state)
            if llm_reply:
                state.reply = llm_reply
            else:
                state.reply = self._get_default_reply(state.detected_intent, state.user_message)

        state.messages.append({
            "role": "assistant",
            "content": state.reply,
            "intent": state.detected_intent,
            "tool_calls": [tc.tool_name for tc in state.tool_calls],
            "timestamp": datetime.now().isoformat(),
        })

        return AgentNode.END

    async def _generate_response_with_llm(self, state: AgentState) -> str:
        """使用 LLM 生成响应，失败时返回 None 由调用方降级"""
        try:
            prompt = self._build_llm_prompt(state)
            context_messages = self._build_context_messages(state)

            reply, intent, token_count = await self.llm_service.chat(
                user_id=state.user_id,
                session_id=state.session_id,
                message=prompt,
                context=context_messages,
            )
            state.total_tokens = token_count

            if state.detected_intent not in (IntentType.HUMAN, IntentType.COMPLAINT, IntentType.QUERY_ORDER, IntentType.REFUND):
                state.detected_intent = intent

            logger.info(
                f"LLM 响应生成成功: intent={state.detected_intent}, tokens={token_count}, "
                f"session={state.session_id}"
            )
            return reply
        except Exception as e:
            logger.warning(f"LLM 调用失败: {e}")
            return None

    def _build_llm_prompt(self, state: AgentState) -> str:
        """构建发送给 LLM 的富上下文 prompt"""
        parts = []
        intent_labels = {
            "query_order": "订单查询",
            "refund": "退换货",
            "complaint": "投诉",
            "technical": "技术咨询",
            "promotion": "活动咨询",
            "human": "转人工",
            "general": "通用咨询",
        }
        intent_label = intent_labels.get(state.detected_intent, state.detected_intent)
        parts.append(f"【用户意图】{intent_label}")
        parts.append(f"【用户消息】{state.user_message}")

        successful_tools = [tc for tc in state.tool_calls if tc.success]
        if successful_tools:
            parts.append("【工具执行结果】")
            for tc in successful_tools:
                result = tc.result
                if isinstance(result, dict) and result.get("data"):
                    data = result["data"]
                    if isinstance(data, dict):
                        parts.append(f"  - {tc.tool_name}: {json.dumps(data, ensure_ascii=False, indent=2)}")
                    elif isinstance(data, list) and data:
                        if isinstance(data[0], dict):
                            parts.append(f"  - {tc.tool_name}: 找到 {len(data)} 条结果")
                            for item in data[:3]:
                                title = item.get("title", "")
                                content = item.get("content", "")[:200]
                                if title:
                                    parts.append(f"    【{title}】{content}")
                        else:
                            parts.append(f"  - {tc.tool_name}: {json.dumps(data, ensure_ascii=False)[:500]}")
                    else:
                        parts.append(f"  - {tc.tool_name}: {str(data)[:500]}")
                elif isinstance(result, dict) and result.get("success"):
                    parts.append(f"  - {tc.tool_name}: 操作成功")
                else:
                    parts.append(f"  - {tc.tool_name}: 执行成功")

        failed_tools = [tc for tc in state.tool_calls if not tc.success]
        if failed_tools:
            parts.append("【工具执行失败】")
            for tc in failed_tools:
                parts.append(f"  - {tc.tool_name}: {tc.error_message or '未知错误'}")

        kb_results = state.collected_info.get("kb_results", [])
        if kb_results:
            parts.append("【知识库检索结果】")
            for i, result in enumerate(kb_results[:3], 1):
                title = result.get("title", "")
                content = result.get("content", "")
                category = result.get("category", "")
                score = result.get("final_score", result.get("hybrid_score", 0))
                parts.append(f"  {i}. 【{title}】({category}, 相关度:{score:.0%})")
                if content:
                    parts.append(f"     {content[:300]}")

        parts.append("")
        parts.append("请根据以上信息，用自然、专业、简洁的中文回复用户。回复要点：")
        parts.append("1. 直接回应用户的问题或需求")
        parts.append("2. 如果有工具执行结果，清晰告知用户结果")
        parts.append("3. 如果有知识库内容，基于检索内容给出准确回答")
        parts.append("4. 保持友好专业的语气，适当引导下一步操作")
        parts.append("5. 回复控制在 200 字以内")

        return "\n".join(parts)

    def _build_context_messages(self, state: AgentState) -> list:
        """构建对话历史上下文"""
        context = []
        for msg in state.messages[-6:]:
            if msg.get("role") in ("user", "assistant"):
                context.append({
                    "role": msg["role"],
                    "content": msg.get("content", ""),
                })
        return context

    def _generate_response(self, state: AgentState) -> str:
        intent = state.detected_intent
        collected = state.collected_info
        tool_results = [tc for tc in state.tool_calls if tc.success]

        if tool_results:
            last_result = tool_results[-1]
            result_data = last_result.result if isinstance(last_result.result, dict) else {}

            if intent == IntentType.QUERY_ORDER:
                order_data = result_data.get("data", {}) if result_data else {}
                if order_data and isinstance(order_data, dict):
                    shipping = order_data.get("shipping", {})
                    status_text = order_data.get("status", "未知")
                    shipping_text = (
                        f"{shipping.get('carrier', '')} - {shipping.get('tracking_no', '')}"
                        if shipping
                        else "暂无物流信息"
                    )
                    delivery_status = shipping.get("status", "待发货") if shipping else "待发货"
                    amount = order_data.get("total_amount", 0)

                    refund_info = ""
                    if order_data.get("can_refund"):
                        deadline = order_data.get("refund_deadline", "")
                        if deadline:
                            refund_info = f"\n退换货截止日期：{deadline[:10]}"

                    return (
                        f"您的订单 {order_data.get('order_id', '')} 当前状态：{status_text}\n"
                        f"物流信息：{shipping_text}\n"
                        f"配送状态：{delivery_status}\n"
                        f"订单金额：¥{amount:.2f}"
                        f"{refund_info}"
                    )

            elif intent == IntentType.REFUND:
                refund_data = result_data.get("data", {}) if result_data else {}
                if refund_data and isinstance(refund_data, dict):
                    steps = refund_data.get("next_steps", [])
                    refund_id = refund_data.get("refund_id", "")[:8]
                    refund_type_label = refund_data.get("type_label", "退款")
                    amount = refund_data.get("amount", 0)

                    steps_text = "\n".join(f"• {step}" for step in steps[:3])

                    return (
                        f"{refund_type_label}申请已提交（退款单号：{refund_id}...）\n"
                        f"退款金额：¥{amount:.2f}\n"
                        f"接下来的步骤：\n{steps_text}"
                    )

            elif intent == IntentType.COMPLAINT:
                ticket_data = result_data.get("data", {}) if result_data else {}
                if ticket_data and isinstance(ticket_data, dict):
                    ticket_id = ticket_data.get("ticket_id", "")[:8]
                    sla_deadline = ticket_data.get("sla_deadline", "")[:10]
                    assignee = ticket_data.get("assignee", "")

                    return (
                        f"您的投诉工单已创建（工单号：{ticket_id}...）\n"
                        f"处理专员：{assignee}\n"
                        f"我们将在 {sla_deadline} 前处理您的问题，请保持电话畅通。"
                    )

            if result_data and result_data.get("success"):
                data = result_data.get("data")
                if isinstance(data, dict):
                    msg = data.get("message", "已完成")
                    return f"操作成功：{msg}"
                elif isinstance(data, list) and data:
                    if isinstance(data[0], dict):
                        title = data[0].get("title", "")
                        content = data[0].get("content", "")[:150]
                        category = data[0].get("category", "")
                        return f"已找到 {len(data)} 条相关信息（分类：{category}）：\n\n【{title}】\n{content}"
                    return f"已找到 {len(data)} 条相关信息"
                return "操作成功"

        kb_results = collected.get("kb_results", [])
        if kb_results:
            best_match = kb_results[0] if kb_results else {}
            title = best_match.get("title", "")
            content = best_match.get("content", "")
            category = best_match.get("category", "")
            score = best_match.get("final_score", best_match.get("hybrid_score", 0))

            response_parts = []
            if title:
                response_parts.append(f"【{title}】")
            if content:
                response_parts.append(content)
            if category:
                response_parts.append(f"\n（分类：{category}，相关度：{score:.0%}）")

            return "\n".join(response_parts)

        return self._get_default_reply(intent, state.user_message)

    def _get_default_reply(self, intent: str, message: str) -> str:
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
        tool = get_tool("escalate_to_human")
        if tool:
            result = await tool.execute(
                reason=state.human_reason or "用户要求转人工",
                priority="urgent" if state.need_human else "normal",
                user_id=state.user_id,
                session_id=state.session_id,
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
        return AgentNode.END
