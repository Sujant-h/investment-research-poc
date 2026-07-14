@echo off
set PYTHONPATH=%~dp0..\src
python -m investment_research_poc.webapp --port 8099
