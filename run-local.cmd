@echo off
setlocal

set "ROOT=%~dp0"
set "PYTHONPATH=%ROOT%src"

"C:\Users\Sujanth\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m investment_research_poc.cli ^
  --input "%ROOT%data\samples" ^
  --query "Assess AlphaTech AG as a potential acquisition target in industrial AI" ^
  --output "%ROOT%output\local_run"

endlocal
