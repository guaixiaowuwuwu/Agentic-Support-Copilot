# OpenAI opt-in smoke

这条 smoke 只用于本地或受控演示环境有 OpenAI-compatible key 时验证真实链路。CI 和默认本地回归继续使用 deterministic fallback，不依赖外部 API。

## 环境变量

必需变量：

```bash
SUPPORT_COPILOT_LLM_ENABLED=true
SUPPORT_COPILOT_LLM_BASE_URL=https://api.openai.com/v1
SUPPORT_COPILOT_LLM_MODEL=gpt-4.1-mini
SUPPORT_COPILOT_LLM_API_KEY="$OPENAI_API_KEY"
SUPPORT_COPILOT_EMBEDDING_PROVIDER=openai_compatible
SUPPORT_COPILOT_EMBEDDING_BASE_URL=https://api.openai.com/v1
SUPPORT_COPILOT_EMBEDDING_MODEL=text-embedding-3-small
SUPPORT_COPILOT_EMBEDDING_API_KEY="$OPENAI_API_KEY"
```

`scripts/openai_smoke.py` 默认使用 `SUPPORT_COPILOT_STORE=memory`、`APP_ENV=development` 和本地 header 身份，因此不需要先启动 API server 或 PostgreSQL。你也可以显式设置 store/database 变量来验证自己的运行环境。

## 运行

```bash
SUPPORT_COPILOT_LLM_ENABLED=true \
SUPPORT_COPILOT_LLM_BASE_URL=https://api.openai.com/v1 \
SUPPORT_COPILOT_LLM_MODEL=gpt-4.1-mini \
SUPPORT_COPILOT_LLM_API_KEY="$OPENAI_API_KEY" \
SUPPORT_COPILOT_EMBEDDING_PROVIDER=openai_compatible \
SUPPORT_COPILOT_EMBEDDING_BASE_URL=https://api.openai.com/v1 \
SUPPORT_COPILOT_EMBEDDING_MODEL=text-embedding-3-small \
SUPPORT_COPILOT_EMBEDDING_API_KEY="$OPENAI_API_KEY" \
  .venv/bin/python scripts/openai_smoke.py
```

## 验证内容

脚本会：

1. 检查必需环境变量。缺失、关闭或 placeholder key 时跳过并返回 0。
2. 读取 `/api/health`，只打印 enabled、provider、model、base URL configured、API key configured 等非敏感状态。
3. 创建一篇 API 401 runbook 知识库文档。
4. 触发 `/api/knowledge/embeddings/ingest`，确认状态为 `embedded`。
5. 创建一个 API 401 工单并启动 run。
6. 等待 run 到达 `awaiting_approval`，确认产生 draft reply。
7. 查询 `llm_call_completed` 审计记录，确认 LLM draft 成功；如果发生 policy fallback，会打印 fallback 状态。

## 安全边界

- 脚本和 API 响应都不打印真实 API key、token 或 secret。
- `/api/health` 和 `/api/admin/config` 不返回真实 base URL 或 API key，只返回 configured 布尔状态和 model/provider 名称。
- LLM 失败时工作流仍会 fallback 到 deterministic draft；smoke 会把失败摘要做脱敏后输出并返回非零。
