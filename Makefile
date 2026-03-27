.PHONY: up down logs build seed reset test migrate

# Start the full Docker Compose stack, building images as needed
up:
	docker compose -f deploy/docker-compose.yml up --build

# Stop and remove all Docker Compose containers
down:
	docker compose -f deploy/docker-compose.yml down

# Follow logs from all services
logs:
	docker compose -f deploy/docker-compose.yml logs -f

# Build all service images without starting them
build:
	docker compose -f deploy/docker-compose.yml build

# Seed the dev database with a fixed tenant, user, and API key (dev-api-key-local)
seed:
	cd xeter && python scripts/seed.py

# Tear down all DB schemas and re-run seed — use for a clean slate
reset:
	cd xeter && python scripts/reset.py

# Run the full test suite
test:
	cd xeter && python -m pytest tests/ -v

# Apply all pending Alembic migrations
migrate:
	cd xeter && alembic upgrade head
