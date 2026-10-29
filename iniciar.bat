@echo off
cd /d "%~dp0"
start "AURA API" cmd /k uv run uvicorn backend.app.main:app --reload --port 8000
start "AURA UI" cmd /k "set AURA_ENTORNO=dev&& uv run streamlit run frontend/app.py"
