#!/usr/bin/env bash
# Post-deploy checks, run on the VPS from inside the containers, never through the tunnel
# (a tunnel or Cloudflare problem is not a failed release, and vice versa).
set -euo pipefail
cd "$(dirname "$0")/.."

files=(-f deploy/compose.yml -f deploy/compose.tunnel.yml)
web=false
if grep -q "^WEB_ENABLED='true'$" .env; then
  files+=(-f deploy/compose.web.yml)
  web=true
fi
compose=(docker compose --env-file .env "${files[@]}")

fail() {
  echo "SMOKE FAILED: $1" >&2
  "${compose[@]}" ps
  "${compose[@]}" logs --tail=80 "${2:-api}"
  exit 1
}

ready=false
for _ in $(seq 1 40); do
  if "${compose[@]}" exec -T api python -c \
    "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/v1/ready')" 2> /dev/null; then
    ready=true
    break
  fi
  sleep 3
done
[ "$ready" = true ] || fail "the API never became ready (database unreachable?)"

"${compose[@]}" exec -T caddy wget -qO- http://127.0.0.1/v1/health > /dev/null \
  || fail "Caddy does not route /v1 to the API" caddy
if [ "$web" = true ]; then
  "${compose[@]}" exec -T caddy wget -qO- http://127.0.0.1/ > /dev/null \
    || fail "Caddy does not reach the web app" web
fi

not_running=$("${compose[@]}" ps --format '{{.Service}} {{.State}}' | awk '$2 != "running"')
[ -z "$not_running" ] || fail "not running: $not_running" cloudflared

echo "smoke OK: api ready, caddy routing, all services running"
