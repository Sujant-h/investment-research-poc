@echo off
setlocal

set "ROOT=%~dp0"
set "PYTHONPATH=%ROOT%src"

"C:\Users\Sujanth\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m investment_research_poc.cli ^
  --input "%ROOT%data\samples" ^
  --live-news ^
  --provider marketaux ^
  --symbols "SAP,MSFT" ^
  --query "Assess whether SAP is an attractive strategic acquisition candidate in enterprise AI software" ^
  --output "%ROOT%output\live_run"

endlocal
