#!/usr/bin/env bash

set -euo pipefail

if [ -t 1 ]; then
  RED="$(printf '\033[0;31m')"
  GREEN="$(printf '\033[0;32m')"
  YELLOW="$(printf '\033[1;33m')"
  BLUE="$(printf '\033[0;34m')"
  BOLD="$(printf '\033[1m')"
  RESET="$(printf '\033[0m')"
else
  RED=""
  GREEN=""
  YELLOW=""
  BLUE=""
  BOLD=""
  RESET=""
fi

info() {
  printf '%s\n' "${BLUE}ℹ️  $*${RESET}"
}

success() {
  printf '%s\n' "${GREEN}✅ $*${RESET}"
}

warn() {
  printf '%s\n' "${YELLOW}⚠️  $*${RESET}"
}

fail() {
  printf '%s\n' "${RED}❌ $*${RESET}"
  exit 1
}

update_env_value() {
  key="$1"
  value="$2"
  file="$3"
  tmp_file="$(mktemp)"

  if grep -q "^${key}=" "$file"; then
    awk -v env_key="$key" -v env_value="$value" '
      BEGIN { updated = 0 }
      $0 ~ "^" env_key "=" {
        print env_key "=" env_value
        updated = 1
        next
      }
      { print }
      END {
        if (!updated) {
          print env_key "=" env_value
        }
      }
    ' "$file" > "$tmp_file"
  else
    cp "$file" "$tmp_file"
    printf '\n%s=%s\n' "$key" "$value" >> "$tmp_file"
  fi

  mv "$tmp_file" "$file"
}

printf '%s\n' "${BOLD}${BLUE}"
printf '%s\n' "明鉴 MingJian Docker Setup"
printf '%s\n' "==========================="
printf '%s\n' "${RESET}"
printf '%s\n' "🚀 Let's get MingJian running with Docker."
printf '\n'

command -v docker >/dev/null 2>&1 || fail "Docker is not installed. Please install Docker Desktop first: https://www.docker.com/products/docker-desktop/"
success "Docker is installed."

docker compose version >/dev/null 2>&1 || fail "Docker Compose is not installed. Please install Docker Desktop or Docker Compose v2."
success "Docker Compose is installed."

docker info >/dev/null 2>&1 || fail "Docker is installed, but it does not seem to be running. Please start Docker Desktop and run this script again."
success "Docker is running."

if [ ! -f ".env.example" ]; then
  fail ".env.example was not found. Please run this script from the MingJian project root."
fi

if [ ! -f "docker-compose.yml" ]; then
  fail "docker-compose.yml was not found. This setup script only supports roots that ship a Docker Compose stack."
fi

if [ ! -f ".env" ]; then
  info "Creating .env from .env.example..."
  cp .env.example .env
  success ".env created."
else
  warn ".env already exists. I will keep your existing settings and update the OpenAI API key."
fi

auth_secret_key="$(awk '
  /^PLANAGENT_AUTH_SECRET_KEY=/ {
    sub(/^PLANAGENT_AUTH_SECRET_KEY=/, "")
    print
    exit
  }
' .env)"
if [ "${#auth_secret_key}" -lt 32 ]; then
  command -v od >/dev/null 2>&1 || fail "od is required to generate the local authentication secret."
  auth_secret_key="$(od -An -N32 -tx1 /dev/urandom | tr -d '[:space:]')"
  [ "${#auth_secret_key}" -ge 32 ] || fail "Could not generate a strong authentication secret."
  update_env_value "PLANAGENT_AUTH_SECRET_KEY" "$auth_secret_key" ".env"
  success "Generated PLANAGENT_AUTH_SECRET_KEY for optional authenticated remote access."
else
  success "Keeping the existing PLANAGENT_AUTH_SECRET_KEY."
fi

bootstrap_admin_password="$(awk '
  /^PLANAGENT_BOOTSTRAP_ADMIN_PASSWORD=/ {
    sub(/^PLANAGENT_BOOTSTRAP_ADMIN_PASSWORD=/, "")
    print
    exit
  }
' .env)"
if [ "${#bootstrap_admin_password}" -lt 16 ]; then
  command -v od >/dev/null 2>&1 || fail "od is required to generate the bootstrap admin password."
  bootstrap_admin_password="$(od -An -N24 -tx1 /dev/urandom | tr -d '[:space:]')"
  [ "${#bootstrap_admin_password}" -ge 16 ] || fail "Could not generate a bootstrap admin password."
  update_env_value "PLANAGENT_BOOTSTRAP_ADMIN_PASSWORD" "$bootstrap_admin_password" ".env"
  success "Generated the initial admin credential for optional authenticated remote access."
else
  success "Keeping the existing PLANAGENT_BOOTSTRAP_ADMIN_PASSWORD."
fi

local_proxy_secret="$(awk '
  /^PLANAGENT_LOCAL_PROXY_SECRET=/ {
    sub(/^PLANAGENT_LOCAL_PROXY_SECRET=/, "")
    print
    exit
  }
' .env)"
if [ "${#local_proxy_secret}" -lt 32 ]; then
  command -v od >/dev/null 2>&1 || fail "od is required to generate the local proxy secret."
  local_proxy_secret="$(od -An -N32 -tx1 /dev/urandom | tr -d '[:space:]')"
  [ "${#local_proxy_secret}" -ge 32 ] || fail "Could not generate a strong local proxy secret."
  update_env_value "PLANAGENT_LOCAL_PROXY_SECRET" "$local_proxy_secret" ".env"
  success "Generated the same-deployment local proxy credential."
else
  success "Keeping the existing PLANAGENT_LOCAL_PROXY_SECRET."
fi

printf '\n'
printf '%s\n' "${BOLD}🔑 Enter your OpenAI API key.${RESET}"
printf '%s\n' "It will be saved as PLANAGENT_OPENAI_API_KEY in .env."

openai_api_key=""
while [ -z "$openai_api_key" ]; do
  printf 'OpenAI API key: '
  stty -echo 2>/dev/null || true
  IFS= read -r openai_api_key
  stty echo 2>/dev/null || true
  printf '\n'

  if [ -z "$openai_api_key" ]; then
    warn "The API key cannot be empty. Please paste your key and press Enter."
  fi
done

update_env_value "PLANAGENT_OPENAI_API_KEY" "$openai_api_key" ".env"
success "Saved PLANAGENT_OPENAI_API_KEY to .env."

printf '\n'
info "Starting MingJian services. The first run may take a few minutes..."
docker compose up -d

printf '\n'
success "MingJian is starting up!"
printf '\n'
printf '%s\n' "${BOLD}Open these URLs in your browser:${RESET}"
printf '%s\n' "🌐 Frontend: http://localhost:3001"
printf '%s\n' "🧠 API:      http://localhost:8000"
printf '%s\n' "📦 MinIO:    http://localhost:9001"
printf '\n'
printf '%s\n' "MinIO login: use PLANAGENT_MINIO_ACCESS_KEY / PLANAGENT_MINIO_SECRET_KEY from .env"
printf '%s\n' "Remote admin: username admin; password is PLANAGENT_BOOTSTRAP_ADMIN_PASSWORD in .env"
printf '%s\n' "To stop MingJian later, run: docker compose down"
