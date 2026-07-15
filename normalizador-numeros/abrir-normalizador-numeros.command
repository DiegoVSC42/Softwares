#!/bin/bash
# Abre o Normalizador de Números no Mac (clique duplo).
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 nao encontrado. Instale em https://www.python.org/downloads/"
  read -n 1 -s -r -p "Pressione qualquer tecla para fechar"
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "Primeira execucao: preparando o ambiente (1 a 2 minutos)..."
  python3 -m venv .venv
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install --quiet -r requirements.txt
fi

exec ./.venv/bin/python normalizador_numeros.py
