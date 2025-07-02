# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Requirements for the project are located in REQUIREMENTS.md

## Claude CLI Configuration

The project has a `.claude/settings.local.json` file that allows specific bash commands:
- `ls` command for directory listing
- `find` command for file searching

## Development Setup

### Quick Start Commands
```bash
# Install dependencies
make install

# Start all services (PostgreSQL, Redis, Weaviate, MinIO)
make docker-up

# Run database migrations
make db-upgrade

# Start API development server
make api-dev

# Run tests
make test

# Format and lint code
make format
make lint
```

### Key Development Commands
- Build: `make docker-build`
- Test: `make test` or `make test-coverage` for coverage report
- Lint: `make lint` (runs black, ruff, and mypy)
- Format: `make format` (auto-formats with black and ruff)
- Database Migration: `make db-migrate msg="your migration message"`

### Architecture Overview

Harness is built as a microservices architecture:

1. **API Layer** (FastAPI): RESTful and GraphQL endpoints at `backend/api/`
2. **Services Layer**: 
   - Ask Service: RAG-based Q&A at `backend/services/ask/`
   - Retrieval Service: Vector search at `backend/services/retrieval/`
   - Inference Service: LLM integration at `backend/services/inference/`
3. **Data Layer**:
   - PostgreSQL: User data, audit logs, metadata
   - Redis: Caching and task queue
   - Weaviate: Vector database for document search
   - S3/MinIO: Document storage
4. **Workers**: Celery for async tasks at `backend/workers/`

### Testing Strategy
- Unit tests: Test individual functions and classes
- Integration tests: Test service interactions
- E2E tests: Test complete API flows
- Run with: `poetry run pytest` or `make test`

### Common Workflows

#### Adding a New API Endpoint
1. Create router in `backend/api/routers/`
2. Add models in `backend/models/`
3. Implement service logic in `backend/services/`
4. Add tests in `backend/tests/`
5. Update API documentation

#### Running Database Migrations
```bash
# Create migration
make db-migrate msg="add user table"

# Apply migration
make db-upgrade

# Rollback if needed
make db-downgrade
```

#### Debugging Services
```bash
# View logs
make logs-api      # API logs
make logs-worker   # Celery worker logs

# Access databases
make shell-db      # PostgreSQL shell
make shell-redis   # Redis CLI
```

#### Deploying AWS Infrastructure
```bash
# Initialize Terraform
cd infrastructure/terraform
terraform init

# Plan changes
terraform plan

# Apply infrastructure
terraform apply

# Destroy infrastructure (careful!)
terraform destroy
```

### Data Pipeline

The veterinary paper acquisition pipeline is managed by Apache Airflow:
- DAGs located in `data-pipeline/dags/`
- Main DAG: `veterinary_corpus_acquisition.py` runs daily
- Crawls PubMed, Europe PMC, and conference sites
- Processes PDFs with GROBID
- Generates embeddings and updates vector DB

### ML Training

MedGemma fine-tuning is handled by:
- Training script: `data-pipeline/scripts/train_medgemma_vet.py`
- Uses LoRA for efficient fine-tuning
- Supports distributed training on multiple GPUs
- Integrates with Weights & Biases and MLflow for tracking
