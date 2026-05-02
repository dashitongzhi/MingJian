#!/bin/bash
# Run all PlanAgent workers in background
set -uo pipefail

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

WORKER_PIDS=()
SHUTTING_DOWN=0
GRACE_EXPIRED=0

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*"
}

start_worker() {
  local index="$1"
  local worker="${WORKERS[$index]}"
  local pid

  log "Starting worker: ${worker}"
  planagent-worker "${worker}" --loop &
  pid="$!"
  WORKER_PIDS[$index]="${pid}"
  log "Started worker: ${worker} (pid ${pid})"
}

tracked_workers_remaining() {
  local pid

  for pid in "${WORKER_PIDS[@]:-}"; do
    if [[ -n "${pid:-}" ]]; then
      return 0
    fi
  done

  return 1
}

send_signal_to_workers() {
  local signal="$1"
  local index worker pid

  for index in "${!WORKERS[@]}"; do
    worker="${WORKERS[$index]}"
    pid="${WORKER_PIDS[$index]:-}"

    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      log "Sending ${signal} to worker: ${worker} (pid ${pid})"
      kill "-${signal}" "${pid}" 2>/dev/null || true
    fi
  done
}

reap_stopped_workers() {
  local wait_status="${1:-unknown}"
  local index worker pid actual_status status

  for index in "${!WORKERS[@]}"; do
    worker="${WORKERS[$index]}"
    pid="${WORKER_PIDS[$index]:-}"

    if [[ -z "${pid}" ]] || kill -0 "${pid}" 2>/dev/null; then
      continue
    fi

    actual_status="${wait_status}"
    if wait "${pid}" 2>/dev/null; then
      actual_status=0
    else
      status="$?"
      if [[ "${status}" -ne 127 ]]; then
        actual_status="${status}"
      fi
    fi

    log "Stopped worker: ${worker} (pid ${pid}, status ${actual_status})"
    WORKER_PIDS[$index]=""

    if [[ "${SHUTTING_DOWN}" -eq 0 ]]; then
      log "Worker exited unexpectedly: ${worker} (pid ${pid}, status ${actual_status}); restarting"
      start_worker "${index}"
    fi
  done
}

shutdown() {
  local timer_pid status index worker pid

  SHUTTING_DOWN=1
  trap - SIGTERM SIGINT
  log "Shutdown signal received; stopping workers"

  send_signal_to_workers TERM

  trap 'GRACE_EXPIRED=1' SIGALRM
  ( sleep 10; kill -ALRM "$$" 2>/dev/null ) &
  timer_pid="$!"

  while tracked_workers_remaining && [[ "${GRACE_EXPIRED}" -eq 0 ]]; do
    if wait -n; then
      status=0
    else
      status="$?"
    fi

    if [[ "${GRACE_EXPIRED}" -eq 1 ]] || [[ "${status}" -eq 127 ]]; then
      break
    fi

    reap_stopped_workers "${status}"
  done

  kill "${timer_pid}" 2>/dev/null || true
  wait "${timer_pid}" 2>/dev/null || true
  trap - SIGALRM

  if tracked_workers_remaining; then
    log "Grace period expired; killing remaining workers"
    send_signal_to_workers KILL
  fi

  for index in "${!WORKERS[@]}"; do
    worker="${WORKERS[$index]}"
    pid="${WORKER_PIDS[$index]:-}"

    if [[ -z "${pid}" ]]; then
      continue
    fi

    if wait "${pid}" 2>/dev/null; then
      status=0
    else
      status="$?"
    fi

    log "Stopped worker: ${worker} (pid ${pid}, status ${status})"
    WORKER_PIDS[$index]=""
  done

  log "All workers stopped"
  exit 0
}

trap shutdown SIGTERM SIGINT

log "Starting all PlanAgent workers..."
for index in "${!WORKERS[@]}"; do
  start_worker "${index}"
done

log "All workers started. PIDs: ${WORKER_PIDS[*]}"

while true; do
  if wait -n; then
    status=0
  else
    status="$?"
  fi

  if [[ "${status}" -eq 127 ]]; then
    log "No tracked worker processes remain; exiting"
    exit 1
  fi

  reap_stopped_workers "${status}"
done
