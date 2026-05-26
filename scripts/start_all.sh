#!/usr/bin/env bash
# ============================================================
# Start all MCP services + FastAPI
# Works on:
#   - Windows (Git Bash)
#   - WSL
#   - Linux/macOS
# ============================================================

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
LOGS="$ROOT/logs"

mkdir -p "$LOGS"

echo "Project root: $ROOT"

# --------------------------------------------------
# Resolve python interpreter
# --------------------------------------------------

if [[ -x "$ROOT/.venv/Scripts/python.exe" ]]; then
    PY="$ROOT/.venv/Scripts/python.exe"

elif [[ -x "$ROOT/.venv/bin/python" ]]; then
    PY="$ROOT/.venv/bin/python"

elif [[ -x "$BACKEND/.venv/Scripts/python.exe" ]]; then
    PY="$BACKEND/.venv/Scripts/python.exe"

elif [[ -x "$BACKEND/.venv/bin/python" ]]; then
    PY="$BACKEND/.venv/bin/python"

elif command -v python >/dev/null 2>&1; then
    PY="$(command -v python)"

elif command -v python3 >/dev/null 2>&1; then
    PY="$(command -v python3)"

else
    echo "ERROR: Python not found."
    exit 1
fi

echo "Using Python:"
echo "$PY"

cd "$BACKEND"

declare -a PIDS=()

cleanup() {

    echo
    echo "Stopping services..."

    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done

    wait 2>/dev/null || true
}

trap cleanup INT TERM EXIT


start_service() {

    local script="$1"
    local name="$2"
    local log="$LOGS/$name.log"

    echo "Starting $name"

    "$PY" "$script" > "$log" 2>&1 &

    PIDS+=("$!")
}


echo
echo "Launching MCP microservices..."
echo

start_service mcp_data.py mcp-data
start_service mcp_eda.py mcp-eda
start_service mcp_modeling.py mcp-modeling
start_service mcp_explain.py mcp-explain
start_service mcp_export.py mcp-export


echo
echo "Waiting 3 seconds..."
sleep 3


echo
echo "Launching FastAPI..."

"$PY" -m uvicorn main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    > "$LOGS/fastapi.log" 2>&1 &

PIDS+=("$!")


echo
echo "=================================================="
echo "Unisole platform running"
echo
echo "FastAPI:"
echo "http://localhost:8000"
echo
echo "Frontend:"
echo "cd frontend && npm run dev"
echo
echo "Logs:"
echo "$LOGS"
echo
echo "Press Ctrl+C to stop"
echo "=================================================="

wait