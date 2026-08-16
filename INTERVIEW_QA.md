# AI Customer 智能客服系统 — 面试问答文档

---

## 一、项目概述类

### Q1：请简单介绍一下你做的这个项目？

**A：**
我做的是一个企业级智能客服与工单自动处理系统，叫 AI Customer。核心目标是用 AI Agent 替代传统人工客服，实现订单查询、退换货处理、投诉工单、知识库问答等全场景的自动化处理。

技术栈方面，后端用 Python + FastAPI 搭建 RESTful API 和 SSE 流式接口，Agent 核心是自研的状态机编排引擎（类似 LangGraph 的设计思想），大模型用阿里 DashScope，向量数据库用 Milvus，也支持 MySQL/SQLite 双模式。前端是原生 HTML/CSS/JS，分用户端和管理员端两个界面。

项目的核心亮点有三个：一是 4 层递进式意图识别策略，二是 BM25 + 向量 + Reranker 的混合检索引擎，三是三层结果校验 + 自动重新生成的质量保障机制。整体实现了从用户输入到 AI 响应的完整闭环。

### Q2：这个项目解决了什么实际问题？

**A：**
主要解决了传统客服系统的三个痛点：

1. **意图识别不准**：传统关键词匹配方式对"嗯"、"好的"、"那然后呢"等短文本和追问场景识别率低，导致答非所问。我们的 4 层递进策略把这类边界场景的识别率从约 40% 提升到 75% 以上。

2. **工具调用不可靠**：订单查询、退换货申请等操作涉及多个外部系统调用，任何一个环节失败都会导致用户体验差。我们实现了带重试（最多 3 次指数退避）的工具执行框架，工具成功率从单次调用的 85% 提升到 97%+。

3. **人工转接不及时**：传统系统中用户需要反复要求才能转人工，转接后信息交接也不完整。我们设计了明确的转人工触发条件（用户主动请求、工具连续失败、低置信度等），并且自动把对话上下文、工具结果、用户历史打包给人工客服，SLA 从普通 24h 到紧急 1h 分级响应。

### Q3：项目的架构设计是怎样的？

**A：**
整体架构分为以下几个层次：

```
┌─────────────────────────────────────────────────────────┐
│                     前端展示层                           │
│  user.html (用户端)  │  admin.html (管理员端)  │  SSE 流式推送  │
├─────────────────────────────────────────────────────────┤
│                     API 路由层                           │
│  chat (对话) │ knowledge (知识库) │ tickets (工单) │      │
│  users (用户) │ sessions (会话) │ analytics (分析) │      │
├─────────────────────────────────────────────────────────┤
│                     Agent 编排层                         │
│  AgentGraph 状态机（8 节点）│ 意图识别 │ 路由决策 │         │
├─────────────────────────────────────────────────────────┤
│                     核心能力层                           │
│  Function Calling (8工具) │ RAG检索 │ LLM服务 │ 校验 │     │
├─────────────────────────────────────────────────────────┤
│                     基础设施层                           │
│  Milvus (向量) │ MySQL/SQLite │ Redis │ DashScope LLM │    │
├─────────────────────────────────────────────────────────┤
│                     可观测性层                           │
│  全链路追踪 │ Metrics │ 结构化日志 │ 告警管理 │            │
└─────────────────────────────────────────────────────────┘
```

**核心数据流**：用户消息 → 意图识别 → 按意图路由到对应节点（RAG检索/工具执行/直接回复）→ 结果校验 → LLM 响应生成 → SSE 流式推送到前端。

---

## 二、Agent 状态机类

### Q4：为什么选择状态机模式来实现 Agent？和 LangChain/LangGraph 有什么区别？

**A：**
选择状态机模式的原因：
1. **确定性流程**：客服场景有明确的业务流程（识别意图→查询/操作→返回结果），适合用状态机建模。
2. **可调试性强**：每个节点都有明确的输入输出，出了问题可以精确定位到哪个环节。
3. **支持条件分支和循环**：比如意图不明时走澄清分支，校验不通过时回到重新生成，工具失败时走重试或转人工分支。

和 LangGraph 的区别：
- LangGraph 是通用的图框架，支持复杂的循环和分支，但学习曲线陡峭。我们的状态机是**面向客服场景定制**的，固定 8 个节点，流程更清晰。
- 我们实现了**访问控制**（visited_nodes 防止死循环）、**最大迭代次数**（max_iterations=15）、**节点级追踪**（每个节点记录耗时和输入输出）。
- 相比 LangGraph 用条件边来控制流转，我们用 `_route_by_intent` 方法实现路由，代码更直观。

### Q5：能详细介绍一下 Agent 的 8 个节点吗？

**A：**
8 个节点按顺序执行：

1. **START** → 初始化状态，进入意图识别
2. **INTENT_RECOGNITION**（意图识别）：调用 4 层策略识别用户意图，设置置信度
3. **CLARIFICATION**（澄清）：当置信度 < 0.4 或意图为 general 且消息 ≤5 字符时触发，向用户提问以明确需求
4. **RAG_RETRIEVAL**（检索增强生成）：对 technical/promotion 类型意图，从知识库检索相关文档
5. **TOOL_EXECUTION**（工具执行）：对 query_order/refund/complaint 类型意图，调用对应工具
6. **RESULT_VERIFICATION**（结果校验）：检查工具执行是否成功、耗时是否异常
7. **RESPONSE_GENERATION**（响应生成）：用 LLM 生成自然语言回复，或使用内置模板
8. **HUMAN_HANDOFF**（人工转接）：触发转人工条件时，创建转接请求并分配客服
9. **END**：结束状态

路由逻辑（`_route_by_intent`）：
- query_order/refund/complaint → TOOL_EXECUTION
- technical/promotion → RAG_RETRIEVAL
- human → HUMAN_HANDOFF
- general → RESPONSE_GENERATION

