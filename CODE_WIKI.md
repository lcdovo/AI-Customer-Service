# Code Wiki - 企业智能客服与工单自动处理系统

> 版本: v1.0.3 | 最后更新: 2026-08-16

---

## 目录

- [1. 项目架构概述](#1-项目架构概述)
- [2. 核心模块详解](#2-核心模块详解)
  - [2.1 Agent 模块](#21-agent-模块)
  - [2.2 业务服务模块](#22-业务服务模块)
  - [2.3 API 路由模块](#23-api-路由模块)
  - [2.4 数据模型模块](#24-数据模型模块)
  - [2.5 工具与配置模块](#25-工具与配置模块)
- [3. 关键类与函数参考](#3-关键类与函数参考)
- [4. 数据流与依赖关系](#4-数据流与依赖关系)
- [5. 扩展与自定义指南](#5-扩展与自定义指南)
- [6. 配置说明](#6-配置说明)
- [7. 测试与调试](#7-测试与调试)

---

## 1. 项目架构概述

### 1.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          客户端层                                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                              │
│  │login.html│  │user.html │  │admin.html│                              │
│  └──────────┘  └──────────┘  └──────────┘                              │
├─────────────────────────────────────────────────────────────────────────┤
│                          API 网关层 (FastAPI)                             │
│  main.py → 路由注册 → 中间件(追踪/CORS/异常) → 静态文件服务               │
├─────────────────────────────────────────────────────────────────────────┤
│                          Agent 智能体层                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 │
│  │ graph.py     │  │ intent.py    │  │ state.py     │                 │
│  │ (状态机编排)  │  │ (意图识别)    │  │ (状态定义)    │                 │
│  └──────────────┘  └──────────────┘  └──────────────┘                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 │
│  │ tools.py     │  │ retrieval.py │  │ validation.py│                 │
│  │ (8个工具)    │  │ (混合检索)    │  │ (三层校验)    │                 │
│  └──────────────┘  └──────────────┘  └──────────────┘                 │
├─────────────────────────────────────────────────────────────────────────┤
│                          业务服务层 (Services)                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 │
│  │llm_service   │  │embedding_svc │  │knowledge_base│                 │
│  │(LLM多模型)   │  │(向量化)      │  │(知识库)      │                 │
│  └──────────────┘  └──────────────┘  └──────────────┘                 │
│  ┌──────────────┐  ┌──────────────┐                                   │
│  │collaboration │  │evaluation    │                                   │
│  │(协作转人工)  │  │(评价系统)    │                                   │
│  └──────────────┘  └──────────────┘                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                          数据存储层 (Storage)                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 │
│  │ MySQL/SQLite │  │    Redis     │  │ Milvus 向量库│                 │
│  └──────────────┘  └──────────────┘  └──────────────┘                 │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 技术栈

| 类别 | 技术 | 说明 |
|------|------|------|
| 语言 | Python 3.11+ | 主开发语言 |
| Web框架 | FastAPI | 异步API服务 |
| 数据库 | SQLAlchemy + aiomysql | 异步ORM |
| 向量检索 | Milvus / 内存模拟 | 向量数据库 |
| 缓存 | Redis | 会话缓存、限流 |
| 大模型 | DashScope / Mock | 支持降级 |
| Embedding | text-embedding-v3 | 1024维向量 |
| 前端 | 原生HTML/CSS/JS | 轻量无框架 |
| 容器化 | Docker Compose | 基础设施 |

### 1.3 目录结构

```
AI Customer/
├── app/                              # 后端应用
│   ├── agent/                        # Agent智能体模块
│   │   ├── graph.py                  # 状态机编排核心
│   │   ├── intent.py                 # 意图识别引擎
│   │   ├── state.py                  # Agent状态定义
│   │   ├── tools.py                  # 工具集(Function Calling)
│   │   ├── retrieval.py              # 混合检索引擎
│   │   ├── validation.py             # 结果三层校验
│   │   └── memory.py                 # 会话记忆管理
│   ├── config/                       # 配置模块
│   │   └── config.py                 # 全局配置(Settings)
│   ├── models/                       # 数据模型
│   │   └── models.py                 # SQLAlchemy ORM模型
│   ├── routers/                      # API路由
│   │   ├── chat.py                   # 对话接口
│   │   ├── knowledge.py              # 知识库接口
│   │   ├── tickets.py                # 工单接口
│   │   ├── users.py                  # 用户接口
│   │   ├── sessions.py               # 会话接口
│   │   ├── analytics.py              # 数据分析接口
│   │   ├── feedback.py               # 反馈接口
│   │   └── __init__.py               # 路由注册
│   ├── schemas/                      # Pydantic数据结构
│   │   └── schemas.py                # 请求/响应模型
│   ├── services/                     # 业务服务
│   │   ├── llm_service.py            # LLM调用服务
│   │   ├── embedding_service.py      # 向量化服务
│   │   ├── knowledge_base.py         # 知识库管理
│   │   ├── collaboration.py          # 协作/转人工服务
│   │   └── evaluation.py             # 评价系统
│   ├── utils/                        # 工具函数
│   │   ├── database.py               # 数据库连接
│   │   ├── milvus_client.py          # Milvus客户端
│   │   └── tracking.py               # 链路追踪
│   ├── main.py                       # 应用入口
│   └── verify.py                     # 验证脚本
├── static/                           # 前端静态文件
│   ├── css/style.css                 # 样式表
│   ├── js/app.js                     # 管理员后台逻辑
│   ├── login.html                    # 登录页
│   ├── user.html                     # 用户对话页
│   ├── admin.html                    # 管理员后台
│   └── index.html                    # 首页
├── .env                              # 环境配置
├── .env.example                      # 环境配置示例
├── requirements.txt                  # Python依赖
├── Dockerfile                        # Docker配置
├── docker-compose.yml                # 容器编排
├── start.bat / stop.bat              # Windows启动脚本
├── README.md                         # 项目说明
└── CODE_WIKI.md                      # 本文档
```

---

## 2. 核心模块详解

### 2.1 Agent 模块

#### 2.1.1 AgentGraph (graph.py)

Agent状态机核心编排器，实现类似LangGraph的节点式Agent编排。

**类定义：**
```python
class AgentGraph:
    """Agent 状态机 - 核心编排器"""
    
    def __init__(self):
        # 初始化LLM服务、意图识别器、混合检索引擎、校验器
        ...
    
    async def run_stream(self, state: AgentState) -> AsyncGenerator:
        """流式执行Agent状态机"""
        # 逐步产出事件供WebSocket/SSE推送
        ...
    
    async def run(self, state: AgentState) -> AgentState:
        """同步执行Agent状态机"""
        ...
```

**状态机节点流转图：**
```
START
  │
  ▼
INTENT_RECOGNITION (意图识别)
  │
  ├── [需要澄清] → CLARIFICATION → RESPONSE_GENERATION → END
  │
  ├── query_order, refund, complaint → TOOL_EXECUTION → RESULT_VERIFICATION → RESPONSE_GENERATION → END
  │
  ├── technical, promotion → RAG_RETRIEVAL → RESPONSE_GENERATION → END
  │
  ├── human → HUMAN_HANDOFF → RESPONSE_GENERATION → END
  │
  └── general → RESPONSE_GENERATION → END
```

**节点说明：**

| 节点 | 函数 | 功能说明 |
|------|------|---------|
| `start` | `_node_start()` | 初始化，跳转到意图识别 |
| `intent_recognition` | `_node_intent_recognition()` | 识别用户意图 |
| `clarification` | `_node_clarification()` | 要求用户澄清意图 |
| `rag_retrieval` | `_node_rag_retrieval()` | 混合检索知识库 |
| `tool_execution` | `_node_tool_execution()` | 执行结构化工具 |
| `result_verification` | `_node_result_verification()` | 校验工具执行结果 |
| `response_generation` | `_node_response_generation()` | 生成最终回复 |
| `human_handoff` | `_node_human_handoff()` | 转接人工客服 |
| `end` | `_node_end()` | 结束状态机 |

**关键路由逻辑：**
```python
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
```

**LLM响应生成：**
```python
async def _generate_response_with_llm(self, state: AgentState) -> str:
    """使用LLM生成响应"""
    # 构建富上下文prompt（包含意图、工具结果、知识库内容）
    # 调用LLM服务
    # 返回生成的回复
    ...
```

#### 2.1.2 EnhancedIntentRecognizer (intent.py)

增强版意图识别器，采用多层识别策略。

**类定义：**
```python
class EnhancedIntentRecognizer:
    """增强版意图识别器"""
    
    def recognize(self, message: str, context: list, history_intent: str) -> IntentResult:
        """
        多层意图识别：
        1. 关键词匹配（高/中/低权重）
        2. 否定词检查
        3. 上下文推断
        4. 延续性判断
        """
        ...
```

**支持的意图类型：**

| 意图 | 关键词示例 | 路由节点 |
|------|-----------|---------|
| `query_order` | 订单号、物流、快递 | TOOL_EXECUTION |
| `refund` | 退款、退货、退换 | TOOL_EXECUTION |
| `complaint` | 投诉、差评、骗子 | TOOL_EXECUTION |
| `technical` | 怎么用、如何、安装 | RAG_RETRIEVAL |
| `promotion` | 优惠、活动、折扣 | RAG_RETRIEVAL |
| `human` | 人工、客服、转人工 | HUMAN_HANDOFF |
| `general` | 通用咨询 | RESPONSE_GENERATION |

**意图关键词配置示例：**
```python
INTENT_PATTERNS = {
    "query_order": {
        "high": ["订单号", "物流", "快递", "发货", "运单号", "配送"],
        "medium": ["订单", "查询", "跟踪", "到哪", "状态"],
        "low": ["查一下", "帮我看看", "我的单"],
    },
    # ... 其他意图配置
}
```

#### 2.1.3 AgentState (state.py)

Agent运行时状态定义，用于跨节点传递数据。

**类定义：**
```python
class AgentState(BaseModel):
    """Agent运行时状态"""
    
    # 基本信息
    session_id: str                    # 会话ID
    user_id: int                       # 用户ID
    user_message: str                  # 用户消息
    
    # 意图识别
    detected_intent: str               # 检测到的意图
    intent_confidence: float           # 置信度
    needs_clarification: bool          # 是否需要澄清
    
    # 对话历史
    messages: List[Dict]              # 消息历史
    conversation_summary: Optional[str]  # 会话摘要
    
    # Agent执行状态
    current_node: str                  # 当前节点
    tool_calls: List[ToolCall]         # 工具调用记录
    collected_info: Dict[str, Any]     # 已收集的信息
    pending_confirmations: List[str]   # 待确认项
    
    # 结果
    reply: str                         # 最终回复
    response_ready: bool               # 是否准备好响应
    need_human: bool                   # 是否需要人工
    human_reason: Optional[str]        # 转人工原因
    
    # 追踪
    trace: List[Dict]                  # 执行链路
    total_tokens: int                  # Token用量
    execution_time_ms: int             # 执行耗时
```

#### 2.1.4 Tool System (tools.py)

结构化工具系统，支持重试、超时、降级。

**工具基类：**
```python
class BaseTool:
    """工具基类"""
    name: str = ""
    description: str = ""
    parameters: List[Dict] = []
    max_retries: int = 3
    retry_delay_ms: int = 100
    timeout_ms: int = 5000
    
    async def execute_with_retry(self, **kwargs) -> ToolExecutionResult:
        """带重试的执行"""
        ...
    
    async def execute(self, **kwargs) -> Dict:
        """执行具体逻辑（子类实现）"""
        raise NotImplementedError
```

**8个内置工具：**

| 工具名 | 类名 | 功能 | 触发意图 |
|--------|------|------|---------|
| `query_order` | QueryOrderTool | 查询订单状态与物流 | query_order |
| `create_ticket` | CreateTicketTool | 创建客服工单 | complaint |
| `apply_refund` | ApplyRefundTool | 退换货申请 | refund |
| `search_kb` | SearchKBTool | 知识库检索 | (独立调用) |
| `escalate_to_human` | EscalateToHumanTool | 转接人工客服 | human |
| `send_notification` | SendNotificationTool | 发送通知 | (系统调用) |
| `update_ticket_status` | UpdateTicketStatusTool | 更新工单状态 | (系统调用) |
| `get_user_history` | GetUserHistoryTool | 获取用户历史 | (辅助调用) |

**工具注册表：**
```python
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
    """根据名称获取工具"""
    return TOOL_REGISTRY.get(name)
```

#### 2.1.5 HybridRetriever (retrieval.py)

混合检索引擎，融合多种检索策略。

**类结构：**
```python
class BM25Retriever:
    """BM25关键词检索器"""
    def search(self, query: str, top_k: int) -> List[Dict]:
        # 基于TF-IDF的关键词匹配
        ...

class VectorRetriever:
    """向量检索器"""
    def search(self, query: str, top_k: int) -> List[Dict]:
        # 优先使用Milvus，降级到内存模拟
        ...

class Reranker:
    """重排序器"""
    def rerank(self, query: str, candidates: List, top_k: int) -> List:
        # 基于规则的Rerank
        ...

class HybridRetriever:
    """混合检索引擎"""
    def search(self, query: str, top_k: int, filters: Dict) -> Dict:
        # BM25 + 向量 + Reranker
        ...
```

**检索流程：**
```
用户查询
  │
  ├── BM25Retriever.search() → 关键词匹配结果
  │
  ├── VectorRetriever.search() → 向量相似度结果
  │
  ├── _merge_results() → 分数融合
  │
  └── Reranker.rerank() → 重排序
  │
  └── 返回 Top-K 结果
```

#### 2.1.6 ResponseValidator (validation.py)

结果三层校验机制。

**类结构：**
```python
class FactValidator:
    """事实校验器 - 检查回答与工具结果的一致性"""
    def validate(self, response: str, tool_results: List, user_query: str) -> Tuple[float, List]:
        ...

class SafetyValidator:
    """安全校验器 - 检查敏感内容和安全风险"""
    SENSITIVE_WORDS = [("自杀", "危险内容"), ...]
    INJECTION_PATTERNS = [r"(忽略|忽视)...", ...]
    def validate(self, response: str, user_query: str) -> Tuple[float, List]:
        ...

class CompletenessValidator:
    """完整性校验器 - 检查是否回答了用户问题"""
    def validate(self, response: str, user_query: str, intent: str) -> Tuple[float, List]:
        ...

class ResponseValidator:
    """响应校验器 - 整合三层校验"""
    FACT_THRESHOLD = 0.6
    SAFETY_THRESHOLD = 0.8
    COMPLETENESS_THRESHOLD = 0.5
    
    def validate(self, response: str, user_query: str, intent: str, tool_results: List) -> ValidationResult:
        ...
```

---

### 2.2 业务服务模块

#### 2.2.1 LLMService (llm_service.py)

LLM调用服务，支持多模型切换与熔断降级。

**类结构：**
```python
class CircuitBreaker:
    """熔断器 - 防止故障模型被反复调用"""
    def can_execute(self, model_name: str) -> bool
    def record_failure(self, model_name: str)
    def record_success(self, model_name: str)
    def reset(self, model_name: str)

class LLMService:
    """LLM服务 - 支持多模型降级"""
    MAX_RETRIES = 2
    RETRY_DELAY = 1.0
    TIMEOUT = 30.0
    
    async def chat(self, user_id: int, session_id: str, message: str, context: list) -> Tuple[str, str, int]:
        """主调用入口，自动降级"""
        # 1. 检测意图
        # 2. 依次尝试各模型
        # 3. 熔断保护
        # 4. 最终降级到Mock回复
        ...
    
    def _get_mock_reply(self, intent: str, message: str) -> str:
        """Mock回复（离线模式）"""
        ...
```

**模型降级策略：**
```
主模型(真实API) 
  │ 失败/熔断
  ▼
备用模型(可选)
  │ 失败/熔断
  ▼
本地Mock回复
```

#### 2.2.2 KnowledgeBaseService (knowledge_base.py)

知识库服务，管理文档的入库和检索。

**类结构：**
```python
class DocumentChunker:
    """文档分块器"""
    def __init__(self, chunk_size: int, chunk_overlap: int, split_pattern: str):
        ...
    def chunk_document(self, content: str, metadata: Dict) -> List[Dict]:
        """支持 sentence/paragraph/fixed 三种分块策略"""
        ...

class KnowledgeBaseService:
    """知识库服务"""
    def add_document(self, title: str, content: str, category: str, keywords: List) -> Dict:
        """添加文档：分块→向量化→存储"""
        ...
    def search(self, query: str, top_k: int, similarity_threshold: float) -> Dict:
        """检索：向量化查询→Milvus/内存搜索→Rerank"""
        ...
    def delete_document(self, document_id: str) -> bool:
        """删除文档"""
        ...
    def clear_all(self) -> Dict:
        """清空知识库"""
        ...
    def get_stats(self) -> Dict:
        """获取统计信息"""
        ...
```

#### 2.2.3 EmbeddingService (embedding_service.py)

向量化服务，支持真实API和本地模拟。

**功能：**
- 将文本编码为1024维向量
- 支持DashScope text-embedding-v3 API
- API不可用时降级到本地哈希向量

#### 2.2.4 CollaborationService (collaboration.py)

协作服务，处理转人工请求。

**功能：**
- 创建转人工请求
- 优先级分配（normal/urgent）
- 客服自动分配
- SLA计算

#### 2.2.5 EvaluationService (evaluation.py)

评价系统，评估对话质量。

**功能：**
- 准确性评估
- 完整性评估
- 安全性评估
- 低分自动标记

---

### 2.3 API 路由模块

#### 2.3.1 对话接口 (chat.py)

**路由前缀：** `/api/v1/chat`

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/sessions` | 创建新会话 |
| PATCH | `/sessions/{id}/close` | 关闭会话 |
| DELETE | `/sessions/{id}` | 删除会话 |
| GET | `/sessions/{user_id}` | 获取用户会话列表 |
| POST | `/send` | 发送消息（同步） |
| GET | `/history/{session_id}` | 获取对话历史 |
| GET | `/tools` | 获取可用工具列表 |
| GET | `/intents` | 获取支持的意图类型 |
| WS | `/stream` | WebSocket流式对话 |

**发送消息流程：**
```python
@router.post("/send")
async def send_message(chat_data: ChatRequest, db: AsyncSession):
    # 1. 获取/创建会话
    # 2. 保存用户消息
    # 3. 加载历史上下文
    # 4. 运行Agent状态机
    # 5. 保存Agent执行轨迹
    # 6. 保存助手回复
    # 7. 更新会话状态
    # 8. 返回结果
    ...
```

**WebSocket流式对话：**
```python
@router.websocket("/stream")
async def websocket_chat_stream(websocket: WebSocket):
    # 支持实时事件推送：
    # - stream_start / stream_end
    # - intent / rag_result
    # - tool_call_start / tool_call_complete
    # - token (逐字输出)
    # - validation / handoff
    # - done
    ...
```

#### 2.3.2 知识库接口 (knowledge.py)

**路由前缀：** `/api/v1/knowledge`

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/documents` | 导入文档 |
| GET | `/documents` | 获取文档列表 |
| DELETE | `/documents/{id}` | 删除文档 |
| POST | `/documents/seed` | 导入种子文档 |
| GET | `/stats` | 获取知识库统计 |
| POST | `/rag-query` | RAG问答 |
| POST | `/search` | 关键词搜索 |

#### 2.3.3 工单接口 (tickets.py)

**路由前缀：** `/api/v1/tickets`

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/` | 获取工单列表 |
| GET | `/{id}` | 获取工单详情 |
| PATCH | `/{id}` | 更新工单状态 |
| DELETE | `/{id}` | 删除工单 |
| POST | `/{id}/assign` | 分配处理人 |

#### 2.3.4 用户接口 (users.py)

**路由前缀：** `/api/v1/users`

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/login` | 用户登录 |
| GET | `/{id}` | 获取用户信息 |
| PATCH | `/{id}` | 更新用户信息 |
| GET | `/{id}/stats` | 获取用户统计 |

---

### 2.4 数据模型模块

#### 2.4.1 核心模型 (models.py)

**User 模型：**
```python
class User(Base):
    __tablename__ = "users"
    id: int                    # 主键
    username: str              # 用户名(唯一)
    nickname: str              # 昵称
    level: UserLevel           # 用户等级(normal/vip/enterprise)
    avatar_url: str            # 头像URL
    tags: JSON                 # 标签列表
    status: bool               # 状态
    created_at / updated_at    # 时间戳
```

**Session 模型：**
```python
class Session(Base):
    __tablename__ = "sessions"
    id: str                    # 会话ID(UUID)
    user_id: int               # 用户ID(FK)
    status: SessionStatus      # 状态(active/closed/pending)
    csat_score: int            # 满意度评分
    message_count: int         # 消息数量
    last_intent: str           # 最后意图
    summary: Text              # 会话摘要
    created_at / updated_at / closed_at
```

**Message 模型：**
```python
class Message(Base):
    __tablename__ = "messages"
    id: int
    session_id: str            # 会话ID(FK)
    role: MessageRole          # 角色(user/assistant/system/tool)
    content: Text              # 消息内容
    token_count: int           # Token用量
    response_time_ms: int      # 响应耗时
    tool_calls: JSON           # 工具调用记录
    created_at
```

**Ticket 模型：**
```python
class Ticket(Base):
    __tablename__ = "tickets"
    id: str                    # 工单ID(UUID)
    user_id: int
    category: str              # 分类
    status: TicketStatus       # 状态(pending/processing/resolved/closed/escalated)
    priority: TicketPriority   # 优先级(low/medium/high/urgent)
    content: Text              # 工单内容
    assigned_to: str           # 处理人
    sla_deadline: DateTime     # SLA截止时间
    created_at / updated_at / resolved_at
```

**AgentTrace 模型：**
```python
class AgentTrace(Base):
    __tablename__ = "agent_traces"
    id: int
    trace_id: str              # 追踪ID(唯一)
    session_id: str
    intent: str
    node_name: str             # 节点名称
    node_order: int            # 节点顺序
    input_data / output_data   # 输入输出(JSON)
    tool_calls: JSON
    duration_ms: int           # 耗时
    success: bool
    error_message: Text
    created_at
```

**EvaluationResult 模型：**
```python
class EvaluationResult(Base):
    __tablename__ = "evaluation_results"
    id: int
    session_id: str
    sample_id: str
    accuracy_score / completeness_score / safety_score
    overall_score: int
    is_low_score: bool
    failure_reason: str
    processed: bool
    created_at
```

#### 2.4.2 实体关系图

```
User (1) ──── (N) Session
                    │
                    └── (N) Message
                    
User (1) ──── (N) Ticket

Session (1) ──── (N) AgentTrace

Session (1) ──── (N) EvaluationResult
```

---

### 2.5 工具与配置模块

#### 2.5.1 全局配置 (config.py)

```python
class Settings(BaseSettings):
    """全局配置 - 支持.env文件覆盖"""
    
    # 应用配置
    APP_NAME: str = "智能客服系统"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # 数据库配置
    MYSQL_HOST/PORT/USER/PASSWORD/DATABASE
    DATABASE_URL_OVERRIDE: str = ""  # 覆盖数据库URL(SQLite)
    
    # Redis配置
    REDIS_HOST/PORT/PASSWORD/DB
    
    # LLM配置
    LLM_API_BASE/API_KEY/MODEL
    
    # Milvus配置
    MILVUS_HOST/PORT
    USE_MILVUS: bool = False
    
    # Embedding配置
    EMBEDDING_API_BASE/API_KEY/MODEL/DIM
    
    # RAG配置
    COLLECTION_NAME: str
    RAG_TOP_K: int = 3
    RAG_SIMILARITY_THRESHOLD: float = 0.3
    RAG_BM25_WEIGHT/VECTOR_WEIGHT
    RAG_USE_RERANKER: bool = True
    
    # 文档分块配置
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50
    CHUNK_SPLIT_PATTERN: str = "sentence"
    
    @property
    def DATABASE_URL(self) -> str:
        # 优先使用DATABASE_URL_OVERRIDE
        ...
```

#### 2.5.2 数据库连接 (database.py)

```python
# 异步会话管理
async_session = async_sessionmaker(...)

async def get_db():
    """FastAPI依赖注入用"""
    ...

def init_db():
    # 初始化数据库表结构
    ...
```

#### 2.5.3 Milvus客户端 (milvus_client.py)

```python
class MilvusClient:
    """Milvus向量数据库客户端"""
    def connect(self) -> bool
    def insert(self, documents: List, vectors: List)
    def search(self, query_embedding: List, top_k: int, score_threshold: float) -> List
    def delete(self, ids: List)
    def count(self) -> int
    def health_check(self) -> Tuple[bool, str]
    def drop_collection()
```

#### 2.5.4 链路追踪 (tracking.py)

```python
class StructuredLogger:
    """结构化日志记录器"""
    def log_request(trace_id, method, path, detail)
    def log_agent(trace_id, node, intent, session_id, detail)
    def log_error(trace_id, error_type, error_message, method, path)

def generate_trace_id() -> str:
    """生成唯一追踪ID"""
```

---

## 3. 关键类与函数参考

### 3.1 AgentGraph 关键方法

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `run_stream()` | `state: AgentState` | `AsyncGenerator[Dict]` | 流式执行，产出事件序列 |
| `run()` | `state: AgentState` | `AgentState` | 同步执行，返回最终状态 |
| `_route_by_intent()` | `intent: str` | `str` (节点名) | 根据意图路由到对应节点 |
| `_build_llm_prompt()` | `state: AgentState` | `str` | 构建LLM的富上下文prompt |
| `_generate_response_with_llm()` | `state: AgentState` | `str` | 调用LLM生成响应 |
| `_select_tools_for_intent()` | `intent: str, collected_info: Dict` | `List[tuple]` | 根据意图选择工具 |

### 3.2 EnhancedIntentRecognizer 关键方法

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `recognize()` | `message, context, history_intent` | `IntentResult` | 多层意图识别主入口 |
| `_keyword_matching()` | `message: str` | `IntentResult` | 关键词匹配 |
| `get_clarification_question()` | `intent: str` | `str` | 获取澄清问题 |

### 3.3 BaseTool 关键方法

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `execute_with_retry()` | `**kwargs` | `ToolExecutionResult` | 带重试的执行 |
| `validate_params()` | `**kwargs` | `Tuple[bool, List[str]]` | 参数验证 |

### 3.4 LLMService 关键方法

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `chat()` | `user_id, session_id, message, context` | `Tuple[str, str, int]` | 主调用入口 |
| `detect_intent()` | `message: str` | `str` | 基于关键词的意图检测 |

### 3.5 KnowledgeBaseService 关键方法

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `add_document()` | `title, content, category, keywords` | `Dict` | 添加文档 |
| `search()` | `query, top_k, threshold` | `Dict` | 检索 |
| `delete_document()` | `document_id: str` | `bool` | 删除文档 |
| `get_stats()` | 无 | `Dict` | 获取统计 |

---

## 4. 数据流与依赖关系

### 4.1 对话处理数据流

```
用户发送消息
    │
    ▼
API路由接收 (chat.py)
    │
    ├── 获取/创建Session
    ├── 保存用户Message
    │
    ▼
AgentGraph.run()
    │
    ├── 加载历史上下文 (session_manager)
    │
    ▼
INTENT_RECOGNITION
    │ EnhancedIntentRecognizer.recognize()
    │
    ▼
ROUTE_BY_INTENT
    │
    ├── [需要澄清] → CLARIFICATION
    │     └── 生成澄清问题
    │
    ├── [query_order/refund/complaint] → TOOL_EXECUTION
    │     ├── _extract_info_from_message() 提取订单号等
    │     ├── _select_tools_for_intent() 选择工具
    │     └── tool.execute_with_retry() 执行
    │
    ├── [technical/promotion] → RAG_RETRIEVAL
    │     └── HybridRetriever.search() 混合检索
    │
    ├── [human] → HUMAN_HANDOFF
    │     └── EscalateToHumanTool.execute()
    │
    └── [general] → RESPONSE_GENERATION
          └── 直接生成回复
    │
    ▼
RESULT_VERIFICATION (仅工具执行路径)
    │ ResponseValidator.validate()
    │ ├── FactValidator 事实校验
    │ ├── SafetyValidator 安全校验
    │ └── CompletenessValidator 完整性校验
    │
    ├── [校验通过] → RESPONSE_GENERATION
    └── [校验失败] → 重新生成或转人工
    │
    ▼
RESPONSE_GENERATION
    │
    ├── [有LLM] → llm_service.chat()
    │     └── _build_llm_prompt() 构建富上下文
    │
    └── [无LLM] → _generate_response()
          └── 基于工具结果和知识库生成模板回复
    │
    ▼
END
    │
    ├── 保存AgentTrace (执行轨迹)
    ├── 保存Assistant Message
    ├── 更新Session状态
    └── 返回响应给用户
```

### 4.2 依赖关系图

```
app/main.py
    │
    ├── app/routers/__init__.py
    │   ├── chat.py → app/agent/graph.py
    │   ├── knowledge.py → app/services/knowledge_base.py
    │   ├── tickets.py → models.py
    │   ├── users.py → models.py
    │   └── ...
    │
    ├── app/agent/graph.py
    │   ├── app/agent/intent.py
    │   ├── app/agent/state.py
    │   ├── app/agent/tools.py
    │   ├── app/agent/retrieval.py
    │   ├── app/agent/validation.py
    │   └── app/services/llm_service.py
    │
    ├── app/services/llm_service.py
    │   └── app/config/config.py
    │
    ├── app/services/knowledge_base.py
    │   ├── app/services/embedding_service.py
    │   └── app/utils/milvus_client.py
    │
    ├── app/utils/database.py
    │   └── app/models/models.py
    │
    └── static/* (前端静态文件)
```

### 4.3 模块职责说明

| 模块 | 职责 | 依赖 |
|------|------|------|
| `main.py` | 应用入口、路由注册、中间件 | routers, config |
| `graph.py` | Agent状态机编排 | intent, tools, retrieval, validation, llm_service |
| `intent.py` | 意图识别 | 无 |
| `tools.py` | 工具实现 | 无 |
| `retrieval.py` | 混合检索 | config, embedding_service, milvus_client |
| `validation.py` | 结果校验 | 无 |
| `llm_service.py` | LLM调用 | config |
| `knowledge_base.py` | 知识库管理 | config, embedding_service, milvus_client |
| `embedding_service.py` | 向量化 | config |
| `collaboration.py` | 协作转人工 | 无 |
| `evaluation.py` | 评价系统 | 无 |
| `models.py` | ORM模型 | 无 |
| `database.py` | 数据库连接 | config |
| `milvus_client.py` | Milvus客户端 | config |

---

## 5. 扩展与自定义指南

### 5.1 添加新工具

**步骤1：在 `tools.py` 中创建新工具类**
```python
class NewTool(BaseTool):
    """新工具"""
    name = "new_tool"
    description = "工具描述"
    parameters = [
        {"name": "param1", "type": "string", "description": "参数1", "required": True},
    ]
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        param1 = kwargs.get("param1", "")
        # 实现逻辑
        return {"success": True, "data": {"result": "..."}}
```

**步骤2：注册到工具注册表**
```python
TOOL_REGISTRY = {
    # ... 现有工具
    NewTool.name: NewTool(),
}
```

**步骤3：在 `graph.py` 中配置工具选择逻辑**
```python
def _select_tools_for_intent(self, intent, collected_info):
    tool_plan = []
    if intent == "new_intent":
        tool_plan.append(("new_tool", {"param1": "value"}))
    return tool_plan
```

### 5.2 添加新意图

**步骤1：在 `state.py` 中添加意图常量**
```python
class IntentType:
    NEW_INTENT = "new_intent"
```

**步骤2：在 `intent.py` 中添加关键词配置**
```python
INTENT_PATTERNS["new_intent"] = {
    "high": ["关键词1", "关键词2"],
    "medium": ["关键词3"],
    "low": [],
}
```

**步骤3：在 `graph.py` 中配置路由**
```python
def _route_by_intent(self, intent):
    intent_routes = {
        # ... 现有路由
        IntentType.NEW_INTENT: AgentNode.TOOL_EXECUTION,  # 或其他节点
    }
```

### 5.3 添加知识库文档

**方式1：API调用**
```bash
curl -X POST http://localhost:8000/api/v1/knowledge/documents \
  -H "Content-Type: application/json" \
  -d '{
    "title": "文档标题",
    "content": "文档内容",
    "category": "分类",
    "keywords": ["关键词1", "关键词2"]
  }'
```

**方式2：种子文档**
```bash
curl -X POST http://localhost:8000/api/v1/knowledge/documents/seed
```

### 5.4 配置LLM模型

**在 `.env` 文件中配置：**
```env
# 主要模型
LLM_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=your-api-key
LLM_MODEL=qwen-plus

# 备用模型（可选）
LLM_BACKUP_BASE=https://other-api.com/v1
LLM_BACKUP_KEY=backup-key
LLM_BACKUP_MODEL=gpt-4o-mini
```

### 5.5 切换数据库

**方式1：使用MySQL（默认）**
```env
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=123456
MYSQL_DATABASE=customer_service
# DATABASE_URL_OVERRIDE=  # 注释掉或留空
```

**方式2：使用SQLite（开发测试）**
```env
DATABASE_URL_OVERRIDE=sqlite+aiosqlite:///./customer_service.db
```

### 5.6 启用Milvus向量库

```env
USE_MILVUS=true
MILVUS_HOST=localhost
MILVUS_PORT=19531
EMBEDDING_DIM=1024
```

---

## 6. 配置说明

### 6.1 环境变量配置

复制 `.env.example` 为 `.env` 并修改：

```bash
cp .env.example .env
```

**必要配置项：**

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `HOST` | `0.0.0.0` | 服务监听地址 |
| `PORT` | `8000` | 服务端口 |
| `DATABASE_URL_OVERRIDE` | 空 | SQLite覆盖URL |
| `LLM_API_KEY` | 空 | LLM API Key |
| `LLM_API_BASE` | `http://localhost:8001` | LLM API地址 |
| `LLM_MODEL` | `gpt-4o-mini` | LLM模型名 |
| `USE_MILVUS` | `false` | 是否启用Milvus |
| `MILVUS_HOST` | `localhost` | Milvus地址 |
| `MILVUS_PORT` | `19530` | Milvus端口 |

**RAG相关配置：**

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `COLLECTION_NAME` | `customer_service_knowledge` | Milvus集合名 |
| `RAG_TOP_K` | `3` | 返回结果数 |
| `RAG_SIMILARITY_THRESHOLD` | `0.3` | 相似度阈值 |
| `RAG_BM25_WEIGHT` | `0.6` | BM25权重 |
| `RAG_VECTOR_WEIGHT` | `0.4` | 向量权重 |
| `RAG_USE_RERANKER` | `true` | 是否使用Rerank |

**文档分块配置：**

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `CHUNK_SIZE` | `500` | 分块大小 |
| `CHUNK_OVERLAP` | `50` | 分块重叠 |
| `CHUNK_SPLIT_PATTERN` | `sentence` | 分块策略 |

### 6.2 启动服务

**开发模式：**
```bash
# 使用启动脚本
start_server.bat

# 或手动启动
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**生产模式：**
```bash
# 使用Docker
docker-compose up -d

# 或使用启动脚本
start.bat
```

### 6.3 数据库初始化

```bash
# 首次启动会自动创建表
python -c "from app.utils.database import init_db; init_db()"

# 导入测试数据
python init_test_data.py
```

---

## 7. 测试与调试

### 7.1 API测试

```bash
# 健康检查
curl http://localhost:8000/health

# 用户登录
curl -X POST http://localhost:8000/api/v1/users/login \
  -H "Content-Type: application/json" \
  -d '{"username": "user001", "password": "password"}'

# 发送消息
curl -X POST http://localhost:8000/api/v1/chat/send \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "message": "查询我的订单",
    "session_id": "test-session-001"
  }'
```

### 7.2 测试脚本

项目提供了多个测试脚本：

| 脚本 | 测试内容 |
|------|---------|
| `test_phase2.py` | Agent核心功能（意图识别、工具调用、状态机） |
| `test_phase3.py` | 增强功能（混合检索、校验、熔断） |
| `test_phase4.py` | 观测性与协作（追踪、评价、转人工） |
| `test_rag.py` | RAG功能测试 |
| `test_api_phase4.py` | API接口集成测试 |
| `init_test_data.py` | 初始化测试数据 |
| `init_test_db.py` | 初始化测试数据库 |

### 7.3 日志追踪

系统使用结构化日志，可通过以下方式查看：

```python
from app.utils.tracking import structured_logger

# 日志包含trace_id用于全链路追踪
structured_logger.log_request(trace_id, method, path, detail)
structured_logger.log_agent(trace_id, node, intent, session_id, detail)
structured_logger.log_error(trace_id, error_type, error_message, method, path)
```

### 7.4 常见问题排查

| 问题 | 排查方法 |
|------|---------|
| 数据库连接失败 | 检查`DATABASE_URL_OVERRIDE`配置 |
| LLM不响应 | 检查`LLM_API_KEY`是否为占位符 |
| Milvus连接失败 | 检查Docker容器是否运行，端口是否正确 |
| 意图识别不准确 | 调整`intent.py`中的关键词配置 |
| 工具执行失败 | 查看日志中的错误信息，检查重试次数 |

---

## 附录

### A. 配置文件模板 (.env.example)

```env
# 服务配置
HOST=0.0.0.0
PORT=8000
DEBUG=true

# 数据库配置
DATABASE_URL_OVERRIDE=
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=123456
MYSQL_DATABASE=customer_service

# Redis配置
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0

# LLM配置
LLM_API_BASE=http://localhost:8001
LLM_API_KEY=
LLM_MODEL=gpt-4o-mini

# Embedding配置
EMBEDDING_API_BASE=
EMBEDDING_API_KEY=
EMBEDDING_MODEL=
EMBEDDING_DIM=1024

# Milvus配置
MILVUS_HOST=localhost
MILVUS_PORT=19530
USE_MILVUS=false

# RAG配置
COLLECTION_NAME=customer_service_knowledge
RAG_TOP_K=3
RAG_SIMILARITY_THRESHOLD=0.3
RAG_BM25_WEIGHT=0.6
RAG_VECTOR_WEIGHT=0.4
RAG_USE_RERANKER=true

# 文档分块配置
CHUNK_SIZE=500
CHUNK_OVERLAP=50
CHUNK_SPLIT_PATTERN=sentence
```

### B. 项目版本历史

| 版本 | 说明 |
|------|------|
| v1.0.0 | 初始版本 |
| v1.0.1 | 脚本重构、功能修复 |
| v1.0.2 | 管理员后台、RAG功能、转人工流程完善 |
| v1.0.3 | 全面优化版本 |

---

> 本文档由 AI Customer 项目自动生成，如有问题请联系开发团队。
