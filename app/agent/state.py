"""
Agent 状态定义 - 定义 Agent 在执行过程中需要追踪的所有状态
"""
from typing import Any, List, Dict, Optional, Literal
from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """工具调用记录"""
    tool_name: str
    arguments: Dict[str, Any]
    result: Any = None
    success: bool = True
    error_message: Optional[str] = None


class AgentState(BaseModel):
    """Agent 运行时状态"""
    # 基本信息
    session_id: str
    user_id: int
    user_message: str
    
    # 意图识别
    detected_intent: str = "general"
    intent_confidence: float = 0.0
    needs_clarification: bool = False
    
    # 对话历史
    messages: List[Dict[str, Any]] = []
    conversation_summary: Optional[str] = None
    
    # Agent 执行状态
    current_node: str = "start"
    tool_calls: List[ToolCall] = []
    collected_info: Dict[str, Any] = {}  # 已收集的信息（如订单号等）
    pending_confirmations: List[str] = []  # 待确认项
    
    # 结果
    reply: str = ""
    response_ready: bool = False
    need_human: bool = False
    human_reason: Optional[str] = None
    
    # 追踪
    trace: List[Dict[str, Any]] = []  # 执行链路追踪
    total_tokens: int = 0
    execution_time_ms: int = 0
    
    # 用户情绪
    user_emotion: str = "neutral"  # neutral, positive, negative, angry
    
    def add_trace(self, node_name: str, input_data: Any = None, output_data: Any = None, duration_ms: int = 0):
        """添加执行轨迹"""
        self.trace.append({
            "node": node_name,
            "input": input_data,
            "output": output_data,
            "duration_ms": duration_ms,
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        })
    
    def add_tool_call(self, tool_name: str, arguments: Dict[str, Any], result: Any = None, success: bool = True, error_message: Optional[str] = None):
        """添加工具调用记录"""
        self.tool_calls.append(ToolCall(
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            success=success,
            error_message=error_message,
        ))
    
    def get_last_tool_result(self, tool_name: str) -> Optional[Any]:
        """获取最后一个指定工具的调用结果"""
        for tool_call in reversed(self.tool_calls):
            if tool_call.tool_name == tool_name and tool_call.success:
                return tool_call.result
        return None


# 意图类型定义
class IntentType:
    QUERY_ORDER = "query_order"
    REFUND = "refund"
    COMPLAINT = "complaint"
    TECHNICAL = "technical"
    PROMOTION = "promotion"
    HUMAN = "human"
    GENERAL = "general"
    UNKNOWN = "unknown"


# Agent 节点名称
class AgentNode:
    START = "start"
    INTENT_RECOGNITION = "intent_recognition"
    CLARIFICATION = "clarification"
    RAG_RETRIEVAL = "rag_retrieval"
    TOOL_EXECUTION = "tool_execution"
    RESULT_VERIFICATION = "result_verification"
    RESPONSE_GENERATION = "response_generation"
    HUMAN_HANDOFF = "human_handoff"
    END = "end"