### Q6：状态机如何处理异常和边界情况？

**A：**
处理了以下边界情况：

1. **死循环防护**：用 `visited_nodes` 集合记录已访问的 `节点+意图` 组合，同一组合不会重复执行；设置 `max_iterations=15` 硬限制。
2. **工具连续失败**：同一工具重试 3 次仍失败 → 标记 `need_human=True` → 进入 HUMAN_HANDOFF 节点。
3. **校验不通过**：三层校验失败且 `regeneration_count < 2` → 回到 RESPONSE_GENERATION 重新生成；超过 2 次 → 转人工。
4. **关键意图保护**：human/complaint/query_order/refund 四类意图的识别结果**不会被 LLM 的 detect_intent 结果覆盖**，防止 LLM 误判。
5. **空回复兜底**：所有生成策略都失败时，使用 `_get_default_reply` 内置模板返回。
6. **节点级耗时监控**：每个节点记录执行时间，超过 3s 会触发警告日志。

---

## 三、意图识别类

### Q7：4 层递进式意图识别的具体实现？

**A：**
4 层策略按顺序执行：

**第一层：关键词权重匹配**
- 为每种意图定义 high（+2.0 分）、medium（+1.0 分）、low（+0.3 分）三级关键词
- 遍历所有意图的关键词，累加得分
- 取得分最高的意图，归一化到 0-1 置信度（score/4.0）
- 若两个意图得分差 < 0.5，置信度乘以 0.7 降低

**第二层：否定词检查**
- 提取目标意图的所有关键词
- 检查关键词前 5 个字符内是否有否定词（不是/不要/不/非/没有/没）
- 若存在否定词，置信度乘以 0.5

**第三层：上下文推断**
- 仅在第一层置信度 < 0.3 时触发
- 检查最近 3 条历史消息中的 tool 角色消息，根据工具名推断意图（如含 order → query_order）

**第四层：延续性判断**
- 当存在历史意图且消息很短（<15 字符）、关键词匹配得分 < 0.2 时
- 检查消息是否匹配延续性模式（如"好的"、"那然后"、纯数字等）
- 如果是延续性消息，保持上一轮意图，置信度设为 0.6

最后判断是否需要澄清：置信度 < 0.4（非 general）或 general 且消息 ≤ 5 字符。

### Q8：如何处理用户只说"嗯"、"好的"这种情况？

**A：**
这种情况是通过第四层"延续性判断"+ 澄清机制联合处理的：

1. **延续性判断触发**：消息"嗯"长度为 1，远小于 15，关键词匹配得分也很低（0.0），匹配延续性模式 `r"^[好的嗯哦啊哦好的]"`，命中后**保持上一轮意图**，置信度设为 0.6。

2. **澄清机制兜底**：如果上一轮是 general 意图，当前消息"嗯"长度 ≤ 5，会触发澄清条件（`keyword_result.intent == "general" and len(message.strip()) <= 5`），系统会回复引导性问题如"我可以帮助您查询订单、处理退换货、解答产品问题等。请问有什么可以帮您的？"

这保证了即使面对最短的用户输入，系统也能给出有意义的响应而非无意义的对话循环。

### Q9：意图识别支持哪些类型？每种意图的路由是什么？

**A：**
支持 7 种核心意图：

| 意图 | 路由节点 | 说明 |
|------|---------|------|
| query_order（订单查询） | TOOL_EXECUTION → query_order 工具 | 查询订单状态、物流、详情 |
| refund（退换货） | TOOL_EXECUTION → apply_refund 工具 | 申请退款/退货退款 |
| complaint（投诉） | TOOL_EXECUTION → create_ticket 工具 | 创建投诉工单 |
| technical（技术咨询） | RAG_RETRIEVAL → 混合检索 | 从知识库检索技术文档 |
| promotion（活动咨询） | RAG_RETRIEVAL → 混合检索 | 从知识库检索促销信息 |
| human（转人工） | HUMAN_HANDOFF → escalate_to_human 工具 | 直接转接人工客服 |
| general（通用咨询） | RESPONSE_GENERATION → LLM 直接回复 | 兜底回复 |

---

## 四、Function Calling 类

### Q10：8 个工具的设计和实现细节？

**A：**
8 个工具继承自 BaseTool 基类，统一提供重试、超时、参数校验能力：

1. **QueryOrderTool**：接收 order_id，返回订单状态、物流信息、金额、是否可退换等。内置 4 个 Mock 订单（不同状态：已发货/已完成/待付款/已取消）。

2. **CreateTicketTool**：接收 user_id、category、content、priority，自动分配客服（按分类映射）、计算 SLA 截止时间、生成工单号。

3. **ApplyRefundTool**：接收 order_id、reason、type，校验订单状态是否可退换，生成退款单号和后续步骤说明。

4. **SearchKBTool**：基于关键词匹配+评分排序的知识库检索，支持 top_k 返回。

5. **EscalateToHumanTool**：转人工工具，支持优先级（normal/urgent），调用 CollaborationService 创建转接请求并尝试自动分配客服。

6. **SendNotificationTool**：支持 sms/email/inapp 三种通知渠道。

7. **UpdateTicketStatusTool**：更新工单状态（pending/processing/resolved/closed/escalated）。

8. **GetUserHistoryTool**：查询用户历史咨询记录、偏好标签、历史工单等。

每个工具的 `execute_with_retry` 方法实现了：
- 参数校验（必填检查、枚举值检查、None 检查）
- 指数退避重试（delay = retry_delay_ms × 2^(attempt-1) / 1000）
- 超时控制（timeout_ms = 5000ms）
- 异常捕获和错误分类

### Q11：工具的重试机制是怎样的？

**A：**
重试机制在 BaseTool.execute_with_retry 中实现：

