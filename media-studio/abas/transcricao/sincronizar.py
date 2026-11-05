"""Aba "Sincronizar" da categoria Transcricao do Media Studio.

A tela mora em `compartilhado/aba_sincronizar.py`, que e copia da fonte em
`abas-compartilhadas/`, porque a mesma aba tambem existe no Transcript
Studio. Aqui so dizemos em qual programa ela esta, para as mensagens saírem
com o nome certo.
"""

from compartilhado import aba_sincronizar


def montar(pai):
    return aba_sincronizar.montar(pai, programa="Media Studio")
