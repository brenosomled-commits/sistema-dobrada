@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON=py -3"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python nao foi encontrado.
        echo Instale o Python 3.11 ou superior em https://www.python.org/downloads/
        pause
        exit /b 1
    )
    set "PYTHON=python"
)

if not exist ".venv\Scripts\python.exe" (
    echo Criando ambiente virtual...
    %PYTHON% -m venv .venv
    if errorlevel 1 goto :erro
)

echo Instalando/verificando dependencias...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :erro

if "%SECRET_KEY%"=="" set "SECRET_KEY=troque-esta-chave-antes-de-publicar"
if not exist "ordens.db" if "%ADMIN_PASSWORD%"=="" set "ADMIN_PASSWORD=admin1234"

start "Sistema OS" http://127.0.0.1:5000
echo Sistema iniciado em http://127.0.0.1:5000
".venv\Scripts\python.exe" app.py
goto :fim

:erro
echo.
echo Nao foi possivel iniciar o sistema.
pause

:fim
endlocal
