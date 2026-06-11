@echo off
REM ===================================================================
REM  Baixa o aplicativo do MAC (gerado na nuvem pelo GitHub Actions)
REM  e salva o ARQUIVO .ZIP na PASTA DE REDE.
REM
REM  IMPORTANTE: o app do Mac (.app) e um "pacote". Ele NAO pode ser
REM  extraido no Windows, senao perde as permissoes e nao abre no Mac.
REM  Por isso deixamos o .ZIP aqui, e a pessoa do Mac descompacta NO MAC.
REM
REM  Pre-requisito (so na primeira vez):
REM    1. Instalar o GitHub CLI: https://cli.github.com  (botao Download)
REM    2. Abrir o "Prompt de Comando" e rodar:  gh auth login
REM       (siga: GitHub.com > HTTPS > login pelo navegador)
REM ===================================================================

REM ---- Configuracao -------------------------------------------------
set "REPO=DiegoVSC42/Softwares"
set "DESTINO=D:\Softwares\Mac"
REM -------------------------------------------------------------------

setlocal
cd /d "%~dp0"

where gh >nul 2>&1
if errorlevel 1 (
    echo.
    echo O GitHub CLI ^(gh^) nao foi encontrado.
    echo Instale uma unica vez em: https://cli.github.com
    echo Depois rode no Prompt de Comando:  gh auth login
    echo.
    pause
    exit /b 1
)

if not exist "%DESTINO%" mkdir "%DESTINO%"

echo.
echo [1/2] Baixando o aplicativo do Mac do ultimo build da nuvem...
gh run download -R "%REPO%" -n FolderManagerMAC -D "%DESTINO%"
if errorlevel 1 (
    echo.
    echo ERRO ao baixar. Verifique se:
    echo   - voce rodou "gh auth login" uma vez
    echo   - o nome do repositorio em REPO esta correto
    echo   - ja existe um build CONCLUIDO (check verde) na aba Actions
    echo.
    pause
    exit /b 1
)

echo.
echo [2/2] Pronto!
echo.
echo O arquivo foi salvo em:
echo     %DESTINO%\FolderManagerMAC-mac.zip
echo.
echo ===================================================================
echo  COMO A PESSOA DO MAC USA:
echo   1. Copia o "FolderManagerMAC-mac.zip" da rede para o Mac dela.
echo   2. Da dois cliques no .zip (o Mac descompacta sozinho).
echo   3. Abre o "FolderManagerMAC.app" que aparece.
echo      (Na 1a vez: clique com o botao direito ^> Abrir, para liberar.)
echo ===================================================================
echo.
pause
