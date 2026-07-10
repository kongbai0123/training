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
"%BUILD_PYTHON%" -m pip install --disable-pip-version-check "pyinstaller==6.21.0" "numpy==1.26.4" "Pillow>=10,<13" "PyYAML>=6,<7" "PyQt5==5.15.11" "imgviz>=2,<3" "loguru>=0.7,<1" "natsort>=8,<9" "scikit-image>=0.21,<1" "scipy>=1.11,<2" "tifffile>=2024.1.30" "osam==0.4.0" "onnxruntime>=1.23.2,<2"
if errorlevel 1 exit /b %errorlevel%
"%BUILD_PYTHON%" -m pip install --disable-pip-version-check --no-deps "labelme==6.3.1"
if errorlevel 1 exit /b %errorlevel%

set "LABELME_VERSION="
for /f "delims=" %%V in ('%BUILD_PYTHON% -c "import labelme; print(labelme.__version__)"') do set "LABELME_VERSION=%%V"
if not defined LABELME_VERSION (
  echo [ERROR] Unable to read LabelMe version from the isolated build environment.
  exit /b 1
)
set "DIST_DIR=%CD%\release_artifacts\components\LabelMe"
set "OUTPUT_ZIP=%CD%\release_artifacts\components\labelme-runtime-windows-x64.zip"

"%BUILD_PYTHON%" -m PyInstaller --noconfirm --clean --windowed --name LabelMe --distpath "%CD%\release_artifacts\components" --workpath "%CD%\build\labelme-component" --specpath "%CD%\build\labelme-component" --collect-all labelme --collect-all osam --collect-all PyQt5 packaging\labelme_component_entry.py
if errorlevel 1 exit /b %errorlevel%

rem PyQt5 ships older VC runtime copies that shadow the newer runtime required by
rem ONNX Runtime. The root PyInstaller runtime already includes compatible copies.
del /q "%DIST_DIR%\_internal\PyQt5\Qt5\bin\msvcp140.dll" 2>nul
del /q "%DIST_DIR%\_internal\PyQt5\Qt5\bin\vcruntime140.dll" 2>nul
del /q "%DIST_DIR%\_internal\PyQt5\Qt5\bin\vcruntime140_1.dll" 2>nul

"%BUILD_PYTHON%" scripts\package_labelme_component.py --dist "%DIST_DIR%" --output "%OUTPUT_ZIP%" --version "%LABELME_VERSION%"
if errorlevel 1 exit /b %errorlevel%

echo LabelMe offline component: %OUTPUT_ZIP%
exit /b 0
