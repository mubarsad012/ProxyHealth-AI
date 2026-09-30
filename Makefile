# ProxyHealth AI — repo-root commands (ARCHITECTURE §5.1, BUILD_PLAN §1.4 / §5.9). Owner: WP8.
# Everything runs with zero API keys (AI_PROVIDER=mock is the default without apps/api/.env).

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

export PATH := $(HOME)/.local/node/bin:$(PATH)

API    := apps/api
MOBILE := apps/mobile
PY     := $(API)/.venv/bin/python
PYTEST := $(API)/.venv/bin/pytest
RUFF   := $(API)/.venv/bin/ruff
MYPY   := $(API)/.venv/bin/mypy

# Baked into the web bundle at export time (ARCHITECTURE §6.2).
EXPO_PUBLIC_API_URL ?= http://127.0.0.1:8000

.PHONY: help dev api web types types-check sync sync-check test test-api lint-api test-mobile \
        smoke export-web ci clean-web

help: ## list the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-12s %s\n", $$1, $$2}'

dev: ## API (mock unless apps/api/.env says otherwise) on :8000 + Expo web on :8081; Ctrl-C stops both
	@scripts/dev.sh

api: ## the API alone on :8000 (with --reload)
	cd $(API) && CORS_ORIGINS="$${CORS_ORIGINS:-http://localhost:8081,http://127.0.0.1:8081}" \
	  .venv/bin/uvicorn proxyhealth_api.main:app --reload --host 127.0.0.1 --port 8000

web: ## Expo web alone on :8081 against EXPO_PUBLIC_API_URL
	cd $(MOBILE) && EXPO_PUBLIC_API_URL=$(EXPO_PUBLIC_API_URL) npx expo start --web --port 8081

types: ## regenerate openapi.json and schema.d.ts (contract owner only — WP0)
	@scripts/gen-types.sh

types-check: ## verify openapi.json and schema.d.ts are current (writes nothing)
	@scripts/gen-types.sh --check

sync: ## copy packs, languages, fixtures, fonts and resources into apps/mobile (sync_to_mobile.py)
	$(PY) $(API)/scripts/sync_to_mobile.py

sync-check: ## verify the mobile copies equal the API data (writes nothing)
	$(PY) $(API)/scripts/sync_to_mobile.py --check

test-api: ## API tests (all but live)
	$(PYTEST) $(API) -q

lint-api: ## ruff + strict mypy in the BUILD_PLAN §1.4 form
	$(RUFF) check $(API)
	$(MYPY) --config-file $(API)/pyproject.toml $(API)/proxyhealth_api $(API)/scripts $(API)/tests

test-mobile: ## mobile type-check, unit tests and lint
	cd $(MOBILE) && npx tsc --noEmit && npx jest --maxWorkers=2 && npx expo lint

test: test-api lint-api test-mobile ## everything above: API tests, ruff, mypy, tsc, jest, expo lint

smoke: ## boot the mock API on a free port and exercise every endpoint (apps/api/scripts/smoke.py)
	@scripts/smoke.sh

export-web: ## static web build → apps/mobile/dist (includes dist/privacy/index.html)
	cd $(MOBILE) && EXPO_PUBLIC_API_URL=$(EXPO_PUBLIC_API_URL) npx expo export --platform web --clear

ci: ## the full CI sequence locally, stopping at the first failure (scripts/ci.sh)
	@scripts/ci.sh

clean-web: ## remove the web build output
	rm -rf $(MOBILE)/dist
