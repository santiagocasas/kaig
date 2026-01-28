#!/usr/bin/env bash
set -euo pipefail

DB_NAME="${DB_NAME:-test_db}"
export DB_NAME
export KG_DB_URL="${KG_DB_URL:-ws://localhost:8000/rpc}"
export KG_ENABLE_INGESTION="${KG_ENABLE_INGESTION:-false}"
export KG_EMBEDDINGS_PROVIDER="${KG_EMBEDDINGS_PROVIDER:-sentence-transformers}"
export KG_LOCAL_EMBEDDINGS_MODEL="${KG_LOCAL_EMBEDDINGS_MODEL:-sentence-transformers/all-MiniLM-L6-v2}"
export KG_DOCLING_TOKENIZER="${KG_DOCLING_TOKENIZER:-cl100k_base}"
export STREAMLIT_SERVER_MAX_UPLOAD_SIZE="${STREAMLIT_SERVER_MAX_UPLOAD_SIZE:-50}"
export STREAMLIT_SERVER_HEADLESS="${STREAMLIT_SERVER_HEADLESS:-true}"
export STREAMLIT_SERVER_PORT="${STREAMLIT_SERVER_PORT:-8501}"
export STREAMLIT_SERVER_ADDRESS="${STREAMLIT_SERVER_ADDRESS:-0.0.0.0}"

mkdir -p /app/logs

surreal start -u root -p root rocksdb:/dbs/knowledge-graph \
    >/var/log/surrealdb.log 2>&1 &

for _ in $(seq 1 60); do
    python /app/scripts/helpers/is_port_open.py 127.0.0.1 8000 && break
    sleep 1
done

exec uv run streamlit run examples/knowledge-graph/streamlit_app.py \
    --server.address="${STREAMLIT_SERVER_ADDRESS}" \
    --server.port="${STREAMLIT_SERVER_PORT}"
