@echo off
setlocal

cd /d "%~dp0"

echo Installing/updating dependencies...
python -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo Failed to install dependencies.
    pause
    exit /b 1
)

set ADD_DATA_ARGS=
if exist "ICO" (
    set ADD_DATA_ARGS=--add-data "ICO;ICO"
)

if not exist "ICO\app.ico" (
    echo.
    echo Error: put the executable icon at ICO\app.ico
    pause
    exit /b 1
)

if not exist "ICO\logo.ico" (
    echo.
    echo Error: put the internal app logo at ICO\logo.ico
    pause
    exit /b 1
)

echo.
echo Creating single-file executable...
python -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --windowed ^
    --onefile ^
    --name "Soe Character Launcher" ^
    --icon "ICO\app.ico" ^
    %ADD_DATA_ARGS% ^
    --collect-all customtkinter ^
    --collect-all tkinterdnd2 ^
    soe_character_launcher.py

if errorlevel 1 (
    echo.
    echo Failed to create executable.
    pause
    exit /b 1
)

echo.
echo Done!
echo The executable is here:
echo dist\Soe Character Launcher.exe
echo.
pause
