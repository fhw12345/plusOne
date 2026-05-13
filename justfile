# Plus One — cross-cutting commands
# Install just: https://github.com/casey/just

default:
    @just --list

# === Backend ===

# Install backend deps with uv
backend-install:
    cd backend && uv sync

# Run backend dev server with hot reload
backend-dev:
    cd backend && uv run uvicorn plus_one.main:app --reload --host 0.0.0.0 --port 8000

# Lint backend
backend-lint:
    cd backend && uv run ruff check .

# Format backend
backend-format:
    cd backend && uv run ruff format .

# Typecheck backend
backend-typecheck:
    cd backend && uv run mypy src

# Run backend tests
backend-test:
    cd backend && uv run pytest

backend-test-unit:
    cd backend && uv run pytest tests/unit -m unit

backend-test-integration:
    cd backend && uv run pytest tests/integration -m integration

# Run all backend checks (matches CI)
backend-check: backend-lint backend-typecheck backend-test-unit

# === Frontend ===

frontend-install:
    cd frontend && pnpm install

frontend-dev:
    cd frontend && pnpm dev

frontend-lint:
    cd frontend && pnpm lint

frontend-typecheck:
    cd frontend && pnpm typecheck

frontend-build:
    cd frontend && pnpm build

frontend-check: frontend-lint frontend-typecheck

# === Infra ===

# Start local services (postgres + redis + langfuse)
infra-up:
    docker compose -f infra/docker-compose.yml up -d

infra-down:
    docker compose -f infra/docker-compose.yml down

infra-logs:
    docker compose -f infra/docker-compose.yml logs -f

# Reset local DB (DESTRUCTIVE)
infra-reset:
    docker compose -f infra/docker-compose.yml down -v
    docker compose -f infra/docker-compose.yml up -d

# === DB ===

# Run migrations
db-migrate:
    cd backend && uv run alembic upgrade head

# Create new migration (autogenerate)
db-revision message:
    cd backend && uv run alembic revision --autogenerate -m "{{message}}"

# Downgrade one migration
db-downgrade:
    cd backend && uv run alembic downgrade -1

# === Eval ===

# Run LLM eval suite (slow, costs tokens — runs against real LLM)
eval:
    cd backend && uv run python -m plus_one.eval.run_evals

# === All-in-one ===

# Set up everything for first-time local dev
setup: backend-install frontend-install
    cp -n backend/.env.example backend/.env || true
    cp -n frontend/.env.example frontend/.env.local || true
    @echo ""
    @echo "✅ Setup complete. Next steps:"
    @echo "   1. just infra-up    # start postgres/redis/langfuse"
    @echo "   2. just db-migrate  # run migrations"
    @echo "   3. just backend-dev # start backend"
    @echo "   4. just frontend-dev # start frontend (separate terminal)"

# Run all checks (matches CI)
check: backend-check frontend-check
