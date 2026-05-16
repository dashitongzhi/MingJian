#!/usr/bin/env bash
# Start the local PlanAgent stack in detached screen sessions.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-${ROOT_DIR}/.venv312/bin/python}"
DB_URL="${PLANAGENT_DATABASE_URL:-sqlite+aiosqlite:////tmp/planagent-local.db}"
EVENT_BUS="${PLANAGENT_EVENT_BUS_BACKEND:-memory}"
if [[ -n "${PLANAGENT_LOCAL_WORKERS:-}" ]]; then
  WORKERS="${PLANAGENT_LOCAL_WORKERS}"
elif [[ "${DB_URL}" == sqlite* ]]; then
  WORKERS="watch-ingest-worker strategic-watch-worker prediction-revision-worker"
else
  WORKERS="watch-ingest-worker strategic-watch-worker prediction-revision-worker knowledge-worker graph-worker review-worker calibration-worker"
fi
ALL_WORKERS="watch-ingest-worker strategic-watch-worker prediction-revision-worker knowledge-worker graph-worker review-worker calibration-worker ingest-worker simulation-worker report-worker"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*"
}

start_screen() {
  local name="$1"
  local command="$2"

  screen -S "${name}" -X quit >/dev/null 2>&1 || true
  screen -dmS "${name}" zsh -lc "${command}"
  log "started ${name}"
}

stop_project_port() {
  local port="$1"
  local pid command

  while IFS= read -r pid; do
    [[ -z "${pid}" ]] && continue
    command="$(ps -p "${pid}" -o command= 2>/dev/null || true)"
    if [[ "${command}" == *"${ROOT_DIR}"* || "${command}" == *"planagent.main:app"* || "${command}" == *"frontend-v2"* ]]; then
      log "stopping existing listener on :${port} (pid ${pid})"
      kill "${pid}" 2>/dev/null || true
    else
      log "port :${port} is occupied by pid ${pid}; leaving it untouched"
    fi
  done < <(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)
}

stop_worker_processes() {
  local pid command

  while IFS= read -r pid; do
    [[ -z "${pid}" ]] && continue
    command="$(ps -p "${pid}" -o command= 2>/dev/null || true)"
    if [[ "${command}" == *"${ROOT_DIR}"* || "${command}" == *"planagent.worker_cli"* ]]; then
      log "stopping existing worker process (pid ${pid})"
      kill "${pid}" 2>/dev/null || true
    fi
  done < <(pgrep -f "planagent.worker_cli" 2>/dev/null || true)
}

if ! command -v screen >/dev/null 2>&1; then
  log "screen is required for detached local runs"
  exit 1
fi

if [[ ! -x "${PYTHON_BIN}" ]]; then
  log "python executable not found: ${PYTHON_BIN}"
  exit 1
fi

COMMON_ENV="cd '${ROOT_DIR}' && PLANAGENT_DATABASE_URL='${DB_URL}' PLANAGENT_EVENT_BUS_BACKEND='${EVENT_BUS}' PLANAGENT_INLINE_INGEST_DEFAULT=true PLANAGENT_INLINE_SIMULATION_DEFAULT=true"

for worker in ${ALL_WORKERS}; do
  screen -S "planagent-${worker}" -X quit >/dev/null 2>&1 || true
done

stop_worker_processes
stop_project_port 8000
stop_project_port 3000

start_screen "planagent-backend" "${COMMON_ENV} '${PYTHON_BIN}' -m uvicorn planagent.main:app --host 127.0.0.1 --port 8000"
start_screen "planagent-frontend-v2" "cd '${ROOT_DIR}/frontend-v2' && npm run dev -- --host 127.0.0.1 --port 3000"

for worker in ${WORKERS}; do
  start_screen "planagent-${worker}" "${COMMON_ENV} '${PYTHON_BIN}' -m planagent.worker_cli '${worker}' --loop"
done

log "local stack started"
log "frontend: http://127.0.0.1:3000"
log "api:      http://127.0.0.1:8000"
log "sessions: screen -ls | grep planagent"
