# Agent Startup Scenario Pack

This folder captures a reusable "AI agent startup" simulation template for 明鉴.

## Files

- `evidence_ingest.json`: seed evidence for the 2026 enterprise-agent market.
- `baseline_simulation.json`: moderate starting position with real traction but tight cash discipline.
- `upside_simulation.json`: stronger proof points, better runway, and healthier delivery posture.
- `downside_simulation.json`: weaker trust, shorter runway, and more pressure from bundled platforms.

## Run it

1. Ingest the market signals:

```bash
curl -X POST http://127.0.0.1:8000/ingest/runs \
  -H "Content-Type: application/json" \
  --data @examples/agent_startup/evidence_ingest.json
```

2. Run the baseline:

```bash
curl -X POST http://127.0.0.1:8000/simulation/runs \
  -H "Content-Type: application/json" \
  --data @examples/agent_startup/baseline_simulation.json
```

3. Run the upside or downside branch:

```bash
curl -X POST http://127.0.0.1:8000/simulation/runs \
  -H "Content-Type: application/json" \
  --data @examples/agent_startup/upside_simulation.json
```

```bash
curl -X POST http://127.0.0.1:8000/simulation/runs \
  -H "Content-Type: application/json" \
  --data @examples/agent_startup/downside_simulation.json
```

4. Inspect results:

```bash
curl http://127.0.0.1:8000/companies/agent-founder-baseline/reports/latest
curl http://127.0.0.1:8000/companies/agent-founder-upside/reports/latest
curl http://127.0.0.1:8000/companies/agent-founder-downside/reports/latest
```

## One-click preset

If you want this pack to run inside an isolated tenant so it does not mix with older experiment data, use:

```bash
curl -X POST http://127.0.0.1:8000/presets/agent-startup/runs \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"founder-lab","scenarios":["baseline","upside","downside"]}'
```

The response includes run ids, report paths, and a startup KPI pack for each scenario. You can also query the scorecard later with:

```bash
curl http://127.0.0.1:8000/runs/{run_id}/startup-kpis
curl "http://127.0.0.1:8000/companies/agent-founder-baseline/reports/latest?tenant_id=founder-lab"
```

## What changed in this template

The corporate rules now capture four startup-specific forces that were missing from the initial baseline:

- platform bundling pressure
- enterprise buying friction
- reliability incidents
- validated ROI and renewal pull

That means the simulation is less likely to over-index on pure adoption momentum and more likely to reflect the operational trade-offs of building an agent startup in enterprise software.
