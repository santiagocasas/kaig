#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_NAME="${DB_NAME:-test_db}"
PORT_CHECK_SCRIPT="${ROOT_DIR}/scripts/helpers/is_port_open.py"

source "${ROOT_DIR}/scripts/export_blablador_env.sh"

if [[ -z "${KG_DB_URL:-}" ]]; then
    export KG_DB_URL="ws://localhost:8000/rpc"
fi

if [[ -z "${KG_SEARCH_THRESHOLD:-}" ]]; then
    export KG_SEARCH_THRESHOLD="0.15"
fi
if [[ -z "${KG_SEARCH_FALLBACK:-}" ]]; then
    export KG_SEARCH_FALLBACK="true"
fi

if ! python "${PORT_CHECK_SCRIPT}" 127.0.0.1 8000; then
    echo "SurrealDB is not running on port 8000." >&2
    echo "Start it with: ./scripts/run_surrealdb.sh" >&2
    exit 1
fi

DB_NAME="${DB_NAME}" uv run -- fastapi run \
    examples/knowledge-graph/src/knowledge_graph/server.py --port 8080
