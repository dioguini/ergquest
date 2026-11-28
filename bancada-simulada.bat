@echo off
rem Banco de testes do ErgQuest com aparelhos simulados (sem Bluetooth).
cd /d "%~dp0"
py -m ergquest.bench --sim
pause
