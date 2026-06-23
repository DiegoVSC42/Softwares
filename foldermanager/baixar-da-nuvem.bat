@echo off
REM ===================================================================
REM  Baixa os DOIS executaveis do ultimo build da nuvem (GitHub Actions)
REM  e salva cada um na sua pasta de rede, SOBRESCREVENDO se ja existir:
REM     - FolderManagerWIN.exe        -> D:\Softwares\Windows
REM     - FolderManagerMAC-mac.zip    -> D:\Softwares\Mac
REM
REM  O Mac fica como .ZIP de proposito: a pessoa do Mac descompacta NO
REM  MAC (extrair no Windows quebra as permissoes do app).
REM
REM  Pre-requisito (so na primeira vez):
REM    1. Instalar o GitHub CLI: https://cli.github.com
REM    2. No Prompt de Comando rodar:  gh auth login
REM ===================================================================

REM ---- Configuracao -------------------------------------------------
set "REPO=DiegoVSC42/Softwares"
set "DEST_WIN=D:\Softwares\Windows"
set "DEST_MAC=D:\Softwares\Mac"
REM -------------------------------------------------------------------

setlocal
cd /d "%~dp0"

where gh >nul 2>&1
if errorlevel 1 (
    echo.
    echo [X] O GitHub CLI ^(gh^) nao foi encontrado.
    echo     Instale em: https://cli.github.com
    echo     Depois rode no Prompt de Comando:  gh auth login
    goto :fim
)

REM Descobre o ULTIMO build do workflow do FolderManager (e nao de outro
REM software que tambem rode no mesmo repositorio).
set "RUNID="
for /f "delims=" %%i in ('gh run list -R "%REPO%" --workflow foldermanager-build.yml -L 1 --json databaseId --jq ".[0].databaseId" 2^>nul') do set "RUNID=%%i"
if "%RUNID%"=="" (
    echo.
    echo [X] Nao encontrei um build do FolderManager na nuvem.
    echo     Rode o ATUALIZAR-TUDO.bat (ou envie o codigo) e espere o build.
    goto :fim
)

echo.
echo [1/2] Baixando o executavel do WINDOWS...
call :baixar FolderManagerWIN "%DEST_WIN%" win
set "ERR_WIN=%ERRORLEVEL%"

echo.
echo [2/2] Baixando o aplicativo do MAC...
call :baixar FolderManagerMAC "%DEST_MAC%" mac
set "ERR_MAC=%ERRORLEVEL%"

echo.
echo ===================================================================
if "%ERR_WIN%"=="0" echo  [OK]     Windows: %DEST_WIN%\FolderManagerWIN.exe
if not "%ERR_WIN%"=="0" echo  [FALHOU] Windows: nao foi possivel baixar.
if "%ERR_MAC%"=="0" echo  [OK]     Mac:     %DEST_MAC%\FolderManagerMAC-mac.zip
if not "%ERR_MAC%"=="0" echo  [FALHOU] Mac:     nao foi possivel baixar.
echo ===================================================================

if "%ERR_WIN%"=="0" if "%ERR_MAC%"=="0" goto :tudo_ok

echo.
echo  ALGO FALHOU. Causas mais comuns:
echo    - voce ainda nao rodou "gh auth login" neste PC
echo    - o nome do repositorio esta errado. Atual: %REPO%
echo    - ainda nao existe um build CONCLUIDO (check verde) em Actions
echo    - o build existe, mas um dos lados falhou la na nuvem
goto :fim

:tudo_ok
echo.
echo  TUDO CERTO! Os dois executaveis foram atualizados na rede.
echo.
echo   WINDOWS: a pessoa abre direto o FolderManagerWIN.exe
echo   MAC: a pessoa copia o .zip para o Mac, da dois cliques para
echo        descompactar, e abre o FolderManagerMAC.app
echo        Na primeira vez: botao direito e depois Abrir, para liberar.
goto :fim


REM ---- Sub-rotina de download (baixa em pasta temp e copia por cima) -
:baixar
REM  %1 = nome do artefato | %2 = pasta destino | %3 = nome temp
set "TMPD=%TEMP%\fm_dl_%~3"
if exist "%TMPD%" rmdir /s /q "%TMPD%"
mkdir "%TMPD%"
call gh run download %RUNID% -R "%REPO%" -n %~1 -D "%TMPD%"
if errorlevel 1 exit /b 1
if not exist "%~2" mkdir "%~2"
copy /Y "%TMPD%\*" "%~2\" >nul
if errorlevel 1 exit /b 1
rmdir /s /q "%TMPD%"
exit /b 0


:fim
echo.
echo ------------------------------------------------------------------
echo  Terminou. Pressione qualquer tecla para fechar esta janela.
pause >nul
