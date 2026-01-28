#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PDF_PATH="${1:-${PDF_PATH:-}}"
DB_NAME="${DB_NAME:-test_db}"
READ_TOML_SCRIPT="${ROOT_DIR}/scripts/helpers/read_toml_value.py"
PORT_CHECK_SCRIPT="${ROOT_DIR}/scripts/helpers/is_port_open.py"
SECRETS_PATHS=(
    "${ROOT_DIR}/.secrets/secrets.toml"
    "${ROOT_DIR}/.streamlit/secrets.toml"
)
ENV_FILE_PATH="${ROOT_DIR}/.env"

read_toml_value() {
    local path="$1"
    local key="$2"
    python "${READ_TOML_SCRIPT}" "${path}" "${key}"
}

is_port_open() {
    local port="$1"
    python "${PORT_CHECK_SCRIPT}" "127.0.0.1" "${port}"
}

wait_for_port() {
    local port="$1"
    local tries="${2:-30}"
    for _ in $(seq 1 "${tries}"); do
        if is_port_open "${port}"; then
            return 0
        fi
        sleep 1
    done
    return 1
}

for secrets_path in "${SECRETS_PATHS[@]}"; do
    if [[ ! -f "${secrets_path}" ]]; then
        continue
    fi
    if [[ -z "${BLABLADOR_API_KEY:-}" ]]; then
        BLABLADOR_API_KEY="$(read_toml_value "${secrets_path}" "BLABLADOR_API_KEY")"
        export BLABLADOR_API_KEY
    fi
    if [[ -z "${OPENAI_API_KEY:-}" ]]; then
        OPENAI_API_KEY="$(read_toml_value "${secrets_path}" "OPENAI_API_KEY")"
        export OPENAI_API_KEY
    fi
    if [[ -z "${BLABLADOR_BASE_URL:-}" ]]; then
        BLABLADOR_BASE_URL="$(read_toml_value "${secrets_path}" "BLABLADOR_BASE_URL")"
        export BLABLADOR_BASE_URL
    fi
    if [[ -z "${OPENAI_BASE_URL:-}" ]]; then
        OPENAI_BASE_URL="$(read_toml_value "${secrets_path}" "OPENAI_BASE_URL")"
        export OPENAI_BASE_URL
    fi
done

if [[ -n "${BLABLADOR_API_KEY:-}" ]]; then
    export OPENAI_API_KEY="${BLABLADOR_API_KEY}"
fi

if [[ -n "${BLABLADOR_BASE_URL:-}" ]]; then
    export OPENAI_BASE_URL="${BLABLADOR_BASE_URL}"
elif [[ -z "${OPENAI_BASE_URL:-}" ]]; then
    export OPENAI_BASE_URL="https://api.helmholtz-blablador.fz-juelich.de/v1/"
fi
export OPENAI_API_BASE="${OPENAI_BASE_URL}"

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
    echo "Missing OPENAI_API_KEY (or BLABLADOR_API_KEY)." >&2
    exit 1
fi

echo "Using OPENAI_BASE_URL=${OPENAI_BASE_URL}"

if ! wait_for_port 8000 15; then
    echo "SurrealDB is not running on port 8000." >&2
    echo "Start it with: ./scripts/run_surrealdb.sh" >&2
    exit 1
fi

stop_children() {
    if [[ -n "${SERVER_PID:-}" ]]; then
        kill "${SERVER_PID}" >/dev/null 2>&1 || true
    fi
    if [[ -n "${AGENT_PID:-}" ]]; then
        kill "${AGENT_PID}" >/dev/null 2>&1 || true
    fi
}

cleanup() {
    stop_children
    exit 0
}

trap cleanup INT TERM
trap stop_children EXIT

cd "${ROOT_DIR}"

ENV_FILE_ARGS=()
if [[ -f "${ENV_FILE_PATH}" ]]; then
    ENV_FILE_ARGS=(--env-file "${ENV_FILE_PATH}")
fi

DB_NAME="${DB_NAME}" \
OPENAI_API_KEY="${OPENAI_API_KEY}" \
OPENAI_BASE_URL="${OPENAI_BASE_URL}" \
OPENAI_API_BASE="${OPENAI_API_BASE}" \
uv run "${ENV_FILE_ARGS[@]}" -- \
    fastapi run examples/knowledge-graph/src/knowledge_graph/server.py \
    --port 8080 &
SERVER_PID=$!

DB_NAME="${DB_NAME}" \
OPENAI_API_KEY="${OPENAI_API_KEY}" \
OPENAI_BASE_URL="${OPENAI_BASE_URL}" \
OPENAI_API_BASE="${OPENAI_API_BASE}" \
uv run "${ENV_FILE_ARGS[@]}" \
    uvicorn knowledge_graph.agent:app --host 127.0.0.1 --port 7932 &
AGENT_PID=$!

if ! wait_for_port 8080 30; then
    echo "Server did not start on port 8080." >&2
    cleanup
    exit 1
fi

if ! wait_for_port 7932 30; then
    echo "Agent UI did not start on port 7932." >&2
    cleanup
    exit 1
fi

if [[ -n "${PDF_PATH}" ]]; then
    if [[ ! -f "${PDF_PATH}" ]]; then
        echo "PDF not found: ${PDF_PATH}" >&2
        exit 1
    fi
    curl -sS -F "file=@${PDF_PATH}" http://127.0.0.1:8080/upload >/dev/null
    echo "Uploaded: ${PDF_PATH}"
fi

echo "Server: http://127.0.0.1:8080"
echo "Chat UI: http://127.0.0.1:7932"

wait
