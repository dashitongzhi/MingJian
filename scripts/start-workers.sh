#!/bin/bash
# Run all PlanAgent workers in background
set -e

WORKERS=(
  ingest-worker
  knowledge-worker
  graph-worker
  review-worker
  simulation-worker
  report-worker
  strategic-watch-worker
  watch-ingest-worker
  calibration-worker
)

echo "Starting all PlanAgent workers..."
for w in "${WORKERS[@]}"; do
  echo "  -> $w"
  planagent-worker "$w" --loop &
done

echo "All workers started. PIDs: $(jobs -p | tr '\n' ' ')"
wait
