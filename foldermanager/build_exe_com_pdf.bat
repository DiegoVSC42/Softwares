@echo off
REM ===================================================================
REM  Gera o executavel COMPLETO do Windows (COM PDF) na PASTA DE REDE.
REM  Use so se voce realmente precisa gerar relatorio em PDF nativo.
REM  Este arquivo e maior e abre um pouco mais devagar que o leve.
REM
REM  Nome do executavel: FolderManagerWIN-PDF.exe
REM  (fica ao lado do leve, sem substituir)
REM
REM  Requisitos: Python 3.8+ instalado e no PATH.
REM ===================================================================

set "DESTINO=D:\Softwares\Windows"

cd /d "%~dp0"

if not exist "%DESTINO%" mkdir "%DESTINO%"

echo.
echo [1/3] Instalando dependencias (reportlab, pyinstaller)...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install reportlab pyinstaller
if errorlevel 1 (
    echo.
    echo ERRO: nao foi possivel instalar as dependencias.
    pause
    exit /b 1
)

echo.
echo [2/3] Gerando o executavel COM PDF direto em "%DESTINO%"...
python -m PyInstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name "FolderManagerWIN-PDF" ^
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
echo O executavel COM PDF foi salvo em:
echo     %DESTINO%\FolderManagerWIN-PDF.exe
echo.
pause
