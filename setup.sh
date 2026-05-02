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

if [ ! -f ".env" ]; then
  info "Creating .env from .env.example..."
  cp .env.example .env
  success ".env created."
else
  warn ".env already exists. I will keep your existing settings and update the OpenAI API key."
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
printf '%s\n' "🌐 Frontend: http://localhost:3000"
printf '%s\n' "🧠 API:      http://localhost:8000"
printf '%s\n' "📦 MinIO:    http://localhost:9001"
printf '\n'
printf '%s\n' "MinIO login: planagent / planagent123"
printf '%s\n' "To stop MingJian later, run: docker compose down"
