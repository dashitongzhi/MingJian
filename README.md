# PlanAgent

PlanAgent is the bootstrap implementation of the platform described in [PLAN.md](./PLAN.md). The current state covers `Phase 1` evidence ingestion, `Phase 2` corporate simulation/reporting, and a `Phase 3` MVP slice for military baseline runs plus scenario branching.

## What is implemented now

- FastAPI control plane with the Phase 1 endpoints working:
  - `POST /analysis`
  - `POST /analysis/stream`
  - `POST /ingest/runs`
  - `GET /evidence`
  - `GET /claims`
  - `GET /signals`
  - `GET /events`
  - `GET /trends`
  - `GET /review/items`
  - `POST /review/items/{id}/accept`
  - `POST /review/items/{id}/reject`
- Phase 2 corporate simulation/report endpoints:
  - `POST /simulation/runs`
  - `POST /scenario/runs/{simulation_run_id}`
  - `GET /runs/{run_id}/decision-trace`
  - `GET /runs/{run_id}/scenario-compare`
  - `GET /runs/{run_id}/geo-assets`
  - `GET /runs/{run_id}/external-shocks`
  - `GET /companies/{company_id}/reports/latest`
  - `GET /military/scenarios/{scenario_id}/reports/latest`
  - `POST /admin/rules/reload`
  - `GET /admin/openai/status`
  - `POST /admin/openai/test`
- Root status page:
  - `GET /`
- Shared core types for the evidence chain, simulation artifacts, and debate protocol.
- SQLAlchemy models for ingestion, evidence, claims, review items, lightweight signal/event/trend promotion, and event archive.
- Event bus abstraction with in-memory and Redis Streams backends.
- Optional OpenAI `Responses API` integration for evidence extraction and report enhancement.
- Worker entrypoints for the first orchestration slice, including an ingest worker that can process queued runs.
- YAML-backed corporate and military rule loading with reload support.
- Corporate and military baseline simulation services with deterministic decision trace generation.
- Military scenario branching with baseline fork metadata and KPI comparison output.
- Geo-asset snapshots and external-shock records for military operational views.
- Report generation that persists latest company reports and scenario-scoped military reports.
- Alembic bootstrap migration for the Phase 1 schema.
- Initial simulation/domain-pack registry scaffold so later phases can add corporate and military execution logic without rewriting the core package layout.

## Quick start

1. Create a virtual environment and install the package:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .[dev]
```

2. Copy `.env.example` to `.env` if you want PostgreSQL or Redis instead of the local SQLite/memory defaults.

If you want OpenAI-backed extraction/reporting, you can configure one shared OpenAI-compatible endpoint with `PLANAGENT_OPENAI_API_KEY` + `PLANAGENT_OPENAI_BASE_URL`, or configure each role separately with `PLANAGENT_OPENAI_PRIMARY_*`, `PLANAGENT_OPENAI_EXTRACTION_*`, `PLANAGENT_OPENAI_X_SEARCH_*`, and `PLANAGENT_OPENAI_REPORT_*`. The model selector accepts OpenClaw-style values such as `openai/gpt-5.2`, and it also normalizes Codex UI names such as `GPT-5.4` or `GPT-5.3-Codex` to the raw model id used by the SDK.

A practical pattern is:
- `primary`: GPT endpoint for `/admin/openai/test` and the default model route
- `extraction`: Gemini-compatible endpoint for evidence extraction
- `x_search`: Grok-compatible endpoint for model-backed X search and `source_type=x` extraction
- `report`: Claude-compatible endpoint for report enhancement

The app now tries `Responses API` first and falls back to `chat.completions` for compatibility gateways.

3. Start the API:

```powershell
python -m uvicorn planagent.main:app --reload
```

4. Submit a sample ingest run:

```powershell
curl -X POST http://127.0.0.1:8000/ingest/runs ^
  -H "Content-Type: application/json" ^
  -d "{\"requested_by\":\"analyst\",\"items\":[{\"source_type\":\"rss\",\"source_url\":\"https://example.com/post\",\"title\":\"Acme ships new GPU service\",\"content_text\":\"Acme shipped a new GPU service across three regions and reduced model training cost by 22 percent. Demand rose.\",\"published_at\":\"2026-03-15T09:00:00Z\"}]}"