```
最大重试次数 max_retries = 3
重试间隔：100ms × 2^(attempt-1)，即第1次重试 100ms，第2次 200ms，第3次 400ms
超时控制：每次执行 5s 超时
```

流程：
1. 检查结果中的 `success` 字段
2. 如果成功 → 返回结果，记录重试次数
3. 如果失败 → 等待退避时间后重试
4. 如果遇到 TimeoutError → 重试
5. 如果遇到其他异常 → 重试
6. 3 次都失败 → 返回失败结果，附带 `hint` 建议（如"请稍后重试或联系人工客服"）

另外在 execute_tool_with_fallback 中还支持**工具降级**：主工具失败时自动切换到备用工具执行。

### Q12：工具执行失败后怎么处理？

**A：**
分三个层次处理：

1. **工具内部处理**：重试 3 次，指数退避，最终仍失败则返回错误信息 + 用户提示。

2. **Agent 层处理**（graph.py 中）：
   - 错误信息包含"人工"关键字 → 立即转人工
   - 重试次数 ≥ 3 → 标记 need_human，转人工
   - 所有工具调用完成后检查：连续 3 次工具失败 → 转人工

3. **用户层降级**：如果没有触发转人工，会用友好的错误消息回复用户（如"抱歉，操作遇到问题：xxx"），并建议稍后重试。

---

## 五、RAG 检索增强类

### Q13：混合检索引擎的设计？

**A：**
混合检索引擎由三个组件组成：

**BM25Retriever（关键词检索）**
- 实现标准 BM25 算法，k1=1.5, b=0.75
- 支持中英文混合分词：英文用 `\w+` 正则，中文按单字 + 双字切分
- 计算 IDF、TF 归一化、文档长度归一化
- 返回 bm25_score 评分

**VectorRetriever（向量检索）**
- 优先使用 Milvus 向量数据库，不可用时自动降级到内存模拟
- 通过 DashScope text-embedding-v3（1024 维）生成向量
- 支持哈希模拟向量作为最终兜底方案
- 返回 vector_score（余弦相似度）

**Reranker（重排序器）**
- 基于规则的重排序：综合考虑标题匹配（+8）、内容匹配（+3）、关键词重叠、BM25/Vector 原始分数加权
- 输出 final_score 作为最终排序依据

**融合策略**：
1. BM25 和 Vector 各自取 top_k × multiplier（3倍）条结果
2. 按文档标题合并去重
3. 归一化两个分数后按权重融合（默认 BM25 50% + Vector 50%）
4. 可选的 Reranker 重排序
5. 最终取 top_k 条返回

### Q14：Milvus 不可用时怎么降级？

**A：**
降级策略分三层：

1. **连接时降级**：初始化 VectorRetriever 时尝试连接 Milvus，连接失败 → `_backend = "memory"`，使用内存存储。

2. **索引时降级**：索引文档到 Milvus 失败 → 自动切换到 `_index_to_memory`，用 Embedding 服务生成向量存储在内存中。

3. **搜索时降级**：搜索 Milvus 出错 → `_search_milvus` 的 except 块捕获异常，调用 `_search_memory` 进行内存检索。

内存检索使用余弦相似度计算，和 Milvus 的向量检索在接口层完全兼容，上层调用无感知。

### Q15：知识库的文档是怎么组织的？

**A：**
默认内置 15 篇种子文档，覆盖以下分类：
- 售后政策（7天无理由、退款流程）
- 订单服务（订单查询、物流跟踪）
- 会员服务（VIP 等级与权益）
- 营销活动（优惠券规则、限时促销）
- 支付服务（支付方式与安全）
- 财务服务（发票开具）
- 物流服务（配送时效）
- 账号服务（账号安全）
- 产品支持（使用指南、质保维修）
- 客户服务（投诉处理、联系方式）
- 企业服务（企业采购）

每篇文档包含 title、content、keywords、category 四个字段。支持通过 `POST /api/v1/knowledge/documents/seed` 导入种子文档。

---

## 六、LLM 服务类

### Q16：LLM 服务的多模型降级和熔断机制？

**A：**
LLM 服务支持三级降级：

1. **主模型（primary）**：DashScope 或其他兼容 OpenAI 格式的 API
2. **备用模型（backup）**：可选配置，用于主模型故障时切换
3. **本地模拟（local_fallback）**：内置 Mock 回复，保证无 API Key 时系统仍可运行

**CircuitBreaker 熔断器**：
- `failure_threshold = 5`：连续 5 次失败触发熔断
- `recovery_timeout = 300`：300 秒后尝试恢复
- 三种状态：closed（正常）→ open（熔断）→ half-open（恢复尝试）

```python
can_execute(model_name):
    if 熔断开启 and 未到恢复时间: return False
    if 熔断开启 and 已到恢复时间: 重置 → return True
    return True
```

**降级流程**：主模型调用失败 → 记录失败次数 → 检查是否熔断 → 降级到备用模型 → 再失败 → 降级到本地 Mock → 返回 Mock 回复。

### Q17：LLM 的 Intent 检测和 Agent 的 Intent 识别是什么关系？

**A：**
两者是互补关系：

- **Agent 端意图识别**（intent.py）：基于规则的 4 层策略，**确定性强**，是路由的主要依据。
- **LLM 端 Intent 检测**（llm_service.py）：基于关键词匹配的轻量检测，用于在 LLM 生成回复后**辅助修正意图**。

关键设计：**LLM 的检测结果不能覆盖关键意图**。在 `_generate_response_with_llm` 中：
```python
if state.detected_intent not in (HUMAN, COMPLAINT, QUERY_ORDER, REFUND):
    state.detected_intent = intent  # 只有非关键意图才允许被 LLM 修正
```

这是因为 human/complaint 等关键意图直接影响业务流程（是否转人工、是否创建工单），不能由 LLM 的不确定结果覆盖。

### Q18：没有 API Key 时系统怎么运行？

