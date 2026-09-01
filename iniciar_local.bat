@echo off
setlocal
cd /d "%~dp0"

net session >nul 2>&1
if not %errorlevel%==0 (
    echo Solicitando permissao de administrador para liberar o acesso na rede...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

where py >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON=py -3"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python nao foi encontrado.
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
netsh advfirewall firewall add rule name="Sistema OS - Porta 5000" dir=in action=allow protocol=TCP localport=5000 profile=any >nul 2>nul

for /f %%A in ('powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -like '192.168.*' } | Select-Object -ExpandProperty IPAddress | Select-Object -First 1)"') do set "IP_REDE=%%A"
start "Sistema OS" http://127.0.0.1:5000
echo Sistema iniciado neste computador em http://127.0.0.1:5000
echo Acesso pela rede: http://%IP_REDE%:5000
echo Compartilhe esse endereco com as outras maquinas da mesma rede.
".venv\Scripts\python.exe" app.py
goto :fim

:erro
echo.
echo Nao foi possivel iniciar o sistema.
pause

:fim
endlocal