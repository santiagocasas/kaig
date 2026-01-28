#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_NAME="${DB_NAME:-test_db}"

source "${ROOT_DIR}/scripts/export_blablador_env.sh"

if [[ -z "${KG_DB_URL:-}" ]]; then
    export KG_DB_URL="ws://localhost:8000/rpc"
fi

if [[ -z "${KG_DOCLING_TOKENIZER:-}" ]]; then
    export KG_DOCLING_TOKENIZER="cl100k_base"
fi

DB_NAME="${DB_NAME}" uv run python -m knowledge_graph.ingestion_runner
