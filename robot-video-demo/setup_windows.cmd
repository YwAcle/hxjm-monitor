@echo off
setlocal
pushd "%~dp0"
if exist ".venv\Scripts\python.exe" goto dependencies
where py >nul 2>nul
if errorlevel 1 goto python_fallback
py -3 -m venv .venv
if errorlevel 1 goto failed
goto dependencies
:python_fallback
python -m venv .venv
if errorlevel 1 goto failed
:dependencies
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" tools\install_tools.py
if errorlevel 1 goto failed
echo Setup complete. Double-click run_simulated.cmd first.
popd
pause
exit /b 0
:failed
echo Setup failed. Read the error above and docs\FROM-ZERO.md.
popd
pause
exit /b 1
