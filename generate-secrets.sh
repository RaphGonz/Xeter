#!/usr/bin/env bash
set -euo pipefail

# Guard against overwriting a git-tracked .env
if git ls-files --error-unmatch .env 2>/dev/null; then
  echo "ERROR: .env is tracked by git. Run: git rm --cached .env" >&2
  exit 1
fi

# Generate shared secrets ONCE — reused across multiple vars to keep passwords consistent
PG_PASS=$(openssl rand -hex 32)
REDIS_PASS=$(openssl rand -hex 32)
MINIO_PASS=$(openssl rand -hex 32)
CH_PASS=$(openssl rand -hex 32)
SECRET_KEY=$(openssl rand -hex 32)
MINIO_USER=xeter

cat > .env <<EOF
# PostgreSQL
DATABASE_URL=postgresql+asyncpg://xeter:${PG_PASS}@localhost:5432/xeter
POSTGRES_URL=postgresql://xeter:${PG_PASS}@localhost:5432/xeter
POSTGRES_PASSWORD=${PG_PASS}

# ClickHouse
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_DB=default
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=${CH_PASS}

# Redis
REDIS_URL=redis://:${REDIS_PASS}@localhost:6379
REDIS_PASSWORD=${REDIS_PASS}

# MinIO / S3
MINIO_ENDPOINT=http://localhost:9100
MINIO_ROOT_USER=${MINIO_USER}
MINIO_ROOT_PASSWORD=${MINIO_PASS}
MINIO_ACCESS_KEY=${MINIO_USER}
MINIO_SECRET_KEY=${MINIO_PASS}
S3_ACCESS_KEY=${MINIO_USER}
S3_SECRET_KEY=${MINIO_PASS}
MINIO_BUCKET=xeter-payloads
S3_BUCKET=xeter-payloads

# Dev bootstrap
DEV_API_KEY=dev-api-key-local
DEV_TENANT_NAME=dev-tenant
DEV_USER_EMAIL=dev@example.com
DEV_USER_PASSWORD=$(openssl rand -hex 16)

# App
SECRET_KEY=${SECRET_KEY}

# Diagnosticer LLM config
DIAGNOSTICER_PROVIDER=anthropic
DIAGNOSTICER_MODEL=claude-sonnet-4-6
ANTHROPIC_API_KEY=CHANGE_ME_BEFORE_DEPLOY
OPENAI_API_KEY=CHANGE_ME_BEFORE_DEPLOY
EOF

echo ".env written. Fill ANTHROPIC_API_KEY and OPENAI_API_KEY before starting services."
