# PlanAgent

PlanAgent is the bootstrap implementation of the platform described in [PLAN.md](./PLAN.md). The current state covers `Phase 1` evidence ingestion, `Phase 2` corporate simulation/reporting, `Phase 3` military baseline runs plus scenario branching, and a first `Phase 4/5` backend slice for the unified workbench and debate protocol.

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
  - `GET /runs/{run_id}/workbench`
  - `GET /runs/{run_id}/scenario-compare`
  - `POST /runs/{run_id}/scenario-search`
  - `GET /runs/{run_id}/geo-assets`
  - `GET /runs/{run_id}/geojson`
  - `GET /runs/{run_id}/external-shocks`
  - `GET /runs/{run_id}/replay-package`
  - `GET /companies/{company_id}/reports/latest`
  - `GET /military/scenarios/{scenario_id}/reports/latest`
  - `GET /debates/{debate_id}`
  - `GET /runs/{run_id}/debates`
  - `POST /debates/trigger`
  - `POST /jarvis/runs`
  - `GET /jarvis/runs`
  - `POST /admin/rules/reload`
  - `GET /admin/runtime/queues`
  - `GET /admin/analysis/cache`
  - `GET /admin/openai/status`
  - `POST /admin/openai/test`
  - `GET /knowledge/graph`
  - `GET /knowledge/search`
  - `GET /sources/health`
  - `GET /sources/snapshots`
- Root status page:
  - `GET /`
- Shared core types for the evidence chain, simulation artifacts, and debate protocol.
- SQLAlchemy models for ingestion, source snapshots, source health, evidence, claims, review items, lightweight signal/event/trend promotion, graph nodes/edges, scenario replay packages, Jarvis orchestration records, dead-letter records, and event archive. Source snapshots default to local filesystem storage and can be switched to MinIO with `PLANAGENT_SOURCE_SNAPSHOT_BACKEND=minio`.
- Event bus abstraction with in-memory and Redis Streams backends, including `{topic}.dlq` dead-letter publication.
- Optional OpenAI `Responses API` integration for evidence extraction and report enhancement.
- Worker entrypoints for the orchestration slice, including a queued ingest path split across `ingest-worker` and `knowledge-worker`, a persisted embedding-backed `graph-worker`, source-watch workers, report/simulation workers, plus a conflict-aware `review-worker`.
- Strategic console endpoints for saved watch sessions, daily brief history, run snapshots, and streaming multi-model discussion:
  - `GET /console`
  - `POST /assistant/sessions`
  - `GET /assistant/sessions`
  - `GET /assistant/sessions/{session_id}`
  - `POST /assistant/daily-brief`
  - `POST /assistant/runs`
  - `POST /assistant/stream`
- YAML-backed corporate and military rule loading with reload support.
- Corporate and military baseline simulation services with deterministic decision trace generation.
- Military and corporate scenario branching with baseline fork metadata, KPI comparison output, compact beam-search branch generation, and replay package export.
- Geo-asset snapshots and external-shock records for military operational views.
- Unified workbench aggregation for review queue, evidence graph, timeline, geo map, scenario tree, KPI comparison, and debate records.
- Debate session persistence with manual trigger, audit trail rounds, verdict storage, and event publication.
- Report generation that persists latest company reports and scenario-scoped military reports.
- Jarvis `plan-agent` profile plus PlanAgent-specific self-review, cross-review, repair, arbitrator, and debate prompt files under `E:\Project\jarvis\source\jarvis\`; this app also persists local Jarvis lifecycle records through `/jarvis/runs`.
- Alembic bootstrap migration for the Phase 1 schema.
- Initial simulation/domain-pack registry scaffold so later phases can add corporate and military execution logic without rewriting the core package layout.

## Quick start

1. Create a virtual environment and install the package.

On Windows:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .[dev]
```

On macOS:

```bash
/opt/homebrew/bin/python3.12 -m venv .venv-mac
./.venv-mac/bin/python -m pip install --upgrade pip setuptools wheel
./.venv-mac/bin/python -m pip install -e '.[dev]'
./.venv-mac/bin/python -m pytest -q
```

2. Copy `.env.example` to `.env` if you want PostgreSQL or Redis instead of the local SQLite/memory defaults.

