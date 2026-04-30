# PlanAgent

**AI-Powered Multi-Agent Platform for Evidence-Driven Scenario Simulation & Strategic Decision-Making**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green.svg)](https://fastapi.tiangolo.com/)
[![GitHub stars](https://img.shields.io/github/stars/dashitongzhi/planagent?style=social)](https://github.com/dashitongzhi/planagent/stargazers)

PlanAgent is an AI-powered multi-agent platform that enables evidence-driven scenario simulation and strategic decision-making for both corporate and military domains. It features a debate protocol, real-time evidence ingestion, and advanced simulation capabilities.

## 🚀 Key Features

- **Evidence-Driven Intelligence**: Automatically ingest and analyze data from multiple sources (RSS, news, Reddit, GitHub, X, GDELT)
- **Multi-Domain Simulation**: Support for both corporate and military scenario modeling
- **AI Debate Protocol**: Multi-agent debate system for rigorous decision validation
- **Real-Time Analysis**: Streaming analysis with progress tracking and source attribution
- **Strategic Console**: Unified workbench for evidence review, scenario comparison, and decision tracing
- **Extensible Architecture**: Plugin-based design with YAML-configurable rules and models

## 🎯 Use Cases

- **Corporate Strategy**: Market analysis, competitive intelligence, and scenario planning
- **Military Planning**: Operational analysis, logistics simulation, and threat assessment
- **Risk Management**: Evidence-based risk assessment with multi-perspective validation
- **Investment Research**: Data-driven investment thesis development and stress testing

## 📦 Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL (optional, SQLite for development)
- Redis (optional, for event bus)

### Installation

```bash
# Clone the repository
git clone https://github.com/dashitongzhi/planagent.git
cd planagent

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"
```

### Configuration

```bash
# Copy example configuration
cp .env.example .env

# Configure your environment variables
# Required: PLANAGENT_OPENAI_API_KEY for AI features
# Optional: PostgreSQL, Redis, and other service connections
```

### Run the Application

```bash
# Start the API server
uvicorn planagent.main:app --reload

# Access the strategic console
open http://127.0.0.1:8000/console
```

### Submit Your First Analysis

```bash
# Corporate analysis
curl -X POST http://127.0.0.1:8000/analysis \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Analyze recent developments in AI chip manufacturing",
    "domain_id": "corporate",
    "auto_fetch_news": true,
    "include_google_news": true,
    "include_reddit": true,
    "include_hacker_news": true
  }'

# Military analysis
curl -X POST http://127.0.0.1:8000/analysis/stream \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Assess logistics challenges in eastern theater operations",
    "domain_id": "military",
    "auto_fetch_news": true
  }'
```

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Strategic Console                 │
├─────────────────────────────────────────────────────┤
│                  FastAPI Control Plane              │
├─────────────┬─────────────┬─────────────────────────┤
│  Evidence   │ Simulation  │      Debate Engine      │
│  Ingestion  │   Engine    │   (Multi-Agent AI)      │
├─────────────┼─────────────┼─────────────────────────┤
│  Source Adapters │ Corporate │ Military │  Jarvis   │
│  (RSS, News,     │ Models    │ Models   │  Integration│
│   Reddit, X...)  │           │          │            │
└─────────────────────────────────────────────────────┘
```

## 📚 Documentation

- **[API Reference](docs/api.md)**: Complete endpoint documentation
- **[Configuration Guide](docs/configuration.md)**: Environment variables and settings
- **[Simulation Examples](examples/)**: Ready-to-use scenario templates
- **[Architecture Overview](docs/architecture.md)**: System design and components

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/)
- Powered by [SQLAlchemy](https://www.sqlalchemy.org/) and [Pydantic](https://docs.pydantic.dev/)
- AI capabilities via OpenAI-compatible APIs

---

**⭐ Star this repository if you find it useful!**

**📧 Contact**: [dashitongzhi](https://github.com/dashitongzhi)