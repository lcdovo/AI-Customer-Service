# 🤖 企业智能客服系统

> **一句话介绍**：一个能自动回复用户、处理订单查询、退款、投诉的 AI 客服系统。

---

## 目录

- [一、项目简介](#一项目简介)
- [二、你需要准备什么](#二你需要准备什么)
- [三、最快启动：Docker 一键部署](#三最快启动docker-一键部署)
- [四、配置 API Key（可选，不配置也能跑）](#四配置-api-key可选不配置也能跑)
- [五、验证启动成功](#五验证启动成功)
- [六、测试对话功能](#六测试对话功能)
- [七、WebSocket 实时流式对话](#七websocket-实时流式对话)
- [八、进阶：手动启动（不用 Docker）](#八进阶手动启动不用-docker)
- [九、配置说明](#九配置说明)
- [十、项目结构](#十项目结构)
- [十一、常见问题解答](#十一常见问题解答)

---

## 一、项目简介

这是一个**企业级智能客服与工单自动处理系统**，核心能力：

| 能力 | 说明 |
|------|------|
| 🤖 **Agent 状态机** | LangGraph 风格的节点式编排，支持条件分支、工具调用、多轮对话 |
| 🔍 **意图识别** | 3 层识别（关键词 → LLM 确认 → 上下文推断），支持 7 类意图 |
| 🛠️ **8 个工具** | 查询订单、创建工单、申请退款、搜索知识库、转人工、发送通知等 |
| 📚 **RAG 知识库** | Milvus 向量库 + BM25 关键词混合检索，支持多文档源 |
| ✅ **结果校验** | 3 层校验（事实校验 → 安全校验 → 完整性校验） |
| 🔄 **降级策略** | LLM 多模型降级、Redis 内存降级、Milvus 内存降级 |
| 👥 **人机协同** | 自动检测转人工时机、客服智能分配、工单生命周期管理 |
| 📊 **可观测性** | 全链路追踪、指标采集、告警管理、评价体系、A/B 测试 |

---

## 二、你需要准备什么

### ✅ 必须

| 工具 | 下载地址 | 安装说明 |
|------|---------|---------|
| **Docker Desktop for Windows** | [docker.com](https://www.docker.com/products/docker-desktop/) | 下载安装后重启电脑，确保 Docker Engine 运行中（系统托盘有小鲸鱼图标） |
| **PowerShell** | Windows 自带 | 按 `Win + S` 搜索 "PowerShell"，右键以管理员身份运行 |

### 💡 可选（没有也能跑）

| 工具 | 用途 | 不装的后果 |
|------|------|-----------|
| **Embedding API Key** | 真实向量模型 | 用本地模拟向量代替（功能正常，效果稍差） |
| **LLM API Key** | 真实 AI 对话 | 用内置模拟回复代替 |
| **MySQL 客户端** | 查看数据库 | 不需要，数据存在 Docker 容器里 |

> 💬 **总结**：只要有 Docker Desktop，其他一切都不需要安装！

---

## 三、最快启动：Docker 一键部署

### 第 1 步：打开 PowerShell

按 `Win + S`，搜索 **PowerShell**，右键选择 **"以管理员身份运行"**。

### 第 2 步：进入项目目录

```powershell
cd C:\Users\你的用户名\Desktop\项目1
```

### 第 3 步：启动所有服务

```powershell
docker compose up -d
```

这条命令会自动：
- ✅ 构建应用镜像（基于 Python 3.11）
- ✅ 启动 MySQL 8.0 容器
- ✅ 启动 Redis 7 容器
- ✅ 启动 Etcd + MinIO（Milvus 依赖）
- ✅ 启动 Milvus 2.5.6 向量数据库
- ✅ 启动智能客服应用

> ⏰ **首次启动会比较慢**（需要下载镜像 + 构建），大约 3-5 分钟。
> 后续启动会很快（秒级）。

### 第 4 步：查看启动状态

```powershell
docker compose ps
```

你应该看到类似的输出：

```
NAME                STATUS
cs_mysql            Up (healthy)
cs_redis            Up (healthy)
cs_etcd             Up (healthy)
cs_minio            Up (healthy)
cs_milvus           Up (healthy)
cs_app              Up
```

> ⚠️ 每个服务后面都要显示 **Up (healthy)** 或 **Up**，表示启动成功。
> 如果某个服务显示 `Restarting` 或 `Exited`，说明启动失败，请看 [第十章](#十常见问题解答)。

### 第 5 步：验证服务

打开浏览器访问：

```
http://localhost:8000/docs
```

如果看到 **Swagger API 文档页面**（绿色背景的交互式文档），说明启动成功！🎉

---

## 四、配置 API Key（可选，不配置也能跑）

### 4.1 Embedding 向量模型（推荐配置）

向量模型决定了知识库检索的准确度。不配置时使用本地模拟向量（能跑，但效果一般）。

**配置步骤：**

1. 用记事本打开项目目录下的 `.env` 文件：
   ```powershell
   notepad .env
   ```

2. 找到 Embedding 部分，填入你的 API 信息：
   ```
   # Embedding API
   EMBEDDING_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
   EMBEDDING_API_KEY=sk-你的真实API密钥
   EMBEDDING_MODEL=text-embedding-v3
   EMBEDDING_DIM=1024
   ```

**常见服务商配置示例：**

| 服务商 | EMBEDDING_API_BASE | EMBEDDING_MODEL |
|--------|-------------------|-----------------|
| 阿里 DashScope | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `text-embedding-v3` |
| 智谱 AI | `https://open.bigmodel.cn/api/paas/v4` | `embedding-3` |
| OpenAI | `https://api.openai.com/v1` | `text-embedding-3-small` |
| 任何兼容 OpenAI 格式的服务 | 对应地址 | 对应模型名 |

3. 保存文件后，重启应用：
   ```powershell
   docker compose restart app
   ```

### 4.2 LLM 对话模型（可选）

不配置时，系统用内置规则模拟回复（足够演示所有功能）。

**配置步骤：**

在 `.env` 文件中：
```
LLM_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=sk-你的真实API密钥
LLM_MODEL=qwen-plus
```

保存后重启：
```powershell
docker compose restart app
```

---

## 五、验证启动成功

### 5.1 查看健康状态

浏览器访问 `http://localhost:8000/health`，应该返回：
```json
{"status": "healthy", "app": "智能客服系统", "version": "1.0.0"}
```

### 5.2 查看 Swagger API 文档

浏览器访问 `http://localhost:8000/docs`，你会看到所有可用的 API 接口。

### 5.3 查看容器日志

```powershell
# 查看应用日志
docker compose logs -f app

# 查看 MySQL 日志
docker compose logs -f mysql

# 查看 Milvus 日志
docker compose logs -f milvus
```

### 5.4 停止服务

```powershell
# 停止所有服务（保留数据）
docker compose down

# 停止并删除所有数据（彻底清理）
docker compose down -v
```

---

## 六、测试对话功能

### 方法 1：在 Swagger 页面测试

1. 打开 `http://localhost:8000/docs`
2. 找到 **POST /api/v1/chat/send**
3. 点击 **Try it out**
4. 在请求体中输入：

```json
{
  "user_id": 1,
  "message": "你好，我的订单ORD20260801到哪了？"
}
```

5. 点击 **Execute** 按钮
6. 查看回复结果

### 方法 2：用 PowerShell 命令行测试

```powershell
# 查询订单
curl -X POST http://localhost:8000/api/v1/chat/send `
  -H "Content-Type: application/json" `
  -d "{\"user_id\": 1, \"message\": \"我的订单ORD20260801到哪了\"}"

# 咨询退换货
curl -X POST http://localhost:8000/api/v1/chat/send `
  -H "Content-Type: application/json" `
  -d "{\"user_id\": 1, \"message\": \"我想申请退款\"}"

# 投诉
curl -X POST http://localhost:8000/api/v1/chat/send `
  -H "Content-Type: application/json" `
  -d "{\"user_id\": 1, \"message\": \"产品有问题，我要投诉\"}"
```

### 方法 3：用浏览器直接访问

```
http://localhost:8000/docs
```

在 Swagger 页面可以测试所有 API：

| API | 功能 | 示例 |
|-----|------|------|
| `POST /api/v1/chat/send` | 发送消息对话 | `"我的订单到哪了"` |
| `GET /api/v1/chat/history/{session_id}` | 查看历史对话 | session_id 为对话ID |
| `GET /api/v1/chat/tools` | 查看 AI 可用工具列表 | - |
| `POST /api/v1/tickets` | 创建工单 | 投诉、问题反馈 |
| `GET /api/v1/tickets` | 查询工单列表 | 查看处理进度 |
| `POST /api/v1/handoff` | 请求转人工 | 转接真人客服 |
| `GET /api/v1/analytics/metrics` | 查看系统指标 | 对话量、响应时间 |
| `POST /api/v1/feedback/submit` | 提交反馈 | 点赞/点踩 |

---

## 七、WebSocket 实时流式对话

如果你想在自己的网页/APP 中嵌入智能客服，用 WebSocket 是最佳选择——用户可以看到 AI **逐字打字**的效果，体验更流畅。

### 7.1 连接地址

```
ws://localhost:8000/api/v1/chat/stream
```

> 💡 如果用 HTTPS 部署，地址改为 `wss://你的域名/api/v1/chat/stream`

### 7.2 发送消息格式

客户端通过 WebSocket 发送 **JSON 文本**：

```json
{
  "user_id": 1,
  "message": "我的订单ORD20260801到哪了",
  "session_id": "可选，不传则自动创建新会话"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_id` | int | ✅ | 用户 ID（需要在系统中存在，可以先通过 API 创建） |
| `message` | string | ✅ | 用户发送的消息内容 |
| `session_id` | string | ❌ | 会话 ID，不传则自动创建新会话；传了则恢复之前的对话上下文 |

### 7.3 接收消息格式

服务端会推送一系列 **JSON 事件**，每个事件都有 `type` 字段表示类型：

| 事件类型 | 说明 | 关键字段 |
|---------|------|---------|
| `stream_start` | 对话开始 | `session_id`, `trace_id` |
| `node_start` | 某个处理节点开始 | `node`（节点名） |
| `node_complete` | 节点完成 | `node`, `duration_ms`, `next_node` |
| `intent` | 意图识别完成 | `intent`, `confidence` |
| `tool_call_start` | 工具调用开始 | `tool`, `args` |
| `tool_call_complete` | 工具调用完成 | `tool`, `success`, `execution_time_ms` |
| `rag_result` | 知识库检索完成 | `results_count`, `top_score` |
| `validation` | 结果校验完成 | `passed`, `overall_score` |
| `handoff` | 触发转人工 | `reason` |
| `token` | **流式回复的一个字/词** | `content`, `index` |
| `done` | 本次对话全部完成 | `reply`, `intent`, `execution_time_ms` |
| `stream_end` | 对话结束（已存入数据库） | `message_id`, `session_id` |
| `error` | 发生错误 | `code`, `message` |

> 💡 **流式打字效果**：`token` 事件就是 AI 回复的每个文字片段，你可以用它实现打字机效果。

### 7.4 前端 JavaScript 示例

```javascript
// 连接 WebSocket
const ws = new WebSocket("ws://localhost:8000/api/v1/chat/stream");

// 用户发送消息
function sendMessage(userId, message, sessionId = null) {
  const payload = { user_id: userId, message };
  if (sessionId) payload.session_id = sessionId;
  ws.send(JSON.stringify(payload));
}

// 接收消息
let fullReply = "";
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  switch (data.type) {
    case "stream_start":
      console.log("对话开始，会话ID:", data.session_id);
      break;

    case "intent":
      console.log("识别意图:", data.intent, "置信度:", data.confidence);
      break;

    case "tool_call_start":
      console.log("调用工具:", data.tool);
      break;

    case "tool_call_complete":
      console.log("工具完成:", data.tool, "成功:", data.success);
      break;

    case "token":
      // 逐字显示，实现打字机效果
      fullReply += data.content;
      document.getElementById("reply").textContent = fullReply;
      break;

    case "done":
      console.log("回复完成:", data.reply);
      console.log("耗时:", data.execution_time_ms, "ms");
      fullReply = "";
      break;

    case "error":
      console.error("错误:", data.message);
      break;
  }
};

// 页面加载后发送一条消息
sendMessage(1, "你好，我的订单ORD20260801到哪了");
```

### 7.5 Python 示例

```python
import asyncio
import json
import websockets

async def chat():
    uri = "ws://localhost:8000/api/v1/chat/stream"
    async with websockets.connect(uri) as ws:
        # 发送消息
        msg = json.dumps({
            "user_id": 1,
            "message": "我的订单ORD20260801到哪了"
        })
        await ws.send(msg)

        # 接收回复
        full_reply = ""
        while True:
            raw = await ws.recv()
            event = json.loads(raw)

            if event["type"] == "token":
                full_reply += event["content"]
                print(event["content"], end="", flush=True)

            elif event["type"] == "done":
                print(f"\n\n意图: {event['intent']}")
                print(f"耗时: {event['execution_time_ms']}ms")
                break

            elif event["type"] == "error":
                print(f"\n错误: {event['message']}")
                break

asyncio.run(chat())
```

### 7.6 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| 连接不上 | 服务没启动或地址错了 | 确认服务在运行，地址正确 |
| 收到 error 404 | 用户不存在 | 先调用 `POST /api/v1/users/` 创建用户 |
| 收到 error 400 | 参数缺失 | 检查 `user_id` 和 `message` 是否都传了 |
| 消息收不到 | 连接被防火墙拦截 | 检查端口是否放行 |

---

## 八、进阶：手动启动（不用 Docker）

如果你不想用 Docker，也可以直接在本地运行。

### 8.1 安装 Python 3.11

1. 访问 [python.org/downloads](https://www.python.org/downloads/)
2. 点击 **Download Python 3.11.x**
3. 运行安装程序，**重要**：勾选 **"Add Python to PATH"**
4. 选择 **Install Now**
5. 验证：
   ```powershell
   python --version
   # 应显示: Python 3.11.x
   ```

### 8.2 安装依赖

```powershell
cd C:\Users\你的用户名\Desktop\项目1

# 使用国内镜像加速（推荐）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 8.3 启动服务

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 8.4 验证

浏览器访问 `http://localhost:8000/docs`

> 💡 **注意**：手动启动时，MySQL 和 Redis 需要你自己安装，或者通过 Docker Compose 单独启动它们：
> ```powershell
> # 只启动基础设施
> docker compose up -d mysql redis milvus
> ```

---

## 九、配置说明

### 9.1 环境变量（.env 文件）

所有配置都在项目根目录的 `.env` 文件中。用记事本打开编辑：

```powershell
notepad .env
```

**完整配置项说明：**

```ini
# ========== 基础设置 ==========
APP_NAME=智能客服系统          # 应用名称
APP_VERSION=1.0.0             # 版本号
DEBUG=true                   # 调试模式（生产环境改为 false）
HOST=0.0.0.0                 # 监听地址
PORT=8000                    # 端口号

# ========== MySQL 数据库 ==========
MYSQL_HOST=localhost          # MySQL 地址
MYSQL_PORT=3306               # MySQL 端口
MYSQL_USER=root               # MySQL 用户名
MYSQL_PASSWORD=123456         # MySQL 密码
MYSQL_DATABASE=customer_service  # 数据库名

# ========== Redis 缓存 ==========
REDIS_HOST=localhost          # Redis 地址
REDIS_PORT=6379               # Redis 端口
REDIS_PASSWORD=               # Redis 密码（没有就留空）
REDIS_DB=0                    # Redis 数据库编号

# ========== LLM 对话模型 ==========
LLM_API_BASE=http://localhost:8001  # API 地址
LLM_API_KEY=                  # API 密钥（留空则使用模拟回复）
LLM_MODEL=gpt-4o-mini         # 模型名称

# ========== Milvus 向量数据库 ==========
MILVUS_HOST=localhost         # Milvus 地址
MILVUS_PORT=19530             # Milvus 端口
USE_MILVUS=true               # 是否启用 Milvus

# ========== Embedding 向量模型 ==========
EMBEDDING_API_BASE=           # Embedding API 地址（留空用模拟）
EMBEDDING_API_KEY=            # Embedding API 密钥
EMBEDDING_MODEL=              # Embedding 模型名称
EMBEDDING_DIM=1024            # 向量维度

# ========== RAG 检索增强生成 ==========
COLLECTION_NAME=customer_service_knowledge  # Milvus 集合名
RAG_TOP_K=3                   # 检索返回文档数量
RAG_SIMILARITY_THRESHOLD=0.3  # 相似度阈值（0-1）
RAG_BM25_WEIGHT=0.6           # BM25 关键词检索权重
RAG_VECTOR_WEIGHT=0.4         # 向量检索权重
RAG_USE_RERANKER=true         # 是否启用 Reranker 重排序

# ========== 文档分块配置 ==========
CHUNK_SIZE=500                # 每个分块最大字符数
CHUNK_OVERLAP=50              # 分块重叠字符数
CHUNK_SPLIT_PATTERN=sentence  # 分块模式：sentence/paragraph/fixed
```

### 9.2 Docker Compose 服务架构

```
┌─────────────────────────────────────────────────────┐
│                   docker compose                      │
│                                                       │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐              │
│  │  MySQL  │  │  Redis  │  │ Milvus  │              │
│  │ 8.0     │  │  7     │  │ 2.5.6   │              │
│  │ :3306   │  │ :6379  │  │ :19530  │              │
│  └─────────┘  └─────────┘  └─────────┘              │
│                                  ↑                    │
│                            ┌─────┴─────┐              │
│                            │   Etcd    │              │
│                            │   +MinIO  │              │
│                            └───────────┘              │
│                                                       │
│  ┌─────────────────────────────────────────────────┐ │
│  │                   应用 (app)                      │ │
│  │  Python 3.11 + FastAPI + SQLAlchemy + pymilvus   │ │
│  │  端口: 8000                                      │ │
│  └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

### 9.3 端口占用说明

| 端口 | 服务 | 冲突怎么办 |
|------|------|-----------|
| 8000 | 应用 | 修改 `.env` 中的 `PORT` 和 `docker-compose.yml` 中的端口映射 |
| 3306 | MySQL | 修改 `docker-compose.yml` 中的 MySQL 端口映射 |
| 6379 | Redis | 修改 `docker-compose.yml` 中的 Redis 端口映射 |
| 19531 | Milvus | 独立端口，避免与其他项目冲突；如需再改，同步修改 `.env` 中的 `MILVUS_PORT` |
| 9092 | Milvus 健康检查 | 同上 |
| 2380 | Etcd | 独立端口，如需修改同步改 `docker-compose.yml` |
| 9002 | MinIO | 独立端口，如需修改同步改 `docker-compose.yml` |

---

## 十、项目结构

```
项目1/
│
├── app/                              # 📁 核心代码
│   │
│   ├── agent/                        # 🤖 Agent 智能体
│   │   ├── graph.py                  #   状态机编排（Agent 大脑，支持流式输出）
│   │   ├── intent.py                 #   意图识别（理解用户意图）
│   │   ├── tools.py                  #   8 个工具（查询/创建/退款等）
│   │   ├── retrieval.py              #   混合检索（Milvus + BM25）
│   │   ├── validation.py            #   三层结果校验
│   │   ├── memory.py                 #   对话记忆与会话管理
│   │   └── state.py                  #   状态定义
│   │
│   ├── services/                     # ⚙️ 业务服务
│   │   ├── llm_service.py            #   LLM 模型服务
│   │   ├── embedding_service.py      #   Embedding 向量化服务
│   │   ├── knowledge_base.py         #   知识库服务（文档分块+向量化+存储）
│   │   ├── evaluation.py             #   评价体系与 A/B 测试
│   │   └── collaboration.py          #   人机协同与工单管理
│   │
│   ├── routers/                      # 🌐 API 路由
│   │   ├── chat.py                   #   对话接口（REST + WebSocket）
│   │   ├── tickets.py                #   工单接口
│   │   ├── analytics.py              #   统计分析接口
│   │   └── feedback.py               #   用户反馈接口
│   │
│   ├── utils/                        # 🔧 工具模块
│   │   ├── database.py               #   数据库管理
│   │   ├── milvus_client.py          #   Milvus 客户端
│   │   └── tracking.py               #   全链路追踪与监控
│   │
│   ├── models/                       # 📊 数据模型（ORM）
│   ├── schemas/                      # 📨 数据校验（Pydantic）
│   ├── config/                       # ⚙️ 配置管理
│   └── main.py                       # 🚀 程序入口
│
├── test_phase2.py                    # 🧪 Agent 核心测试
├── test_phase3.py                    # 🧪 增强功能测试
├── test_phase4.py                    # 🧪 可观测性测试
│
├── Dockerfile                        # 🐳 Docker 镜像定义
├── docker-compose.yml                # 🐳 服务编排配置
├── requirements.txt                  # 📦 Python 依赖清单
├── .env                              # ⚙️ 环境变量配置（你的配置）
├── .env.example                      # 📋 环境变量模板
└── README.md                         # 📖 本文档
```

---

## 十一、常见问题解答

### Q1: `docker compose up -d` 很慢？

**正常现象**。首次需要下载多个 Docker 镜像（MySQL、Redis、Milvus 等），大约 500MB+ 数据。

**加速方法**：配置 Docker 镜像加速器
1. 打开 Docker Desktop
2. 点击右上角 ⚙️ Settings
3. 选择 Docker Engine
4. 在 JSON 配置中添加：
```json
{
  "registry-mirrors": [
    "https://docker.1ms.run",
    "https://docker.xuanyuan.me"
  ]
}
```
5. 点击 Apply & Restart

---

### Q2: Milvus 启动失败？

Milvus 依赖 Etcd 和 MinIO。如果 Milvus 容器状态不是 `healthy`：

```powershell
# 查看 Milvus 日志
docker compose logs milvus

# 查看 Etcd 日志
docker compose logs etcd

# 查看 MinIO 日志
docker compose logs minio
```

**常见原因**：
- Etcd 未就绪 → 等待 10-30 秒后自动恢复
- 端口冲突（9001/2379） → 修改 `docker-compose.yml` 中的端口映射
- 磁盘空间不足 → 清理 Docker 空间：`docker system prune -a`

---

### Q3: 端口被占用？

**错误信息**: `Error starting ... : bind: address already in use`

**解决方法**：修改 `docker-compose.yml` 中的端口映射。

例如端口 8000 被占用，改成 8080：
```yaml
  app:
    ports:
      - "8080:8000"    # 左边改 8080，右边保持 8000
```

### Q4: 已经有其他项目在用 Milvus，会冲突吗？

**不会！** 我们的 Milvus 使用独立端口 **19531**（默认），和其他项目的 19530 天然隔离：

| 组件 | 我们的端口 | 常见默认端口 | 是否冲突 |
|------|-----------|-------------|---------|
| Milvus | **19531** | 19530 | ❌ 不冲突 |
| Milvus 健康检查 | **9092** | 9091 | ❌ 不冲突 |
| Etcd | **2380** | 2379 | ❌ 不冲突 |
| MinIO | **9002** | 9001 | ❌ 不冲突 |

启动后两套 Milvus 完全独立，数据存储在不同的 Docker Volume 中，互不影响。

如果你还有其他项目占用了这些新端口，再按同样思路修改 `docker-compose.yml` 左侧的数字就行（比如改成 19532、9093 等）。

---

### Q4: 如何查看容器状态？

```powershell
# 查看所有服务状态
docker compose ps

# 查看某个服务的日志
docker compose logs -f app       # 应用日志
docker compose logs -f mysql     # MySQL 日志
docker compose logs -f redis     # Redis 日志
docker compose logs -f milvus    # Milvus 日志

# 查看资源占用
docker stats
```

---

### Q5: 如何重置数据？

```powershell
# 停止并删除所有容器和数据
docker compose down -v

# 重新启动（空数据库）
docker compose up -d
```

> ⚠️ **警告**：`docker compose down -v` 会删除所有数据（数据库、Redis、Milvus），不可恢复！

---

### Q6: Embedding API 连接失败？

如果配置了 Embedding API 但连接失败：

1. 检查 `.env` 中的配置是否正确
2. 确认 API Key 有效
3. 查看应用日志：
   ```powershell
   docker compose logs app | findstr "Embedding"
   ```

系统会自动降级到本地模拟向量，功能不受影响。

---

### Q7: 应用无法连接数据库？

MySQL 容器可能还没完全就绪。等待几秒后重试。

如果持续失败：
```powershell
# 检查 MySQL 状态
docker compose ps mysql

# 查看 MySQL 日志
docker compose logs mysql
```

---

### Q8: 如何更新项目？

```powershell
# 拉取最新代码（如果用 Git）
git pull

# 重新构建并启动
docker compose up -d --build
```

---

### Q9: 如何修改密码或配置？

1. 修改 `.env` 文件中的配置
2. 重启应用：
   ```powershell
   docker compose restart app
   ```

如果修改了数据库密码，还需要修改 `docker-compose.yml` 中 MySQL 的 `MYSQL_ROOT_PASSWORD`。

---

### Q10: Docker 容器占用空间太大？

```powershell
# 查看 Docker 占用
docker system df

# 清理未使用的镜像和容器
docker system prune -a

# 清理所有未使用资源（谨慎使用）
docker system prune -a --volumes
```

---

### Q11: WebSocket 连接失败或无响应？

**常见原因与解决：**

| 现象 | 原因 | 解决 |
|------|------|------|
| 连接立即断开 | 服务未启动 | 确认 `docker compose ps` 中 app 为 Up 状态 |
| 收到 `error 404` | 用户不存在 | 先调用 `POST /api/v1/users/` 创建用户 |
| 收到 `error 400` | 参数缺失 | 确保 `user_id` 和 `message` 都传了 |
| 收到 `error 500` | 数据库未就绪 | 等待 MySQL 就绪，或查看 app 日志排查 |
| 连不上但端口通 | 反向代理未配 WebSocket | Nginx 添加 `proxy_set_header Upgrade $http_upgrade` |
| 连接后无事件 | 发送的消息格式不对 | 确保发送的是 JSON 文本，不是二进制 |

**调试技巧**：查看应用日志追踪 WebSocket 事件：
```powershell
docker compose logs -f app | findstr "stream"
```

---

## 附录：API 快速参考

### 对话接口

```
POST /api/v1/chat/send        发送消息（同步返回）
WS   /api/v1/chat/stream      WebSocket 实时流式对话
GET  /api/v1/chat/history/{id} 查看历史
GET  /api/v1/chat/tools        可用工具列表
GET  /api/v1/chat/intents      支持的意图类型
```

### 工单接口

```
POST /api/v1/tickets           创建工单
GET  /api/v1/tickets           查询工单列表
GET  /api/v1/tickets/{id}      查询单个工单
PUT  /api/v1/tickets/{id}      更新工单状态
```

### 人机协同

```
POST /api/v1/handoff           请求转人工
GET  /api/v1/agents            客服列表
GET  /api/v1/agents/{id}       客服详情
```

### 监控与反馈

```
GET  /api/v1/analytics/metrics     系统指标
GET  /api/v1/analytics/session      会话统计
POST /api/v1/feedback/submit       提交反馈
GET  /api/v1/feedback/stats        反馈统计
```

---

**启动顺利，使用愉快！🎉**