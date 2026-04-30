# Investment Analysis Scenario

This example demonstrates PlanAgent's capability to support data-driven investment research and portfolio analysis in the AI technology sector.

## Overview

The investment analysis scenario focuses on:
- **Market intelligence**: Tracking funding trends, competitive dynamics, and technology maturity
- **Risk assessment**: Regulatory, competitive, and macroeconomic risk factors
- **Scenario planning**: Modeling different market conditions and their impact on portfolio value
- **Evidence synthesis**: Combining multiple data sources into coherent investment theses

## Files

- `evidence_ingest.json`: Market research, financial data, and competitive intelligence
- `baseline_simulation.json`: Baseline simulation parameters for AI startup portfolio

## Usage

### 1. Ingest Market Intelligence

```bash
curl -X POST http://127.0.0.1:8000/ingest/runs \
  -H "Content-Type: application/json" \
  --data @examples/investment_analysis/evidence_ingest.json
```

### 2. Run Portfolio Simulation

```bash
curl -X POST http://127.0.0.1:8000/simulation/runs \
  -H "Content-Type: application/json" \
  --data @examples/investment_analysis/baseline_simulation.json
```

### 3. Trigger Investment Thesis Debate

```bash
curl -X POST http://127.0.0.1:8000/debates/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "run_id": "{run_id}",
    "topic": "Should we increase allocation to foundation model startups given current market dynamics?",
    "trigger_type": "pivot_decision",
    "target_type": "run",
    "context_lines": [
      "Base analysis on market data, funding trends, and competitive dynamics",
      "Consider regulatory risks and open-source disruption"
    ]
  }'
```

### 4. Analyze Results

```bash
# View decision trace
curl http://127.0.0.1:8000/runs/{run_id}/decision-trace

# Compare investment scenarios
curl http://127.0.0.1:8000/runs/{run_id}/scenario-compare

# View workbench
curl http://127.0.0.1:8000/runs/{run_id}/workbench

# Read debate results
curl http://127.0.0.1:8000/runs/{run_id}/debates
```

## Key Insights

This scenario helps investors and analysts:
1. **Synthesize market intelligence** from multiple sources into actionable insights
2. **Model portfolio performance** under different market conditions
3. **Identify risks and opportunities** through evidence-based analysis
4. **Validate investment theses** through multi-agent debate
5. **Generate comprehensive reports** with source attribution

## Customization

Modify the simulation to test different investment scenarios:
- Adjust `initial_state` to reflect different market assumptions
- Add `external_factors` for macro-economic scenario testing
- Change `tick_count` to model different investment horizons
- Update `actor_template` to represent different company types (SaaS, infrastructure, etc.)