#!/bin/bash
# ===================================================================
#  Gera o aplicativo do Gerenciador de Pastas no macOS.
#  Como usar:
#    1. Copie a pasta do projeto para um Mac.
#    2. Abra o Terminal nesta pasta (ou de dois cliques neste arquivo).
#    3. Se o duplo clique nao funcionar, rode antes, uma vez:
#         chmod +x build_app_mac.command
#
#  Requisitos: Python 3.8+ (instale em https://python.org se necessario).
# ===================================================================

cd "$(dirname "$0")" || exit 1

echo
echo "[1/3] Instalando dependencias (reportlab, pyinstaller)..."
python3 -m pip install --upgrade pip >/dev/null 2>&1
python3 -m pip install reportlab pyinstaller
if [ $? -ne 0 ]; then
    echo
    echo "ERRO: nao foi possivel instalar as dependencias."
    echo "Verifique se o Python 3 esta instalado (python3 --version)."
    read -n 1 -s -r -p "Pressione qualquer tecla para sair..."
    exit 1
fi

echo
echo "[2/3] Gerando o aplicativo (pode demorar 1-2 minutos)..."
python3 -m PyInstaller \
    --noconfirm \
    --onefile \
    --windowed \
    --name "FolderManagerMAC" \
    --hidden-import reportlab \
    app.py

if [ $? -ne 0 ]; then
    echo
    echo "ERRO ao gerar o aplicativo."
    read -n 1 -s -r -p "Pressione qualquer tecla para sair..."
    exit 1
fi

echo
echo "[3/3] Pronto!"
echo
echo "O aplicativo foi gerado em:"
echo "    $(pwd)/dist/FolderManagerMAC.app"
echo
echo "Esse .app pode ser copiado para outros Macs e aberto com dois cliques,"
echo "SEM precisar instalar Python."
echo
echo "Observacao: na primeira vez, o macOS pode bloquear por ser um app sem"
echo "assinatura. Libere em: Ajustes do Sistema > Privacidade e Seguranca >"
echo "\"Abrir mesmo assim\"."
echo
read -n 1 -s -r -p "Pressione qualquer tecla para sair..."
