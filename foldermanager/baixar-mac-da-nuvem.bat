@echo off
REM ===================================================================
REM  Baixa o aplicativo do MAC (gerado na nuvem pelo GitHub Actions)
REM  e salva na PASTA DE REDE, para o pessoal do escritorio pegar.
REM
REM  Pre-requisito (so na primeira vez):
REM    1. Instalar o GitHub CLI: https://cli.github.com  (botao Download)
REM    2. Abrir o "Prompt de Comando" e rodar:  gh auth login
REM       (siga as perguntas: GitHub.com > HTTPS > login pelo navegador)
REM ===================================================================

REM ---- Configuracao (ajuste estas duas linhas) ----------------------
set "REPO=DiegoVSC42/Softwares"
set "DESTINO=D:\Softwares\Mac"
REM -------------------------------------------------------------------

setlocal
cd /d "%~dp0"

REM Confere se o GitHub CLI esta instalado
where gh >nul 2>&1
if errorlevel 1 (
    echo.
    echo O GitHub CLI ^(gh^) nao foi encontrado.
    echo.
    echo Instale uma unica vez em: https://cli.github.com
    echo Depois rode no Prompt de Comando:  gh auth login
    echo.
    pause
    exit /b 1
)

if not exist "%DESTINO%" mkdir "%DESTINO%"

set "TMP_MAC=%TEMP%\fm_mac_download"
if exist "%TMP_MAC%" rmdir /s /q "%TMP_MAC%"
mkdir "%TMP_MAC%"

echo.
echo [1/3] Baixando o aplicativo do Mac do ultimo build da nuvem...
gh run download -R "%REPO%" -n FolderManagerMAC -D "%TMP_MAC%"
if errorlevel 1 (
    echo.
    echo ERRO ao baixar. Verifique se:
    echo   - voce rodou "gh auth login" uma vez
    echo   - o nome do repositorio em REPO esta correto
    echo   - ja existe um build concluido na aba Actions do GitHub
    echo.
    pause
    exit /b 1
)

echo.
echo [2/3] Extraindo o aplicativo para "%DESTINO%"...
powershell -NoProfile -Command ^
  "Expand-Archive -Force -LiteralPath '%TMP_MAC%\FolderManagerMAC-mac.zip' -DestinationPath '%DESTINO%'"
if errorlevel 1 (
    echo ERRO ao extrair o arquivo.
    pause
    exit /b 1
)

rmdir /s /q "%TMP_MAC%"

echo.
echo [3/3] Pronto!
echo.
echo O aplicativo do Mac foi salvo em:
echo     %DESTINO%\FolderManagerMAC.app
echo.
echo Quem usa Mac ja pode copiar essa pasta pela rede e abrir o app.
echo.
pause
