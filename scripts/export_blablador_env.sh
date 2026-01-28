#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
READ_TOML_SCRIPT="${ROOT_DIR}/scripts/helpers/read_toml_value.py"
SECRETS_PATHS=(
    "${ROOT_DIR}/.secrets/secrets.toml"
    "${ROOT_DIR}/.streamlit/secrets.toml"
)

read_secret() {
    local key="$1"
    local value=""
    for secrets_path in "${SECRETS_PATHS[@]}"; do
        if [[ ! -f "${secrets_path}" ]]; then
            continue
        fi
        value="$(python "${READ_TOML_SCRIPT}" "${secrets_path}" "${key}")"
        if [[ -n "${value}" ]]; then
            echo "${value}"
            return 0
        fi
    done
    return 1
}

if [[ -z "${BLABLADOR_API_KEY:-}" ]]; then
    BLABLADOR_API_KEY="$(read_secret "BLABLADOR_API_KEY" || true)"
fi
if [[ -z "${BLABLADOR_BASE_URL:-}" ]]; then
    BLABLADOR_BASE_URL="$(read_secret "BLABLADOR_BASE_URL" || true)"
fi

if [[ -z "${OPENAI_API_KEY:-}" && -n "${BLABLADOR_API_KEY:-}" ]]; then
    OPENAI_API_KEY="${BLABLADOR_API_KEY}"
fi
if [[ -z "${OPENAI_BASE_URL:-}" && -n "${BLABLADOR_BASE_URL:-}" ]]; then
    OPENAI_BASE_URL="${BLABLADOR_BASE_URL}"
fi
if [[ -z "${OPENAI_BASE_URL:-}" ]]; then
    OPENAI_BASE_URL="https://api.helmholtz-blablador.fz-juelich.de/v1/"
fi

export BLABLADOR_API_KEY
export BLABLADOR_BASE_URL
export OPENAI_API_KEY
export OPENAI_BASE_URL
export OPENAI_API_BASE="${OPENAI_BASE_URL}"

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
    echo "Missing BLABLADOR_API_KEY (or OPENAI_API_KEY)." >&2
    exit 1
fi

echo "Loaded BLABLADOR_API_KEY and BLABLADOR_BASE_URL"
echo "OPENAI_BASE_URL=${OPENAI_BASE_URL}"