If you want OpenAI-backed extraction/reporting, you can configure one shared OpenAI-compatible endpoint with `PLANAGENT_OPENAI_API_KEY` + `PLANAGENT_OPENAI_BASE_URL`, or configure each role separately with `PLANAGENT_OPENAI_PRIMARY_*`, `PLANAGENT_OPENAI_EXTRACTION_*`, `PLANAGENT_OPENAI_X_SEARCH_*`, and `PLANAGENT_OPENAI_REPORT_*`. The model selector accepts OpenClaw-style values such as `openai/gpt-5.2`, and it also normalizes Codex UI names such as `GPT-5.4` or `GPT-5.3-Codex` to the raw model id used by the SDK.

A practical pattern is:
- `primary`: GPT endpoint for `/admin/openai/test` and the default model route
- `extraction`: Gemini-compatible endpoint for evidence extraction
- `x_search`: Grok-compatible endpoint for model-backed X search and `source_type=x` extraction
- `report`: Claude-compatible endpoint for company and military report enhancement

The app now tries `Responses API` first and falls back to `chat.completions` for compatibility gateways.
Each target can also be configured independently. The effective model, API key source, and base URL inheritance are exposed through `GET /admin/openai/status`, which is the fastest way to verify whether a route is using an explicit override or falling back to a shared setting.

3. Start the API:

```powershell
python -m uvicorn planagent.main:app --reload
```

You can then open the strategic console in the browser:

```bash
open http://127.0.0.1:8000/console
```

4. Submit a sample ingest run:

```powershell
curl -X POST http://127.0.0.1:8000/ingest/runs ^
  -H "Content-Type: application/json" ^
  -d "{\"requested_by\":\"analyst\",\"items\":[{\"source_type\":\"rss\",\"source_url\":\"https://example.com/post\",\"title\":\"Acme ships new GPU service\",\"content_text\":\"Acme shipped a new GPU service across three regions and reduced model training cost by 22 percent. Demand rose.\",\"published_at\":\"2026-03-15T09:00:00Z\"}]}"
```

You can also submit a single analysis request and let the app auto-fetch related public sources before returning a result. The current source adapters cover Google News, Reddit, Hacker News, GitHub repository plus Issues/PR search, configured/default RSS feeds, GDELT document search, Open-Meteo weather context, OpenSky aviation snapshots for recognized military theaters, and X. X can be sourced either from the official recent-search API with `PLANAGENT_X_BEARER_TOKEN`, or from a model-backed route when `PLANAGENT_OPENAI_X_SEARCH_*` is configured. Extra RSS feeds can be supplied with `PLANAGENT_ADDITIONAL_RSS_FEEDS` as a comma-separated list. `POST /analysis` also uses a DB-backed TTL cache controlled by `PLANAGENT_ANALYSIS_CACHE_ENABLED` and `PLANAGENT_API_CACHE_TTL_SECONDS`; use `/analysis/stream` when you want a fresh live trace.

```powershell
$body = @{
  content = "分析 OpenAI GPU 成本与模型发布节奏的最新变化"
  domain_id = "corporate"
  auto_fetch_news = $true
  include_google_news = $true
  include_reddit = $true
  include_hacker_news = $true
  include_github = $true
  include_rss_feeds = $true
  include_gdelt = $true
  include_weather = $false
  include_aviation = $false
  include_x = $false
  max_news_items = 5
  max_tech_items = 3
  max_reddit_items = 3
  max_github_items = 3
  max_rss_items = 3
  max_gdelt_items = 3
  max_weather_items = 1
  max_aviation_items = 1
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
curl http://127.0.0.1:8000/knowledge/graph
curl "http://127.0.0.1:8000/knowledge/search?q=agent%20workflow"
curl http://127.0.0.1:8000/sources/snapshots
curl http://127.0.0.1:8000/sources/health
curl http://127.0.0.1:8000/admin/runtime/queues
curl http://127.0.0.1:8000/admin/analysis/cache
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

There is also a reusable enterprise-agent founder scenario pack under `examples/agent_startup/`, plus a concrete operator-facing roadmap in `docs/agent_startup_playbook.md`. Start with:

```bash
curl -X POST http://127.0.0.1:8000/ingest/runs \
  -H "Content-Type: application/json" \
  --data @examples/agent_startup/evidence_ingest.json

