#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_DIR="${ROOT_DIR}/dbs/knowledge-graph"
CONTAINER_NAME="kaig-surrealdb"
PORT_CHECK_SCRIPT="${ROOT_DIR}/scripts/helpers/is_port_open.py"
CLEANUP_SCRIPT="${ROOT_DIR}/scripts/helpers/cleanup_unwritable.py"

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is required but not installed." >&2
    exit 1
fi

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

mkdir -p "${DB_DIR}"
python "${CLEANUP_SCRIPT}" "${DB_DIR}"

if is_port_open 8000; then
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "SurrealDB is already running."
        exit 0
    fi
    echo "Port 8000 is already in use." >&2
    exit 1
fi

if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    docker start "${CONTAINER_NAME}" >/dev/null
else
    docker run -d --name "${CONTAINER_NAME}" -p 8000:8000 \
        -u "$(id -u):$(id -g)" \
        -v "${DB_DIR}:/dbs/knowledge-graph" \
        surrealdb/surrealdb:latest \
        start --user root --pass root rocksdb:/dbs/knowledge-graph >/dev/null
fi

if ! wait_for_port 8000 30; then
    echo "SurrealDB did not start on port 8000." >&2
    docker logs "${CONTAINER_NAME}" | tail -n 50 >&2
    exit 1
fi

echo "SurrealDB running at ws://localhost:8000/rpc"
echo "Logs: docker logs -f ${CONTAINER_NAME}"
