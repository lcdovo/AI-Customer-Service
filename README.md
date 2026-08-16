# 🤖 企业智能客服与工单自动处理系统

> **定位**：成熟可落地的企业级 AI 客服系统，具备完整的 Agent 状态机、RAG 检索增强、人机协同、可观测性等核心能力。

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
| 🤖 **Agent 状态机** | 类 LangGraph 节点式编排，支持条件分支、工具调用、多轮对话、流式输出 |
| 🎯 **意图识别** | 多层识别策略（关键词匹配 → 否定词检测 → 上下文推断 → 延续性判断），支持 7 类意图 |
| 🛠️ **8 个工具** | 订单查询、工单创建、退换货申请、知识库检索、转人工、发送通知、工单状态更新、用户历史查询 |
| 📚 **RAG 知识库** | 混合检索引擎（BM25 + 向量检索 + Reranker 重排序），支持 Milvus 向量库与内存降级 |
| ✅ **三层校验** | 事实校验、安全校验、完整性校验，保证回答质量 |
| 🔄 **降级策略** | LLM 多模型降级、Redis 内存降级、Milvus 内存降级 |
| 👥 **人机协同** | 自动检测转人工时机、客服智能分配、工单生命周期管理、上下文传递 |
| 📊 **可观测性** | 全链路追踪、结构化日志、指标采集、评价体系 |

---

## 二、技术架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         前端层 (Web)                              │
│              login.html / user.html / admin.html                 │
├─────────────────────────────────────────────────────────────────┤
│                       API 网关 (FastAPI)                          │
│    鉴权 │ 限流 │ 路由 │ SSE/WebSocket 流式输出 │ CORS              │
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
│     MySQL 8.0 │ Redis 7 │ Milvus 2.5 (向量数据库)                │
├─────────────────────────────────────────────────────────────────┤
│                      可观测性层                                    │
│         全链路追踪 │ 结构化日志 │ 指标采集 │ 评价体系               │
└─────────────────────────────────────────────────────────────────┘
```

### Agent 状态机流程

```
用户输入
  │
  ▼
┌────────────┐    ┌──────────────┐
│ 意图识别    │───▶│ 需要澄清?     │───▶ 澄清追问
└────────────┘    └──────────────┘
  │ 明确意图
  ▼
┌────────────┐    ┌──────────────┐
│ 路由决策    │───▶│ RAG 检索路径  │ (技术咨询/活动咨询)
│            │    └──────────────┘
│            │
│            ├──▶│ 工具执行路径   │ (订单查询/退换货/投诉)
│            │    └──────────────┘
│            │
│            └──▶│ 直接回复路径   │ (通用咨询)
│                 └──────────────┘
│
│            ┌──────────────┐
└──────────────▶ 转人工路径   │ (用户请求/连续失败)
               └──────────────┘
```

---

## 三、核心功能

### 3.1 意图识别

系统采用**多层识别策略**，确保意图识别的准确性：

| 层级 | 方法 | 说明 |
|------|------|------|
| 第一层 | 关键词匹配 | 带权重的关键词匹配（高/中/低三级），快速识别常见意图 |
| 第二层 | 否定词检测 | 检查关键词附近的否定词（如"不是退款"），降低误判 |
| 第三层 | 上下文推断 | 基于历史对话中的工具调用结果推断意图 |
| 第四层 | 延续性判断 | 识别追问（如"好的"、"然后呢"），保持上下文意图 |

**支持的意图类型**：

| 意图类型 | 说明 | 典型触发词 |
|---------|------|-----------|
| `query_order` | 订单查询 | 订单号、物流、发货、配送 |
| `refund` | 退换货 | 退款、退货、退换、退钱 |
| `complaint` | 投诉 | 投诉、差评、气愤、骗子 |
| `technical` | 技术咨询 | 怎么用、如何、安装、设置 |
| `promotion` | 活动咨询 | 优惠、活动、折扣、促销 |
| `human` | 转人工 | 人工、客服、转人工 |
| `general` | 通用咨询 | 其他所有问题 |

### 3.2 Agent 工具

系统实现了 **8 个结构化工具**，支持重试、超时、错误处理：

| 工具名 | 中文 | 功能描述 |
|--------|------|---------|
| `query_order` | 订单查询 | 根据订单号查询订单状态、物流信息 |
| `create_ticket` | 工单创建 | 创建客服工单，自动分配处理人 |
| `apply_refund` | 退换货申请 | 申请退换货，校验订单状态 |
| `search_kb` | 知识库搜索 | 从知识库检索相关问题答案 |
| `escalate_to_human` | 转人工客服 | 转接人工客服，支持优先级 |
| `send_notification` | 发送通知 | 发送短信/邮件/站内信通知 |
| `update_ticket_status` | 更新工单状态 | 更新工单处理状态 |
| `get_user_history` | 用户历史记录 | 获取用户历史咨询记录 |

### 3.3 RAG 知识库

**混合检索引擎**架构：

```
用户查询
  │
  ▼
