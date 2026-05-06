# 明鉴 MCP Server — 工具文档

> 明鉴通过 MCP (Model Context Protocol) 2024-11-05 协议将自身能力暴露为工具，供外部 AI 客户端调用。

## 启用方式

在 `.env` 中设置：

```bash
PLANAGENT_MCP_ENABLED=true
```

或通过环境变量：

```bash
export PLANAGENT_MCP_ENABLED=true
```

## 传输端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/mcp/sse` | GET | SSE 传输 — 建立服务端事件流连接 |
| `/mcp/messages` | POST | SSE 传输 — 客户端发送消息（需 `?session_id=`） |
| `/mcp` | POST | Streamable HTTP 传输 — 单端点请求/响应 |

### SSE 连接示例

```bash
# 1. 建立 SSE 连接
curl -N http://localhost:8000/mcp/sse
# 返回: event: endpoint\ndata: /mcp/messages?session_id=<uuid>\n\n

# 2. 发送 initialize 请求
curl -X POST "http://localhost:8000/mcp/messages?session_id=<uuid>" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'

# 3. 发送 notifications/initialized 通知
curl -X POST "http://localhost:8000/mcp/messages?session_id=<uuid>" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'

# 4. 列出工具
curl -X POST "http://localhost:8000/mcp/messages?session_id=<uuid>" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

### Streamable HTTP 示例

```bash
# 单端点调用
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

---

## 工具列表

### 1. `submit_task` — 提交决策任务

触发明鉴的数据采集、分析和辩论流程，返回任务 ID。

**参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `query` | string | ✅ | — | 决策问题或分析主题 |
| `domain_id` | string | ❌ | `"default"` | 领域标识（如 default、military、corporate） |
| `source_types` | array | ❌ | `[]` | 指定数据源类型列表，为空则使用全部 |

**返回：**

```json
{
  "content": [
    {
      "type": "text",
      "text": "{\"task_id\": \"uuid\", \"status\": \"submitted\", \"query\": \"...\", \"domain_id\": \"default\", \"message\": \"决策任务已提交...\"}"
    }
  ]
}
```

**调用示例：**

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "submit_task",
    "arguments": {
      "query": "分析当前 AI 芯片供应链风险",
      "domain_id": "default"
    }
  }
}
```

---

### 2. `get_debate_status` — 查询辩论状态

根据辩论 ID 或关联的任务/模拟运行 ID 获取辩论进度。

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `debate_id` | string | ❌* | 辩论会话 ID |
| `run_id` | string | ❌* | 关联的模拟运行 ID |
| `claim_id` | string | ❌* | 关联的声明 ID |

> *至少提供一个参数

**返回：**

```json
{
  "content": [
    {
      "type": "text",
      "text": "{\"found\": true, \"count\": 1, \"debates\": [{\"debate_id\": \"...\", \"topic\": \"...\", \"status\": \"COMPLETED\", \"verdict\": {...}}]}"
    }
  ]
}
```

**调用示例：**

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "tools/call",
  "params": {
    "name": "get_debate_status",
    "arguments": {
      "run_id": "your-run-id-here"
    }
  }
}
```

---

### 3. `get_decision_result` — 获取决策结果

返回辩论裁决、用户决策或模拟决策记录。

**参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `run_id` | string | ❌* | — | 模拟运行 ID |
| `debate_id` | string | ❌* | — | 辩论会话 ID |
| `session_id` | string | ❌* | — | 战略会话 ID（用户决策） |
| `limit` | integer | ❌ | `20` | 返回条数上限 |

> *至少提供一个参数

**返回：**

```json
{
  "content": [
    {
      "type": "text",
      "text": "{\"decisions\": [...], \"verdicts\": [...], \"user_decisions\": [...], \"total\": 5}"
    }
  ]
}
```

返回包含三个列表：
- `decisions` — 模拟运行中的决策记录（tick、actor、action、reasoning）
- `verdicts` — 辩论裁决（decision、confidence、reasoning）
- `user_decisions` — 用户手动决策（decision、notes、outcome）

---

### 4. `list_sources` — 列出已配置数据源

返回所有已注册的数据源类型、状态、健康度和数据统计。

