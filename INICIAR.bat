@echo off
setlocal
chcp 65001 >nul
title BSOBPDF
cd /d "%~dp0"

echo.
echo   BSOBPDF - herramientas PDF en tu computador
echo   ------------------------------------------
echo.

rem El entorno de Python va fuera de OneDrive para no sincronizar miles de archivos
set "VENV=%LOCALAPPDATA%\BSOBPDF\venv"
set "VPY=%VENV%\Scripts\python.exe"

rem 1. Buscar Python 3.9 o superior
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)" >nul 2>nul && set "PY=py -3"
if not defined PY (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo   No se encontro Python 3.9 o superior.
  echo   Instala Python 3.12 desde https://www.python.org/downloads/
  echo   y marca la casilla "Add python.exe to PATH" durante la instalacion.
  echo.
  start "" "https://www.python.org/downloads/"
  pause
  exit /b 1
)

rem 2. Crear el entorno la primera vez
if not exist "%VPY%" (
  echo   Preparando BSOBPDF por primera vez. Esto tarda unos minutos...
  %PY% -m venv "%VENV%"
  if errorlevel 1 goto :error
)

rem 3. Instalar o actualizar dependencias solo si cambiaron
fc /b "requirements.txt" "%VENV%\requirements.ok" >nul 2>nul
if errorlevel 1 (
  echo   Instalando componentes. Necesita internet solo esta vez...
  "%VPY%" -m pip install --upgrade pip --disable-pip-version-check -q
  "%VPY%" -m pip install -r requirements.txt --disable-pip-version-check
  if errorlevel 1 goto :error
  copy /y "requirements.txt" "%VENV%\requirements.ok" >nul
)

rem 4. Arrancar
echo   Abriendo BSOBPDF en tu navegador...
"%VPY%" app.py
echo.
echo   BSOBPDF se cerro.
pause
exit /b 0

:error
echo.
echo   Algo fallo durante la instalacion. Revisa tu conexion a internet
echo   y vuelve a ejecutar INICIAR.bat. Si el error continua, borra la carpeta:
echo   %VENV%
echo.
pause
exit /b 1
