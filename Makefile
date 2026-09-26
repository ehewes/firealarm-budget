# Local development entry points. Production never runs these: CI builds the
# images and the VPS only ever sees docker compose. See docs/local-development.md.

# The Supabase CLI through npx, so nobody has to install it globally.
SUPABASE := npx --yes supabase@2
COMPOSE_LOCAL := docker compose --env-file .env -f deploy/compose.yml -f deploy/compose.local.yml

.PHONY: help install db db-stop db-reset db-status api scraper widget web dev test test-db lint fmt up-local down-local

help: ## list the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

install: ## install the Python and Node dependencies
	uv sync
	npm install

db: ## start local Supabase in Docker and apply every migration
	$(SUPABASE) start

db-stop: ## stop local Supabase
	$(SUPABASE) stop

db-reset: ## rebuild the local database from the migrations and seed
	$(SUPABASE) db reset

db-status: ## print local Supabase URLs and keys for .env
	$(SUPABASE) status

api: ## FastAPI on :8000, reloading on change
	uv run uvicorn api.main:app --reload --port 8000

scraper: ## the scraper worker
	uv run python -m scraper

widget: ## build widget.js into the web app's public/
	npm run build -w apps/widget

web: widget ## Next.js on :3000
	npm run dev -w apps/web

dev: ## api, scraper and web together; Ctrl-C stops all three
	$(MAKE) -j3 api scraper web

test: ## unit tests (Python and web)
	uv run pytest -m "not db"
	npm run test -w apps/web

test-db: ## database tests against local Supabase (run `make db` first)
	TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres uv run pytest -m db

lint: ## ruff, eslint and tsc
	uv run ruff check .
	uv run ruff format --check .
	npm run lint -w apps/web
	npm run typecheck --workspaces --if-present

fmt: ## format and autofix Python
	uv run ruff format .
	uv run ruff check --fix .

up-local: ## the production topology on http://localhost:8080
	$(COMPOSE_LOCAL) up --build

down-local: ## stop the local production topology
	$(COMPOSE_LOCAL) down
