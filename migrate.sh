#!/usr/bin/env bash
# migrate.sh — стартира инфраструктурата и прилага Alembic миграциите.
# Използване: bash migrate.sh [--reset]
# --reset: изтрива и пресъздава всички таблици (само dev)

set -euo pipefail

COMPOSE_FILE="docker-compose.dev.yml"
API_SERVICE="api"

# ── копиране на .env ако липсва ──────────────────────────────────────────────
if [ ! -f .env ]; then
  echo "⚠  .env не е намерен — копирам от .env.example"
  cp .env.example .env
  echo "   Попълнете OPENAI_API_KEY в .env преди да продължите."
fi

# ── стартиране на инфраструктурата ───────────────────────────────────────────
echo "▶  docker compose up -d (postgres, redis, minio)..."
docker compose -f "$COMPOSE_FILE" up -d postgres redis minio

echo "⏳ Чакам PostgreSQL да стане готов..."
until docker compose -f "$COMPOSE_FILE" exec -T postgres \
  pg_isready -U "${POSTGRES_USER:-tpai}" -d "${POSTGRES_DB:-tpai}" &>/dev/null; do
  sleep 1
done
echo "✓  PostgreSQL е готов."

# ── reset (по желание) ────────────────────────────────────────────────────────
if [[ "${1:-}" == "--reset" ]]; then
  echo "⚠  RESET: изтривам alembic_version таблицата (само dev)..."
  docker compose -f "$COMPOSE_FILE" exec -T postgres \
    psql -U "${POSTGRES_USER:-tpai}" -d "${POSTGRES_DB:-tpai}" \
    -c "DROP TABLE IF EXISTS alembic_version CASCADE;" || true
fi

# ── генериране или прилагане на миграция ─────────────────────────────────────
echo "▶  Стартирам api service за Alembic..."
docker compose -f "$COMPOSE_FILE" up -d "$API_SERVICE"

sleep 3

MIGRATIONS_DIR="services/api/alembic/versions"
if [ -z "$(ls -A "$MIGRATIONS_DIR" 2>/dev/null)" ]; then
  echo "▶  Генерирам начална миграция..."
  docker compose -f "$COMPOSE_FILE" exec -T "$API_SERVICE" \
    alembic revision --autogenerate -m "initial"
  echo "✓  Миграцията е генерирана в $MIGRATIONS_DIR"
fi

echo "▶  Прилагам миграции (alembic upgrade head)..."
docker compose -f "$COMPOSE_FILE" exec -T "$API_SERVICE" \
  alembic upgrade head

echo ""
echo "✅ Миграциите са приложени успешно!"
echo "   API:       http://localhost:8000/docs"
echo "   MinIO UI:  http://localhost:9001  (minioadmin / minioadmin)"
