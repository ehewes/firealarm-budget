#!/usr/bin/env bash
# Runs on the VPS, from /opt/firealarm-budget, after CI has copied the compose files and a
# freshly rendered .env.new. Touches only this project: the box is shared with other stacks.
set -euo pipefail
cd "$(dirname "$0")/.."

tag=${1:?usage: remote-deploy.sh <image tag>}

# The new settings replace the old ones in one step, readable by deploy only.
install -m 600 .env.new .env
rm -f .env.new

files=(-f deploy/compose.yml -f deploy/compose.tunnel.yml)
if grep -q "^WEB_ENABLED='true'$" .env; then
  files+=(-f deploy/compose.web.yml)
fi
compose=(docker compose --env-file .env "${files[@]}")

# Remove this project's superseded image tags *before* pulling, because the pull is what
# runs out of disk (the disk hit 100% on 2026-09-15 from other stacks' old tags).
# Scoped to our own images on purpose: other stacks run images that exist in no registry.
# `latest` and the tag being deployed are kept; rmi refuses images a container still uses.
docker images --filter 'reference=ghcr.io/ehewes/firealarm-budget-*' \
  --format '{{.Repository}}:{{.Tag}}' \
  | grep -v ':latest$' | grep -v ":${tag}$" \
  | xargs -r -n1 docker rmi 2>/dev/null || true
df -h / | tail -1

"${compose[@]}" pull
"${compose[@]}" up -d --remove-orphans

# The Caddyfile is a bind mount, and changing it does not recreate the container.
"${compose[@]}" exec -T caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile \
  || echo "caddy reload skipped (container was just recreated)"

docker image prune -f > /dev/null
