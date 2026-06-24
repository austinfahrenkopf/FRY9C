@echo off
cd /d "%~dp0_app"
powershell -NoProfile -ExecutionPolicy Bypass -File "serve.ps1" -Port 8003
