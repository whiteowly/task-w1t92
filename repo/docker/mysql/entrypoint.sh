#!/bin/sh
set -eu

SECRETS_DIR="${RUNTIME_SECRETS_DIR:-/run/runtime-secrets}"
ROOT_PASSWORD_FILE="${SECRETS_DIR}/mysql_root_password"
USER_PASSWORD_FILE="${SECRETS_DIR}/mysql_user_password"

mkdir -p "${SECRETS_DIR}"
chmod 700 "${SECRETS_DIR}"

generate_secret() {
  file_path="$1"
  length="$2"

  if [ ! -s "${file_path}" ]; then
    umask 077
    tr -dc 'A-Za-z0-9!@#$%^&*()_+-=' </dev/urandom | head -c "${length}" > "${file_path}"
  fi
  chmod 600 "${file_path}"
}

generate_secret "${ROOT_PASSWORD_FILE}" 48
generate_secret "${USER_PASSWORD_FILE}" 48

export MYSQL_ROOT_PASSWORD_FILE="${ROOT_PASSWORD_FILE}"
export MYSQL_PASSWORD_FILE="${USER_PASSWORD_FILE}"

exec docker-entrypoint.sh "$@"
