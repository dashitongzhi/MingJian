# Military Logistics Scenario

This example demonstrates PlanAgent's capability to analyze military logistics operations and simulate various scenarios for supply chain optimization.

## Overview

The military logistics scenario focuses on:
- **Supply route analysis**: Evaluating efficiency and vulnerability of logistics corridors
- **Resource management**: Tracking fuel, medical supplies, ammunition, and vehicle readiness
- **Risk assessment**: Weather, security threats, and infrastructure conditions
- **Operational planning**: Optimizing logistics under constraints

## Files

- `evidence_ingest.json`: Sample intelligence and logistics data for eastern sector operations
- `baseline_simulation.json`: Baseline simulation parameters for logistics command

## Usage

### 1. Ingest Evidence Data

```bash
curl -X POST http://127.0.0.1:8000/ingest/runs \
  -H "Content-Type: application/json" \
  --data @examples/military_logistics/evidence_ingest.json
```

### 2. Run Baseline Simulation

```bash
curl -X POST http://127.0.0.1:8000/simulation/runs \
  -H "Content-Type: application/json" \
  --data @examples/military_logistics/baseline_simulation.json
```

### 3. Analyze Results

```bash
# Get simulation results
curl http://127.0.0.1:8000/runs/{run_id}/decision-trace

# Compare scenarios
curl http://127.0.0.1:8000/runs/{run_id}/scenario-compare

# View workbench
curl http://127.0.0.1:8000/runs/{run_id}/workbench
```

## Key Insights

This scenario helps military planners:
1. Identify critical supply chain vulnerabilities
2. Optimize resource allocation under constraints
3. Plan for weather and security contingencies
4. Develop contingency routes and backup plans
5. Train logistics personnel with realistic scenarios

## Customization

You can modify the simulation parameters to test different scenarios:
- Adjust `initial_state` values to reflect current inventory levels
- Modify `external_factors` to simulate different environmental conditions
- Change `tick_count` to model different time horizons
- Update `actor_template` to represent different unit types