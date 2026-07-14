<div align="center">

<br />

# 明鉴 MingJian

### *明察秋毫，鉴往知来*

**开源战略智能驾驶舱：用证据驱动决策、多智能体辩论、场景推演和可审计推荐。**

---

[![Edition](https://img.shields.io/badge/Edition-Community%20OSS-1f6f5b.svg)](#版本边界)
[![License](https://img.shields.io/badge/License-Apache%202.0-2f6f9f.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12%2B-2b6cb0.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-0f766e.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-3b82f6.svg)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-frontend-7c3aed.svg)](https://vite.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.8%2B-2563eb.svg)](https://www.typescriptlang.org/)

**语言 / Language**

[English](README.md) · [中文](README.zh-CN.md) · [हिन्दी](README.hi.md) · [日本語](README.ja.md)

<br />

| 信号 | 明鉴交付什么 |
| --- | --- |
| 证据优先 | 每条建议都连接到采集来源、抽取声明和可回放追踪。 |
| 不是独白，而是辩论 | 专门角色会先挑战假设，再返回建议。 |
| 本地主权 | Community 可本地运行，开源代码、本地数据控制、24 小时监控窗口。 |
| 决策记忆 | 会话、推荐版本、刷新、源健康和用户反馈保持同一条链路。 |

</div>

---

## 产品阅读

明鉴面向需要在不确定性下做重要判断的人：创始人、分析师、运营者、研究者、战略团队，以及任何需要可检查证据而不是盲信答案的团队。

它更像战略智能驾驶舱，而不是聊天框。用户提交决策问题后，明鉴采集证据、执行分析和推演、召集辩论委员会、返回首次建议，并把后续源变化、推荐版本和反馈记录沉淀下来。

---

## 版本边界

| 版本 | 分发方式 | 核心工作流 | 商业层 |
| --- | --- | --- | --- |
| **Community** | Apache 2.0 自托管上游 | 完整公共决策工作流 + 24 小时本地监控 | 无 |
| **Cloud** | 托管 SaaS 订阅 | Community 公共核心的超集 | 订阅、计量、租户运营 |
| **Enterprise** | 私有化 / 本地部署 | Community 公共核心的超集 | License、审计、治理、私有连接器 |

本仓库是 **Community** 版本。它必须保持强开源核心：不加入 Cloud 订阅界面、不加入 Enterprise 专属治理代码，也不把商业移动端作为公开入口，除非后续明确决定开放。

---

## 决策工作流

```text
问题
  -> 来源发现
  -> 证据抽取
  -> 分析与推演
  -> 角色化辩论
  -> 推荐建议
  -> 版本时间线
  -> 定时 / 源变化刷新
  -> 决策记录与结果反馈
```

| 阶段 | 目的 | 用户可见证明 |
| --- | --- | --- |
| 采集 | 从新闻、代码、社交和公开数据源收集多源证据。 | 来源列表、游标健康、最后检查时间。 |
| 推理 | 将证据转成论点、风险、推演和结构化声明。 | 分析产物、报告章节、辩论轮次。 |
| 辩论 | 让角色化智能体质疑、修正并仲裁决策。 | 支持方、挑战方、仲裁方追踪。 |
| 记忆 | 持久化会话、推荐版本、刷新触发和结果反馈。 | 时间线、推荐历史、反馈记录。 |

---

## 明鉴的不同

| 旧式 AI 分析 | 明鉴 |
| --- | --- |
| 一个答案，少量上下文。 | 证据链、辩论链、推荐版本。 |
| 单模型盲区。 | 支持、挑战、仲裁多角色批判。 |
| 静态回答。 | 定时刷新和源变化触发更新。 |
| 难以审计。 | 确定性追踪、来源归属、决策记录。 |
| 泛化流程。 | 战略、风险、市场、政策、技术、社会和安全视角。 |

---

## 🔬 核心功能

### 1. 证据驱动，非猜测驱动

**问题：** 传统AI工具给您答案却不展示推理过程。

**我们的方案：** 明鉴将每个决策建立在来自10+数据源的**真实世界证据**之上。每个声明可追溯，每个决策可审计。

### 2. 多代理辩论协议

**问题：** 单一AI模型存在盲点和偏见。

**我们的方案：** 多个AI模型（GPT、Gemini、Claude、Grok）**辩论**您的决策，挑战假设并达成有证据支持的结论。

### 3. 双领域专业能力

**问题：** 大多数AI工具是通用的，不理解您的特定领域。

**我们的方案：** 明鉴支持**企业**（市场分析、竞争情报）和**军事**（作战规划、物流）两个领域，具有领域特定的规则和模型。

### 4. 完全可审计的决策追踪

**问题：** 您无法解释AI如何得出结论。

**我们的方案：** 每个模拟产生**确定性决策追踪**——AI如何得出结论的逐步记录。没有黑箱。

### 5. Jarvis自我修复引擎

**问题：** AI输出可能错误，但您往往为时已晚才发现。

**我们的方案：** 明鉴审查自己的输出，识别弱点，并迭代直到达到质量阈值——全程无需人工干预。

### 6. 实时流式分析

**问题：** 您等待AI完成，然后得到一个黑箱结果。

**我们的方案：** 提交分析请求，实时观看AI工作——流式进度事件、来源归属和中间结果。

### 7. 9智能体决策委员会

**问题：** 单一AI模型存在盲点和偏见。

**我们的方案：** 明鉴部署**9个专业AI智能体**——每个都有独特的角色、视角和模型——组成决策委员会：

| 角色 | 智能体 | 功能 |
|------|--------|------|
| 🟢 **战略支持者** | 核心 | 支持论证，寻找有利证据 |
| 🔴 **风险挑战者** | 核心 | 反对论证，寻找反面证据 |
| ⚖️ **首席仲裁官** | 核心 | 基于证据做出最终裁决 |
| 🔍 **情报分析师** | 视角 | 评估证据质量 |
| 🌍 **地缘政治专家** | 视角 | 地缘政治分析 |
| 💰 **经济分析师** | 视角 | 经济/市场分析 |
| ⚔️ **军事战略家** | 视角 | 军事/安全分析 |
| 🔮 **技术前瞻者** | 视角 | 技术趋势分析 |
| 👥 **社会影响评估师** | 视角 | 社会/舆论分析 |

---

## 🆚 明鉴 vs 竞品

| 特性 | 明鉴 | Manus | 传统AI | 单代理 | LangChain |
|------|------|-------|--------|--------|-----------|
| **数据源** | ✅ 10+实时源 | ⚠️ 通用搜索 | ❌ 手动输入 | ⚠️ 有限 | ⚠️ 有限 |
| **证据链** | ✅ 完全可追溯 | ❌ 无追踪 | ❌ 无追踪 | ❌ 无追踪 | ❌ 无追踪 |
| **多代理辩论** | ✅ 9智能体对抗 | ⚠️ 编排层+子代理 | ❌ 单模型 | ❌ 单模型 | ⚠️ 基础 |
| **决策追踪** | ✅ 确定性 | ❌ 黑箱 | ❌ 黑箱 | ❌ 黑箱 | ❌ 黑箱 |
| **自我修复** | ✅ Jarvis引擎 | ⚠️ 动态重规划 | ❌ 无 | ❌ 无 | ❌ 无 |
| **流式分析** | ✅ 实时 | ✅ 实时 | ❌ 仅批量 | ❌ 仅批量 | ⚠️ 有限 |
| **持续监控** | ✅ WatchRule+自动更新 | ❌ 一次性任务 | ❌ 无 | ❌ 无 | ❌ 无 |
| **企业领域** | ✅ 完整支持 | ❌ 通用 | ⚠️ 通用 | ❌ 通用 | ❌ 通用 |
| **军事领域** | ✅ 完整支持 | ❌ 通用 | ⚠️ 通用 | ❌ 通用 | ❌ 通用 |
| **场景分支** | ✅ 束搜索 | ❌ 无 | ❌ 手动 | ❌ 无 | ❌ 无 |
| **知识图谱** | ✅ 嵌入支持 | ❌ 无 | ❌ 无 | ❌ 无 | ❌ 无 |
| **代码执行** | ⚠️ 计划中 | ✅ 完整沙箱VM | ❌ 无 | ⚠️ 有限 | ❌ 无 |
| **数据主权** | ✅ 自部署 | ❌ 仅云端 | ⚠️ 多样 | ⚠️ 多样 | ✅ 自部署 |
| **开源** | ✅ Apache 2.0 | ❌ 闭源 | ⚠️ 多样 | ⚠️ 多样 | ✅ 多样 |

---

## 🧭 明鉴 的定位：AI 决策参谋

> **不是通用工具，而是专属参谋团。**

AI Agent 时代已经到来。编排层（Orchestrator）协调多个子 Agent 和工具，在沙箱环境中自主完成复杂任务 — 这已经被证明是有效的范式。

明鉴在此基础上更进一步，专注于**决策智能**：

### 设计理念

 设计原则 | 明鉴的实践 |
---------|-----------|
 编排层 > 底层模型 | 9智能体注册中心，按角色分配模型 |
 实时流式展示建立信任 | 辩论逐轮渲染，用户看到每一步推理 |
 多工具协同完成任务 | 12个数据源 + 辩论引擎 + 仿真引擎 |
 动态重规划应对失败 | 辩论失败时自动调整策略重新论证 |

### 核心差异化

 维度 | 明鉴 |
------|------|
 **目标** | 做出更好的决策 |
 **推理方式** | 9个智能体独立论证、交叉质询、仲裁裁决 |
 **证据基础** | 12个数据源结构化采集 → 证据提取 → 知识图谱 |
 **持续性** | WatchRule 持续监控 + 定时更新 + 突发事件检测 |
 **领域深度** | 企业/军事双领域仿真，KPI 追踪，场景分支 |
 **透明度** | 展示推理过程 + 用户可投票质疑 |
 **数据主权** | 自部署，数据完全在本地 |
 **成本** | 自有模型，边际成本趋近于零 |

### MoE 架构思想

明鉴的 9 智能体系统借鉴了 **Mixture of Experts (MoE)** 的核心思想：

```
用户问题 → 路由器（辩论流程）→ 选择专家组合 → 独立推理 → 加权裁决
```

就像 DeepSeek-V3 用 256 个专家中只激活少数最相关的，明鉴在 9 个智能体中根据问题类型选择最合适的组合。核心 3 角色（支持方/挑战方/仲裁官）始终激活，视角 6 角色按需参与 — 这就是软件层的稀疏激活。

---

## 🎯 使用场景

 场景 | 说明 | 收益 |
------|------|------|
 **📊 投资研究** | 分析市场趋势，辩论投资论文 | 更快研究，更好决策 |
 **🏭 企业战略** | 竞争情报，场景规划 | 数据驱动，降低风险 |
 **⚔️ 军事规划** | 作战分析，物流优化 | 战略优势，更好结果 |
 **🛡️ 风险管理** | 多视角风险评估 | 减少不确定性 |
 **📈 市场分析** | 实时市场情报 | 更快洞察，更好定位 |
 **🎯 政策分析** | 多利益相关者影响评估 | 明智政策，更好结果 |

---

## 🚀 快速开始

### 一键 Docker 部署

最快的方式是使用 Docker 一键部署脚本。脚本会自动检测 Docker 环境、创建 `.env` 文件、提示输入 API Key，然后启动全部服务。

**前置要求：** 安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)

```bash
git clone https://github.com/dashitongzhi/MingJian.git
cd MingJian
chmod +x setup.sh
./setup.sh
```

启动后打开：

 服务 | URL |
------|-----|
 前端 | http://localhost:3001 |
 API | http://localhost:8000 |
 MinIO 控制台 | http://localhost:9001 |

停止服务：

```bash
docker compose down
```

### 手动开发环境部署

如果你想在本地直接运行后端和前端进行开发，请按以下步骤操作。

#### 前置要求

在开始之前，请确保已安装以下软件：

 要求 | 版本 | 安装方式 |
------|------|----------|
 **Python** | 3.12+ | [python.org](https://www.python.org/downloads/) |
 **Node.js** | 18+ | [nodejs.org](https://nodejs.org/) |
 **npm** | 9+ | 随Node.js一起安装 |
 **Git** | 2.30+ | [git-scm.com](https://git-scm.com/) |
 **PostgreSQL** | 14+（可选） | [postgresql.org](https://www.postgresql.org/download/) |
 **Redis** | 7+（可选） | [redis.io](https://redis.io/download) |

#### 系统要求

 组件 | 最低要求 | 推荐配置 |
------|----------|----------|
 **CPU** | 2核 | 4+核 |
 **内存** | 4 GB | 8+ GB |
 **存储** | 10 GB | 50+ GB |
 **操作系统** | macOS、Linux、Windows | macOS或Linux |

#### 环境变量配置

在项目根目录创建 `.env` 文件，包含以下变量：

```bash
# ═══════════════════════════════════════════════════════════════
# AI 模型配置
# ═══════════════════════════════════════════════════════════════
# 只需一个 API Key 即可启动。
# 系统会自动将同一组凭证填充到全部 7 个模型槽位
# （primary、extraction、x_search、report、debate_advocate、
#  debate_challenger、debate_arbitrator），除非你单独覆盖。

PLANAGENT_OPENAI_API_KEY=你的API密钥

# 按需覆盖单个槽位（未覆盖的自动回退到 shared）
# PLANAGENT_OPENAI_PRIMARY_MODEL=gpt-4.1
# PLANAGENT_OPENAI_PRIMARY_API_KEY=sk-...
# PLANAGENT_OPENAI_EXTRACTION_MODEL=gpt-4.1-mini
# PLANAGENT_OPENAI_DEBATE_ADVOCATE_MODEL=claude-sonnet-4-20250514
# PLANAGENT_OPENAI_DEBATE_CHALLENGER_MODEL=gemini-2.5-flash
# PLANAGENT_OPENAI_DEBATE_ARBITRATOR_MODEL=grok-3

# ═══════════════════════════════════════════════════════════════
# 数据库（可选 — 本地开发默认使用 SQLite）
# ═══════════════════════════════════════════════════════════════
# PLANAGENT_DATABASE_URL=postgresql+psycopg://planagent:planagent@localhost:5432/planagent

# ═══════════════════════════════════════════════════════════════
# Redis（可选 — 生产环境用于事件总线）
# ═══════════════════════════════════════════════════════════════
# PLANAGENT_REDIS_URL=redis://localhost:6379/0

# ═══════════════════════════════════════════════════════════════
# MinIO 对象存储（可选）
# ═══════════════════════════════════════════════════════════════
# PLANAGENT_MINIO_ENDPOINT=localhost:9000
# PLANAGENT_MINIO_ACCESS_KEY=minioadmin
# PLANAGENT_MINIO_SECRET_KEY=minioadmin

# ═══════════════════════════════════════════════════════════════
# X / Twitter（可选 — 社交情报数据源）
# ═══════════════════════════════════════════════════════════════
# X_BEARER_TOKEN=你的X平台Bearer Token

# ═══════════════════════════════════════════════════════════════
# 前端
# ═══════════════════════════════════════════════════════════════
NEXT_PUBLIC_API_URL=/api
```

> **💡 关键提示：** 即使你只有**一个**模型供应商（比如 OpenAI，或任何兼容 OpenAI 接口的服务），也可以用它填满全部 7 个模型槽位。只需设置 `PLANAGENT_OPENAI_API_KEY`，系统自动完成剩余配置。无需 4 个不同的 API Key 才能启动。

#### 兼容提供商

所有槽位均使用 OpenAI 兼容的 `/chat/completions` 接口，可自由混搭：

 提供商 | Base URL |
---|---|
 OpenAI | `https://api.openai.com/v1` |
 **Anthropic (Claude)** | **`https://api.anthropic.com/v1/openai`** |
 DeepSeek | `https://api.deepseek.com/v1` |
 Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` |
 xAI Grok | `https://api.x.ai/v1` |
 小米 MiMo | `https://token-plan-cn.xiaomimimo.com/v1` |
 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` |
 MiniMax | `https://api.minimax.chat/v1` |
 任意兼容代理 | 你的代理地址 |

#### 安装步骤

```bash
# 1. 克隆仓库
git clone https://github.com/dashitongzhi/MingJian.git
cd planagent

# 2. 创建并激活Python虚拟环境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. 安装Python依赖
pip install -e ".[dev]"

# 4. 安装前端依赖
cd frontend-v2
npm install
cd ..

# 5. 配置环境
cp .env.example .env
# 编辑 .env 文件，添加您的API密钥和设置

# 6. 初始化数据库（如果使用PostgreSQL）
# 创建名为 'planagent' 的数据库
# 运行迁移
alembic upgrade head

# 7. 启动后端服务器
uvicorn planagent.main:app --reload --host 127.0.0.1 --port 8000

# 8. 启动前端（在新终端中）
cd frontend-v2
npm run dev
# 打开 http://localhost:3000
```

Community 本地模式仅监听回环地址，并使用部署级本地单用户会话。除非已经设置
`PLANAGENT_REMOTE_ACCESS_ENABLED=true`，并配置至少 32 字节且可持久化的
`PLANAGENT_AUTH_SECRET_KEY`，否则不要把 API 绑定到 `0.0.0.0` 或其他非回环地址。
Community 始终禁用远程自注册；远程模式只开放 bootstrap 管理员 `admin` 登录。
`setup.sh` 会把首次远程管理员密码保存到本地 `.env` 的
`PLANAGENT_BOOTSTRAP_ADMIN_PASSWORD`；首次
管理员登录后应通过 `POST /auth/change-password` 立即轮换密码，并同步更新本地 `.env`。

---

## 📦 依赖项

### 后端依赖（Python）

 包名 | 版本 | 用途 |
------|------|------|
 **FastAPI** | 0.110+ | 高性能异步API框架 |
 **SQLAlchemy** | 2.0+ | 数据库ORM |
 **Alembic** | 1.16+ | 数据库迁移 |
 **Pydantic** | 2.11+ | 数据验证 |
 **OpenAI** | 2.28+ | OpenAI API客户端 |
 **Anthropic** | 0.52+ | Anthropic API客户端 |
 **Redis** | 6.2+ | 事件总线和缓存 |
 **pgvector** | 0.3+ | 向量相似性搜索 |
 **MinIO** | 7.2+ | 对象存储 |
 **HTTPX** | 0.28+ | 异步HTTP客户端 |
 **Uvicorn** | 0.35+ | ASGI服务器 |

### 前端依赖（Node.js）

 包名 | 版本 | 用途 |
------|------|------|
 **Vite** | 8+ | 前端构建工具 |
 **React** | 19+ | UI库 |
 **TypeScript** | 6.0+ | 类型安全 |
 **Tailwind CSS** | 4.2+ | 实用优先的CSS |
 **React Router** | 7+ | 客户端路由 |
 **Recharts** | 3.8+ | 图表库 |

### 开发依赖

 包名 | 版本 | 用途 |
|------|------|------|
| **pytest** | 8.4+ | 测试框架 |
| **pytest-asyncio** | 1.1+ | 异步测试支持 |
| **Ruff** | 0.12+ | Python代码检查 |
| **ESLint** | 9+ | JavaScript代码检查 |
| **Prettier** | 3+ | 代码格式化 |
| **Vitest** | ^4.1.5 | 单元测试框架 |
| **@testing-library/react** | ^16.x | React组件测试 |
| **@testing-library/jest-dom** | ^6.x | Jest自定义匹配器 |

---

## 🏗️ 系统架构

```mermaid
graph TB
    subgraph "用户界面"
        Console[战略控制台]
        API[FastAPI控制平面]
    end
    
    subgraph "核心服务"
        Evidence[证据采集]
        Simulation[模拟引擎]
        Debate[辩论引擎]
        Jarvis[Jarvis集成]
    end
    
    subgraph "数据源"
        RSS[RSS订阅]
        News[Google News]
        Reddit[Reddit]
        GitHub[GitHub]
        X[X/Twitter]
        GDELT[GDELT]
    end
    
    subgraph "存储"
        PostgreSQL[(PostgreSQL)]
        Redis[(Redis)]
        MinIO[(MinIO)]
    end
    
    Console --> API
    API --> Evidence
    API --> Simulation
    API --> Debate
    API --> Jarvis
    
    Evidence --> RSS
    Evidence --> News
    Evidence --> Reddit
    Evidence --> GitHub
    Evidence --> X
    Evidence --> GDELT
```

---

## 📁 项目结构

**后端结构：**

```
src/planagent/
├── config/              # 配置包（原 config.py 527行 → 4个文件）
│   ├── __init__.py
│   ├── base.py          # 核心配置（数据库、Redis、Minio）
│   ├── openai.py        # 动态OpenAI目标解析
│   └── main.py          # 组合式Settings类
├── services/
│   ├── debate/          # 辩论包（原 debate.py 3273行 → 7个模块）
│   │   ├── prompts.py   # Agent角色提示词与轮次规划
│   │   ├── rounds.py    # 轮次执行逻辑
│   │   ├── llm.py       # LLM调用与重试
│   │   ├── adjudication.py # 裁决与建议生成
│   │   ├── revisions.py # 立场修订追踪
│   │   └── triggers.py  # 自动触发逻辑
│   ├── simulation/      # 推演包（原 simulation.py 2281行 → 6个模块）
│   │   ├── engine.py    # 核心推演引擎
│   │   ├── scenarios.py # 场景生成
│   │   ├── impact.py    # 影响评估与评分
│   │   ├── report.py    # 报告生成
│   │   └── domain_packs.py # 领域包管理
│   └── ...
├── db.py                # 数据库层（已清理，仅用Alembic迁移）
└── ...
```

**前端结构：**

```
frontend-v2/src/
├── components/
│   ├── layout/          # 应用外壳、侧边栏、导航框架
│   └── ui/              # 共享驾驶舱界面和状态组件
├── pages/               # 仪表盘、助手、监控、报告、设置
├── api/                 # API 端点辅助函数
├── hooks/               # 主题和应用级 React hooks
└── main.tsx             # Vite 入口
```

---

## 🧪 运行测试

**后端测试 (pytest)**
- 运行所有单元测试（92个，<1秒）: `python -m pytest tests/unit/ -v`
- 运行集成测试: `python -m pytest tests/ -v`

**前端测试 (Vitest)**
- `cd frontend-v2 && npm run build`

**压力测试**
- 7维压力测试（需要后端运行）: `python tests/stress_test.py`

**最新结果：**
- ✅ 后端：92个单元测试通过（0.26秒）
- ✅ 前端：16个组件测试通过（0.55秒）
- ✅ 压力测试：112通过，0失败，2警告
- 🔥 并发：20用户，844 RPS，P50=1ms，零500错误

---

## 📊 质量与性能

 指标 | 数值 |
|------|------|
| 后端单元测试 | 92个通过 |
| 前端组件测试 | 16个通过 |
| 压力测试通过率 | 112/114 (98.2%) |
| 并发负载（20用户）| 844 RPS，零500错误 |
| 响应时间 P50 | 1ms |
| 响应时间 P95 | 11ms |
| API端点测试数 | 82 |
| 最大后端文件 | ~900行（原3273行）|
| 最大前端页面 | ~550行（原1665行）|

---

## 📚 文档

- [📖 完整技术报告](docs/planagent_full_report.md)
- [🚀 Agent启动手册](docs/agent_startup_playbook.md)
- [🔧 技术债务积压](TECHNICAL_DEBT_BACKLOG.md)
- [🤝 贡献指南](CONTRIBUTING.md)
- [📝 变更日志](CHANGELOG.md)

---

## 🤝 贡献

我们欢迎贡献！请参阅[贡献指南](CONTRIBUTING.md)。

```bash
# 1. Fork仓库
# 2. 创建功能分支
git checkout -b feature/amazing-feature

# 3. 进行更改
# 4. 运行测试
pytest

# 5. 提交更改
git commit -m "feat: add amazing feature"

# 6. 推送到分支
git push origin feature/amazing-feature

# 7. 打开Pull Request
```

---

## 📄 许可证

本项目根据Apache License 2.0授权 - 详见[LICENSE](LICENSE)文件。

---

## 🙏 致谢

- [FastAPI](https://fastapi.tiangolo.com/) - 高性能异步API
- [Vite](https://vite.dev/) - 前端构建工具
- [PostgreSQL](https://www.postgresql.org/) + [pgvector](https://github.com/pgvector/pgvector) - 数据库
- [Redis Streams](https://redis.io/docs/data-types/streams/) - 事件流
- [MinIO](https://min.io/) - 对象存储
- [Linux.do](https://linux.do) - 开源社区支持与交流

---

## 📞 联系我们

如果你对这个项目感兴趣——无论是想合作、提建议，还是单纯想聊聊——欢迎随时联系！

- 📧 邮箱：[cajd6876@gmail.com](mailto:cajd6876@gmail.com) | [2965866908@qq.com](mailto:2965866908@qq.com)
- 🐛 问题：[GitHub Issues](https://github.com/dashitongzhi/MingJian/issues)
- 💬 讨论：[GitHub Discussions](https://github.com/dashitongzhi/MingJian/discussions)

---

<div align="center">

## 🌟 Star History

[![Star History Chart](https://api.star-history.com/svg?repos=dashitongzhi/MingJian&type=Date)](https://star-history.com/#dashitongzhi/MingJian&Date)

---

**明鉴** — *明察秋毫，鉴往知来*

**明鉴** — *See Clearly, Judge Wisely*

---

**Made with ❤️ by the 明鉴 Team**

</div>