┌────────────┐    ┌──────────────┐
│ BM25 检索   │    │ 向量检索      │
│ (关键词匹配) │    │ (语义匹配)    │
└────────────┘    └──────────────┘
  │                    │
  ▼                    ▼
┌──────────────────────────────┐
│       结果融合 (分数加权)       │
└──────────────────────────────┘
  │
  ▼
┌──────────────┐
│ Reranker 重排 │
└──────────────┘
  │
  ▼
  最终结果
```

- **BM25 检索**：基于关键词统计的经典信息检索算法，擅长精确匹配
- **向量检索**：支持 Milvus 向量数据库，不可用时自动降级到内存模式
- **Reranker**：基于规则的重排序，综合考虑标题匹配、内容匹配、关键词重叠度等
- **多路召回**：BM25 权重 0.6 + 向量权重 0.4，可配置

### 3.4 结果校验

三层校验机制确保回答质量：

| 校验层 | 说明 | 通过条件 |
|--------|------|---------|
| **事实校验** | 检查回答中的关键信息与工具返回结果的一致性 | 事实分数 ≥ 0.6 |
| **安全校验** | 敏感词过滤、Prompt 注入检测、越权操作拦截 | 安全分数 ≥ 0.8 |
| **完整性校验** | 检查是否回答了用户的所有问题点 | 完整性分数 ≥ 0.5 |

校验不通过时自动重生成（最多 2 次），仍失败则转人工。

### 3.5 降级策略

| 故障场景 | 降级策略 |
|---------|---------|
| LLM API 超时/限流 | 自动切换备用模型或使用规则生成默认回复 |
| Milvus 不可用 | 降级为内存向量检索 |
| Embedding API 不可用 | 使用本地哈希向量模拟 |
| Redis 不可用 | 跳过缓存功能，直接操作数据库 |
| 数据库连接失败 | 使用 SQLite 本地存储 |
| 工具调用连续失败 | 终止自动处理，转人工并携带上下文 |

### 3.6 人机协同

**转人工流程**：

1. **触发时机**：
   - 用户主动要求转人工
   - Agent 连续失败（工具/校验）
   - 用户高优先级投诉
   - 系统检测到情绪激动

2. **上下文传递**：
   - 完整会话历史
   - 已调用的工具结果
   - 用户情绪分析
   - 问题分类和建议

3. **客服分配**：
   - 根据工单分类自动分配对应组别的客服
   - 支持优先级（普通/紧急）
   - SLA 时限管理

---

## 四、技术栈

| 层级 | 技术 | 版本 | 用途 |
|------|------|------|------|
| 语言 | Python | 3.11+ | 主力开发语言 |
| Web 框架 | FastAPI | 0.115 | 异步 Web 服务 |
| ASGI 服务器 | Uvicorn | 0.30 | 生产级 ASGI 服务器 |
| ORM | SQLAlchemy | 2.0 | 数据库操作 |
| 关系数据库 | MySQL | 8.0 | 用户/工单/会话数据 |
| 缓存 | Redis | 7 | 会话状态/缓存 |
| 向量数据库 | Milvus | 2.5.6 | 向量存储与检索 |
| 数据校验 | Pydantic | 2.9 | 请求/响应模型校验 |
| LLM 调用 | httpx | 0.27 | 异步 HTTP 客户端 |
| 向量客户端 | pymilvus | 2.5.6 | Milvus Python SDK |
| 配置管理 | pydantic-settings | 2.5 | 环境变量管理 |
| 环境变量 | python-dotenv | 1.0 | .env 文件加载 |
| 容器化 | Docker | - | 应用容器化 |
| 容器编排 | Docker Compose | V2 | 多服务编排 |
| 前端 | HTML/CSS/JS | - | 原生前端页面 |

---

## 五、快速开始

### 方式一：Docker Compose 一键部署（推荐）

```bash
# 克隆项目
git clone <repository-url>
cd AI-Customer

