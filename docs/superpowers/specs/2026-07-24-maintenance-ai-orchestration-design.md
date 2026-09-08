# 维修器材需求系统实施计划 04：LLM、编排、审查与报告设计

- 日期：2026-07-24
- 基线分支：`feature/demand-calculation-engine`
- 基线提交：`cb5261a923bc66cddfe06d7115ad4d6802c6dc49`
- 设计状态：已通过逐节评审

## 1. 目标

在不改造 WeKnora 核心、不削弱现有确定性需求计算能力的前提下，增加可复用的 AI 核心包和 Maintenance API 适配层，形成以下闭环：

```text
自然语言任务描述
→ 风险分级场景解析
→ WeKnora 证据检索与主数据匹配
→ 受限执行计划
→ 确定性工具编排
→ 用户确认
→ 需求计算与库存缺口
→ 需求清单审查
→ 结果解释
→ Markdown、JSON、DOCX 报告
```

本阶段同时支持本地 Ollama、远程 OpenAI-compatible 模型和规则降级，并确保所有专业数值、参数、状态和引用可追溯。

## 2. 核心原则

1. LLM 负责理解、规划、解释和写作，不负责专业数值计算。
2. 需求数量、置信区间、库存缺口、修理回流和保障率只能由确定性业务服务产生。
3. 装备构型、可靠性参数和器材关系只能来自数据库、用户确认或可追溯证据。
4. 所有结构化模型输出必须通过 Pydantic 和业务规则双重校验。
5. LLM 不能直接操作数据库、执行 SQL、运行 Python、发起任意 HTTP 请求或调用未注册工具。
6. 正式计算、场景发布、任务取消和敏感外发必须经过后端确认状态机。
7. 模型不可用时，核心业务流程通过 `RULE_FALLBACK` 继续运行。
8. 已发布场景、正式计算结果和正式报告不可原地覆盖，只能生成新版本。
9. WeKnora 继续负责知识库、文档解析、向量检索、GraphRAG、通用问答和 MCP 接入。
10. 本阶段不新增独立微服务进程、Redis 或外部消息队列。

## 3. 总体架构

```text
用户 / WeKnora / 后续 Streamlit
                │
                ▼
extensions/maintenance-api
├─ AI 会话与消息接口
├─ SSE 流式事件接口
├─ 确认与权限状态机
├─ 业务工具注册中心
├─ 会话、审计和任务持久化
├─ 需求计算、库存和修理业务适配
└─ 报告文件导出
                │
                ▼
extensions/maintenance-ai
├─ Provider Protocol
│  ├─ OllamaProvider
│  ├─ OpenAICompatibleProvider
│  ├─ DeterministicTestProvider
│  └─ RuleFallbackProvider
├─ Model Router
├─ Structured Output Validator
├─ Natural-language Scenario Parser
├─ Evidence Package Builder
├─ Restricted Planner
├─ Deterministic Orchestrator Core
├─ Review Explanation Engine
└─ Report Section Generator
                │
       ┌────────┼─────────┐
       ▼        ▼         ▼
 WeKnora RAG  需求计算引擎  业务数据库
```

### 3.1 `extensions/maintenance-ai`

负责统一模型调用、模型路由、结构化输出、场景解析、证据包处理、受限计划、审查解释和报告章节生成。该包不直接发布场景、不直接写业务数据库、不直接修改计算结果。

### 3.2 `extensions/maintenance-api`

作为业务执行和安全边界，负责工具注册、计划校验、权限与确认、业务服务调用、会话和审计持久化、异步任务、SSE 以及报告导出。

## 4. 模型供应商与路由

### 4.1 统一协议

```python
class LLMProvider(Protocol):
    async def complete_text(self, request: TextCompletionRequest) -> TextCompletionResult: ...
    async def complete_structured(
        self,
        request: StructuredCompletionRequest,
        response_model: type[BaseModel],
    ) -> StructuredCompletionResult: ...
    async def stream_text(self, request: TextCompletionRequest) -> AsyncIterator[StreamEvent]: ...
    async def health_check(self) -> ProviderHealth: ...
```

统一元数据包含 provider、model、request_id、finish_reason、latency_ms、token 数、重试次数、结构化校验次数、降级标记和原始响应摘要哈希。

### 4.2 Provider

- `OllamaProvider`：本地调用，支持文本、流式、JSON Schema、健康检查、超时和有限重试。
- `OpenAICompatibleProvider`：通过 `httpx` 接入 OpenAI、DeepSeek、通义兼容接口、vLLM 和企业网关。
- `DeterministicTestProvider`：固定输出并可模拟超时、无效 JSON、服务不可用和敏感外发拒绝。
- `RuleFallbackProvider`：执行有限的规则解析、模板解释和固定报告章节，不伪装成 LLM。

