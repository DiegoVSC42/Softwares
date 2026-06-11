@echo off
REM ===================================================================
REM  Gera o executavel LEVE do Windows e salva na PASTA DE REDE.
REM  (Sem PDF -> arquivo pequeno e abertura rapida. Relatorio em CSV e HTML.)
REM
REM  Para uma versao COM PDF, use o build_exe_com_pdf.bat.
REM
REM  Requisitos: Python 3.8+ instalado e no PATH.
REM ===================================================================

REM ---- Pasta de destino na rede (mude aqui se precisar) -------------
set "DESTINO=D:\Softwares\Windows"
REM -------------------------------------------------------------------

cd /d "%~dp0"

if not exist "%DESTINO%" mkdir "%DESTINO%"

echo.
echo [1/3] Instalando o empacotador (pyinstaller)...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install pyinstaller
if errorlevel 1 (
    echo.
    echo ERRO: nao foi possivel instalar o pyinstaller.
    echo Verifique se o Python esta instalado e no PATH.
    pause
    exit /b 1
)

echo.
echo [2/3] Gerando o executavel LEVE direto em "%DESTINO%"...
python -m PyInstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name "FolderManagerWIN" ^
    --exclude-module reportlab ^
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
echo O executavel LEVE foi salvo em:
echo     %DESTINO%\FolderManagerWIN.exe
echo.
echo Relatorios disponiveis nesta versao: CSV e HTML.
echo (O HTML pode ser impresso como PDF pelo proprio navegador.)
echo.
pause
