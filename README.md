# Harness - Veterinary Clinical AI Platform

Harness is a veterinary clinical AI platform that provides instant, evidence-based answers to clinical questions and interactive diagnostic support for veterinary professionals.

## Features

- **Ask Service**: RAG-based Q&A system with veterinary literature citations
- **Diagnose Service**: Interactive clinical decision support with differential diagnosis
- **Evidence-Based**: Powered by MedGemma models fine-tuned on veterinary corpora
- **Multi-Platform**: Web PWA and native iOS applications

## Prerequisites

- Python 3.12+
- Docker and Docker Compose
- PostgreSQL 16
- Redis 7
- Node.js 20+ (for frontend)
- AWS CLI (for cloud deployment)

## Quick Start

1. Clone the repository:
```bash
git clone https://github.com/your-org/harness.git
cd harness
```

2. Copy environment variables:
```bash
cp .env.example .env
```

3. Start the development environment:
```bash
docker-compose up -d
```

4. Install Python dependencies:
```bash
poetry install
```

5. Run database migrations:
```bash
poetry run alembic upgrade head
```

6. Start the API server:
```bash
poetry run uvicorn backend.api.main:app --reload
```

The API will be available at http://localhost:8000

## Development

### Running Tests
```bash
poetry run pytest
```

### Code Quality
```bash
poetry run black backend/
poetry run ruff backend/
poetry run mypy backend/
```

### Database Migrations
```bash
# Create a new migration
poetry run alembic revision --autogenerate -m "Description"

# Apply migrations
poetry run alembic upgrade head
```

## Architecture

See [REQUIREMENTS.md](REQUIREMENTS.md) for detailed architecture and implementation plans.

## Documentation

- API Documentation: http://localhost:8000/api/docs
- GraphQL Playground: http://localhost:8000/graphql

## License

Copyright (c) 2024 Harness Team. All rights reserved.


To get started:
  # Deploy infrastructure
  ./scripts/deployment/deploy.sh

  # Start training when ready
  ./scripts/deployment/start_training.sh start

  # Evaluate models
  ./scripts/deployment/run_evaluation.sh run <model>
