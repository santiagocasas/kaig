#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${ROOT_DIR}/logs"
SERVER_LOG="${LOG_DIR}/server.log"
UI_LOG="${LOG_DIR}/ui.log"
PORT_CHECK_SCRIPT="${ROOT_DIR}/scripts/helpers/is_port_open.py"
LOG_LINES="${LOG_LINES:-20}"

if [[ -t 1 ]]; then
    RED=$'\033[31m'
    GREEN=$'\033[32m'
    YELLOW=$'\033[33m'
    BLUE=$'\033[34m'
    RESET=$'\033[0m'
else
    RED=""
    GREEN=""
    YELLOW=""
    BLUE=""
    RESET=""
fi

separator="------------------------------------------------------------"

is_port_open() {
    python "${PORT_CHECK_SCRIPT}" 127.0.0.1 "$1"
}

print_status() {
    if is_port_open 8000; then
        echo "${GREEN}SurrealDB: running (port 8000)${RESET}"
    else
        echo "${RED}SurrealDB: not running (port 8000)${RESET}"
    fi
    if is_port_open 8080; then
        echo "${GREEN}Server: running (port 8080)${RESET}"
    else
        echo "${RED}Server: not running (port 8080)${RESET}"
    fi
    if is_port_open 7932; then
        echo "${GREEN}UI: running (port 7932)${RESET}"
    else
        echo "${RED}UI: not running (port 7932)${RESET}"
    fi
}

check_http() {
    local url="$1"
    if curl -sS -m 2 "${url}" >/dev/null; then
        echo "${GREEN}HTTP: OK${RESET} (${url})"
    else
        echo "${YELLOW}HTTP: FAIL${RESET} (${url})"
    fi
}

print_status
check_http "http://127.0.0.1:8080/"
check_http "http://127.0.0.1:7932/"

echo "${BLUE}${separator}${RESET}"
if [[ -f "${SERVER_LOG}" ]]; then
    echo "--- server log (last ${LOG_LINES}) ---"
    tail -n "${LOG_LINES}" "${SERVER_LOG}" || true
else
    echo "--- server log not found: ${SERVER_LOG} ---"
fi

echo "${BLUE}${separator}${RESET}"
if [[ -f "${UI_LOG}" ]]; then
    echo "--- ui log (last ${LOG_LINES}) ---"
    tail -n "${LOG_LINES}" "${UI_LOG}" || true
else
    echo "--- ui log not found: ${UI_LOG} ---"
fi

echo "${BLUE}${separator}${RESET}"
echo "--- end of logs ---"
echo "${BLUE}${separator}${RESET}"
print_status
check_http "http://127.0.0.1:8080/"
check_http "http://127.0.0.1:7932/"