**参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `include_health` | boolean | ❌ | `true` | 是否包含健康状态详情 |
| `source_type` | string | ❌ | — | 按数据源类型过滤 |

**返回：**

```json
{
  "content": [
    {
      "type": "text",
      "text": "{\"total\": 8, \"sources\": [{\"key\": \"google_news\", \"label\": \"Google News\", \"available\": true, \"item_count\": 150, \"health\": {\"status\": \"OK\", \"consecutive_failures\": 0}}]}"
    }
  ]
}
```

每个数据源包含：
- `key` — 数据源标识
- `label` — 显示名称
- `agent_name` — 对应 Agent 名称
- `available` — 是否可用
- `item_count` — 已采集条目数
- `health` — 健康状态（status、consecutive_failures、last_error、last_success_at）

**内置数据源：**
- `google_news` — Google News
- `reddit` — Reddit
- `hacker_news` — Hacker News
- `github` — GitHub
- `rss` — RSS 订阅源
- `gdelt` — GDELT 全球事件数据库
- `weather` — 天气数据
- `aviation` — 航空数据
- `x_provider` — X (Twitter)
- `linux_do` — Linux.do
- `xiaohongshu` — 小红书
- `douyin` — 抖音

---

### 5. `query_knowledge` — 查询知识图谱

按关键词搜索知识图谱节点和关系，返回结构化知识。

**参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `query` | string | ✅ | — | 搜索关键词 |
| `node_type` | string | ❌ | — | 节点类型过滤（如 entity、event、concept） |
| `limit` | integer | ❌ | `20` | 返回结果数量上限 |
| `include_edges` | boolean | ❌ | `true` | 是否包含关联边 |

**返回：**

```json
{
  "content": [
    {
      "type": "text",
      "text": "{\"query\": \"AI\", \"node_count\": 5, \"edge_count\": 8, \"nodes\": [...], \"edges\": [...]}"
    }
  ]
}
```

**节点结构：**
```json
{
  "node_key": "entity:openai",
  "label": "OpenAI",
  "node_type": "entity",
  "source_table": "evidence_items",
  "source_id": "uuid",
  "metadata": {}
}
```

**边结构：**
```json
{
  "source": "entity:openai",
  "target": "concept:ai_safety",
  "relation": "related_to",
  "metadata": {}
}
```

---

## 错误码

| 错误码 | 说明 |
|--------|------|
| `-32700` | 解析错误 — 无效的 JSON |
| `-32600` | 无效请求 |
| `-32601` | 方法不存在 |
| `-32602` | 无效参数 / 未知工具 |
| `-32603` | 内部错误 |

## 配置环境变量

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `PLANAGENT_MCP_ENABLED` | `false` | 是否启用 MCP Server |
| `PLANAGENT_MCP_SERVER_NAME` | `MingJian MCP Server` | 服务器名称 |
| `PLANAGENT_MCP_SERVER_VERSION` | `0.1.0` | 服务器版本 |
| `PLANAGENT_MCP_PROTOCOL_VERSION` | `2024-11-05` | MCP 协议版本 |
| `PLANAGENT_MCP_TRANSPORT` | `sse` | 传输方式 |
| `PLANAGENT_MCP_ROUTE_PREFIX` | `/mcp` | 路由前缀 |
| `PLANAGENT_MCP_MAX_CONNECTIONS` | `50` | 最大并发连接数 |
| `PLANAGENT_MCP_REQUEST_TIMEOUT` | `60.0` | 请求超时（秒） |
| `PLANAGENT_MCP_LOG_TOOL_CALLS` | `true` | 是否记录工具调用日志 |

## 使用场景

1. **AI Agent 集成** — 外部 AI Agent（如 Claude、GPT）通过 MCP 协议调用明鉴进行情报分析
2. **自动化决策** — 定时任务通过 `submit_task` 提交批量分析请求
3. **知识检索** — 其他系统通过 `query_knowledge` 查询明鉴的知识图谱
4. **数据源管理** — 通过 `list_sources` 监控数据采集状态
5. **结果获取** — 通过 `get_decision_result` 获取自动化决策结果并集成到下游系统
