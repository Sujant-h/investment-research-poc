@echo off
setlocal

set "ROOT=%~dp0"
set "PYTHONPATH=%ROOT%src"
set "BASE_DIR=%ROOT%"
if "%BASE_DIR:~-1%"=="\" set "BASE_DIR=%BASE_DIR:~0,-1%"

"C:\Users\ssuja\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m investment_research_poc.webapp ^
  --host 127.0.0.1 ^
  --port 8080 ^
  --base-dir "%BASE_DIR%"

if errorlevel 1 pause
endlocal
