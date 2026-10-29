@echo off
setlocal
pushd "%~dp0"
if not exist ".venv\Scripts\python.exe" goto missing
".venv\Scripts\python.exe" check_camera.py %*
set "robot_result=%errorlevel%"
popd
pause
exit /b %robot_result%
:missing
echo Run setup_windows.cmd first.
popd
pause
exit /b 1
