@echo off
setlocal
pushd "%~dp0"
if not exist ".venv\Scripts\python.exe" goto missing
echo Hardware mode: front camera only. Default robot address: 192.168.126.176:8765.
echo To override: run_hardware.cmd --robot-host YOUR_IP --robot-port 8765
".venv\Scripts\python.exe" run_demo.py --mode hardware --config cameras.front-only.json %*
set "robot_result=%errorlevel%"
popd
if not "%robot_result%"=="0" pause
exit /b %robot_result%
:missing
echo Run setup_windows.cmd first.
popd
pause
exit /b 1
