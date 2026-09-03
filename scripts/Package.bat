@echo off
REM === Build Python Script into EXE ===

REM Path to your Python script
set SCRIPT_NAME=ConvaiModdingTool.py

REM Desired output EXE name
set EXE_NAME=ConvaiAssetUploader

REM Icon file (must be .ico)
set ICON_FILE=resources/Convai.ico

REM PyInstaller bundles what the interpreter RUNNING it can import. A bare `pyinstaller`
REM is whichever one is first on PATH, which is not necessarily the one the requirements
REM were installed into: that mismatch builds an exe whose imports fail at start-up, not
REM at build time. `python -m PyInstaller` keeps the two the same.
python -c "import PyInstaller" 2>NUL
if errorlevel 1 (
  echo [ERROR] PyInstaller is not installed for this Python.
  python -c "import sys; print('        python is', sys.executable)"
  echo         Fix: python -m pip install pyinstaller
  exit /b 1
)

python -c "import webview" 2>NUL
if errorlevel 1 (
  echo [ERROR] pywebview is not installed for this Python, so the UI would not be bundled.
  python -c "import sys; print('        python is', sys.executable)"
  echo         Fix: python -m pip install -r resources/requirements.txt
  exit /b 1
)

REM The UI is files, not code: without --add-data the exe starts with nothing to show.
REM pywebview injects its own JS into the page (--collect-data) and picks its backend at
REM runtime, so nothing imports it statically (--hidden-import).
python -m PyInstaller %SCRIPT_NAME% --onefile --noconfirm --icon=%ICON_FILE% --name=%EXE_NAME% ^
  --add-data "gui/webui;gui/webui" ^
  --collect-data webview ^
  --hidden-import webview.platforms.edgechromium ^
  --hidden-import webview.platforms.winforms ^
  --hidden-import clr
if errorlevel 1 (
  echo [ERROR] PyInstaller failed.
  exit /b 1
)

echo.
echo Build Complete! EXE located in the "dist" folder as %EXE_NAME%.exe
