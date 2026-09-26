# Local development shortcuts. They run the same commands CLAUDE.md lists, so either
# works. Production never runs these: see docs/DEPLOYMENT.md.

# The Supabase CLI through npx, so nobody has to install it globally.
SUPABASE := npx --yes supabase@2

.PHONY: help db db-stop db-reset db-status api api-test web web-check

help: ## list the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

db: ## start local Supabase in Docker and apply every migration
	$(SUPABASE) start

db-stop: ## stop local Supabase
	$(SUPABASE) stop

db-reset: ## rebuild the local database from the migrations and seed
	$(SUPABASE) db reset

db-status: ## print local Supabase URLs and keys for your .env files
	$(SUPABASE) status

api: ## FastAPI on :8000, reloading on change
	cd apps/api && uvicorn app.main:app --reload --port 8000

api-test: ## API tests
	cd apps/api && pytest

web: ## Next.js on :3000
	cd apps/web && npm run dev

web-check: ## lint and build the web app
	cd apps/web && npm run lint && npm run build
