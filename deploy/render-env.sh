#!/usr/bin/env bash
# Writes the production .env from this step's environment, where the deploy workflow maps
# GitHub secrets and variables. Runs on the GitHub runner, never on the VPS.
#
# - Never prints a value; errors name the variable only.
# - Values are single-quoted so compose takes them literally ($ and # included). A value
#   containing a single quote or a newline is refused rather than silently mangled.
# - Required names fail the deploy before anything on the box changes.
set -euo pipefail
umask 077

out=${1:?usage: render-env.sh <output file>}

required=(
  IMAGE_TAG
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY
  ALLOWED_DOMAINS
  WEB_ORIGIN
  IP_HASH_SALT
  CLOUDFLARE_TUNNEL_TOKEN
)
optional=(
  WEB_ENABLED
  SUPABASE_JWT_SECRET
  BRIGHTDATA_API_KEY
  BRIGHTDATA_UNLOCKER_ZONE
  OPENROUTER_API_KEY
  GROK_API_KEY
  GROK_BOT_URL
  SESSION_TTL_HOURS
  SCRAPE_CONCURRENCY
  MAX_PRODUCT_PAGES
  SCRAPE_MONTHLY_MAX
  JEV_MONTHLY_BUDGET_USD
)

missing=0
for name in "${required[@]}"; do
  if [ -z "${!name:-}" ]; then
    echo "::error::$name is not set (see docs/SECRETS.md)"
    missing=1
  fi
done
[ "$missing" -eq 0 ] || exit 1

: > "$out"
for name in "${required[@]}" "${optional[@]}"; do
  value="${!name:-}"
  [ -n "$value" ] || continue
  case "$value" in
    *"'"* | *$'\n'*)
      echo "::error::$name contains a single quote or a newline; regenerate it without one"
      exit 1
      ;;
  esac
  printf "%s='%s'\n" "$name" "$value" >> "$out"
done
echo "rendered $(wc -l < "$out" | tr -d ' ') settings into $out"
