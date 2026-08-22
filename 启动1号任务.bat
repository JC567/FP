@echo off
chcp 65001 >nul
cd /d "%~dp0"
start "" pythonw run_task.py
