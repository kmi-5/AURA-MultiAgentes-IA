@echo off
cd /d "%~dp0"
uv run pytest -q
if not "%1"=="--nopause" pause
