#!/usr/bin/env bash
set -euo pipefail

load_secret_from_file() {
  local var_name="$1"
  local file_var_name="${var_name}_FILE"
  local file_path="${!file_var_name:-}"

  if [[ -n "${file_path}" && -f "${file_path}" && -z "${!var_name:-}" ]]; then
    export "${var_name}=$(<"${file_path}")"
  fi
}

ensure_django_secret_key() {
  local file_path="${DJANGO_SECRET_KEY_FILE:-/run/runtime-secrets/django_secret_key}"
  local dir_path
  dir_path="$(dirname "${file_path}")"

  mkdir -p "${dir_path}"
  chmod 700 "${dir_path}" || true

  if [[ ! -s "${file_path}" ]]; then
    (
      umask 077
      python - <<'PY' > "${file_path}"
from django.core.management.utils import get_random_secret_key
print(get_random_secret_key(), end="")
PY
    )
  fi

  chmod 600 "${file_path}" || true
  export DJANGO_SECRET_KEY_FILE="${file_path}"
}

ensure_django_secret_key
load_secret_from_file "DJANGO_SECRET_KEY"
load_secret_from_file "MYSQL_PASSWORD"

if [ "${SKIP_MIGRATE:-0}" != "1" ]; then
  python manage.py wait_for_db
  python manage.py migrate --noinput
fi

exec "$@"
