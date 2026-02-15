.PHONY: help setup up down logs test test-quick test-integration clean keys status

SHELL := /bin/bash

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# === Local Development ===

setup: ## First-time setup (create .env, start services, smoke test)
	@bash scripts/setup.sh

up: ## Start all services
	docker compose up -d

down: ## Stop all services
	docker compose down

restart: ## Restart all services
	docker compose restart

logs: ## Tail logs (all services)
	docker compose logs -f --tail=50

logs-litellm: ## Tail LiteLLM proxy logs only
	docker compose logs -f --tail=100 litellm

status: ## Show service status and health
	@docker compose ps
	@echo ""
	@echo "Health check:"
	@curl -sf http://localhost:4000/health/liveliness && echo " -> OK" || echo " -> FAIL"

# === Keys & Admin ===

keys: ## Create team virtual keys
	@bash scripts/create-team-keys.sh

# === Testing ===

test: ## Run full test suite (requires running gateway)
	cd tests && pip install -q -r requirements.txt && pytest -v

test-quick: ## Run quick validation (no pytest needed)
	@bash scripts/test-gateway.sh

test-integration: ## Run only integration tests
	cd tests && pip install -q -r requirements.txt && pytest -v -m integration

test-guardrails: ## Run only guardrail/PII tests
	cd tests && pip install -q -r requirements.txt && pytest -v -m guardrails

# === Kubernetes ===

k8s-dry-run: ## Validate K8s manifests (dry-run)
	kubectl apply -k k8s/base --dry-run=client

k8s-deploy-base: ## Deploy to K8s (base)
	kubectl apply -k k8s/base

k8s-deploy-prod: ## Deploy to K8s (production overlay)
	kubectl apply -k k8s/overlays/production

k8s-status: ## Show K8s pod status
	kubectl get pods -n claudex -o wide

k8s-logs: ## Tail K8s LiteLLM logs
	kubectl logs -n claudex -l app=litellm-proxy -f --tail=50

# === Cleanup ===

clean: ## Remove all containers, volumes, and .env
	docker compose down -v
	@echo "Cleaned up. Note: .env was NOT removed (manual action)."

nuke: ## Remove everything including .env (DESTRUCTIVE)
	docker compose down -v
	rm -f .env
	@echo "All clean."
