@echo off
cd /d "%~dp0"
python src\depgraph.py %*
