@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0\.."

set "PYTHON_EXE=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"

echo [Vision Training Studio] Checking JavaScript syntax...
where node >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  for %%F in (
    static\*.js
    static\core\*.js
    static\pages\*.js
    static\state\*.js
    static\state\i18n\*.js
    static\ui\*.js
  ) do (
    if exist "%%F" (
      echo [JS] %%F
      node --check "%%F" || exit /b 1
    )
  )
) else (
  echo [WARN] node was not found. Skipping JavaScript syntax checks.
)

echo [Vision Training Studio] Compiling Python files...
"%PYTHON_EXE%" -m py_compile app.py launcher.py || exit /b 1
"%PYTHON_EXE%" -m compileall -q src || exit /b 1

echo [Vision Training Studio] Build checks passed.
exit /b 0
