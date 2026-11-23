@echo off
setlocal
pushd "%~dp0"
wsl.exe -- sh scripts/launch.sh
if errorlevel 1 (
  echo.
  echo AntiFlood could not start. See the message above and docs\RUNNING.md.
  pause
) else (
  start "" "http://127.0.0.1:8000"
)
popd
