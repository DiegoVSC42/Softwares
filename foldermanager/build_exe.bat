@echo off
REM ===================================================================
REM  Gera o executavel do Windows e salva na PASTA DE REDE.
REM  Basta dar dois cliques neste arquivo.
REM
REM  Requisitos: Python 3.8+ instalado e no PATH.
REM ===================================================================

REM ---- Pasta de destino na rede (mude aqui se precisar) -------------
set "DESTINO=D:\Softwares\Windows"
REM -------------------------------------------------------------------

cd /d "%~dp0"

if not exist "%DESTINO%" mkdir "%DESTINO%"

echo.
echo [1/3] Instalando dependencias (reportlab, pyinstaller)...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install reportlab pyinstaller
if errorlevel 1 (
    echo.
    echo ERRO: nao foi possivel instalar as dependencias.
    echo Verifique se o Python esta instalado e no PATH.
    pause
    exit /b 1
)

echo.
echo [2/3] Gerando o executavel direto em "%DESTINO%" (pode demorar 1-2 minutos)...
python -m PyInstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name "FolderManagerWIN" ^
    --hidden-import reportlab ^
    --distpath "%DESTINO%" ^
    --workpath "%~dp0build" ^
    --specpath "%~dp0build" ^
    app.py

if errorlevel 1 (
    echo.
    echo ERRO ao gerar o executavel.
    pause
    exit /b 1
)

echo.
echo [3/3] Pronto!
echo.
echo O executavel foi salvo em:
echo     %DESTINO%\FolderManagerWIN.exe
echo.
echo As pessoas do escritorio ja podem abrir esse arquivo pela rede.
echo.
pause