### 4.3 路由策略

```text
功能默认模型
→ 请求级 provider/model 覆盖
→ 权限校验
→ 数据敏感等级筛选
→ 模型能力筛选
→ 上下文长度检查
→ 主模型
→ fallback_chain
→ RULE_FALLBACK
```

敏感等级为 `PUBLIC`、`INTERNAL`、`CONFIDENTIAL`、`RESTRICTED`。后两级禁止调用远程模型，用户显式指定远程模型也不能绕过。

### 4.4 结构化输出修复

```text
JSON 提取
→ 语法解析
→ Pydantic 校验
→ 业务规则校验
→ 来源约束校验
```

第一层只进行确定性修复；第二层允许同一模型最多两次结构修复，但不得改变业务含义。持续失败后进入备用模型或规则降级。

## 5. 场景解析与混合澄清

`ScenarioDraft` 包含场景名称、装备型号、构型版本、任务时间、阶段、装备分组、年龄分组、使用强度、服务水平、计算方法、修理策略、共同冲击策略、参数覆盖、假设、澄清项和阻断项。

每个关键字段同时保存值、来源类型、来源引用、置信度、是否确认和风险等级。来源优先级为：

```text
USER_CONFIRMED
> USER_PROVIDED
> MASTER_DATA
> KNOWLEDGE_RETRIEVED
> SYSTEM_DEFAULT
> LLM_INFERRED
```

低风险字段可使用系统默认值并醒目标注；中风险字段给出推荐值和候选项；以下高风险字段缺失时阻止正式计算：装备型号、构型版本、装备数量、任务阶段及持续时间、使用强度、可靠性参数来源、服务水平、修理周转策略和共同冲击策略。

解析结果状态为 `READY_FOR_PREVIEW`、`CLARIFICATION_REQUIRED` 或 `BLOCKED`。

主数据匹配顺序为精确编码、唯一名称、别名、模糊候选和用户选择。存在多个候选时不得自动选取相似度最高项作为正式事实。

## 6. WeKnora 证据包

```python
class EvidenceRetriever(Protocol):
    async def retrieve(self, query: EvidenceQuery) -> EvidencePackage: ...
```

`EvidencePackage` 包含结构化事实、参数证据、规则证据、精选原文、引用、冲突、缺失证据和检索元数据。每条证据保存适用装备、构型、有效期、来源文档、页码、知识节点、chunk 引用、检索分数、敏感等级和状态。

状态包括 `VALID`、`STALE`、`CONFLICTED`、`INCOMPLETE`、`UNVERIFIED`。只有 `VALID` 证据可自动补全字段。高影响参数冲突必须由用户确认，不能自动覆盖已发布参数。

## 7. 受限计划器与确定性编排器

### 7.1 首版意图

```text
GENERAL_QA
SCENARIO_PARSE
SCENARIO_CREATE
SCENARIO_REVIEW
DEMAND_PREVIEW
DEMAND_CALCULATE
CALCULATION_EXPLAIN
INVENTORY_GAP_ANALYZE
DEMAND_LIST_REVIEW
MODEL_COMPARE
REPORT_GENERATE
TASK_STATUS_QUERY
TASK_CANCEL
SESSION_RESUME
```

每个意图绑定允许工具集合。计划必须通过 Schema、依赖图、意图匹配、权限、风险确认和敏感性校验。编排器可以提高确认等级，不能降低工具固定风险等级。

每个工具显式声明名称、版本、输入输出模型、权限、确认等级、幂等性、超时、重试策略、允许意图和允许敏感等级。禁止任意 SQL、Python、Shell、HTTP 和任意文件读取工具。

首版工具覆盖主数据、构型、场景、需求计算、库存、修理、审查、证据和报告，并提供三个固定复合工具：

- `prepare_demand_scenario`；
- `run_demand_assessment`；
- `prepare_management_report`。

复合工具内部顺序由代码固定，不由 LLM 生成。

## 8. 会话、状态机与确认

```text
CREATED
→ UNDERSTANDING
→ CLARIFICATION_REQUIRED
→ PLANNED
→ EXECUTING
→ CONFIRMATION_REQUIRED
→ WAITING_ASYNC_TASK
→ PARTIALLY_COMPLETED / COMPLETED / FAILED
```

状态只能由确定性编排器推进。

确认等级：