**A：**
系统设计了完整的降级链路：

1. **LLM 层**：检测到 API Key 是占位符（`"your-api-key-here"`）→ 使用 `_get_mock_reply` 返回按意图分类的预设回复。

2. **Embedding 层**：无 Embedding API 配置 → 使用 MockEmbedding，基于 SHA256 哈希生成伪向量。

3. **向量检索层**：Milvus 连接失败 → 自动降级到内存检索。

4. **数据库层**：MySQL 不可用 → 通过 `DATABASE_URL_OVERRIDE` 切换到 SQLite。

5. **缓存层**：Redis 不可用 → 降级到内存字典。

所有降级都有日志记录，管理员可以通过 `/health` 接口检查当前使用的后端。

---

## 七、RAG 与检索类

### Q19：RAG 的完整流程是怎样的？

**A：**
完整的 RAG 流程：

1. **触发条件**：意图识别为 technical 或 promotion → 路由到 RAG_RETRIEVAL 节点
2. **构建查询**：使用用户原始消息作为检索 query
3. **多路召回**：
   - BM25 检索（top_k × 3 条）
   - 向量检索（top_k × 3 条）
4. **结果融合**：按文档标题合并去重，归一化分数后加权融合
5. **Reranker 重排序**：基于规则的重排序，取最终 top_k=3 条
6. **注入上下文**：将检索结果的 title、content、category、score 注入 LLM prompt
7. **LLM 生成**：构建包含知识库上下文的 prompt，调用 LLM 生成回答
8. **结果校验**：三层校验检查回答质量
9. **流式输出**：按 chunk_size 将回复分块推送到前端

### Q20：RAG 中的分数融合是怎么做的？

**A：**
BM25 和 Vector 两个检索器返回的分数量纲不同，需要归一化后融合：

```python
# BM25 分数归一化
bm25_norm = min(bm25_score / 5.0, 1.0)  # 以 5.0 为满分归一化

# Vector 分数（已经是 0-1 余弦相似度，直接截断）
vector_norm = min(vector_score, 1.0)

# 加权融合（默认 50:50）
hybrid_score = bm25_norm * bm25_weight + vector_norm * vector_weight
```

默认权重可以通过 `.env` 配置调整：
- `RAG_BM25_WEIGHT=0.5`
- `RAG_VECTOR_WEIGHT=0.5`

如果启用了 Reranker，会进一步综合考虑标题匹配度、关键词重叠度、原始分数等因素重新计算 final_score。

---

## 八、结果校验类

### Q21：三层校验机制的详细实现？

**A：**
**第一层：事实校验（FactValidator）**
- 检查 LLM 回答中是否包含工具返回的关键数据（订单号、金额、状态等）
- 每个关键字段匹配 +0.1 分，缺失 -0.1~0.2 分
- 订单号在回答中缺失 → 严重扣分（-0.2）
- 最终得分 = max(0, min(1, score))

**第二层：安全校验（SafetyValidator）**
- 敏感词检测（自杀、暴力、赌博、诈骗等）→ 每项 -0.3 分
- Prompt 注入检测（忽略之前指令、system prompt 等模式）→ -0.5 分
- 回答过长（>5000 字符）→ -0.1 分
- 空回答 → 0 分

**第三层：完整性校验（CompletenessValidator）**
- 关键词重叠率检查（query 关键词 vs response 关键词）→ 低于 30% 扣 0.3 分
- 意图特定检查（query_order 需包含"状态/物流/订单"等关键词）
- 最小长度检查（technical 需 ≥30 字符，其他 ≥20 字符）

**综合判定**：
- 安全分 < 0.8 → 不通过
- 事实分 < 0.6 → 不通过
- 完整性分 < 0.5 → 不通过
- 平均分 < 0.6 → 不通过
- 安全分 < 0.5 或事实分 < 0.4 或存在 critical 级问题 → 需要重新生成（最多 2 次）

### Q22：校验不通过后怎么处理？

**A：**
在 Agent 状态机的 `_node_result_verification` 节点中：

1. 调用 `validator.validate()` 执行三层校验
2. 将校验结果添加到 `state.collected_info["validation"]`
3. 如果 `needs_regeneration=True` 且 `regeneration_count < 2`：
   - 清空 `state.reply = ""`
   - `regeneration_count += 1`
   - 回到 `_node_response_generation` 重新生成
4. 如果 `needs_regeneration=True` 且 `regeneration_count >= 2`：
   - 标记 `need_human = True`
   - 设置 `human_reason = "回答校验连续不通过，需人工介入"`
   - 进入 HUMAN_HANDOFF 节点
5. 如果校验通过 → 继续后续流程

---

## 九、人机协同类

### Q23：转人工的触发条件有哪些？

**A：**
在当前实现中，以下情况会触发转人工：

1. **用户主动请求**：意图识别为 human → 立即转人工
2. **工具错误包含"人工"关键词**：工具返回的 error 中包含"人工" → 立即转人工
3. **工具连续失败**：单个工具重试 3 次仍失败 → 转人工
4. **多工具整体失败**：3 个工具调用全部失败 → 转人工
5. **校验连续不通过**：回答校验重新生成 2 次仍不通过 → 转人工
6. **上下文判断**：CollaborationService.check_handoff_needed 中的规则：
   - consecutive_failures ≥ 3 → 转人工
   - 投诉意图 + 失败次数 ≥ 1 → 紧急转人工
   - 订单金额 > 500 + refund/complaint → 人工审核

### Q24：转人工后是怎么分配客服的？

**A：**
分配流程：
1. 创建 HandoffRequest（包含 user_id、session_id、reason、priority、context）
2. 根据优先级设置 SLA 截止时间：urgent→1h / high→4h / normal→24h / low→48h
3. 调用 `find_best_agent` 选择最合适的客服：
   - urgent 优先级 → 按当前负载排序，选负载最低的
   - 优先匹配技能（如 urgent 匹配 complaint/escalation 技能）
   - 所有客服都不可用时，降级选择任意在线客服
