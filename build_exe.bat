@echo off
setlocal

cd /d "%~dp0"

echo Instalando/atualizando dependencias...
python -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo Erro ao instalar dependencias.
    pause
    exit /b 1
)

set ADD_DATA_ARGS=
if exist "ICO" (
    set ADD_DATA_ARGS=--add-data "ICO;ICO"
)

if not exist "ICO\app.ico" (
    echo.
    echo Erro: coloque o icone do executavel em ICO\app.ico
    pause
    exit /b 1
)

if not exist "ICO\logo.ico" (
    echo.
    echo Erro: coloque o logo interno em ICO\logo.ico
    pause
    exit /b 1
)

echo.
echo Criando executavel...
python -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --windowed ^
    --onedir ^
    --name "WildLife Prop Manager" ^
    --icon "ICO\app.ico" ^
    %ADD_DATA_ARGS% ^
    --collect-all customtkinter ^
    --collect-all tkinterdnd2 ^
    soe_character_launcher.py

if errorlevel 1 (
    echo.
    echo Erro ao criar o executavel.
    pause
    exit /b 1
)

echo.
echo Pronto!
echo O executavel ficou em:
echo dist\WildLife Prop Manager\WildLife Prop Manager.exe
echo.
pause
