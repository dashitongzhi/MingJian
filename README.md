# PlanAgent

PlanAgent is the bootstrap implementation of the platform described in [PLAN.md](./PLAN.md). The current state covers `Phase 1` evidence ingestion, `Phase 2` corporate simulation/reporting, and a `Phase 3` MVP slice for military baseline runs plus scenario branching.

## What is implemented now

- FastAPI control plane with the Phase 1 endpoints working:
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

If you want OpenAI-backed extraction/reporting, also set either `PLANAGENT_OPENAI_API_KEY` or `OPENAI_API_KEY`. The model selector accepts OpenClaw-style values such as `openai/gpt-5.2`; the app normalizes that to the raw OpenAI model id before calling the SDK. You can also manually test a candidate model such as `openai/gpt-5.4` through `POST /admin/openai/test`, but the current official OpenAI docs still list GPT-5.2 on the model pages, so GPT-5.4 should be treated as an explicit opt-in experiment instead of the default.

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

5. Inspect the generated evidence and review queue:

```powershell
curl http://127.0.0.1:8000/evidence
curl http://127.0.0.1:8000/claims
curl http://127.0.0.1:8000/review/items
curl http://127.0.0.1:8000/admin/openai/status
curl -X POST http://127.0.0.1:8000/admin/openai/test -H "Content-Type: application/json" -d "{}"
```

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
- Tests are included, but they require the project dependencies to be installed first.
