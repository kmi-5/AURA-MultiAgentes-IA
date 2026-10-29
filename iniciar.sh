#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
uv run uvicorn backend.app.main:app --reload --port 8000 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT INT TERM
AURA_ENTORNO=dev uv run streamlit run frontend/app.py
