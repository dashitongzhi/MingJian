<div align="center">

<br />

# 明鉴 MingJian

### *See Clearly, Judge Wisely*

**An open-source strategic intelligence cockpit for evidence-grounded decisions, multi-agent debate, scenario simulation, and auditable recommendations.**

---

[![Edition](https://img.shields.io/badge/Edition-Community%20OSS-1f6f5b.svg)](#edition-boundary)
[![License](https://img.shields.io/badge/License-Apache%202.0-2f6f9f.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12%2B-2b6cb0.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-0f766e.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-3b82f6.svg)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-frontend-7c3aed.svg)](https://vite.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.8%2B-2563eb.svg)](https://www.typescriptlang.org/)

**Language / 语言**

[English](README.md) · [中文](README.zh-CN.md) · [हिन्दी](README.hi.md) · [日本語](README.ja.md)

<br />

<img src="docs/assets/mingjian-brand-poster.png" alt="明鉴中文品牌海报：证据先于观点" width="760" />

<br />

<sub>证据先于观点 · 多源求证 · 多方辩论 · 持续校验</sub>

<br />
<br />

| Signal | What MingJian Delivers |
| --- | --- |
| Evidence first | Every recommendation is grounded in collected sources, extracted claims, and replayable traces. |
| Debate, not monologue | Specialized agents challenge assumptions before the system returns a recommendation. |
| Local sovereignty | Community runs locally with open-source code, local data control, and a 24-hour monitoring window. |
| Decision memory | Sessions, recommendation versions, refreshes, source health, and user outcomes stay connected. |

</div>

---

## Product Read

MingJian is built for people who need to make consequential decisions under uncertainty: founders, analysts, operators, researchers, strategists, and teams that need evidence they can inspect instead of answers they have to blindly trust.

The product experience is closer to a strategic intelligence cockpit than a chat box. A user submits a decision-support request; MingJian gathers evidence, runs analysis and simulation, convenes a debate council, returns a first recommendation, then keeps a versioned record that can be refreshed when source material changes.

---

## Edition Boundary

| Edition | Distribution | Core Workflow | Commercial Layer |
| --- | --- | --- | --- |
| **Community** | Apache 2.0 self-hosted upstream | Full public decision workflow with 24-hour local monitoring | None |
| **Cloud** | Hosted SaaS subscription | Superset of Community public core | Subscription, metering, tenant operations |
| **Enterprise** | Private / on-prem deployment | Superset of Community public core | License, audit, governance, private connectors |

This repository is the **Community** edition. It must remain a strong open-source core: no Cloud subscription surfaces, no Enterprise-only governance code, and no proprietary mobile entry point unless explicitly published later.

---

## Decision Workflow

```text
Question
  -> source discovery
  -> evidence extraction
  -> analysis and simulation
  -> role-based debate
  -> recommendation
  -> version timeline
  -> scheduled / source-change refresh
  -> decision record and outcome feedback
```

| Stage | Purpose | User-Visible Proof |
| --- | --- | --- |
| Gather | Collect multi-source evidence from news, code, social, and public data feeds. | Source list, cursor health, last checked time. |
| Reason | Convert evidence into arguments, risks, simulations, and structured claims. | Analysis artifacts, report sections, debate rounds. |
| Debate | Let role-based agents critique, revise, and arbitrate the decision. | Support/challenge/arbiter traces. |
| Remember | Persist sessions, recommendation versions, refresh triggers, and outcomes. | Timeline, recommendation history, feedback records. |

---

## What Makes It Different

| Old AI Analysis | MingJian |
| --- | --- |
| One answer, little context. | Evidence chain, debate trail, and recommendation versions. |
| Single-model blind spots. | Multi-agent critique with support, challenge, and arbitration roles. |
| Static responses. | Scheduled refresh and source-change triggered updates. |
| Hard to audit. | Deterministic traces, source attribution, and decision records. |
| Generic workflow. | Strategy, risk, market, policy, technical, social, and security perspectives. |

---

## 🔬 Core Features

### 1. Evidence-Driven, Not Guess-Driven

**The Problem:** Traditional AI tools give you answers without showing their work.

**Our Solution:** 明鉴 grounds every decision in **real-world evidence** from 10+ data sources. Every claim is traceable, every decision is auditable.

### 2. Multi-Agent Debate Protocol

**The Problem:** Single AI models have blind spots and biases.

**Our Solution:** Multiple AI models (GPT, Gemini, Claude, Grok) **debate** your decisions, challenging assumptions and reaching evidence-backed conclusions.

### 3. Dual-Domain Expertise

**The Problem:** Most AI tools are generic and don't understand your specific domain.

**Our Solution:** 明鉴 supports both **Corporate** (market analysis, competitive intelligence) and **Military** (operational planning, logistics) with domain-specific rules and models.

### 4. Full Auditability with Decision Traces

**The Problem:** You can't explain how AI reached a conclusion.

**Our Solution:** Every simulation produces a **deterministic decision trace** — a step-by-step record of how the AI reached its conclusion. No black boxes.

### 5. Jarvis Self-Repair Engine

**The Problem:** AI outputs can be wrong, but you don't know until it's too late.

**Our Solution:** 明鉴 reviews its own outputs, identifies weaknesses, and iterates until quality thresholds are met — all without human intervention.

### 6. Real-Time Streaming Analysis

**The Problem:** You wait for AI to finish, then get a black-box result.

**Our Solution:** Submit an analysis request and watch the AI work in real-time — streaming progress events, source attribution, and intermediate results.

### 7. 9-Agent Decision Council

**The Problem:** Single AI models have blind spots and biases.

**Our Solution:** 明鉴 deploys **9 specialized AI agents** — each with a distinct role, perspective, and model — to form a decision council:

| Role | Agent | Function |
|------|-------|----------|
| 🟢 **Strategic Advocate** | Core | Argues FOR, finds supporting evidence |
| 🔴 **Risk Challenger** | Core | Argues AGAINST, finds counter-evidence |
| ⚖️ **Chief Arbitrator** | Core | Delivers final verdict based on evidence |
| 🔍 **Intelligence Analyst** | Perspective | Assesses evidence quality |
| 🌍 **Geopolitical Expert** | Perspective | Geopolitical analysis |
| 💰 **Economic Analyst** | Perspective | Economic/market analysis |
| ⚔️ **Military Strategist** | Perspective | Military/security analysis |
| 🔮 **Tech Forecaster** | Perspective | Technology trend analysis |
| 👥 **Social Impact Assessor** | Perspective | Social/public opinion analysis |

Inspired by **Mixture of Experts (MoE)** architecture: core agents are always active, perspective agents are activated as needed — sparse activation at the software layer.

---

## 🆚 明鉴 vs The Competition

| Feature | 明鉴 | Manus | Traditional AI | Single-Agent | LangChain |
|---------|------|-------|----------------|--------------|-----------|
| **Data Sources** | ✅ 10+ real-time | ⚠️ General search | ❌ Manual input | ⚠️ Limited | ⚠️ Limited |
| **Evidence Chain** | ✅ Full traceability | ❌ No tracking | ❌ No tracking | ❌ No tracking | ❌ No tracking |
| **Multi-Agent Debate** | ✅ 9-agent adversarial | ⚠️ Orchestrator + sub-agents | ❌ Single model | ❌ Single model | ⚠️ Basic |
| **Decision Traces** | ✅ Deterministic | ❌ Black box | ❌ Black box | ❌ Black box | ❌ Black box |
| **Self-Repair** | ✅ Jarvis engine | ⚠️ Dynamic re-planning | ❌ None | ❌ None | ❌ None |
| **Streaming Analysis** | ✅ Real-time | ✅ Real-time | ❌ Batch only | ❌ Batch only | ⚠️ Limited |
| **Continuous Monitoring** | ✅ WatchRule + auto-update | ❌ One-shot tasks | ❌ None | ❌ None | ❌ None |
| **Corporate Domain** | ✅ Full support | ❌ Generic | ⚠️ Generic | ❌ Generic | ❌ Generic |
| **Military Domain** | ✅ Full support | ❌ Generic | ⚠️ Generic | ❌ Generic | ❌ Generic |
| **Scenario Branching** | ✅ Beam-search | ❌ None | ❌ Manual | ❌ None | ❌ None |
| **Knowledge Graph** | ✅ Embedding-backed | ❌ None | ❌ None | ❌ None | ❌ None |
| **Code Execution** | ⚠️ Planned | ✅ Full sandbox VM | ❌ None | ⚠️ Limited | ❌ None |
| **Data Sovereignty** | ✅ Self-hosted | ❌ Cloud only | ⚠️ Varies | ⚠️ Varies | ✅ Self-hosted |
| **Open Source** | ✅ Apache 2.0 | ❌ Closed source | ⚠️ Varies | ⚠️ Varies | ✅ Various |

---

## 🧭 明鉴 的定位：AI 决策参谋

> **不是通用工具，而是专属参谋团。**

AI Agent 时代已经到来。编排层（Orchestrator）协调多个子 Agent 和工具，在沙箱环境中自主完成复杂任务 — 这已经被证明是有效的范式。

明鉴在此基础上更进一步，专注于**决策智能**：

### 设计理念

| 设计原则 | 明鉴的实践 |
|---------|-----------|
| 编排层 > 底层模型 | 9智能体注册中心，按角色分配模型 |
| 实时流式展示建立信任 | 辩论逐轮渲染，用户看到每一步推理 |
| 多工具协同完成任务 | 12个数据源 + 辩论引擎 + 仿真引擎 |
| 动态重规划应对失败 | 辩论失败时自动调整策略重新论证 |

### 核心差异化

| 维度 | 明鉴 |
|------|------|
| **目标** | 做出更好的决策 |
| **推理方式** | 9个智能体独立论证、交叉质询、仲裁裁决 |
| **证据基础** | 12个数据源结构化采集 → 证据提取 → 知识图谱 |
| **持续性** | WatchRule 持续监控 + 定时更新 + 突发事件检测 |
| **领域深度** | 企业/军事双领域仿真，KPI 追踪，场景分支 |
| **透明度** | 展示推理过程 + 用户可投票质疑 |
| **数据主权** | 自部署，数据完全在本地 |
| **成本** | 自有模型，边际成本趋近于零 |

### MoE 架构思想

明鉴的 9 智能体系统借鉴了 **Mixture of Experts (MoE)** 的核心思想：

```
用户问题 → 路由器（辩论流程）→ 选择专家组合 → 独立推理 → 加权裁决
```

就像 DeepSeek-V3 用 256 个专家中只激活少数最相关的，明鉴在 9 个智能体中根据问题类型选择最合适的组合。核心 3 角色（支持方/挑战方/仲裁官）始终激活，视角 6 角色按需参与 — 这就是软件层的稀疏激活。

---

## 🎯 Use Cases

| Use Case | Description | Benefit |
|----------|-------------|---------|
| **📊 Investment Research** | Analyze market trends, debate investment theses | Faster research, better decisions |
| **🏭 Corporate Strategy** | Competitive intelligence, scenario planning | Data-driven decisions, reduced risk |
| **⚔️ Military Planning** | Operational analysis, logistics optimization | Strategic advantage, better outcomes |
| **🛡️ Risk Management** | Multi-perspective risk assessment | Reduced uncertainty |
| **📈 Market Analysis** | Real-time market intelligence | Faster insights, better positioning |
| **🎯 Policy Analysis** | Multi-stakeholder impact assessment | Informed policy, better outcomes |

---

## 🚀 Quick Start

### One-Click Docker Setup

The fastest way to run 明鉴 locally is the Docker setup script. It checks Docker, creates `.env` from `.env.example`, asks for your OpenAI API key, and starts the full stack.

#### Prerequisites

Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) first, then run:

```bash
chmod +x setup.sh
./setup.sh
```

When the script finishes, open:

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3001 |
| API | http://localhost:8000 |
| MinIO Console | http://localhost:9001 |

MinIO login: use `PLANAGENT_MINIO_ACCESS_KEY` / `PLANAGENT_MINIO_SECRET_KEY` from your `.env`.

To stop the Docker stack:

```bash
docker compose -f docker-compose.yml down
```

### Manual Development Setup

Use this path if you want to run the backend and frontend directly on your machine for development.

#### Frontend Directory Policy

`frontend-v2/` is the active Vite frontend. The older `frontend/` and `frontend-new/` experiments have been retired, so new product UI, builds, and Docker development should target `frontend-v2/`.

#### Prerequisites

Before you begin, ensure you have the following installed:

| Requirement | Version | Installation |
|-------------|---------|--------------|
| **Python** | 3.12+ | [python.org](https://www.python.org/downloads/) |
| **Node.js** | 18+ | [nodejs.org](https://nodejs.org/) |
| **npm** | 9+ | Comes with Node.js |
| **Git** | 2.30+ | [git-scm.com](https://git-scm.com/) |
| **PostgreSQL** | 14+ (optional) | [postgresql.org](https://www.postgresql.org/download/) |
| **Redis** | 7+ (optional) | [redis.io](https://redis.io/download) |

#### System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **CPU** | 2 cores | 4+ cores |
| **RAM** | 4 GB | 8+ GB |
| **Storage** | 10 GB | 50+ GB |
| **OS** | macOS, Linux, Windows | macOS or Linux |

#### Environment Variables

Create a `.env` file in the project root with the following variables:

```bash
# ═══════════════════════════════════════════════════════════════
# AI Model Configuration
# ═══════════════════════════════════════════════════════════════
# You only need ONE API key to get started.
# The system automatically uses the same key for all 7 model slots
# (primary, extraction, x_search, report, debate_advocate,
#  debate_challenger, debate_arbitrator) unless you override them.

PLANAGENT_OPENAI_API_KEY=your_api_key_here

# Override individual targets (all fall back to shared if unset).
# Set the API key first, run the provider connection test to fetch available models,
# then paste one of the returned model IDs if you need a manual override.
# PLANAGENT_OPENAI_PRIMARY_MODEL=
# PLANAGENT_OPENAI_PRIMARY_API_KEY=sk-...
# PLANAGENT_OPENAI_EXTRACTION_MODEL=
# PLANAGENT_OPENAI_DEBATE_ADVOCATE_MODEL=
# PLANAGENT_OPENAI_DEBATE_CHALLENGER_MODEL=
# PLANAGENT_OPENAI_DEBATE_ARBITRATOR_MODEL=

# ═══════════════════════════════════════════════════════════════
# Database (optional — defaults to SQLite for local dev)
# ═══════════════════════════════════════════════════════════════
# PLANAGENT_DATABASE_URL=postgresql+psycopg://planagent:planagent@localhost:5432/planagent

# ═══════════════════════════════════════════════════════════════
# Redis (optional — for event bus in production)
# ═══════════════════════════════════════════════════════════════
# PLANAGENT_REDIS_URL=redis://localhost:6379/0

# ═══════════════════════════════════════════════════════════════
# MinIO Object Storage (optional)
# ═══════════════════════════════════════════════════════════════
# PLANAGENT_MINIO_ENDPOINT=localhost:9000
# PLANAGENT_MINIO_ACCESS_KEY=minioadmin
# PLANAGENT_MINIO_SECRET_KEY=minioadmin

# ═══════════════════════════════════════════════════════════════
# X / Twitter (optional — for social intelligence)
# ═══════════════════════════════════════════════════════════════
# X_BEARER_TOKEN=your_x_bearer_token

# ═══════════════════════════════════════════════════════════════
# Frontend
# ═══════════════════════════════════════════════════════════════
NEXT_PUBLIC_API_URL=/api
```

> **💡 Key Point:** Even if you only have access to **one** model provider (e.g., OpenAI, or any OpenAI-compatible API), you can use it for all 7 model slots. Just set `PLANAGENT_OPENAI_API_KEY` — the system fills in the rest automatically. No need for 4 different API keys to get started.

#### Compatible Providers

All slots use the OpenAI-compatible `/chat/completions` endpoint. You can mix and match providers freely:

| Provider | Base URL |
|---|---|
| OpenAI | `https://api.openai.com/v1` |
| **Anthropic (Claude)** | **`https://api.anthropic.com/v1/openai`** |
| DeepSeek | `https://api.deepseek.com/v1` |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` |
| xAI Grok | `https://api.x.ai/v1` |
| Xiaomi MiMo | `https://token-plan-cn.xiaomimimo.com/v1` |
| Zhipu GLM | `https://open.bigmodel.cn/api/paas/v4` |
| MiniMax | `https://api.minimax.chat/v1` |
| Any compatible proxy | Your proxy URL |

#### Installation Steps

```bash
# 1. Clone the repository
git clone https://github.com/dashitongzhi/MingJian.git
cd planagent

# 2. Create and activate Python virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install Python dependencies
pip install -e ".[dev]"

# 4. Install frontend dependencies
cd frontend-v2
npm install
cd ..

# 5. Configure environment
cp .env.example .env
# Edit .env file with your API keys and settings

# 6. Initialize database (if using PostgreSQL)
# Create database named 'planagent'
# Run migrations
alembic upgrade head

# 7. Start backend server
uvicorn planagent.main:app --reload --host 127.0.0.1 --port 8000

# 8. Start frontend (in a new terminal)
cd frontend-v2
npm run dev
# Open http://localhost:3000
```

Community local mode is loopback-only and uses a deployment-local single-user session. Do not
bind the API to `0.0.0.0` or another non-loopback address unless
`PLANAGENT_REMOTE_ACCESS_ENABLED=true` and a persistent
`PLANAGENT_AUTH_SECRET_KEY` of at least 32 bytes are configured. Remote self-registration remains
disabled unless `PLANAGENT_REMOTE_REGISTRATION_ENABLED=true` is explicitly enabled for a
controlled onboarding window.

---

## 📦 Dependencies

### Backend Dependencies (Python)

| Package | Version | Purpose |
|---------|---------|---------|
| **FastAPI** | 0.110+ | High-performance async API framework |
| **SQLAlchemy** | 2.0+ | Database ORM |
| **Alembic** | 1.16+ | Database migrations |
| **Pydantic** | 2.11+ | Data validation |
| **OpenAI** | 2.28+ | OpenAI API client |
| **Anthropic** | 0.52+ | Anthropic API client |
| **Redis** | 6.2+ | Event bus and caching |
| **pgvector** | 0.3+ | Vector similarity search |
| **MinIO** | 7.2+ | Object storage |
| **HTTPX** | 0.28+ | Async HTTP client |
| **Uvicorn** | 0.35+ | ASGI server |

### Frontend Dependencies (Node.js)

| Package | Version | Purpose |
|---------|---------|---------|
| **Vite** | 8+ | Frontend build tool |
| **React** | 19+ | UI library |
| **TypeScript** | 6.0+ | Type safety |
| **Tailwind CSS** | 4.2+ | Utility-first CSS |
| **React Router** | 7+ | Client-side routing |
| **Recharts** | 3.8+ | Charting library |

### Development Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| **pytest** | 8.4+ | Testing framework |
| **pytest-asyncio** | 1.1+ | Async test support |
| **Ruff** | 0.12+ | Python linter |
| **ESLint** | 9+ | JavaScript linter |
| **Prettier** | 3+ | Code formatter |
| **vitest** | ^4.1.5 | Unit testing framework |
| **@testing-library/react** | ^16.x | React component testing |
| **@testing-library/jest-dom** | ^6.x | Custom Jest matchers |

---

## 🏗️ System Architecture

```mermaid
graph TB
    subgraph "User Interface"
        Console[Strategic Console]
        API[FastAPI Control Plane]
    end
    
    subgraph "Core Services"
        Evidence[Evidence Ingestion]
        Simulation[Simulation Engine]
        Debate[Debate Engine]
        Jarvis[Jarvis Integration]
    end
    
    subgraph "Data Sources"
        RSS[RSS Feeds]
        News[Google News]
        Reddit[Reddit]
        GitHub[GitHub]
        X[X/Twitter]
        GDELT[GDELT]
    end
    
    subgraph "Storage"
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

## 📁 Project Structure

**Backend:**
```
src/planagent/
├── config/              # Settings package (was config.py 527 lines → 4 files)
│   ├── __init__.py
│   ├── base.py          # Core settings (DB, Redis, Minio)
│   ├── openai.py        # Dynamic OpenAI target resolution
│   └── main.py          # Composed Settings class
├── services/
│   ├── debate/          # Debate package (was debate.py 3273 lines → 7 modules)
│   │   ├── prompts.py   # Agent role prompts & round plans
│   │   ├── rounds.py    # Round execution logic
│   │   ├── llm.py       # LLM calls & retry
│   │   ├── adjudication.py # Verdict & recommendations
│   │   ├── revisions.py # Stance revision tracking
│   │   └── triggers.py  # Auto-trigger logic
│   ├── simulation/      # Simulation package (was simulation.py 2281 lines → 6 modules)
│   │   ├── engine.py    # Core simulation engine
│   │   ├── scenarios.py # Scenario generation
│   │   ├── impact.py    # Impact assessment & scoring
│   │   ├── report.py    # Report generation
│   │   └── domain_packs.py # Domain pack management
│   └── ...              # Other services
├── db.py                # Database layer (cleaned, Alembic-only migrations)
└── ...
```

**Frontend:**
```
frontend-v2/src/
├── components/
│   ├── layout/          # App shell, sidebar, navigation chrome
│   └── ui/              # Shared cockpit surfaces and status components
├── pages/               # Dashboard, assistant, monitoring, reports, settings
├── api/                 # API endpoint helpers
├── hooks/               # Theme and app-level React hooks
└── main.tsx             # Vite entry point
```

---

## 🧪 Testing

### Backend Tests (pytest)
```bash
# Run all unit tests (92 tests, <1s)
python -m pytest tests/unit/ -v

# Run integration tests
python -m pytest tests/ -v
```

### Frontend Tests (Vitest)
```bash
cd frontend-v2
npm run build
```

### Stress Test
```bash
# 7-dimension stress test (requires running backend)
python tests/stress_test.py
```

**Latest Results:**
- ✅ Backend: 92 unit tests passing (0.26s)
- ✅ Frontend: 16 component tests passing (0.55s)
- ✅ Stress Test: 112 pass, 0 fail, 2 warnings
- 🔥 Concurrent: 20 users, 844 RPS, P50=1ms, zero 500 errors

---

## 📊 Quality & Performance

| Metric | Value |
|--------|-------|
| Backend Unit Tests | 92 passing |
| Frontend Component Tests | 16 passing |
| Stress Test Pass Rate | 112/114 (98.2%) |
| Concurrent Load (20 users) | 844 RPS, zero 500 errors |
| Response Time P50 | 1ms |
| Response Time P95 | 11ms |
| API Endpoints Tested | 82 |
| Max File Size (backend) | ~900 lines (down from 3273) |
| Max Page Size (frontend) | ~550 lines (down from 1665) |

---

## 📚 Documentation

- [📖 Full Technical Report](docs/planagent_full_report.md)
- [🚀 Agent Startup Playbook](docs/agent_startup_playbook.md)
- [🔧 Technical Debt Backlog](TECHNICAL_DEBT_BACKLOG.md)
- [🤝 Contributing Guide](CONTRIBUTING.md)
- [📝 Changelog](CHANGELOG.md)

---

## 🤝 Contributing

We welcome contributions! See our [Contributing Guide](CONTRIBUTING.md).

```bash
# 1. Fork the repository
# 2. Create a feature branch
git checkout -b feature/amazing-feature

# 3. Make your changes
# 4. Run tests
pytest

# 5. Commit your changes
git commit -m "feat: add amazing feature"

# 6. Push to the branch
git push origin feature/amazing-feature

# 7. Open a Pull Request
```

---

## 📄 License

This project is licensed under the Apache License 2.0 - see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/) - High-performance async APIs
- [Vite](https://vite.dev/) - Frontend build tooling
- [PostgreSQL](https://www.postgresql.org/) + [pgvector](https://github.com/pgvector/pgvector) - Database
- [Redis Streams](https://redis.io/docs/data-types/streams/) - Event streaming
- [MinIO](https://min.io/) - Object storage
- [Linux.do](https://linux.do) - 开源社区支持与交流

---

## 📞 Support & Contact

If you're interested in this project — whether for collaboration, feedback, or just a chat — feel free to reach out! We'd love to hear from you.

- 📧 Email: [cajd6876@gmail.com](mailto:cajd6876@gmail.com) | [2965866908@qq.com](mailto:2965866908@qq.com)
- 🐛 Issues: [GitHub Issues](https://github.com/dashitongzhi/MingJian/issues)
- 💬 Discussions: [GitHub Discussions](https://github.com/dashitongzhi/MingJian/discussions)

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