- `NONE`：只读查询；
- `IMPLICIT`：临时草稿和建议；
- `EXPLICIT`：正式计算和正式报告；
- `SECONDARY`：场景发布、任务取消、覆盖性操作和敏感外发。

确认请求保存参数预览、影响对象、风险等级、外发情况、模型和工具、有效期、令牌和输入摘要。参数变化后旧确认失效，普通聊天消息不能替代结构化批准接口。

核心 SSE 事件包括会话启动、意图识别、澄清、场景更新、证据检索、计划创建和校验、工具开始和完成、确认、模型路由、降级、计算关联、审查完成、报告章节完成、完成和失败。客户端通过 `session_id + last_event_sequence` 恢复，已成功步骤不重复执行。

## 9. 持久化模型

本阶段新增 19 张表：

```text
ai_sessions
ai_messages
ai_session_snapshots
ai_execution_plans
ai_plan_steps
ai_tool_calls
ai_confirmation_requests
ai_events
ai_model_calls
ai_evidence_packages
ai_evidence_items
ai_review_runs
ai_review_findings
ai_report_jobs
ai_report_versions
ai_report_sections
ai_report_citations
ai_report_validation_findings
ai_report_exports
```

大型工具输出只保存业务对象引用和摘要，不复制完整计算结果。会话快照保存场景草稿、字段来源、执行上下文、待确认事项、已完成步骤和证据包引用。

## 10. 审查引擎与解释边界

确定性审查覆盖数据完整性、构型与器材适配、可靠性参数合理性、需求数量异常、库存与保障能力、修理周转、替代互斥配套关系以及证据和版本一致性。

每条发现保存规则编号、规则版本、严重程度、阻断级别、影响对象、观测值、期望范围、证据引用、计算引用、建议动作和 LLM 解释。

严重程度为 `INFO`、`WARNING`、`ERROR`、`CRITICAL`；阻断级别为 `NONE`、`BLOCK_REPORT_FINALIZATION`、`BLOCK_FORMAL_CALCULATION`、`BLOCK_SCENARIO_PUBLISH`。

LLM 可以解释原因、业务影响和建议优先级，但不能修改严重程度、阻断级别、删除规则发现、声称问题已解决或生成新的需求数量。

## 11. 报告生成

首版支持需求计算报告、库存缺口与保障分析报告、管理决策综合报告。

报告骨架、核心数据、表格、引用和版本信息由后端确定性生成。LLM 只生成管理摘要、风险解释、模型差异说明、保障建议、决策事项和结论。

正式报告前必须校验：

- 文中数量来自固定计算快照；
- 库存和修理数据来自固定快照；
- 缺口、百分比、表格总计和明细正确；
- 章节间数字、单位、日期和版本一致；
- LLM 文字中的数字均能匹配允许数字白名单；
- 所有引用对象存在、有效、相关且有访问权限。

数字或引用校验失败时报告保持 `DRAFT`，不得进入 `FINAL`。

导出格式为 Markdown、JSON 和 DOCX。DOCX 使用固定模板和 `python-docx` 填充已验证内容，首版不生成 PDF。

## 12. API 边界

```text
POST   /api/v1/ai/sessions
GET    /api/v1/ai/sessions/{session_id}
POST   /api/v1/ai/sessions/{session_id}/messages
GET    /api/v1/ai/sessions/{session_id}/events
GET    /api/v1/ai/sessions/{session_id}/stream
POST   /api/v1/ai/sessions/{session_id}/resume
POST   /api/v1/ai/sessions/{session_id}/cancel

GET    /api/v1/ai/confirmations/{confirmation_id}
POST   /api/v1/ai/confirmations/{confirmation_id}/approve
POST   /api/v1/ai/confirmations/{confirmation_id}/reject

GET    /api/v1/ai/model-routes
POST   /api/v1/ai/model-routes/preview
GET    /api/v1/ai/providers/health

POST   /api/v1/ai/reviews/scenarios
POST   /api/v1/ai/reviews/demand-lists
GET    /api/v1/ai/reviews/{review_id}
GET    /api/v1/ai/reviews/{review_id}/findings

POST   /api/v1/ai/reports
GET    /api/v1/ai/reports/{report_id}
POST   /api/v1/ai/reports/{report_id}/generate
POST   /api/v1/ai/reports/{report_id}/validate
POST   /api/v1/ai/reports/{report_id}/finalize
GET    /api/v1/ai/reports/{report_id}/exports/{format}
```

普通快速查询使用同步 REST；场景解析、工具编排和解释使用 SSE；正式计算、批量审查和复杂报告使用异步任务，并支持 SSE 或轮询恢复。

