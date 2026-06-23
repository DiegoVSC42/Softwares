@echo off
REM ===================================================================
REM  FAZ TUDO em um clique:
REM    1. Envia o codigo para o GitHub (repo Softwares / foldermanager)
REM    2. Espera a nuvem compilar Windows e Mac (mostra o progresso)
REM    3. Baixa os dois executaveis prontos para a pasta de rede:
REM         FolderManagerWIN.exe       -> D:\Softwares\Windows
REM         FolderManagerMAC-mac.zip   -> D:\Softwares\Mac
REM
REM  Requisitos (so na primeira vez):
REM    - Git para Windows .......... https://git-scm.com/download/win
REM    - GitHub CLI (gh) ........... https://cli.github.com
REM      e depois, no Prompt de Comando:  gh auth login
REM ===================================================================

setlocal enabledelayedexpansion

REM ---- Configuracao -------------------------------------------------
set "REPO=DiegoVSC42/Softwares"
set "REPO_URL=https://github.com/DiegoVSC42/Softwares.git"
set "SUBPASTA=foldermanager"
set "STAGE=%TEMP%\fm_repo"
set "DEST_WIN=D:\Softwares\Windows"
set "DEST_MAC=D:\Softwares\Mac"
REM -------------------------------------------------------------------

cd /d "%~dp0"

where git >nul 2>&1
if errorlevel 1 (
    echo [X] Git nao encontrado. Instale: https://git-scm.com/download/win
    goto :fim
)
where gh >nul 2>&1
if errorlevel 1 (
    echo [X] GitHub CLI nao encontrado. Instale: https://cli.github.com
    echo     Depois rode no Prompt de Comando:  gh auth login
    goto :fim
)

REM Guarda o id do build anterior, para detectar o novo depois do envio.
set "RUN_ANTES="
for /f "delims=" %%i in ('gh run list -R "%REPO%" --workflow foldermanager-build.yml -L 1 --json databaseId --jq ".[0].databaseId" 2^>nul') do set "RUN_ANTES=%%i"

echo.
echo [1/4] Enviando o codigo para o GitHub...
if exist "%STAGE%" rmdir /s /q "%STAGE%"
git clone "%REPO_URL%" "%STAGE%"
if errorlevel 1 (
    echo [X] Erro ao baixar o repositorio. Verifique o login do GitHub e a URL.
    goto :fim
)

if exist "%STAGE%\%SUBPASTA%" rmdir /s /q "%STAGE%\%SUBPASTA%"
mkdir "%STAGE%\%SUBPASTA%"
copy /Y "%~dp0*.py"             "%STAGE%\%SUBPASTA%\" >nul
copy /Y "%~dp0requirements.txt" "%STAGE%\%SUBPASTA%\" >nul
copy /Y "%~dp0*.md"             "%STAGE%\%SUBPASTA%\" >nul
copy /Y "%~dp0*.bat"            "%STAGE%\%SUBPASTA%\" >nul
copy /Y "%~dp0*.command"        "%STAGE%\%SUBPASTA%\" >nul
copy /Y "%~dp0.gitignore"       "%STAGE%\%SUBPASTA%\" >nul
if not exist "%STAGE%\.github\workflows" mkdir "%STAGE%\.github\workflows"
REM remove o workflow ANTIGO do FolderManager (build.yml), se for o nosso,
REM para nao rodar duplicado. Nao mexe em workflows de outros softwares.
if exist "%STAGE%\.github\workflows\build.yml" (
    findstr /m "FolderManagerWIN" "%STAGE%\.github\workflows\build.yml" >nul 2>&1 && del /q "%STAGE%\.github\workflows\build.yml"
)
copy /Y "%~dp0.github\workflows\foldermanager-build.yml" "%STAGE%\.github\workflows\" >nul

cd /d "%STAGE%"
git add -A
git -c user.email="foldermanager@local" -c user.name="FolderManager" commit -m "Atualiza FolderManager" >nul 2>&1
if errorlevel 1 echo     (nada novo no codigo - o GitHub ja estava igual)
git push origin HEAD
if errorlevel 1 (
    echo [X] Erro ao enviar para o GitHub.
    cd /d "%~dp0"
    goto :fim
)
cd /d "%~dp0"

echo.
echo [2/4] Aguardando o build comecar na nuvem...
set "RUNID=%RUN_ANTES%"
for /L %%n in (1,1,24) do (
    timeout /t 5 /nobreak >nul
    for /f "delims=" %%i in ('gh run list -R "%REPO%" --workflow foldermanager-build.yml -L 1 --json databaseId --jq ".[0].databaseId" 2^>nul') do set "RUNID=%%i"
    if not "!RUNID!"=="!RUN_ANTES!" goto :temrun
)
:temrun
if "!RUNID!"=="" (
    echo [X] Nao encontrei o build. Abra a aba Actions no GitHub para conferir.
    goto :fim
)

echo.
echo [3/4] Compilando na nuvem (Windows e Mac). Leva alguns minutos...
call gh run watch !RUNID! -R "%REPO%" --exit-status
if errorlevel 1 (
    echo.
    echo [X] O build FALHOU na nuvem. Abra a aba Actions no GitHub para ver o erro.
    goto :fim
)

echo.
echo [4/4] Baixando os executaveis para a rede...
set "ERR_WIN=0"
set "ERR_MAC=0"
call :baixar FolderManagerWIN "%DEST_WIN%" win
if errorlevel 1 set "ERR_WIN=1"
call :baixar FolderManagerMAC "%DEST_MAC%" mac
if errorlevel 1 set "ERR_MAC=1"

echo.
echo ===================================================================
if "!ERR_WIN!"=="0"     echo  [OK]     Windows: %DEST_WIN%\FolderManagerWIN.exe
if not "!ERR_WIN!"=="0" echo  [FALHOU] Windows: nao baixou.
if "!ERR_MAC!"=="0"     echo  [OK]     Mac:     %DEST_MAC%\FolderManagerMAC-mac.zip
if not "!ERR_MAC!"=="0" echo  [FALHOU] Mac: nao baixou.
echo ===================================================================
if "!ERR_WIN!"=="0" if "!ERR_MAC!"=="0" (
    echo.
    echo  TUDO PRONTO! Os executaveis na rede estao atualizados.
    echo   WINDOWS: abre direto o .exe.
    echo   MAC: copiar o .zip para o Mac, descompactar la e abrir o .app.
)
goto :fim


REM ---- Sub-rotina de download (baixa em pasta temp e copia por cima) -
:baixar
set "TMPD=%TEMP%\fm_dl_%~3"
if exist "%TMPD%" rmdir /s /q "%TMPD%"
mkdir "%TMPD%"
call gh run download !RUNID! -R "%REPO%" -n %~1 -D "%TMPD%"
if errorlevel 1 exit /b 1
if not exist "%~2" mkdir "%~2"
copy /Y "%TMPD%\*" "%~2\" >nul
if errorlevel 1 exit /b 1
rmdir /s /q "%TMPD%"
exit /b 0


:fim
echo.
echo ------------------------------------------------------------------
echo  Pressione qualquer tecla para fechar.
pause >nul
