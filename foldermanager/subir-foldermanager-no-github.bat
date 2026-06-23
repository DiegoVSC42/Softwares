@echo off
REM ===================================================================
REM  Envia/ATUALIZA o FolderManager no repositorio "Softwares" do GitHub.
REM
REM  Funciona tanto na 1a vez (repo vazio) quanto nas seguintes
REM  (atualiza o que ja esta la, sem dar erro de "ja existe").
REM
REM  Estrutura no repositorio:
REM     Softwares/
REM     |- .github/workflows/build.yml   (robo que gera os executaveis)
REM     |- foldermanager/                (codigo deste software)
REM
REM  Na primeira vez, abre o login do GitHub no navegador.
REM  Requisito: Git para Windows (https://git-scm.com/download/win)
REM ===================================================================

set "REPO_URL=https://github.com/DiegoVSC42/Softwares.git"
set "SUBPASTA=foldermanager"
set "STAGE=%TEMP%\fm_repo"

cd /d "%~dp0"

where git >nul 2>&1
if errorlevel 1 (
    echo.
    echo [X] Git nao encontrado. Instale o "Git para Windows":
    echo     https://git-scm.com/download/win
    goto :fim
)

echo.
echo [1/5] Baixando o repositorio atual do GitHub...
if exist "%STAGE%" rmdir /s /q "%STAGE%"
git clone "%REPO_URL%" "%STAGE%"
if errorlevel 1 (
    echo.
    echo [X] Erro ao baixar o repositorio. Verifique o login do GitHub
    echo     e se a URL esta correta: %REPO_URL%
    goto :fim
)

echo.
echo [2/5] Atualizando os arquivos do FolderManager...
if exist "%STAGE%\%SUBPASTA%" rmdir /s /q "%STAGE%\%SUBPASTA%"
mkdir "%STAGE%\%SUBPASTA%"
copy /Y "%~dp0*.py"             "%STAGE%\%SUBPASTA%\" >nul
copy /Y "%~dp0requirements.txt" "%STAGE%\%SUBPASTA%\" >nul
copy /Y "%~dp0*.md"             "%STAGE%\%SUBPASTA%\" >nul
copy /Y "%~dp0*.bat"            "%STAGE%\%SUBPASTA%\" >nul
copy /Y "%~dp0*.command"        "%STAGE%\%SUBPASTA%\" >nul
copy /Y "%~dp0.gitignore"       "%STAGE%\%SUBPASTA%\" >nul

if not exist "%STAGE%\.github\workflows" mkdir "%STAGE%\.github\workflows"
if exist "%STAGE%\.github\workflows\build.yml" (
    findstr /m "FolderManagerWIN" "%STAGE%\.github\workflows\build.yml" >nul 2>&1 && del /q "%STAGE%\.github\workflows\build.yml"
)
copy /Y "%~dp0.github\workflows\foldermanager-build.yml" "%STAGE%\.github\workflows\" >nul

echo.
echo [3/5] Registrando as mudancas...
cd /d "%STAGE%"
git add -A
git -c user.email="foldermanager@local" -c user.name="FolderManager" commit -m "Atualiza FolderManager"
if errorlevel 1 echo     (nada novo para enviar - o codigo no GitHub ja estava igual)

echo.
echo [4/5] Enviando para o GitHub (pode abrir o login no navegador)...
git push origin HEAD
if errorlevel 1 (
    echo.
    echo [X] Erro ao enviar. Se aparecer "rejected", me avise para ajustar.
    goto :fim
)

echo.
echo [5/5] PRONTO! Codigo atualizado em: %REPO_URL%
echo.
echo ===================================================================
echo  IMPORTANTE - ESPERE O BUILD ANTES DE BAIXAR:
echo   1. Abra o repositorio no GitHub e va na aba "Actions".
echo   2. Espere a execucao mais recente ficar com o check VERDE
echo      (leva uns 3 minutos - ela compila Windows e Mac).
echo   3. SO ENTAO rode o "baixar-da-nuvem.bat".
echo.
echo  Se baixar antes do verde, voce pega o build ANTERIOR (antigo).
echo ===================================================================

:fim
echo.
echo ------------------------------------------------------------------
echo  Pressione qualquer tecla para fechar esta janela.
pause >nul
