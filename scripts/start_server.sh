#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_NAME="${DB_NAME:-test_db}"
PORT_CHECK_SCRIPT="${ROOT_DIR}/scripts/helpers/is_port_open.py"
LOG_DIR="${ROOT_DIR}/logs"
SERVER_LOG="${LOG_DIR}/server.log"
START_BACKGROUND="${START_BACKGROUND:-false}"
PORT_WAIT_SECONDS="${PORT_WAIT_SECONDS:-60}"
SERVER_LOG_LINES="${SERVER_LOG_LINES:-20}"

case "${1:-}" in
    --background|-b)
        START_BACKGROUND="true"
        ;;
    --foreground|-f)
        START_BACKGROUND="false"
        ;;
esac

source "${ROOT_DIR}/scripts/export_blablador_env.sh"

if [[ -z "${KG_DB_URL:-}" ]]; then
    export KG_DB_URL="ws://localhost:8000/rpc"
fi

if [[ -z "${KG_ENABLE_INGESTION:-}" ]]; then
    export KG_ENABLE_INGESTION="false"
fi

if [[ -z "${KG_SEARCH_THRESHOLD:-}" ]]; then
    export KG_SEARCH_THRESHOLD="0.15"
fi
if [[ -z "${KG_SEARCH_FALLBACK:-}" ]]; then
    export KG_SEARCH_FALLBACK="true"
fi

if [[ -z "${KG_DOCLING_TOKENIZER:-}" ]]; then
    export KG_DOCLING_TOKENIZER="cl100k_base"
fi

if ! python "${PORT_CHECK_SCRIPT}" 127.0.0.1 8000; then
    echo "SurrealDB is not running on port 8000." >&2
    echo "Start it with: ./scripts/run_surrealdb.sh" >&2
    exit 1
fi

is_port_open() {
    python "${PORT_CHECK_SCRIPT}" 127.0.0.1 8080
}

wait_for_port() {
    local deadline=$((SECONDS + PORT_WAIT_SECONDS))
    while (( SECONDS < deadline )); do
        if is_port_open; then
            return 0
        fi
        sleep 1
    done
    return 1
}

if [[ "${START_BACKGROUND}" == "true" ]]; then
    mkdir -p "${LOG_DIR}"
    nohup env DB_NAME="${DB_NAME}" uv run -- fastapi run \
        examples/knowledge-graph/src/knowledge_graph/server.py --port 8080 \
        >"${SERVER_LOG}" 2>&1 &
    SERVER_PID=$!
    echo "Server starting in background (PID ${SERVER_PID})"
    if wait_for_port; then
        echo "Server ready: http://127.0.0.1:8080"
    else
        echo "Server did not open port 8080 within ${PORT_WAIT_SECONDS}s." >&2
    fi
    echo "Logs: ${SERVER_LOG}"
    echo "Tail logs: tail -f ${SERVER_LOG}"
    echo "Recent logs:"
    tail -n "${SERVER_LOG_LINES}" "${SERVER_LOG}" || true
    exit 0
fi

DB_NAME="${DB_NAME}" uv run -- fastapi run \
    examples/knowledge-graph/src/knowledge_graph/server.py --port 8080
