#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT_CHECK_SCRIPT="${ROOT_DIR}/scripts/helpers/is_port_open.py"
SERVER_URL="${KG_SERVER_URL:-http://127.0.0.1:8080}"
UPLOAD_URL="${SERVER_URL%/}/upload"
WAIT_FOR_SERVER="${WAIT_FOR_SERVER:-true}"
SERVER_WAIT_SECONDS="${SERVER_WAIT_SECONDS:-60}"

DOC_PATHS=(
    # "/absolute/path/to/file.pdf"
    # "/absolute/path/to/file.md"
)

DOC_DIRS=(
    # "/absolute/path/to/folder"
)

is_port_open() {
    python "${PORT_CHECK_SCRIPT}" 127.0.0.1 8080
}

wait_for_server() {
    local deadline=$((SECONDS + SERVER_WAIT_SECONDS))
    while (( SECONDS < deadline )); do
        if is_port_open; then
            return 0
        fi
        sleep 1
    done
    return 1
}

if ! is_port_open; then
    if [[ "${WAIT_FOR_SERVER}" == "true" ]]; then
        echo "Waiting for server on port 8080..."
        if ! wait_for_server; then
            echo "Server did not start within ${SERVER_WAIT_SECONDS}s." >&2
            echo "Start it with: ./scripts/start_server.sh" >&2
            exit 1
        fi
    else
        echo "Server is not running on port 8080." >&2
        echo "Start it with: ./scripts/start_server.sh" >&2
        exit 1
    fi
fi

shopt -s nullglob globstar

files=()
extensions=(pdf md markdown txt)

if [[ "$#" -gt 0 ]]; then
    for target in "$@"; do
        if [[ -d "${target}" ]]; then
            for ext in "${extensions[@]}"; do
                for file in "${target}"/**/*.${ext}; do
                    files+=("${file}")
                done
            done
        elif [[ -f "${target}" ]]; then
            files+=("${target}")
        else
            echo "Skipping missing path: ${target}" >&2
        fi
    done
else
    for path in "${DOC_PATHS[@]}"; do
        if [[ -f "${path}" ]]; then
            files+=("${path}")
        else
            echo "Skipping missing file: ${path}" >&2
        fi
    done
    for dir in "${DOC_DIRS[@]}"; do
        if [[ -d "${dir}" ]]; then
            for ext in "${extensions[@]}"; do
                for file in "${dir}"/**/*.${ext}; do
                    files+=("${file}")
                done
            done
        else
            echo "Skipping missing folder: ${dir}" >&2
        fi
    done
fi

if [[ "${#files[@]}" -eq 0 ]]; then
    echo "No document files found to upload." >&2
    exit 1
fi

for file in "${files[@]}"; do
    curl -sS -F "file=@${file}" "${UPLOAD_URL}" >/dev/null
    echo "Uploaded: ${file}"
done