```

You can also submit a single analysis request and let the app auto-fetch related public sources before returning a result. The current source adapters cover Google News, Reddit, Hacker News, and X. X can be sourced either from the official recent-search API with `PLANAGENT_X_BEARER_TOKEN`, or from a model-backed route when `PLANAGENT_OPENAI_X_SEARCH_*` is configured:

```powershell
$body = @{
  content = "分析 OpenAI GPU 成本与模型发布节奏的最新变化"
  domain_id = "corporate"
  auto_fetch_news = $true
  include_google_news = $true
  include_reddit = $true
  include_hacker_news = $true
  include_x = $false
  max_news_items = 5
  max_tech_items = 3
  max_reddit_items = 3
  max_x_items = 3
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/analysis" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

If you want to display progress and rationale summaries while the analysis is running, use the streaming endpoint:

```powershell
$body = @{
  content = "分析东部战区补给线受阻之后的态势变化"
  domain_id = "military"
  auto_fetch_news = $true
  include_reddit = $true
  include_x = $false
} | ConvertTo-Json

Invoke-WebRequest `
  -Uri "http://127.0.0.1:8000/analysis/stream" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

The stream emits `step`, `source`, and `result` events. If X is enabled in the request but neither a bearer token nor an `x_search` model route is configured, the request still completes and emits a `source_skip` step explaining why X was not queried.

5. Inspect the generated evidence and review queue:

```powershell
curl http://127.0.0.1:8000/evidence
curl http://127.0.0.1:8000/claims
curl http://127.0.0.1:8000/review/items
curl http://127.0.0.1:8000/admin/openai/status
curl -X POST http://127.0.0.1:8000/admin/openai/test -H "Content-Type: application/json" -d "{}"
curl -X POST http://127.0.0.1:8000/admin/openai/test -H "Content-Type: application/json" -d "{\"target\":\"primary\",\"model\":\"GPT-5.4\"}"
curl -X POST http://127.0.0.1:8000/admin/openai/test -H "Content-Type: application/json" -d "{\"target\":\"extraction\",\"model\":\"gemini-3.1-pro-preview-search\"}"
curl -X POST http://127.0.0.1:8000/admin/openai/test -H "Content-Type: application/json" -d "{\"target\":\"x_search\",\"model\":\"grok-4.20-beta\"}"
curl -X POST http://127.0.0.1:8000/admin/openai/test -H "Content-Type: application/json" -d "{\"target\":\"report\",\"model\":\"claude-sonnet-4-5-thinking\"}"
```

If you want X-specific extraction to route through Grok, set the ingest item `source_type` to `x` or `twitter`. The pipeline will send those items to the `x_search` model target automatically.

6. Run a company baseline simulation:

```powershell
curl -X POST http://127.0.0.1:8000/simulation/runs ^
  -H "Content-Type: application/json" ^
  -d "{\"company_id\":\"acme-ai\",\"company_name\":\"Acme AI\",\"market\":\"foundation-models\",\"tick_count\":3,\"actor_template\":\"ai_model_provider\"}"
curl http://127.0.0.1:8000/companies/acme-ai/reports/latest
```

7. Run a military baseline and a forked scenario:

```powershell
curl -X POST http://127.0.0.1:8000/simulation/runs ^
  -H "Content-Type: application/json" ^
  -d "{\"domain_id\":\"military\",\"force_id\":\"blue-shield-brigade\",\"force_name\":\"Blue Shield Brigade\",\"theater\":\"eastern-sector\",\"tick_count\":4,\"actor_template\":\"brigade\"}"

curl -X POST http://127.0.0.1:8000/scenario/runs/{baseline_run_id} ^
  -H "Content-Type: application/json" ^
  -d "{\"fork_step\":2,\"tick_count\":2,\"assumptions\":[\"Civilian corridors stay open.\"],\"state_overrides\":{\"civilian_risk\":0.72,\"logistics_throughput\":0.68},\"probability_band\":\"medium-high\"}"

curl http://127.0.0.1:8000/runs/{baseline_run_id}/scenario-compare
curl http://127.0.0.1:8000/runs/{baseline_run_id}/geo-assets
curl http://127.0.0.1:8000/runs/{baseline_run_id}/external-shocks
curl http://127.0.0.1:8000/military/scenarios/{scenario_id}/reports/latest
```

## Infrastructure

`compose.yml` bootstraps PostgreSQL, Redis, MinIO, the API, and an ingest worker. The Compose stack is intentionally conservative for the first pass; pgvector/PostGIS specific tuning can be layered on once the base ingestion loop is stable. The worker CLI now also exposes `simulation-worker` and `report-worker` for queued execution.

## Current limits

- Debate protocols and richer map rendering are still deferred to later phases.
- Claim extraction remains heuristic. The schema and event flow are ready for a stronger knowledge worker in the next pass.
- OpenAI integration is optional. If the API key is missing or a model call fails, the app falls back to the built-in heuristics instead of failing the request.
- X search is optional. Configure either `PLANAGENT_X_BEARER_TOKEN` for the official X API or `PLANAGENT_OPENAI_X_SEARCH_*` for a model-backed X route. Without either one, the analysis flow skips X and continues with Google News, Reddit, and Hacker News.
- Tests are included, but they require the project dependencies to be installed first.