## 13. 安全与可观测性

密钥只来自环境变量、Docker Secret、企业密钥服务或本机受保护配置，不进入 Git、数据库明文字段、日志、SSE 或报告。检索文档一律视为不可信数据，不能改变系统约束和工具权限。工具输入通过 Pydantic、工作区权限和对象访问三重校验。远程调用按敏感等级硬阻断。

结构化日志包含 trace、session、plan、step、tool、model、provider、耗时、状态和错误码，但不保存密钥、完整系统提示词、完整敏感输入或完整证据原文。

指标覆盖模型成功率、超时率、结构化输出失败率、延迟、fallback 次数、会话完成率、澄清率、确认率、工具失败率、自动补全率、报告数字校验失败数和引用有效率。

## 14. 异常、重试与一致性

错误分为 Provider、场景解析、证据、工作流、专业业务和报告六层。业务参数无效、权限不足、高风险字段缺失和正式操作未确认不得通过更换模型掩盖。

数据库采用短事务：先保存状态，再执行外部模型或工具，再以新事务保存结果、事件和快照。模型调用期间不持有数据库事务。

幂等键由会话、计划步骤、工具版本和规范化输入摘要构成。发布、取消、正式计算和正式报告使用独立业务幂等令牌。客户端断线重试不得创建重复任务。

## 15. 测试策略

`maintenance-ai` 单元测试覆盖 Provider 转换、流式解析、结构化输出、模型能力筛选、敏感路由、降级、场景字段来源、证据冲突、计划 Schema 和提示词版本。

Maintenance API 测试覆盖 19 张表、迁移、会话状态、确认令牌、事件序列、幂等、工具注册、权限、审计、报告状态和导出。

使用 `DeterministicTestProvider` 和伪 WeKnora 检索器完成从自然语言场景到 DOCX 报告的端到端测试。故障测试覆盖 Ollama 不可用、远程超时、无效 JSON、全部模型故障、敏感远程阻断、WeKnora 故障、工具超时、断线恢复、确认过期、重复提交、报告中断和 DOCX 失败。

真实模型测试使用 `ollama`、`openai_compatible`、`external`、`integration` 标记隔离。Ollama 冒烟测试为本地验收必测项；远程密钥未配置时相关测试跳过。

## 16. 性能目标

- AI 会话创建和读取 P95 小于 300 ms；
- 非模型状态查询 P95 小于 500 ms；
- SSE 首事件小于 1 s；
- 计划校验小于 200 ms；
- 不含 WeKnora 服务时间的证据包整理小于 1 s；
- 1,000 条器材规则审查小于 5 s；
- Markdown/JSON 导出小于 3 s；
- DOCX 导出小于 10 s；
- 服务重启后中断任务恢复小于 30 s。

本地模型耗时记录模型名称、量化版本、硬件、上下文、token、首 token 延迟和总耗时，不用单一绝对阈值否定适配正确性。

## 17. 配置与部署

```text
config/ai-models.yaml
config/ai-routes.yaml
config/ai-tools.yaml
config/ai-prompts.yaml
config/review-rules.yaml
config/report-templates.yaml
```

运行形态保持为 Maintenance API 进程、`maintenance-ai` Python 包、SQLite、WeKnora 和 Ollama。初始化脚本必须幂等，默认配置不得自动下载大型模型。模型缺失时返回 `CONFIGURED_BUT_MODEL_MISSING`。

## 18. 非目标

本阶段不实现 Streamlit 企业界面、WeKnora 核心重构、独立 AI 微服务、Redis/Celery、自动修改正式可靠性参数、自动写库存或修理状态、通用代码执行、任意 SQL、任意网络工具、PDF 报告、自动下载或训练大模型以及资源配置优化算法本身。

## 19. 验收标准

实施计划 04 完成必须同时满足：

1. `maintenance-ai` 独立包可安装、可测试；
2. Ollama、OpenAI-compatible 和 Deterministic Provider 可用；
3. 模型路由、敏感控制和规则降级有效；
4. 自然语言场景解析和风险分级澄清有效；
5. 受限计划器不能调用白名单外工具；
6. 确认状态机、幂等和 SSE 断点续传有效；
7. 需求清单规则审查与 LLM 解释边界有效；
8. Markdown、JSON、DOCX 报告可生成；
9. 正式报告数字与引用全部通过校验；
10. 迁移和初始化脚本连续执行两次结果一致；
11. Ruff、单元测试、集成测试和编译检查通过；
12. 本地 Ollama 端到端冒烟测试通过；
13. 工作区无密钥、无未追踪运行数据、无未说明降级结果。
