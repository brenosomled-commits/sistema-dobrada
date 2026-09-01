@echo off
setlocal EnableExtensions
cd /d "%~dp0"

:menu
cls
echo ========================================
echo          CONTROLE DO SISTEMA OS
echo ========================================
echo.
echo [1] Ligar sistema
echo [2] Desligar sistema
echo [3] Reiniciar sistema
echo [4] Sair
echo.
choice /c 1234 /n /m "Escolha uma opcao: "
if errorlevel 4 goto fim
if errorlevel 3 goto reiniciar
if errorlevel 2 goto desligar
if errorlevel 1 goto ligar

:ligar
netsh advfirewall firewall add rule name="Sistema OS - Porta 5000" dir=in action=allow protocol=TCP localport=5000 profile=any >nul 2>nul
for /f %%A in ('powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -like '192.168.*' } | Select-Object -ExpandProperty IPAddress | Select-Object -First 1)"') do set "IP_REDE=%%A"
for /f %%A in ('powershell -NoProfile -Command "(Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess"') do set "PID_SERVIDOR=%%A"
if defined PID_SERVIDOR (
    echo O sistema ja esta ligado.
) else (
    start "Sistema OS" /min ".venv\Scripts\python.exe" app.py
    timeout /t 3 /nobreak >nul
    echo Sistema ligado.
)
echo Acesso local: http://127.0.0.1:5000
 echo Acesso na rede: http://%IP_REDE%:5000
pause
goto menu

:desligar
for /f %%A in ('powershell -NoProfile -Command "(Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)"') do powershell -NoProfile -Command "Stop-Process -Id %%A -Force -ErrorAction SilentlyContinue"
 echo Sistema desligado.
pause
goto menu

:reiniciar
call :desligar_silencioso
netsh advfirewall firewall add rule name="Sistema OS - Porta 5000" dir=in action=allow protocol=TCP localport=5000 profile=any >nul 2>nul
start "Sistema OS" /min ".venv\Scripts\python.exe" app.py
timeout /t 3 /nobreak >nul
 echo Sistema reiniciado.
pause
goto menu

:desligar_silencioso
for /f %%A in ('powershell -NoProfile -Command "(Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)"') do powershell -NoProfile -Command "Stop-Process -Id %%A -Force -ErrorAction SilentlyContinue"
exit /b

:fim
endlocal