curl -X POST http://127.0.0.1:8000/simulation/runs \
  -H "Content-Type: application/json" \
  --data @examples/agent_startup/baseline_simulation.json
```

If you want a clean isolated founder lab without reusing older claims, call the preset API instead. It creates a tenant-scoped ingest run plus one or more startup simulations in a single request:

```bash
curl -X POST http://127.0.0.1:8000/presets/agent-startup/runs \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"founder-lab","scenarios":["baseline","upside","downside"]}'
```

You can then inspect the run-specific startup scorecard and tenant-scoped reports:

```bash
curl http://127.0.0.1:8000/runs/{run_id}/startup-kpis
curl "http://127.0.0.1:8000/companies/agent-founder-baseline/reports/latest?tenant_id=founder-lab"
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

8. Inspect the unified workbench or trigger a debate:

```powershell
curl http://127.0.0.1:8000/runs/{run_id}/workbench

curl -X POST http://127.0.0.1:8000/debates/trigger ^
  -H "Content-Type: application/json" ^
  -d "{\"run_id\":\"{run_id}\",\"topic\":\"Should the baseline posture be retained?\",\"trigger_type\":\"pivot_decision\",\"target_type\":\"run\",\"context_lines\":[\"Prefer evidence-grounded reasoning only.\"]}"

curl http://127.0.0.1:8000/runs/{run_id}/debates
curl http://127.0.0.1:8000/debates/{debate_id}
```

## Jarvis integration

Phase 5 now ships a `plan-agent` profile and prompts for the external Jarvis runtime:

- Profile: `E:\Project\jarvis\source\jarvis\profiles\plan-agent.yaml`
- Prompts:
  - `E:\Project\jarvis\source\jarvis\prompts\plan-agent\self_reviewer.md`
  - `E:\Project\jarvis\source\jarvis\prompts\plan-agent\cross_reviewer.md`
  - `E:\Project\jarvis\source\jarvis\prompts\plan-agent\repairer.md`
  - `E:\Project\jarvis\source\jarvis\prompts\plan-agent\arbitrator.md`
  - `E:\Project\jarvis\source\jarvis\prompts\plan-agent\debate_advocate.md`
  - `E:\Project\jarvis\source\jarvis\prompts\plan-agent\debate_challenger.md`
  - `E:\Project\jarvis\source\jarvis\prompts\plan-agent\debate_arbitrator.md`

## Infrastructure

`compose.yml` bootstraps PostgreSQL, Redis, MinIO, the API, `ingest-worker`, `knowledge-worker`, `graph-worker`, `review-worker`, `simulation-worker`, `report-worker`, `watch-ingest-worker`, and `strategic-watch-worker`. The watch worker scans saved strategic sessions and auto-generates daily briefs when `next_refresh_at` is due.

## Current limits

- The strategic console is a single-file frontend served from the API. It is useful today, but not yet broken out into a dedicated frontend workspace.
- Debate execution is currently deterministic/manual on the PlanAgent side. The external multi-model runtime is represented by the Jarvis profile and prompt assets, but not executed inside this FastAPI app.
- `review-worker` now auto-resolves a narrow slice of the queue: pending claims that have accepted corroborating or conflicting evidence and can be routed through a conflict-resolution debate. The rest of the queue still remains analyst-driven.
- Claim extraction still falls back to heuristics whenever no `extraction` or `x_search` model route is configured.
- OpenAI integration is optional. If the API key is missing or a model call fails, the app falls back to the built-in heuristics instead of failing the request.
- X search is optional. Configure either `PLANAGENT_X_BEARER_TOKEN` for the official X API or `PLANAGENT_OPENAI_X_SEARCH_*` for a model-backed X route. Without either one, the analysis flow skips X and continues with Google News, Reddit, and Hacker News.
- Automatic daily updates require a running `strategic-watch-worker`. Saved sessions keep their own timezone, refresh hour, and next due timestamp, but the API process itself does not run a background scheduler.
- Tests are included, but they require the project dependencies to be installed first.
