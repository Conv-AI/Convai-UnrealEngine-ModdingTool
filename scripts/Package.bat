@echo off
REM === Build Python Script into EXE ===

REM Path to your Python script
set SCRIPT_NAME=ConvaiModdingTool.py

REM Desired output EXE name
set EXE_NAME=ConvaiAssetUploader

REM Icon file (must be .ico)
set ICON_FILE=resources/Convai.ico

REM The UI is files, not code: without --add-data the exe starts with nothing to show.
REM pywebview injects its own JS into the page (--collect-data) and picks its backend at
REM runtime, so nothing imports it statically (--hidden-import).
pyinstaller %SCRIPT_NAME% --onefile --icon=%ICON_FILE% --name=%EXE_NAME% ^
  --add-data "gui/webui;gui/webui" ^
  --collect-data webview ^
  --hidden-import webview.platforms.edgechromium ^
  --hidden-import webview.platforms.winforms ^
  --hidden-import clr

echo.
echo Build Complete! EXE located in the "dist" folder as %EXE_NAME%.exe
