@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\iniciar_windows.ps1"
if errorlevel 1 (
 echo.
 echo Ocorreu um erro. Confira a mensagem acima.
 pause
)
