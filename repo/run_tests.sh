#!/usr/bin/env bash
set -euo pipefail

cleanup() {
  docker compose down -v
}
trap cleanup EXIT

docker compose down -v >/dev/null 2>&1 || true
docker compose build api db
docker compose up -d --wait db
docker compose exec -T db sh -lc 'until MYSQL_PWD="$(cat /run/runtime-secrets/mysql_root_password)" mysql -uroot -e "CREATE DATABASE IF NOT EXISTS test_heritage_ops CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" >/dev/null 2>&1; do sleep 1; done'
docker compose run --rm -e SKIP_MIGRATE=1 api python manage.py wait_for_db
docker compose run --rm -e SKIP_MIGRATE=1 api python manage.py migrate --noinput
docker compose run --rm -e SKIP_MIGRATE=1 api python manage.py test --keepdb
