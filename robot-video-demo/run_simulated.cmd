@echo off
setlocal
pushd "%~dp0"
if not exist ".venv\Scripts\python.exe" goto missing
".venv\Scripts\python.exe" run_demo.py --mode simulated %*
set "robot_result=%errorlevel%"
popd
if not "%robot_result%"=="0" pause
exit /b %robot_result%
:missing
echo Run setup_windows.cmd first.
popd
pause
exit /b 1