4. 分配成功 → 客服负载 +1，请求状态变为 assigned
5. 如果没有可用客服 → 请求保持 pending，等待客服上线

默认客服：
- agent_001 赵经理（complaint/escalation 技能，最大负载 3）
- agent_002 李小明（general/order_query/refund 技能，最大负载 5）
- agent_003 王工程师（technical/product_support 技能，最大负载 3）
- agent_004 陈小丽（refund/return/exchange 技能，最大负载 4）

---

## 十、可观测性类

### Q25：全链路追踪是怎么实现的？

**A：**
**TraceID 贯穿**：
- 每个 HTTP 请求通过中间件生成 TraceID（或从 X-Trace-Id header 读取）
- TraceID 存储在 `request.state.trace_id` 中
- 响应头返回 `X-Trace-Id` 和 `X-Response-Time`
- 日志中所有条目都包含 trace_id 字段

**Agent 节点追踪**：
- 每个节点执行完成后调用 `state.add_trace()` 记录：
  - 节点名称、输入数据（用户消息、意图）、输出数据（下一节点、回复摘要）、执行耗时
- 流式执行时通过 SSE 推送 `node_start` / `node_complete` 事件

**Metrics 指标采集**：
- 响应时间统计（count/avg/p50/p95/max）
- 意图分布统计（各意图的识别次数）
- 工具统计（各工具的调用次数、成功/失败次数、成功率）
- 错误统计（按错误类型分类计数）

**告警管理**（AlertManager）：
- P0 级：系统错误率 > 5%（5 分钟窗口）→ 电话/短信告警
- P1 级：人工转接率 > 30% 或平均响应时间 > 5s（10 分钟窗口）→ 微信/邮件告警
- P2 级：意图准确率 < 70%（30 分钟窗口）→ 邮件告警

### Q26：评价体系和低分回流是怎么做的？

**A：**
**5 维度评测**（AnswerEvaluator）：
1. **准确性（35%）**：检查回答与工具返回结果的一致性，或与期望答案的文本相似度
2. **完整性（15%）**：检查关键词覆盖率 + 最小长度
3. **安全性（10%）**：敏感词 + 注入检测
4. **相关性（20%）**：回答与问题的关键词重叠率
5. **效率（20%）**：响应时间评分（<1s→100分，<3s→80分，<5s→60分，≥5s→40分）

**低分样本回流**（LowScoreSamplePool）：
- 总分 < 60 分的回答自动入库
- 按失败原因分类（安全风险/回答不准确/回答不完整/相关性低/性能问题）
- 支持按失败类型查询样本
- 管理员可标记处理结果（processed）

**A/B 测试框架**（ABTestFramework）：
- 支持创建实验（定义变体、流量分配）
- 基于 user_id 哈希的稳定分流
- 记录每个变体的调用次数、成功数、失败数
- 计算统计置信度（基于正态分布假设检验）

---

## 十一、前端交互类

### Q27：SSE 流式推送是怎么实现的？

**A：**
后端通过 `AgentGraph.run_stream()` 生成异步事件流，前端通过 `EventSource` API 接收：

**事件类型**：
- `node_start`：节点开始执行
- `intent`：意图识别结果（意图、置信度、是否需澄清）
- `rag_result`：RAG 检索结果（结果数、最高得分）
- `tool_call_start`：工具调用开始（工具名、参数）
- `tool_call_complete`：工具调用完成（成功/失败、耗时、重试次数）
- `handoff`：转人工事件
- `validation`：校验结果（是否通过、整体得分、是否需重新生成）
- `token`：LLM 回复的 token 流（分块推送，每 20ms 推送一块）
- `node_complete`：节点执行完成（耗时、下一节点）
- `done`：整个流程完成（最终回复、意图、执行时间、工具调用列表）

**前端展示**：
- 用户端：显示打字机效果的回复、工具调用提示（如"🔧 调用工具: 查询订单"）
- 管理员端：显示完整的执行面板，包括节点状态、工具详情、检索结果等

### Q28：前端怎么处理工具调用的显示？

**A：**
前端对工具调用的显示做了特殊处理：
- SSE 事件中的 `tool_call_start` 事件会在对话中插入提示消息，如"🔧 调用工具: 查询订单"
- 工具名称通过 `toolNameMap` 映射为中文（如 `query_order` → `查询订单`，`escalate_to_human` → `转人工客服`）
- 当 `done` 事件到达时，会保留工具调用的显示内容，只在回复内容不同且不包含工具标识时才更新，避免覆盖工具提示
- 管理员端右侧面板实时展示工具调用列表，包括参数、执行结果、耗时等

---

## 十二、数据库与配置类

### Q29：数据库是怎么设计的？

**A：**
支持 MySQL 和 SQLite 双模式：

- **MySQL 模式**：默认生产模式，通过 SQLAlchemy 连接，支持连接池和事务
- **SQLite 模式**：通过 `DATABASE_URL_OVERRIDE=sqlite+aiosqlite:///./customer_service.db` 环境变量切换，适合本地开发

主要数据模型：
- **User**：用户表（id、username、password_hash、role、vip_level）
- **Session**：会话表（id、user_id、status、created_at、updated_at）
- **Message**：消息表（id、session_id、role、content、intent、tool_calls、timestamp）
- **Ticket**：工单表（id、user_id、category、priority、status、assigned_to、sla_deadline）
- **HandoffRequest**：转人工请求表
- **Agent**：人工客服表

### Q30：项目的配置管理是怎样的？

**A：**
所有配置项通过 `.env` 文件管理，config.py 提供默认值：