# 一键启动所有服务
docker compose up -d

# 查看服务状态
docker compose ps
```

启动完成后访问：
- 登录页面：`http://localhost:8000/`
- API 文档：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/health`

### 方式二：本地开发模式

```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 配置环境变量（复制模板）
cp .env.example .env
# 编辑 .env 文件，配置 API Key 等

# 启动服务
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 预置账号

| 角色 | 用户名 | 密码 |
|------|--------|------|
| 普通用户 | user001 | user001 |
| 管理员 | admin | admin123 |

---

## 六、配置说明

### 6.1 环境变量配置

所有配置项在 `.env` 文件中设置：

```ini
# ========== 基础设置 ==========
APP_NAME=智能客服系统
APP_VERSION=1.0.0
DEBUG=true

# ========== 数据库 ==========
# 方式1: MySQL (推荐生产使用)
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=123456
MYSQL_DATABASE=customer_service

# 方式2: SQLite (本地开发)
# DATABASE_URL_OVERRIDE=sqlite+aiosqlite:///./customer_service.db

# ========== Redis ==========
REDIS_HOST=localhost
REDIS_PORT=6379

# ========== LLM 对话模型 ==========
# 留空则使用内置模拟回复
LLM_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=sk-xxx
LLM_MODEL=qwen3.6-plus

# ========== Milvus 向量数据库 ==========
MILVUS_HOST=localhost
MILVUS_PORT=19531
USE_MILVUS=true

# ========== Embedding 向量模型 ==========
# 留空则使用本地哈希向量
EMBEDDING_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_API_KEY=sk-xxx
EMBEDDING_MODEL=text-embedding-v3
EMBEDDING_DIM=1024

# ========== RAG 检索配置 ==========
COLLECTION_NAME=customer_service_knowledge
RAG_TOP_K=3
RAG_SIMILARITY_THRESHOLD=0.3
RAG_BM25_WEIGHT=0.6
RAG_VECTOR_WEIGHT=0.4
RAG_USE_RERANKER=true

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
| 19531 | Milvus | 向量数据库端口（非标准，避免冲突） |

### 6.3 Docker Compose 服务

```yaml
services:
  etcd:       # Milvus 元数据存储
  minio:      # Milvus 对象存储
  milvus:     # 向量数据库
  mysql:      # 关系数据库
  redis:      # 缓存
  app:        # 应用服务
```

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

### 7.2 用户接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/users/` | 创建用户 |
| `GET` | `/api/v1/users/` | 获取用户列表 |
| `GET` | `/api/v1/users/{id}` | 获取用户详情 |
| `POST` | `/api/v1/users/login` | 用户登录 |

### 7.3 会话接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/chat/sessions` | 创建新会话 |
| `GET` | `/api/v1/chat/sessions` | 获取会话列表 |
| `PATCH` | `/api/v1/chat/sessions/{id}/close` | 关闭/保存会话 |

### 7.4 工单接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/tickets` | 创建工单 |
| `GET` | `/api/v1/tickets` | 获取工单列表 |
| `GET` | `/api/v1/tickets/{id}` | 获取工单详情 |
| `PUT` | `/api/v1/tickets/{id}` | 更新工单状态 |

### 7.5 转人工接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/handoff` | 请求转人工 |
| `GET` | `/api/v1/agents` | 获取客服列表 |
| `GET` | `/api/v1/agents/{id}` | 获取客服详情 |

### 7.6 知识库接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/knowledge/upload` | 上传文档到知识库 |
| `GET` | `/api/v1/knowledge/documents` | 获取文档列表 |
| `DELETE` | `/api/v1/knowledge/documents/{id}` | 删除文档 |
| `POST` | `/api/v1/knowledge/search` | 搜索知识库 |
| `POST` | `/api/v1/knowledge/rag-query` | RAG 问答 |
| `GET` | `/api/v1/knowledge/stats` | 获取知识库统计 |

