🚨 Functional Requirements for the project are located in REQUIREMENTS.md

We're building production-quality code together. Your role is to create maintainable, efficient solutions while catching potential issues early.

When you seem stuck or overly complex, I'll redirect you - my guidance helps you stay on track.

🚨 AUTOMATED CHECKS ARE MANDATORY

ALL hook issues are BLOCKING - EVERYTHING must be ✅ GREEN!
No errors. No formatting issues. No linting problems. Zero tolerance.
These are not suggestions. Fix ALL issues before continuing.

CRITICAL WORKFLOW - ALWAYS FOLLOW THIS!

Research → Plan → Implement

NEVER JUMP STRAIGHT TO CODING! Always follow this sequence:

Research: Explore the codebase, understand existing patterns
Plan: Create a detailed implementation plan and verify it with me
Implement: Execute the plan with validation checkpoints
When asked to implement any feature, you'll first say: "Let me research the codebase and create a plan before implementing."

For complex architectural decisions or challenging problems, use "ultrathink" to engage maximum reasoning capacity. Say: "Let me ultrathink about this architecture before proposing a solution."

USE MULTIPLE AGENTS!

Leverage subagents aggressively for better results:

Spawn agents to explore different parts of the codebase in parallel
Use one agent to write tests while another implements features
Delegate research tasks: "I'll have an agent investigate the database schema while I analyze the API structure"
For complex refactors: One agent identifies changes, another implements them
Say: "I'll spawn agents to tackle different aspects of this problem" whenever a task has multiple independent parts.

Reality Checkpoints

Stop and validate at these moments:

After implementing a complete feature
Before starting a new major component
When something feels wrong
Before declaring "done"
WHEN HOOKS FAIL WITH ERRORS ❌
Run: make fmt && make test && make lint

Why: You can lose track of what's actually working. These checkpoints prevent cascading failures.
🚨 CRITICAL: Hook Failures Are BLOCKING

When hooks report ANY issues (exit code 2), you MUST:

STOP IMMEDIATELY - Do not continue with other tasks
FIX ALL ISSUES - Address every ❌ issue until everything is ✅ GREEN
VERIFY THE FIX - Re-run the failed command to confirm it's fixed
CONTINUE ORIGINAL TASK - Return to what you were doing before the interrupt
NEVER IGNORE - There are NO warnings, only requirements
This includes:

Formatting issues (gofmt, black, prettier, etc.)
Linting violations (golangci-lint, eslint, etc.)
Forbidden patterns (time.Sleep, panic(), interface{})
ALL other checks
Your code must be 100% clean. No exceptions.

Recovery Protocol:

When interrupted by a hook failure, maintain awareness of your original task
After fixing all issues and verifying the fix, continue where you left off
Use the todo list to track both the fix and your original task
Working Memory Management

When context gets long:

Re-read this CLAUDE.md file
Summarize progress in a PROGRESS.md file
Document current state before major changes
Maintain TODO.md:

## Current Task
- [ ] What we're doing RIGHT NOW

## Completed
- [x] What's actually done and tested

## Next Steps
- [ ] What comes next

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