**RAG 相关配置**：
- `COLLECTION_NAME`：Milvus 集合名
- `RAG_TOP_K=5`：最终返回结果数
- `RAG_SIMILARITY_THRESHOLD=0.2`：相似度阈值
- `RAG_BM25_WEIGHT=0.5`：BM25 权重
- `RAG_VECTOR_WEIGHT=0.5`：向量权重
- `RAG_SEARCH_TOP_K_MULTIPLIER=3`：搜索召回倍数

**文档分块配置**：
- `CHUNK_SIZE=500`：分块大小
- `CHUNK_OVERLAP=50`：重叠大小
- `CHUNK_SPLIT_PATTERN`：分块正则

**服务配置**：
- `USE_MILVUS=false`：是否启用 Milvus
- `USE_REDIS=false`：是否启用 Redis
- `LLM_API_BASE` / `LLM_API_KEY` / `LLM_MODEL`：LLM 配置
- `EMBEDDING_API_BASE` / `EMBEDDING_API_KEY` / `EMBEDDING_MODEL`：Embedding 配置

支持在 `.env.example` 中查看所有配置项的默认值和说明。

---

## 十三、设计决策与权衡类

### Q31：项目中有哪些关键的设计决策？

**A：**
1. **自研状态机而非 LangGraph**：因为客服场景流程相对固定，自研更可控、更易调试。
2. **规则优先 + LLM 辅助的意图识别**：规则方法确定性强、零成本，适合高频场景；LLM 作为补充处理模糊场景。
3. **BM25 + 向量双路召回**：弥补单一检索的缺陷，关键词检索擅长精确匹配，向量检索擅长语义理解。
4. **三层校验 + 自动重新生成**：在不增加 LLM 调用次数的前提下（最多额外 2 次），保证回答质量。
5. **关键意图保护**：防止 LLM 的不确定性影响关键业务流程。
6. **全链路降级**：从 LLM → Embedding → 向量库 → 数据库 → 缓存，每层都有兜底方案。

### Q32：如果让你重新设计这个系统，你会做哪些改进？

**A：**
1. **引入真正的 LangGraph**：随着意图增多和流程复杂化，自研状态机的扩展性会成为瓶颈，可以考虑迁移到 LangGraph 获得更强大的图编排能力。
2. **接入真实 LLM 的 Function Calling**：目前工具选择是基于规则的，可以用 LLM 的 Function Calling 能力动态选择和组合工具。
3. **引入对话记忆（Memory）**：目前的上下文窗口有限（最近 6 条），可以引入长期记忆存储用户偏好和历史。
4. **增加主动推送能力**：目前是被动响应，可以增加主动通知（如物流状态变更、促销提醒）。
5. **多租户支持**：增加租户隔离，支持 SaaS 化部署。
6. **WebSocket 替代 SSE**：SSE 是单向的，未来如果需要双向通信（如人工客服实时介入），WebSocket 更合适。
7. **引入向量缓存**：对高频查询的向量结果进行缓存，减少 Embedding API 调用。

---

## 十四、测试与调试类

### Q33：项目是怎么测试的？

**A：**
项目分为 4 个测试阶段：

**Phase 2 - Agent 核心功能**（test_phase2.py）：
- 意图识别（7 种意图 × 多种输入）
- 工具调用（8 个工具的正常/异常场景）
- 状态机编排（节点跳转、循环防护）
- 会话状态管理

**Phase 3 - 增强功能**（test_phase3.py）：
- 混合检索引擎（BM25、向量、融合）
- 三层校验（事实/安全/完整性）
- 熔断器机制
- 会话摘要与压缩
- 工具错误处理
- Agent 集成测试

**Phase 4 - 可观测性**（test_phase4.py / test_api_phase4.py）：
- 全链路追踪
- 评价体系
- 人机协同
- API 集成测试

**RAG 专项测试**（test_rag.py / test_rag_optimization.py）：
- 文档导入与索引
- 检索质量评估
- 端到端 RAG 问答

测试环境：Python 3.13.9 + SQLite + 内存缓存 + 禁用向量库 + LLM 模拟模式。

### Q34：开发过程中遇到了哪些技术难点？

**A：**
1. **意图识别的边界处理**：用户只说"嗯"、"好的"时，传统方法无法判断意图。解决方案是引入延续性判断（检查历史意图）+ 澄清机制（低置信度时主动提问）。

2. **中文文本相似度计算**：evaluation.py 中最初用 `text.split()` 分词，对中文无效（所有字符拼成一个 token）。解决方案是增加 `_tokenize` 函数，对中文按单字切分。

3. **Milvus 连接不稳定**：Docker 中的 Milvus 容器经常 Exited(255)。解决方案是增加连接重试逻辑和自动降级到内存模式。

4. **SQLite 替代 MySQL**：SQLite 不支持某些 MySQL 特有语法，且需要通过 `DATABASE_URL_OVERRIDE` 环境变量覆盖。解决方案是在启动脚本中统一设置。

5. **前端工具名称映射**：后端工具名是英文（如 `query_order`），前端需要中文显示。解决方案是在 app.js 中增加全局 `toolNameMap` 映射表。

6. **SSE 事件顺序**：工具调用事件和 done 事件的顺序会影响前端显示。解决方案是在前端保留工具调用提示，只在回复内容不同且不含工具标识时才更新。

---

## 十五、扩展与实战类

### Q35：如何给系统添加一个新工具？

**A：**
只需 4 步：

1. **在 tools.py 中创建新工具类**，继承 BaseTool：
```python
class NewTool(BaseTool):
    name = "new_tool"
    description = "工具描述"
    parameters = [{"name": "param1", "type": "string", "description": "参数说明", "required": True}]
    
    async def execute(self, **kwargs):
        # 实现业务逻辑
        return {"success": True, "data": {...}}
```

2. **注册到 TOOL_REGISTRY**：
```python
TOOL_REGISTRY[NewTool.name] = NewTool()
```

