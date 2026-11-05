"""Aba "Cortar e dividir" do Audio Studio.

A tela mora em `compartilhado/cortar_dividir.py`, que e copia da fonte em
`abas-compartilhadas/`. Aqui so dizemos que neste estudio o foco e audio.
"""

from compartilhado import cortar_dividir


def montar(pai):
    return cortar_dividir.montar(pai, foco="audio")
