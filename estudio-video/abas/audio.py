"""Aba "Extrair audio" do Video Studio.

A tela mora em `compartilhado/extrair_audio.py`, que e copia da fonte em
`abas-compartilhadas/`. Aqui so dizemos que neste estudio o foco e video.
"""

from compartilhado import extrair_audio


def montar(pai):
    return extrair_audio.montar(pai, foco="video")