### 7.7 分析与反馈

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/analytics/metrics` | 系统指标 |
| `GET` | `/api/v1/analytics/session` | 会话统计 |
| `POST` | `/api/v1/feedback/submit` | 提交反馈 |
| `GET` | `/api/v1/feedback/stats` | 反馈统计 |

### 7.8 WebSocket 事件类型

通过 `/api/v1/chat/stream` 连接后，服务端推送以下事件：

| 事件类型 | 说明 |
|---------|------|
| `stream_start` | 对话开始 |
| `node_start` | 处理节点开始 |
| `node_complete` | 节点完成 |
| `intent` | 意图识别完成 |
| `tool_call_start` | 工具调用开始 |
| `tool_call_complete` | 工具调用完成 |
| `rag_result` | 知识库检索完成 |
| `validation` | 结果校验完成 |
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
│   │   ├── graph.py              #   状态机编排（核心大脑）
│   │   ├── intent.py             #   意图识别（多层策略）
│   │   ├── tools.py              #   8 个工具实现
│   │   ├── retrieval.py          #   混合检索引擎
│   │   ├── validation.py         #   三层结果校验
│   │   ├── memory.py             #   对话记忆管理
│   │   └── state.py              #   状态定义
│   ├── services/                  # 业务服务
│   │   ├── llm_service.py        #   LLM 模型服务
│   │   ├── embedding_service.py  #   Embedding 向量化
│   │   ├── knowledge_base.py     #   知识库服务
│   │   ├── evaluation.py         #   评价体系
│   │   └── collaboration.py      #   人机协作服务
│   ├── routers/                   # API 路由
│   │   ├── chat.py               #   对话接口
│   │   ├── tickets.py            #   工单接口
│   │   ├── knowledge.py          #   知识库接口
│   │   ├── analytics.py          #   分析接口
│   │   ├── feedback.py           #   反馈接口
│   │   ├── sessions.py           #   会话接口
│   │   └── users.py              #   用户接口
│   ├── models/                    # 数据模型 (ORM)
│   │   └── models.py             #   SQLAlchemy 模型定义
│   ├── schemas/                   # 数据校验 (Pydantic)
│   ├── utils/                     # 工具模块
│   │   ├── database.py           #   数据库管理
│   │   ├── milvus_client.py      #   Milvus 客户端
│   │   └── tracking.py           #   全链路追踪
│   ├── config/                    # 配置管理
│   │   └── config.py             #   Settings 类定义
│   └── main.py                    # 应用入口
│
├── static/                        # 前端静态文件
│   ├── css/style.css             #   样式表
│   ├── js/app.js                 #   管理员后台逻辑
│   ├── login.html                #   登录页
│   ├── user.html                 #   用户端页面
│   └── admin.html                #   管理员后台
│
├── Dockerfile                     # Docker 镜像定义
├── docker-compose.yml             # 服务编排配置
├── requirements.txt               # Python 依赖
├── .env                           # 环境变量配置
├── .env.example                   # 环境变量模板
├── start.bat                      # 一键启动（Windows）
├── stop.bat                       # 一键停止（Windows）
├── start_server.bat               # 服务启动脚本
├── test_rag.py                    # RAG 功能测试
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
   - **数据看板**：查看系统统计

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
      console.log('识别意图:', data.intent);
      break;
    case 'token':
      console.log(data.content);  // 逐字输出
      break;
    case 'done':
      console.log('完成:', data.reply);
      break;
  }
};
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
```

### Q3: LLM 回复使用模拟模式？

当 `LLM_API_KEY` 为空或无效时，系统使用内置规则生成回复。配置真实 API 后会自动切换。

### Q4: Embedding 未配置？

未配置时使用本地哈希向量模拟，功能正常但检索效果一般。配置后可获得更准确的语义匹配。

### Q5: 如何重置数据？

```bash
# Docker 模式
docker compose down -v    # 停止并删除所有数据卷
docker compose up -d      # 重新启动

# 本地模式
# 删除 customer_service.db 文件
```

### Q6: 如何查看日志？

```bash
# Docker 模式
docker compose logs -f app      # 应用日志
docker compose logs -f mysql    # MySQL 日志
docker compose logs -f milvus   # Milvus 日志

# 本地模式
# 查看控制台输出或配置日志文件
```

### Q7: 知识库如何扩展？

1. 通过 API 上传文档：`POST /api/v1/knowledge/upload`
2. 上传的文档会自动进行分块和向量化
3. 支持通过 `POST /api/v1/knowledge/search` 搜索

### Q8: 如何自定义意图？

编辑 `app/agent/intent.py` 中的 `INTENT_PATTERNS` 字典，添加新的意图类型和关键词。

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