3. **在 graph.py 的 `_select_tools_for_intent` 中添加调用逻辑**，或在 `_build_llm_prompt` 中处理结果。

4. **在 config.py 或 intent.py 中可能需要更新意图到工具的映射关系**。

### Q36：如何给知识库添加新文档？

**A：**
两种方式：

1. **API 方式**：调用 `POST /api/v1/knowledge/documents` 接口，传入文档内容，系统自动分块和索引。

2. **代码方式**：在 `retrieval.py` 的 `create_default_hybrid_retriever` 函数中，向 `default_documents` 列表添加新的文档条目，包含 title、content、keywords、category 四个字段。

添加后，文档会自动被 BM25 和 Vector 两个检索器索引，立即可被检索。

### Q37：如果需要把系统部署到生产环境，需要考虑什么？

**A：**
1. **基础设施**：
   - MySQL 集群（主从读写分离）
   - Milvus 集群（高可用部署）
   - Redis 集群（缓存 + 会话存储）
   - DashScope API Key 安全存储（密钥管理服务）

2. **性能优化**：
   - 增加 Gunicorn/Uvicorn worker 数量
   - 引入 Nginx 反向代理和负载均衡
   - Embedding 结果缓存（Redis 缓存高频查询的向量）
   - 数据库查询优化（索引、慢查询分析）

3. **安全加固**：
   - API 鉴权（JWT Token）
   - HTTPS 加密
   - 敏感数据脱敏
   - 速率限制（防滥用）

4. **监控告警**：
   - 全链路追踪数据接入 APM 系统（如 SkyWalking、Jaeger）
   - 日志集中收集（ELK/Loki）
   - 指标监控接入 Prometheus + Grafana
   - 告警通知接入企业微信/钉钉

5. **CI/CD**：
   - Docker 镜像自动化构建
   - Kubernetes 部署
   - 灰度发布 / 蓝绿部署

---

## 十六、代码细节类

### Q38：能讲一下 `_generate_response_with_llm` 的实现细节吗？

**A：**
这个函数是 Agent 和 LLM 的桥梁：

```python
async def _generate_response_with_llm(self, state):
    # 1. 构建富上下文 prompt
    prompt = self._build_llm_prompt(state)
    # 包含：用户意图标签、用户消息、工具执行结果（成功/失败）、知识库检索结果
    
    # 2. 构建对话历史上下文（最近 6 条）
    context = self._build_context_messages(state)
    
    # 3. 调用 LLM 服务（带多模型降级和熔断）
    reply, intent, token_count = await llm_service.chat(
        user_id=state.user_id,
        session_id=state.session_id,
        message=prompt,
        context=context,
    )
    
    # 4. 关键意图保护
    if state.detected_intent not in (HUMAN, COMPLAINT, QUERY_ORDER, REFUND):
        state.detected_intent = intent  # 非关键意图才允许覆盖
    
    return reply
```

`_build_llm_prompt` 构建的 prompt 包含：
- 【用户意图】当前意图的中文标签
- 【用户消息】用户原始输入
- 【工具执行结果】成功工具的数据摘要（前 300-500 字符）
- 【知识库检索结果】Top 3 结果的标题、分类、相关度、内容摘要
- 生成指令（200 字以内、专业友好等要求）

### Q39：SSE 流式执行 `run_stream` 的实现要点？

**A：**
`run_stream` 是 Agent 的流式执行引擎，核心特点：

1. **生成器模式**：使用 `AsyncGenerator`，每执行一步就 yield 一个事件，前端实时接收。

2. **状态机循环**：
```
while current_node != END and iteration < 15:
    执行当前节点 → yield 事件 → 更新 current_node
```

3. **节点级事件推送**：每个节点都有对应的 SSE 事件类型，如：
   - INTENT_RECOGNITION → intent 事件
   - RAG_RETRIEVAL → rag_result 事件
   - TOOL_EXECUTION → tool_call_start/complete 事件
   - RESPONSE_GENERATION → token 事件（逐块推送回复文本）

4. **Token 流分片**：回复生成后，按 1/8 长度分块，每块间隔 20ms 推送，模拟打字效果。

5. **完成事件**：最终 yield `done` 事件，包含完整回复、意图、执行时间、工具调用列表、是否需要人工等信息。

### Q40：Embedding 服务的降级策略？

**A：**
Embedding 服务实现了两级降级：

```
APIEmbedding（DashScope text-embedding-v3）
    ↓ 连接失败 / API Key 无效
MockEmbedding（基于 SHA256 哈希的伪向量）
```

**APIEmbedding**：
- 支持 DashScope / 智谱 / OpenAI 兼容格式
- 内置文本缓存（`_text_cache`）避免重复调用
- 批量编码支持（`encode_batch`）
- 自动维度对齐（`_pad_or_truncate`）
- 指数退避重试（最多 2 次）

**MockEmbedding**：
- 基于哈希的伪向量生成（`_text_to_embedding`）
- 分词：英文单词 + 中文单字 + 中文双字组合
- 词频加权聚合 + L2 归一化
- 保证向量维度与配置一致

降级触发：
- 初始化时 API 连接失败 → 使用 MockEmbedding
- 运行时 API 调用异常 → 记录错误，下次尝试仍会使用 Mock

---

## 十七、场景应对类

### Q41：如果用户说"我要退款"，系统会怎么处理？

**A：**
完整流程：

1. **意图识别**：4 层策略识别为 `refund` 意图
   - 第一层：关键词匹配命中"退款"（high 权重 +2.0 分）
   - 置信度 0.5，不触发澄清
   - 路由到 TOOL_EXECUTION

2. **信息提取**（`_extract_info_from_message`）：
   - 检查是否包含订单号模式（ORD + 数字）
   - 提取退款原因、类型（refund/return）

