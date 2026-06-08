@echo off
REM Abre o Gerenciador de Pastas SEM janela de terminal.
REM Use isto enquanto ainda nao gerou o executavel (.exe).
cd /d "%~dp0"
start "" pythonw app.py
