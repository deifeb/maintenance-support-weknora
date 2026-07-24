# Maintenance AI Core

`maintenance-ai` 是维修保障系统的可复用大模型编排核心包，不依赖 FastAPI、SQLAlchemy 或数据库。专业需求数量、库存缺口和可靠性参数仍由确定性业务服务产生；本包只负责自然语言解析、模型路由、证据整理、受限计划、审查解释和报告章节生成。

## 能力

- `OllamaProvider`：本地 Ollama 文本、结构化输出、流式响应和健康检查；
- `OpenAICompatibleProvider`：OpenAI、DeepSeek、通义兼容接口、vLLM 和企业兼容网关；
- `DeterministicTestProvider`：无需网络的稳定测试模型；
- `RuleFallbackProvider`：模型不可用时的显式规则降级；
- 按功能、模型能力、上下文长度和数据敏感等级进行路由；
- `CONFIDENTIAL`、`RESTRICTED` 数据禁止远程发送；
- Pydantic 结构化输出校验和有限修复；
- 带字段来源、置信度、风险等级和确认状态的场景草稿；
- 结构化证据包、冲突识别和引用；
- 工具白名单、计划依赖校验和固定确认等级；
- 审查解释及确定性报告章节生成。

## 安装与验证

```powershell
cd extensions\maintenance-ai
python -m pip install --upgrade pip "setuptools>=75" wheel
python -m pip install -e ".[dev]"
python -m pytest -v
python -m ruff check src tests
python -m ruff format src tests --check
python -m compileall -q src
```

默认测试不访问真实模型。真实服务测试由 `maintenance-api/tests/external` 提供。

## 数据安全

模型请求使用四级敏感标记：`PUBLIC`、`INTERNAL`、`CONFIDENTIAL`、`RESTRICTED`。模型路由器不会因为远程模型能力更强而绕过敏感数据限制。规则降级结果始终携带：

```text
execution_mode = RULE_FALLBACK
llm_generated = false
fallback_reason = ...
```

模型不得生成最终器材数量、补造可靠性参数、覆盖用户已确认字段或调用未注册工具。
