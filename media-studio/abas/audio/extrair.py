"""Aba "Extrair audio" do Audio Studio.

A tela mora em `compartilhado/extrair_audio.py`, que e copia da fonte em
`abas-compartilhadas/`. Aqui so dizemos que neste estudio o foco e audio.
"""

from compartilhado import extrair_audio


def montar(pai):
    return extrair_audio.montar(pai, foco="audio")
