# Local development shortcuts. They run the same commands CLAUDE.md lists, so either
# works. Production never runs these: see docs/DEPLOYMENT.md.

# The Supabase CLI through npx, so nobody has to install it globally.
SUPABASE := npx --yes supabase@2

.PHONY: help db db-stop db-reset db-status api-install api api-offline api-test api-test-db web web-check

help: ## list the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

db: ## start local Supabase in Docker and apply every migration
	$(SUPABASE) start

db-stop: ## stop local Supabase
	$(SUPABASE) stop

db-reset: ## rebuild the local database from the migrations and seed
	$(SUPABASE) db reset

db-status: ## print local Supabase URLs and keys for your .env files
	$(SUPABASE) status

api-install: ## create apps/api/.venv and install the API's requirements
	cd apps/api && python3 -m venv .venv && .venv/bin/pip install -q -r requirements-dev.txt

api: ## FastAPI on :8000, reloading on change (reads apps/api/.env)
	cd apps/api && .venv/bin/uvicorn app.main:app --reload --port 8000

api-offline: ## the API scraping saved fixtures instead of Bright Data (no keys needed)
	cd apps/api && FIXTURES_DIR=tests/fixtures .venv/bin/uvicorn app.main:app --reload --port 8000

api-test: ## API unit tests (no database)
	cd apps/api && .venv/bin/python -m pytest -m "not db"

api-test-db: ## API tests against local Supabase (run `make db` first)
	@eval "$$($(SUPABASE) status -o env | grep -E '^(API_URL|SERVICE_ROLE_KEY|DB_URL)=')" && \
	cd apps/api && TEST_SUPABASE_URL="$$API_URL" TEST_SUPABASE_SERVICE_ROLE_KEY="$$SERVICE_ROLE_KEY" \
	TEST_DATABASE_URL="$$DB_URL" .venv/bin/python -m pytest

web: ## Next.js on :3000
	cd apps/web && npm run dev

web-check: ## lint and build the web app
	cd apps/web && npm run lint && npm run build
