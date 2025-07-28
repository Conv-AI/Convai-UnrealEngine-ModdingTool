@echo off
REM === Build Python Script into EXE ===

REM Path to your Python script
set SCRIPT_NAME=ConvaiModdingTool.py

REM Desired output EXE name
set EXE_NAME=ConvaiAssetUploader

REM Icon file (must be .ico)
set ICON_FILE=resources/Convai.ico

REM Run PyInstaller
pyinstaller %SCRIPT_NAME% --onefile --icon=%ICON_FILE% --name=%EXE_NAME%

echo.
echo ✅ Build Complete! EXE located in the "dist" folder as %EXE_NAME%.exe

