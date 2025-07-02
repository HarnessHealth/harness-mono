# Harness Makefile

.PHONY: help
help: ## Show this help message
	@echo "Harness - Veterinary Clinical AI Platform"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install: ## Install all dependencies
	poetry install
	pre-commit install

.PHONY: update
update: ## Update dependencies
	poetry update

.PHONY: format
format: ## Format code with black and ruff
	poetry run black backend/
	poetry run ruff backend/ --fix

.PHONY: lint
lint: ## Run linting checks
	poetry run black backend/ --check
	poetry run ruff backend/
	poetry run mypy backend/

.PHONY: test
test: ## Run tests
	poetry run pytest

.PHONY: test-coverage
test-coverage: ## Run tests with coverage
	poetry run pytest --cov=backend --cov-report=html --cov-report=term

.PHONY: docker-build
docker-build: ## Build Docker images
	docker-compose build

.PHONY: docker-up
docker-up: ## Start all services with Docker Compose
	docker-compose up -d

.PHONY: docker-down
docker-down: ## Stop all services
	docker-compose down

.PHONY: docker-logs
docker-logs: ## Show Docker logs
	docker-compose logs -f

.PHONY: db-migrate
db-migrate: ## Create a new database migration
	poetry run alembic revision --autogenerate -m "$(msg)"

.PHONY: db-upgrade
db-upgrade: ## Apply database migrations
	poetry run alembic upgrade head

.PHONY: db-downgrade
db-downgrade: ## Rollback database migration
	poetry run alembic downgrade -1

.PHONY: api-dev
api-dev: ## Run API in development mode
	poetry run uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000

.PHONY: worker-dev
worker-dev: ## Run Celery worker in development mode
	poetry run celery -A backend.workers.celery_app worker --loglevel=info

.PHONY: beat-dev
beat-dev: ## Run Celery beat in development mode
	poetry run celery -A backend.workers.celery_app beat --loglevel=info

.PHONY: clean
clean: ## Clean up generated files
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.coverage" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	find . -type d -name "htmlcov" -exec rm -rf {} +

.PHONY: setup-aws
setup-aws: ## Setup AWS infrastructure with Terraform
	cd infrastructure/terraform && terraform init && terraform plan

.PHONY: deploy-k8s
deploy-k8s: ## Deploy to Kubernetes
	kubectl apply -f infrastructure/kubernetes/

.PHONY: logs-api
logs-api: ## Show API logs
	docker-compose logs -f backend

.PHONY: logs-worker
logs-worker: ## Show Celery worker logs
	docker-compose logs -f celery-worker

.PHONY: shell-db
shell-db: ## Open PostgreSQL shell
	docker-compose exec postgres psql -U harness -d harness

.PHONY: shell-redis
shell-redis: ## Open Redis CLI
	docker-compose exec redis redis-cli