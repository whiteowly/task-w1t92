#!/usr/bin/env bash
set -euo pipefail

cleanup() {
  docker compose down -v
}
trap cleanup EXIT

docker compose down -v >/dev/null 2>&1 || true
docker compose build api db
docker compose up -d db
docker compose run --rm -e SKIP_MIGRATE=1 api python manage.py wait_for_db
docker compose run --rm -e SKIP_MIGRATE=1 api python manage.py migrate --noinput
docker compose run --rm -e SKIP_MIGRATE=1 api python manage.py test
