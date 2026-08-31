@echo off
setlocal EnableExtensions
cd /d "%~dp0..\"

echo ============================================================
echo  Generador de cadena de certificados para Docker + Netskope
echo  Genera backend\ca\corporate-ca-chain.crt
echo ============================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0generar_ca.ps1"
if errorlevel 1 (
    echo.
    echo ERROR: no se pudo generar la cadena.
    exit /b 1
)

echo ============================================================
echo  Verificando la cadena con openssl...
echo ============================================================
set "OPSSL="
where openssl >nul 2>nul && set "OPSSL=openssl"
if not defined OPSSL if exist "C:\Program Files\Git\usr\bin\openssl.exe" set "OPSSL=C:\Program Files\Git\usr\bin\openssl.exe"
if defined OPSSL (
    echo | "%OPSSL%" s_client -connect pypi.org:443 -servername pypi.org -CAfile "backend\ca\corporate-ca-chain.crt" 2>nul | findstr /i "Verify return code"
) else (
    echo openssl no encontrado. La cadena ya fue guardada en backend\ca\corporate-ca-chain.crt
)
echo.
echo NOTA: el resultado debe decir "Verify return code: 0 (ok)".
echo Luego ejecuta: docker compose build --no-cache backend
echo.
endlocal