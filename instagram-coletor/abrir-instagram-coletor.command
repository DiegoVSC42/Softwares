#!/bin/bash
# ============================================================
#  Instagram Coletor - abrir o programa (Mac)
#  Clique duplo neste arquivo.
#
#  O Mac vem com um Python antigo (Tk 8.5) que desenha a
#  janela toda preta. Este atalho procura um Python bom e,
#  se nao achar, instala um sozinho.
# ============================================================
export TK_SILENCE_DEPRECATION=1
cd "$(dirname "$0")"

echo "============================================"
echo "  Instagram Coletor"
echo "============================================"
echo

pausar_e_sair() {
  echo
  read -n 1 -s -r -p "Pressione qualquer tecla para fechar..."
  exit "${1:-1}"
}

versao_tk() {
  "$1" -c "import tkinter; print(tkinter.TkVersion)" 2>/dev/null
}

tk_bom() {
  # verdadeiro se a versao for 8.6 ou mais nova
  [ -n "$1" ] && [ "$(printf '%s\n8.6\n' "$1" | sort -V | head -1)" = "8.6" ]
}

# Procura um Python com Tk 8.6+ (o 8.5 da Apple abre janela preta).
achar_python_bom() {
  local candidatos=()
  for v in 3.14 3.13 3.12 3.11 3.10; do
    candidatos+=("/Library/Frameworks/Python.framework/Versions/$v/bin/python3")
    candidatos+=("/opt/homebrew/bin/python$v")
    candidatos+=("/usr/local/bin/python$v")
  done
  candidatos+=("/opt/homebrew/bin/python3" "/usr/local/bin/python3")
  for p in "${candidatos[@]}"; do
    [ -x "$p" ] || continue
    tk_bom "$(versao_tk "$p")" && echo "$p" && return 0
  done
  return 1
}

instalar_python() {
  echo "--------------------------------------------"
  echo " Seu Mac so tem o Python antigo da Apple."
  echo " Ele desenha a janela toda preta e nao serve."
  echo " Vou instalar a versao boa agora."
  echo "--------------------------------------------"
  echo

  # Caminho 1: Homebrew (automatico, sem senha)
  if command -v brew >/dev/null 2>&1; then
    echo "Instalando pelo Homebrew (leva 2 a 5 minutos)..."
    echo
    brew install python-tk 2>&1 | grep -vi "warning" || true
    echo
    if achar_python_bom >/dev/null; then
      echo "Instalado."
      return 0
    fi
    echo "[AVISO] O Homebrew nao resolveu. Vou tentar o instalador oficial."
    echo
  fi

  # Caminho 2: instalador oficial do python.org
  echo "Procurando o instalador oficial do Python..."
  local pagina url arquivo
  pagina="$(curl -fsSL --max-time 30 https://www.python.org/downloads/macos/ 2>/dev/null)"
  url="$(printf '%s' "$pagina" \
        | grep -oE 'https://www\.python\.org/ftp/python/3\.1[0-9]+\.[0-9]+/python-3\.1[0-9]+\.[0-9]+-macos11\.pkg' \
        | head -1)"

  if [ -z "$url" ]; then
    echo "[ERRO] Nao consegui achar o instalador automaticamente."
    echo
    echo " FACA ASSIM (leva 3 minutos):"
    echo "  1. Vou abrir o site do Python no seu navegador."
    echo "  2. Clique no botao amarelo 'Download Python'."
    echo "  3. Abra o arquivo baixado e clique em Continuar ate o fim."
    echo "  4. Volte aqui e clique duas vezes neste atalho de novo."
    echo
    open "https://www.python.org/downloads/macos/" 2>/dev/null
    pausar_e_sair 1
  fi

  arquivo="$HOME/Downloads/$(basename "$url")"
  echo "Baixando: $(basename "$url")"
  echo "(sao uns 60 MB, aguarde)"
  curl -fL --progress-bar --max-time 600 -o "$arquivo" "$url" || {
    echo "[ERRO] Falha no download."
    open "https://www.python.org/downloads/macos/" 2>/dev/null
    pausar_e_sair 1
  }

  echo
  echo "--------------------------------------------"
  echo " AGORA E COM VOCE (leva 1 minuto):"
  echo
  echo "  1. Vai abrir o instalador do Python."
  echo "  2. Clique em Continuar, Continuar, Concordo, Instalar."
  echo "  3. Digite a senha do seu Mac quando pedir."
  echo "  4. Quando terminar, feche o instalador."
  echo "  5. Clique duas vezes NESTE ATALHO de novo."
  echo "--------------------------------------------"
  echo
  open "$arquivo"
  pausar_e_sair 0
}

# ---------- escolhe o Python ----------
PY="$(achar_python_bom)"

if [ -z "$PY" ]; then
  instalar_python
  PY="$(achar_python_bom)"
  [ -z "$PY" ] && {
    echo "[ERRO] Ainda nao achei um Python bom. Reinicie o Mac e tente de novo."
    pausar_e_sair 1
  }
fi

TKV="$(versao_tk "$PY")"

# ---------- ambiente ----------
MARCA=".venv/.python-usado"
if [ -d ".venv" ] && [ "$(cat "$MARCA" 2>/dev/null)" != "$PY" ]; then
  echo "Python novo detectado. Refazendo o ambiente..."
  rm -rf .venv
fi

if [ ! -d ".venv" ]; then
  echo "Preparando o programa (leva 1 a 2 minutos)..."
  "$PY" -m venv .venv || pausar_e_sair 1
  echo "$PY" > "$MARCA"
fi

source .venv/bin/activate
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet || {
  echo "[ERRO] Falha ao instalar as dependencias."
  pausar_e_sair 1
}

echo "Abrindo o programa (Tk $TKV)..."
echo
python instagram_coletor.py

echo
read -n 1 -s -r -p "Programa fechado. Pressione qualquer tecla para sair..."
