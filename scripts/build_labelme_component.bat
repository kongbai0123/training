@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0\.."
set "PYTHONUTF8=1"

set "PYTHON_EXE=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"

set "BUILD_VENV=%CD%\build\labelme-component-venv"
set "BUILD_PYTHON=%BUILD_VENV%\Scripts\python.exe"
if not exist "%BUILD_PYTHON%" "%PYTHON_EXE%" -m venv "%BUILD_VENV%"
if errorlevel 1 exit /b %errorlevel%

"%BUILD_PYTHON%" -m pip install --disable-pip-version-check --upgrade "pip<26" >nul
if errorlevel 1 exit /b %errorlevel%
"%BUILD_PYTHON%" -m pip install --disable-pip-version-check "pyinstaller==6.21.0" "numpy==1.26.4" "Pillow>=10,<13" "PyYAML>=6,<7" "qtpy>=2.4,<3" "termcolor>=2,<4" "colorama>=0.4,<1" "PyQt5==5.15.11" "imgviz==1.7.5"
if errorlevel 1 exit /b %errorlevel%
"%BUILD_PYTHON%" -m pip install --disable-pip-version-check --no-deps "labelme==4.6.0"
if errorlevel 1 exit /b %errorlevel%

set "LABELME_VERSION="
for /f "delims=" %%V in ('%BUILD_PYTHON% -c "import labelme; print(labelme.__version__)"') do set "LABELME_VERSION=%%V"
if not defined LABELME_VERSION (
  echo [ERROR] Unable to read LabelMe version from the isolated build environment.
  exit /b 1
)
set "DIST_DIR=%CD%\release_artifacts\components\LabelMe"
set "OUTPUT_ZIP=%CD%\release_artifacts\components\labelme-runtime-windows-x64.zip"

"%BUILD_PYTHON%" -m PyInstaller --noconfirm --clean --windowed --name LabelMe --distpath "%CD%\release_artifacts\components" --workpath "%CD%\build\labelme-component" --specpath "%CD%\build\labelme-component" --collect-all labelme --collect-all qtpy --collect-all PyQt5 packaging\labelme_component_entry.py
if errorlevel 1 exit /b %errorlevel%

"%BUILD_PYTHON%" scripts\package_labelme_component.py --dist "%DIST_DIR%" --output "%OUTPUT_ZIP%" --version "%LABELME_VERSION%"
if errorlevel 1 exit /b %errorlevel%

echo LabelMe offline component: %OUTPUT_ZIP%
exit /b 0
