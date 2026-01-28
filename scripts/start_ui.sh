#!/usr/bin/env bash

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_NAME="${DB_NAME:-test_db}"

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

if [[ -z "${KG_MAX_RETRIEVE_CALLS:-}" ]]; then
    export KG_MAX_RETRIEVE_CALLS="10"
fi

export KG_CHAT_MODEL="7 - Qwen3-Coder-30B-A3B-Instruct - A code model from August 2025"
export KG_LLM_MODEL="7 - Qwen3-Coder-30B-A3B-Instruct - A code model from August 2025"
export KG_LLM_FALLBACK_MODELS="alias-code,alias-fast"

if [[ -z "${KG_EMBEDDINGS_PROVIDER:-}" ]]; then
    export KG_EMBEDDINGS_PROVIDER="sentence-transformers"
fi
if [[ -z "${KG_LOCAL_EMBEDDINGS_MODEL:-}" ]]; then
    export KG_LOCAL_EMBEDDINGS_MODEL="sentence-transformers/all-MiniLM-L6-v2"
fi

DB_NAME="${DB_NAME}" uv run uvicorn knowledge_graph.agent:app --host 127.0.0.1 --port 7932