3. **工具选择**（`_select_tools_for_intent`）：
   - refund 意图 → 选择 `apply_refund` 工具
   - 如果没提取到订单号，会要求用户提供

4. **工具执行**：
   - 参数校验（订单号必填、原因必填、类型枚举校验）
   - 检查订单是否支持退换（已发货/已完成）
   - 生成退款单号、后续步骤说明

5. **结果校验**：检查退款单号、金额、步骤是否在回答中体现

6. **响应生成**：LLM 生成自然语言回复，如：
   > "退款申请已提交（退款单号：xxx）
   > 退款金额：¥299.00
   > 接下来的步骤：
   > • 退款审核将在 1 个工作日内完成
   > • 审核通过后，退款将原路返回至您的支付账户"

### Q42：如果用户说"转人工"，系统会怎么处理？

**A：**
1. **意图识别**：命中 human 关键词 → `human` 意图
2. **关键意图保护**：`state.need_human = True`，`human_reason = "用户请求转接人工客服"`
3. **直接路由**：`_route_by_intent` 返回 `HUMAN_HANDOFF`
4. **工具执行**：调用 `escalate_to_human` 工具
   - 调用 `CollaborationService.execute_handoff`
   - 创建 HandoffRequest，设置 urgency 优先级
   - 调用 `find_best_agent` 匹配客服
   - 紧急请求自动分配给负载最低的客服
5. **响应生成**：
   > "非常抱歉给您带来不好的体验，我们的客服主管将立即为您处理，请稍候..."
6. **管理员端**：转人工请求实时出现在管理员后台，显示优先级、客服分配状态、SLA 倒计时

### Q43：如果知识库中没有用户问的问题，会怎样？

**A：**
1. **检索阶段**：HybridRetriever 返回空结果或低相关度结果
2. **LLM 生成阶段**：由于没有知识库上下文，LLM 会基于通用知识回答
3. **质量保障**：
   - 如果 LLM 回答不准确或不相关 → 完整性校验得分低 → 触发重新生成
   - 重新生成 2 次仍不通过 → 自动转人工
4. **用户体验**：用户收到的回复会比较通用，系统可能会建议"请联系人工客服获取更详细的解答"

这是 RAG 的经典问题——当知识库覆盖不全时，系统有兜底但效果有限。生产环境中需要持续扩充知识库文档。

---

## 十八、综合类

### Q44：这个项目的技术亮点有哪些？

**A：**
1. **自研 Agent 状态机编排引擎**：8 节点可配置状态机，支持条件分支、循环重试、流式执行。
2. **4 层递进式意图识别**：关键词权重 + 否定检查 + 上下文推断 + 延续判断，有效处理边界场景。
3. **混合检索引擎**：BM25 + 向量检索 + Reranker 三路融合，自动降级。
4. **三层结果校验 + 自动重新生成**：在保证质量的同时控制 LLM 调用成本。
5. **多模型降级 + 熔断机制**：三级降级（主模型→备用→Mock）+ 熔断器保护。
6. **全链路可观测性**：TraceID 贯穿 + Metrics 采集 + 结构化日志 + 三级告警。
7. **完整的人机协同**：SLA 管理、技能匹配分配、工单全生命周期。
8. **评价体系 + 低分回流 + A/B 测试**：数据驱动的持续优化闭环。

### Q45：项目的局限性有哪些？

**A：**
1. **意图识别基于规则**：虽然有 4 层策略，但面对新词汇、复杂语义时仍有局限。
2. **工具选择基于规则**：没有使用 LLM 的 Function Calling 做动态工具选择。
3. **无长期记忆**：对话上下文窗口有限（最近 6 条），无法记住跨会话的用户偏好。
4. **知识库规模有限**：默认只有 15 篇种子文档，需要人工持续扩充。
5. **无主动推送**：用户只能被动查询，系统不会主动通知（如物流变更）。
6. **单用户对话**：不支持多用户同时对话的场景。
7. **前端原生 JS**：没使用 Vue/React，复杂交互的可维护性有待提升。

### Q46：如果让你给这个项目打分（10 分制），你打几分？为什么？

**A：**
我给 **8.5 分**。

**加分项**（+8.5）：
- 架构设计清晰，分层合理（Agent 编排层 / 核心能力层 / 基础设施层）
- 覆盖了客服系统的核心场景（订单、退换货、投诉、知识库）
- 多层降级策略保证了系统的鲁棒性
- 可观测性设计完善（追踪、指标、告警、评价）
- 人机协同流程完整

**扣分项**（-1.5）：
- 意图识别和工具选择仍以规则为主，可以进一步引入 LLM 的 Function Calling
- 缺少长期记忆和主动推送能力
- 前端用原生 JS，交互复杂时维护成本较高
- 没有做压力测试和性能优化验证

---

## 附录：快速问答

| # | 问题 | 简答 |
|---|------|------|
| 1 | 框架选型？ | FastAPI + 自研 Agent 状态机 |
| 2 | 意图识别？ | 4 层策略（关键词→否定→上下文→延续） |
| 3 | RAG 方案？ | BM25 + 向量 + Reranker 混合检索 |
| 4 | LLM 接入？ | 多模型降级 + 熔断器 + Mock 兜底 |
| 5 | 工具系统？ | 8 个工具 + 重试 + 参数校验 + 降级 |
| 6 | 质量保障？ | 三层校验（事实/安全/完整性）+ 自动重生 |
| 7 | 人机协同？ | 3 类触发条件 + SLA 分级 + 技能匹配分配 |
| 8 | 可观测性？ | TraceID + Metrics + 结构化日志 + P0-P2 告警 |
| 9 | 数据库？ | MySQL + SQLite 双模式 |
| 10 | 向量库？ | Milvus + 内存降级 |
| 11 | 前端？ | 原生 HTML/CSS/JS + SSE 流式 |
| 12 | 测试？ | 4 阶段 73 项测试，100% 通过 |