# 🤖 企业智能客服与工单自动处理系统

> **定位**：成熟可落地的企业级 AI 客服系统，具备完整的 Agent 状态机、RAG 检索增强、人机协同、可观测性等核心能力。支持 Docker 一键部署与本地 SQLite 开发双模式。

## 目录

- [一、项目简介](#一项目简介)
- [二、技术架构](#二技术架构)
- [三、核心功能](#三核心功能)
- [四、技术栈](#四技术栈)
- [五、快速开始](#五快速开始)
- [六、配置说明](#六配置说明)
- [七、API 接口](#七api-接口)
- [八、项目结构](#八项目结构)
- [九、使用指南](#九使用指南)
- [十、常见问题](#十常见问题)

---

## 一、项目简介

本系统是一个**企业级智能客服与工单自动处理系统**，核心能力覆盖：

| 能力模块 | 说明 |
|---------|------|
| 🤖 **Agent 状态机** | 类 LangGraph 节点式编排，9 个核心节点支持条件分支、工具调用、多轮对话、流式输出，最大 15 轮迭代保护 |
| 🎯 **混合意图识别** | 关键词权重匹配（高/中/低三级）+ 否定词检测 + 上下文推断 + 延续性判断，支持 7 类核心意图（含 unknown 兜底），置信度归一化 |
| 🛠️ **8 个结构化工具** | 订单查询、工单创建、退换货申请、知识库检索、转人工、发送通知、工单状态更新、用户历史查询，统一重试/超时/追踪 |
| 📚 **RAG 混合检索** | BM25 关键词检索 + 向量语义检索 + Reranker 规则重排序，双路召回加权融合，支持 Milvus 向量库与内存自动降级 |
| ✅ **三层校验** | 事实校验、安全校验、完整性校验，保证回答质量，支持自动重生成（最多 2 次） |
| 🔄 **多级降级** | LLM 多模型 + 熔断器降级、Redis 内存降级、Milvus 内存降级、Embedding API → Mock 降级、MySQL → SQLite 降级 |
| 👥 **人机协同** | 自动检测转人工时机、4 类客服技能分配、SLA 时限管理、上下文完整传递、工单生命周期管理 |
| 📊 **可观测性** | 全链路追踪（Trace ID）、结构化日志、指标采集、告警体系、答案评价体系（CSAT） |

---

## 二、技术架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         前端层 (Web)                              │
│         login.html / user.html / admin.html                      │
├─────────────────────────────────────────────────────────────────┤
│                       API 网关 (FastAPI)                          │
│   鉴权 │ 限流 │ 路由 │ WebSocket 流式 │ CORS │ 异常处理          │
├──────────┬──────────┬──────────┬────────────────────────────────┤
│ Agent    │ 意图识别  │ 状态机    │          RAG 引擎               │
│ 编排器    │ (关键词)  │ (Graph)  │    BM25 + 向量 + Reranker        │
├──────────┴──────────┴──────────┴────────────────────────────────┤
│                       工具层 (Function Calling)                    │
│  查询订单 │ 创建工单 │ 退换货 │ 知识库 │ 转人工 │ 通知 │ 更新状态   │
├─────────────────────────────────────────────────────────────────┤
│                      服务层 (Services)                            │
│    LLM 服务 │ Embedding 服务 │ 知识库服务 │ 协作服务 │ 评价服务     │
├─────────────────────────────────────────────────────────────────┤
│                       数据层 (Storage)                            │
│     MySQL 8.0 / SQLite │ Redis 7 │ Milvus 2.5 (向量数据库)       │
├─────────────────────────────────────────────────────────────────┤
│                      可观测性层                                    │
│         全链路追踪 │ 结构化日志 │ 指标采集 │ 告警 │ 评价体系       │
└─────────────────────────────────────────────────────────────────┘
```

### Agent 状态机流程

```
用户输入
  │
  ▼
┌────────────┐    ┌──────────────┐
│ 意图识别    │───▶│ 需要澄清?     │───▶ 澄清追问 (clarification)
└────────────┘    └──────────────┘
  │ 明确意图
  ▼
┌────────────┐    ┌──────────────┐
│ 路由决策    │───▶│ RAG 检索路径  │ (technical / promotion)
│            │    └──────────────┘
│            │
│            ├──▶│ 工具执行路径   │ (query_order / refund / complaint)
│            │    └──────────────┘
│            │
│            └──▶│ 直接回复路径   │ (general)
│                 └──────────────┘
│
│            ┌──────────────┐
└──────────────▶ 转人工路径   │ (human / 连续失败)
               └──────────────┘

节点详情:
  start → intent_recognition → [clarification | rag_retrieval | tool_execution | response_generation | human_handoff] → result_verification → response_generation → end
```

### 意图路由映射

| 意图 | 路由目标 | 执行工具 |
|------|---------|---------|
| `query_order` | tool_execution | query_order |
| `refund` | tool_execution | apply_refund |
| `complaint` | tool_execution | create_ticket |
| `technical` | rag_retrieval | hybrid_search |
| `promotion` | rag_retrieval | hybrid_search |
| `human` | human_handoff | escalate_to_human |
| `general` | response_generation | (直接 LLM 回复) |

---

## 三、核心功能

### 3.1 混合意图识别

系统采用**多层识别策略**，确保意图识别的准确性与鲁棒性：

| 层级 | 方法 | 说明 |
|------|------|------|
| 第一层 | 关键词权重匹配 | 高权重(+2.0) / 中权重(+1.0) / 低权重(+0.3)，快速识别常见意图 |
| 第二层 | 否定词检测 | 检查关键词附近的否定词（如"不是退款"），置信度 × 0.5 |
| 第三层 | 上下文推断 | 基于历史对话中的工具调用结果推断意图 |
| 第四层 | 延续性判断 | 识别追问（如"好的"、"然后呢"），保持上下文意图 |

**支持的意图类型**：

| 意图类型 | 说明 | 典型触发词 |
|---------|------|-----------|
| `query_order` | 订单查询 | 订单号、物流、快递、发货、配送 |
| `refund` | 退换货 | 退款、退货、退换、退钱 |
| `complaint` | 投诉 | 投诉、差评、气愤、骗子 |
| `technical` | 技术咨询 | 怎么用、如何、安装、设置 |
| `promotion` | 活动咨询 | 优惠、活动、折扣、促销 |
| `human` | 转人工 | 人工、客服、转人工 |
| `general` | 通用咨询 | 其他所有问题 |

### 3.2 Agent 工具

系统实现了 **8 个结构化工具**，统一继承 `BaseTool` 基类，支持重试（最多 3 次，指数退避）、超时（5s）、参数校验、执行追踪：

| 工具名 | 中文 | 功能描述 |
|--------|------|---------|
| `query_order` | 订单查询 | 根据订单号查询订单状态、物流信息、订单金额，内置 4 条 Mock 订单数据 |
| `create_ticket` | 工单创建 | 创建客服工单，按分类自动分配处理专员，支持 4 级优先级与 SLA |
| `apply_refund` | 退换货申请 | 申请退换货，校验订单状态是否满足退换条件，生成退款单号与后续步骤 |
| `search_kb` | 知识库搜索 | 从 10 条内置知识库中检索相关问题答案，支持关键词匹配与评分排序 |
| `escalate_to_human` | 转人工客服 | 转接人工客服，支持 normal/urgent 优先级，自动分配在线客服 |
| `send_notification` | 发送通知 | 发送短信/邮件/站内信通知，支持多渠道 |
| `update_ticket_status` | 更新工单状态 | 更新工单处理状态（pending/processing/resolved/closed/escalated） |
| `get_user_history` | 用户历史记录 | 获取用户等级、历史订单、工单历史、偏好标签 |

### 3.3 RAG 混合检索引擎

**双路召回 + 融合 + 重排序**架构：

```
用户查询
  │
  ▼
┌────────────┐    ┌──────────────┐
│ BM25 检索   │    │ 向量检索      │
│ (关键词匹配) │    │ (语义匹配)    │
│ K=5*3=15   │    │ K=5*3=15     │
└────────────┘    └──────────────┘
  │                    │
  ▼                    ▼
┌──────────────────────────────┐
│       结果融合 (分数加权)       │
│   bm25_weight=0.5            │
│   vector_weight=0.5          │
└──────────────────────────────┘
  │
  ▼
┌──────────────┐
│ Reranker 重排 │
│ (规则打分)    │
└──────────────┘
  │
  ▼
  最终 Top-K 结果 (默认 5 条)
```

- **BM25 检索**：标准 BM25 算法（k1=1.5, b=0.75），支持中英文分词，擅长精确关键词匹配
- **向量检索**：支持 Milvus 向量数据库（端口 19530），不可用时自动降级到内存模式
- **Reranker**：基于规则的重排序，综合标题匹配、内容匹配、关键词重叠度、融合分数等
- **多路召回**：BM25 权重 0.5 + 向量权重 0.5，可通过 `.env` 配置
- **内置知识库**：15 条企业常见知识条目（退换货政策、退款流程、订单查询、会员权益、优惠券规则、促销活动、支付方式、发票开具、物流配送、账号安全、产品使用、质保维修、投诉处理、客服联系、企业采购等）

### 3.4 三层结果校验

三层校验机制确保回答质量：

| 校验层 | 说明 | 通过条件 |
|--------|------|---------|
| **事实校验** | 检查回答中的关键信息与工具返回结果的一致性（订单号、金额、状态等） | fact_score ≥ 0.6 |
| **安全校验** | 敏感词过滤、Prompt 注入检测、越权操作拦截、空回答检测 | safety_score ≥ 0.8 |
| **完整性校验** | 检查是否回答了用户的所有问题点、关键词重叠率、意图特定内容要求 | completeness_score ≥ 0.5 |

校验不通过时自动重生成（最多 2 次），连续不通过则转人工。

### 3.5 多级降级策略

| 故障场景 | 降级策略 |
|---------|---------|
| LLM API 超时/限流 | 熔断器保护 + 自动切换备用模型（backup）或 Mock 规则生成回复 |
| Milvus 不可用 | 降级为内存哈希向量检索 |
| Embedding API 不可用 | 使用本地哈希向量模拟（MockEmbedding） |
| Redis 不可用 | 跳过缓存功能，使用内存字典存储会话状态 |
| MySQL 连接失败 | 使用 SQLite 本地文件存储（通过 `DATABASE_URL_OVERRIDE`） |
| 工具调用连续失败（≥3次） | 终止自动处理，转人工并携带完整上下文 |
| 回答校验连续不通过（≥2次） | 自动转人工，附学校验分数与原因 |

### 3.6 人机协同

**转人工流程**：

1. **触发时机**：
   - 用户主动要求转人工（`human` 意图）
   - Agent 连续 3 次工具调用失败
   - 回答校验连续 2 次不通过
   - 用户高优先级投诉
   - 订单金额 > 500 且涉及退款/投诉

2. **上下文传递**：
   - 完整会话历史（最多 40 条，超过自动压缩摘要）
   - 已调用的工具结果与执行状态
   - 用户情绪分析与意图标签
   - 问题分类和处理建议

3. **客服分配**：
   - 4 名预置客服（客服主管 / 客服专员 / 技术支持 / 售后专员）
   - 根据技能标签自动分配对应组别的客服
   - 支持优先级（normal/high/urgent）与 SLA 时限管理
   - 客服负载均衡（每人最大 3-5 个并发会话）

---

## 四、技术栈

| 层级 | 技术 | 版本 | 用途 |
|------|------|------|------|
| 语言 | Python | 3.11+ | 主力开发语言 |
| Web 框架 | FastAPI | 0.115 | 异步 Web 服务 |
| ASGI 服务器 | Uvicorn | 0.30 | 生产级 ASGI 服务器 |
| ORM | SQLAlchemy | 2.0 | 异步数据库操作 |
| 关系数据库 | MySQL / SQLite | 8.0 / 3 | 用户/工单/会话数据 |
| 缓存 | Redis | 7 | 会话状态/缓存（可选） |
| 向量数据库 | Milvus | 2.5.6 | 向量存储与检索（可选） |
| 数据校验 | Pydantic | 2.9 | 请求/响应模型校验 |
| LLM 调用 | httpx | 0.27 | 异步 HTTP 客户端（支持 DashScope / OpenAI 兼容 API） |
| 向量客户端 | pymilvus | 2.5.6 | Milvus Python SDK |
| 配置管理 | pydantic-settings | 2.5 | 环境变量管理 |
| 环境变量 | python-dotenv | 1.0 | .env 文件加载 |
| 容器化 | Docker | - | 应用容器化 |
| 容器编排 | Docker Compose | V2（兼容 V1） | 多服务编排 |
| 前端 | HTML/CSS/JS | - | 原生前端页面 |

---

## 五、快速开始

### 方式一：Docker Compose 一键部署（推荐）

```bash
# 克隆项目
git clone <repository-url>
cd AI-Customer

# 一键启动所有服务
start.bat
# 或使用 Docker 命令：
docker compose up -d

# 查看服务状态
docker compose ps
```

启动完成后访问：
- 登录页面：`http://localhost:8000/`
- API 文档：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/health`
- Milvus 管理：`http://localhost:8080`（Attu）

### 方式二：本地开发模式（SQLite，无需 Docker）

```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 配置环境变量（复制模板）
cp .env.example .env
# 编辑 .env 文件，配置 API Key 等（可选）

# Windows 一键启动（自动配置 SQLite + 初始化数据库）
start_server.bat

# 或手动启动
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

> 本地开发模式使用 SQLite 数据库，无需 MySQL/Redis/Milvus。系统会自动降级所有可选组件。

### 预置账号

| 角色 | 用户名 | 密码 | 说明 |
|------|--------|------|------|
| 普通用户 | user001 | user001 | 普通等级 |
| VIP 用户 | user002 | user002 | VIP 等级 |
| 管理员 | admin | admin123 | 企业级权限 |

---

## 六、配置说明

### 6.1 环境变量配置

所有配置项在 `.env` 文件中设置（完整模板见 `.env.example`）：

```ini
# ========== 基础设置 ==========
APP_NAME=智能客服系统
APP_VERSION=1.0.0
DEBUG=true
HOST=0.0.0.0
PORT=8000

# ========== 数据库 ==========
# 方式1: MySQL (生产推荐)
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=123456
MYSQL_DATABASE=customer_service

# 方式2: SQLite (本地开发)
# DATABASE_URL_OVERRIDE=sqlite+aiosqlite:///./test.db

# ========== Redis (可选) ==========
# 未配置时系统使用内存存储
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0

# ========== LLM 对话模型 ==========
# 留空则使用内置规则生成模拟回复
LLM_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=sk-xxx
LLM_MODEL=qwen3.6-plus

# ========== Milvus 向量数据库 (可选) ==========
# USE_MILVUS=false 时系统使用内存向量检索
# Docker 模式下默认端口 19530，宿主机映射端口 19531
MILVUS_HOST=localhost
MILVUS_PORT=19530
USE_MILVUS=false

# ========== Embedding 向量模型 ==========
# 留空则使用本地哈希向量模拟
EMBEDDING_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_API_KEY=sk-xxx
EMBEDDING_MODEL=text-embedding-v3
EMBEDDING_DIM=1024

# ========== RAG 检索配置 ==========
COLLECTION_NAME=customer_service_knowledge
RAG_TOP_K=5
RAG_SIMILARITY_THRESHOLD=0.2
RAG_BM25_WEIGHT=0.5
RAG_VECTOR_WEIGHT=0.5
RAG_USE_RERANKER=true
RAG_SEARCH_TOP_K_MULTIPLIER=3

# ========== 文档分块配置 ==========
CHUNK_SIZE=500
CHUNK_OVERLAP=50
CHUNK_SPLIT_PATTERN=sentence
```

### 6.2 端口说明

| 端口 | 服务 | 说明 |
|------|------|------|
| 8000 | 应用 | FastAPI 服务端口 |
| 3306 | MySQL | 数据库端口 |
| 6379 | Redis | 缓存端口 |
| 19531 | Milvus | 宿主机访问端口（映射自容器 19530） |
| 19530 | Milvus | 容器内部 gRPC 端口 |
| 9091 | Milvus Health | Milvus 健康检查端口 |
| 8080 | Attu | Milvus 可视化管理界面 |
| 2380 | Etcd | Milvus 元数据存储 |
| 9002 | MinIO | Milvus 对象存储 |

### 6.3 Docker Compose 服务

```yaml
services:
  etcd:       # Milvus 元数据存储（健康检查）
  minio:      # Milvus 对象存储（健康检查）
  milvus:     # 向量数据库（健康检查）
  attu:       # Milvus 可视化管理界面
  mysql:      # 关系数据库（健康检查）
  redis:      # 缓存（健康检查）
  app:        # 应用服务（挂载 .env / static / templates）
```

### 6.4 启动脚本

| 脚本 | 说明 |
|------|------|
| `start.bat` | Docker 模式一键启动（支持 Compose V1/V2 自动检测） |
| `stop.bat` | Docker 模式一键停止（保留数据卷） |
| `restart.bat` | Docker 模式一键重启 |
| `status.bat` | 查看 Docker 服务运行状态 |
| `start_server.bat` | 本地开发模式启动（SQLite + 自动初始化） |
| `start_server.ps1` | PowerShell 版本的本地启动脚本 |

---

## 七、API 接口

### 7.1 对话接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/chat/send` | 发送消息（同步返回） |
| `WS` | `/api/v1/chat/stream` | WebSocket 实时流式对话 |
| `GET` | `/api/v1/chat/history/{session_id}` | 获取会话历史 |
| `GET` | `/api/v1/chat/tools` | 获取可用工具列表 |
| `GET` | `/api/v1/chat/intents` | 获取支持的意图类型 |

### 7.2 会话接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/chat/sessions` | 创建新会话 |
| `GET` | `/api/v1/chat/sessions/{user_id}` | 获取用户会话列表 |
| `PATCH` | `/api/v1/chat/sessions/{session_id}/close` | 关闭会话 |
| `DELETE` | `/api/v1/chat/sessions/{session_id}` | 删除会话（级联清理） |

### 7.3 用户接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/users/` | 创建用户 |
| `GET` | `/api/v1/users/` | 获取用户列表 |
| `GET` | `/api/v1/users/{id}` | 获取用户详情 |
| `POST` | `/api/v1/users/login` | 用户登录 |

### 7.4 工单接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/tickets` | 创建工单 |
| `GET` | `/api/v1/tickets` | 获取工单列表 |
| `GET` | `/api/v1/tickets/{id}` | 获取工单详情 |
| `PUT` | `/api/v1/tickets/{id}` | 更新工单状态 |
| `DELETE` | `/api/v1/tickets/{id}` | 删除工单 |

### 7.5 转人工接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/handoff` | 请求转人工 |
| `GET` | `/api/v1/handoff/requests` | 获取转人工请求列表 |
| `GET` | `/api/v1/agents` | 获取客服列表 |
| `GET` | `/api/v1/agents/{id}` | 获取客服详情 |

### 7.6 知识库接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/knowledge/upload` | 上传文档到知识库（支持 txt/md/json/csv） |
| `GET` | `/api/v1/knowledge/documents` | 获取文档列表 |
| `DELETE` | `/api/v1/knowledge/documents/{id}` | 删除文档 |
| `POST` | `/api/v1/knowledge/search` | 搜索知识库 |
| `POST` | `/api/v1/knowledge/rag-query` | RAG 问答 |
| `GET` | `/api/v1/knowledge/stats` | 获取知识库统计 |
| `GET` | `/api/v1/knowledge/health` | 知识库健康检查 |

### 7.7 分析与反馈

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/analytics/metrics` | 系统指标（含告警） |
| `GET` | `/api/v1/analytics/metrics/summary` | 指标摘要 |
| `GET` | `/api/v1/analytics/session` | 会话统计 |
| `POST` | `/api/v1/feedback/submit` | 提交反馈（like/dislike/CSAT） |
| `GET` | `/api/v1/feedback/stats` | 反馈统计 |

### 7.8 WebSocket 事件类型

通过 `/api/v1/chat/stream` 连接后，服务端推送以下事件：

| 事件类型 | 说明 |
|---------|------|
| `stream_start` | 对话开始 |
| `node_start` | 处理节点开始 |
| `node_complete` | 节点完成（含耗时与下一节点） |
| `intent` | 意图识别完成（含置信度） |
| `tool_call_start` | 工具调用开始 |
| `tool_call_complete` | 工具调用完成（含重试次数） |
| `rag_result` | 知识库检索完成（含结果数与最高分） |
| `validation` | 结果校验完成（含各项分数） |
| `handoff` | 触发转人工 |
| `token` | 流式回复文字片段 |
| `done` | 对话完成 |
| `stream_end` | 会话保存完成 |
| `error` | 发生错误 |

---

## 八、项目结构

```
AI-Customer/
├── app/                           # 核心代码
│   ├── agent/                     # Agent 智能体
│   │   ├── graph.py              #   状态机编排（核心大脑，9 个节点）
│   │   ├── intent.py             #   混合意图识别（关键词+否定词+上下文）
│   │   ├── tools.py              #   8 个结构化工具实现
│   │   ├── retrieval.py          #   混合检索引擎（BM25+向量+Reranker）
│   │   ├── validation.py         #   三层结果校验
│   │   ├── memory.py             #   多轮对话状态管理（Redis 降级）
│   │   └── state.py              #   AgentState / ToolCall / 节点定义
│   ├── services/                  # 业务服务
│   │   ├── llm_service.py        #   LLM 多模型服务（含熔断器）
│   │   ├── embedding_service.py  #   Embedding 向量化（API→Mock 降级）
│   │   ├── knowledge_base.py     #   知识库服务
│   │   ├── evaluation.py         #   评价体系（CSAT、低分池、A/B 测试）
│   │   └── collaboration.py      #   人机协作服务（客服管理+工单管理）
│   ├── routers/                   # API 路由
│   │   ├── chat.py               #   对话接口（同步+WebSocket 流式）
│   │   ├── sessions.py           #   会话接口
│   │   ├── tickets.py            #   工单接口
│   │   ├── knowledge.py          #   知识库接口
│   │   ├── analytics.py          #   分析接口
│   │   ├── feedback.py           #   反馈接口
│   │   └── users.py              #   用户接口
│   ├── models/                    # 数据模型 (SQLAlchemy ORM)
│   │   └── models.py             #   User/Session/Message/Ticket/KnowledgeDoc/AgentTrace/EvaluationResult
│   ├── schemas/                   # 数据校验 (Pydantic)
│   │   └── schemas.py            #   ChatRequest/ChatResponse/APIResponse 等
│   ├── utils/                     # 工具模块
│   │   ├── database.py           #   异步数据库管理（MySQL/SQLite 自动切换）
│   │   ├── milvus_client.py      #   Milvus 客户端封装
│   │   └── tracking.py           #   全链路追踪与告警
│   ├── config/                    # 配置管理
│   │   └── config.py             #   Settings 类（pydantic-settings）
│   ├── verify.py                  #   启动验证脚本
│   └── main.py                    #   FastAPI 应用入口
│
├── scripts/                       # 辅助脚本
│   ├── generate_test_docs.py     #   生成测试文档
│   ├── generate_extra_docs.py    #   生成额外测试文档
│   ├── import_docs.py            #   导入文档到知识库
│   ├── import_extra_docs.py      #   导入额外文档
│   ├── rag_benchmark.py          #   RAG 性能基准测试
│   └── rag_full_benchmark.py     #   RAG 全量基准测试
│
├── test_data/                     # 测试数据
│   ├── test_documents.json       #   测试文档
│   ├── extra_documents.json      #   额外测试文档
│   ├── test_qa_pairs.json        #   测试问答对
│   ├── rag_benchmark_report.json #   RAG 基准测试报告
│   └── rag_optimization_report.json # RAG 优化报告
│
├── static/                        # 前端静态文件
│   ├── css/style.css             #   样式表
│   ├── js/app.js                 #   管理员后台逻辑
│   ├── index.html                #   首页
│   ├── login.html                #   登录页
│   ├── user.html                 #   用户端页面
│   └── admin.html                #   管理员后台
│
├── Dockerfile                     # Docker 镜像定义
├── docker-compose.yml             # 服务编排配置（7 个服务）
├── requirements.txt               # Python 依赖
├── .env.example                   # 环境变量模板
├── .gitignore                     # Git 忽略规则
├── start.bat                      # Docker 模式一键启动
├── stop.bat                       # Docker 模式一键停止
├── restart.bat                    # Docker 模式一键重启
├── status.bat                     # 服务状态检查
├── start_server.bat               # 本地开发启动（SQLite）
├── start_server.ps1               # PowerShell 本地启动
├── init_test_data.py             # 初始化测试数据
├── init_test_db.py                # 初始化测试数据库
├── rag_test_results.json          # RAG 测试结果
├── test_rag.py                    # RAG 测试脚本
├── test_rag_optimization.py       # RAG 优化测试
├── test_phase2.py                 # 第二阶段测试
├── test_phase3.py                 # 第三阶段测试
├── test_phase4.py                 # 第四阶段测试
├── test_api_phase4.py             # Phase4 API 测试
└── README.md                      # 本文档
```

---

## 九、使用指南

### 9.1 用户端使用

1. 打开登录页面 `http://localhost:8000/`
2. 使用预置账号登录：
   - 用户名：`user001`
   - 密码：`user001`
3. 登录后自动创建新会话
4. 在对话框输入消息开始对话：
   - "我的订单 ORD20260801 到哪了" → 触发订单查询
   - "我想申请退款" → 触发退换货流程
   - "我要投诉" → 创建投诉工单
   - "转人工客服" → 转接人工

### 9.2 管理员后台

1. 使用管理员账号登录：
   - 用户名：`admin`
   - 密码：`admin123`
2. 功能模块：
   - **对话管理**：查看用户实时对话，手动回复
   - **工单管理**：查看/处理/分配工单
   - **转人工管理**：处理转人工请求
   - **知识库管理**：上传/删除文档
   - **数据看板**：查看系统指标与统计

### 9.3 API 测试

访问 `http://localhost:8000/docs` 使用 Swagger UI 测试所有 API。

Python 示例：

```python
import requests

# 发送消息对话
response = requests.post('http://localhost:8000/api/v1/chat/send', json={
    'user_id': 1,
    'message': '我的订单ORD20260801到哪了'
})

print(response.json())
```

### 9.4 WebSocket 实时对话

JavaScript 示例：

```javascript
const ws = new WebSocket('ws://localhost:8000/api/v1/chat/stream');

ws.onopen = () => {
  ws.send(JSON.stringify({
    user_id: 1,
    message: '我的订单ORD20260801到哪了'
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  switch (data.type) {
    case 'intent':
      console.log('识别意图:', data.intent, '置信度:', data.confidence);
      break;
    case 'tool_call_start':
      console.log('调用工具:', data.tool, data.args);
      break;
    case 'tool_call_complete':
      console.log('工具完成:', data.tool, '成功:', data.success);
      break;
    case 'token':
      console.log(data.content);  // 逐字输出
      break;
    case 'validation':
      console.log('校验结果:', data.passed, '总分:', data.overall_score);
      break;
    case 'handoff':
      console.log('转人工:', data.reason);
      break;
    case 'done':
      console.log('完成:', data.reply, '耗时:', data.execution_time_ms, 'ms');
      break;
  }
};
```

### 9.5 Docker 管理

```bash
# 启动所有服务
start.bat

# 查看服务状态
status.bat

# 查看实时日志
docker compose logs -f app

# 停止服务（保留数据）
stop.bat

# 完全清理（含数据卷）
docker compose down -v

# 重启服务
restart.bat
```

---

## 十、常见问题

### Q1: 启动失败，端口被占用？

```bash
# Windows: 查找占用端口的进程
netstat -ano | findstr :8000
# 杀掉进程
taskkill /F /PID <进程ID>

# 或修改配置
# 编辑 .env 中的 PORT 字段
# 编辑 docker-compose.yml 中的端口映射
```

### Q2: Milvus 启动失败？

Milvus 依赖 Etcd 和 MinIO，确保它们先启动：

```bash
docker compose logs milvus     # 查看 Milvus 日志
docker compose logs etcd       # 查看 Etcd 日志
docker compose logs minio      # 查看 MinIO 日志

# 或本地开发时直接禁用 Milvus
# 在 .env 中设置 USE_MILVUS=false
# 系统会自动降级到内存向量检索
```

### Q3: LLM 回复使用模拟模式？

当 `LLM_API_KEY` 为空或无效时，系统使用内置规则生成回复。配置真实 API 后会自动切换。

### Q4: Embedding 未配置？

未配置时使用本地哈希向量模拟（MockEmbedding），功能正常但检索效果一般。配置 `EMBEDDING_API_BASE` + `EMBEDDING_API_KEY` + `EMBEDDING_MODEL` 后可获得更准确的语义匹配。

### Q5: 如何切换数据库？

```ini
# MySQL 模式（生产推荐）
# 在 .env 中配置 MYSQL_HOST/PORT/USER/PASSWORD/DATABASE

# SQLite 模式（本地开发）
# 在 .env 中设置：
DATABASE_URL_OVERRIDE=sqlite+aiosqlite:///./test.db
# 或使用 start_server.bat 自动配置
```

### Q6: 如何重置数据？

```bash
# Docker 模式
docker compose down -v    # 停止并删除所有数据卷
docker compose up -d      # 重新启动

# 本地模式
# 删除 test.db / customer_service.db 文件
```

### Q7: 如何查看日志？

```bash
# Docker 模式
docker compose logs -f app      # 应用日志
docker compose logs -f mysql    # MySQL 日志
docker compose logs -f milvus   # Milvus 日志

# 本地模式
# 查看控制台输出或配置日志文件
```

### Q8: 知识库如何扩展？

1. 通过 API 上传文档：`POST /api/v1/knowledge/upload`（支持 txt/md/json/csv）
2. 上传的文档会自动进行分块和向量化
3. 支持通过 `POST /api/v1/knowledge/search` 搜索
4. 支持通过 `POST /api/v1/knowledge/rag-query` 进行 RAG 问答

### Q9: 如何自定义意图？

编辑 `app/agent/intent.py` 中的 `INTENT_PATTERNS` 字典，添加新的意图类型和关键词。同时在 `app/agent/state.py` 的 `IntentType` 类中添加对应常量。

### Q10: 熔断器如何工作？

LLM 服务内置熔断器（CircuitBreaker），当模型连续失败 5 次后自动熔断，300 秒后尝试恢复。支持主模型 → 备用模型 → Mock 回复三级降级。

---

## 附录：版本历史

| 版本 | 说明 |
|------|------|
| v1.0.3 | 管理员后台完善、RAG 功能增强、转人工流程优化 |
| v1.0.2 | 转人工流程修复、工具名中文映射、前端交互优化 |
| v1.0.1 | RAG 配置完善、启动脚本优化、测试修复 |
| v1.0.0 | 初始稳定版本，完整功能实现 |

---

**🎉 开始使用吧！**