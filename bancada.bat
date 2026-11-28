@echo off
rem Banco de testes do ErgQuest (Windows). Duplo clique para abrir.
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Nao encontrei o Python. Instala-o de https://www.python.org/downloads/ ^(marca "Add python.exe to PATH"^).
  pause
  exit /b 1
)
py -c "import bleak" 2>nul
if errorlevel 1 (
  echo A instalar a biblioteca Bluetooth ^(so da primeira vez^)...
  py -m pip install -r requirements-bench.txt
)
py -m ergquest.bench %*
pause
