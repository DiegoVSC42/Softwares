#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Motor da conversao: pega o texto que o TurboScribe deixa na tela (o que sai
de um Cmd+A / Cmd+C) e devolve so a transcricao, sem o resto da pagina.

A transcricao sai EXATAMENTE como esta na tela, inclusive com os horarios no
meio da fala, que sao justamente o que serve para achar o corte. O programa
nao reescreve nada: ele corta o que sobra em volta.

O que entra (uma linha por paragrafo):

    TurboScribe
    Ilimitado
    Atalhos
    Pastas
    2020 Eu Vereador - ...
    ...nomes de pasta, Exportar, Mais, Play, Mute, Settings...
    Diamante maximo 01
    25 de jul. de 2026, 12:11
    Diamante maximo 01
    Play
    18:16
    1:13:09
    Mute
    Settings
    Dr. Fernando Maximo
    (0:00) E isso, por favor.
    Entrevistador NM
    (0:01) A levinha lateral ta de boa? (0:04) E porque ele ta de mais.

O que sai:

    Diamante maximo 01
    25 de jul. de 2026, 12:11

    Dr. Fernando Maximo
    (0:00) E isso, por favor.

    Entrevistador NM
    (0:01) A levinha lateral ta de boa? (0:04) E porque ele ta de mais.

Tres coisas que este arquivo resolve e que nao sao obvias:

* O lixo e cortado POR POSICAO, e nao por lista de palavras: tudo o que vem
  antes do primeiro nome de quem fala vai fora, e depois disso so sobrevive
  quem e nome de quem fala ou fala com horario. Mudar o idioma do site, ou a
  quantidade de pastas na barra lateral, nao quebra nada.
* Os nomes de quem fala nao sao fixos: sao descobertos no proprio texto (linha
  sem horario, curta, seguida de linha com horario). Funciona com qualquer
  entrevista e qualquer numero de participantes.
* O titulo e a data sao achados pela repeticao: na tela do TurboScribe o nome
  da gravacao aparece duas vezes (na aba e no player), e nenhum outro item da
  interface se repete assim. O que estiver entre as duas aparicoes e a data.

Este arquivo nao tem interface e nao depende de nada instalado: so a
biblioteca padrao do Python.
"""

import re
import unicodedata

# (0:00), (12:34) ou (1:07:50) no comeco da linha.
_SO_HORARIO = re.compile(r"^\s*\(\d{1,2}:\d{2}(?::\d{2})?\)")

# Um nome de quem fala e curto. Acima disso e paragrafo de fala sem horario.
_LIMITE_NOME = 60

# Marcas do que cada linha da saida e, para quem for gravar o arquivo saber
# como formatar.
NOME = "nome"      # quem fala
FALA = "fala"      # a fala, com os horarios dentro
VAZIO = "vazio"    # linha em branco entre blocos


def _limpar(texto):
    """Tira o que a colagem trouxe de sujeira, sem mexer no conteudo.

    Espaco nao separavel vira espaco normal e espaco repetido vira um so.
    A pontuacao e a escrita ficam exatamente como estao na tela: o pedido e
    um Cmd+V limpo, nao um texto reescrito.
    """
    texto = texto.replace(" ", " ").replace("​", "")
    return re.sub(r"[ \t]+", " ", texto).strip()


def _normalizar(texto):
    """Para comparar titulo repetido sem tropecar em acento ou caixa."""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.strip().lower()


def _titulo_e_data(cabecalho):
    """Acha o nome da gravacao e a data no lixo do topo.

    Devolve ("", "") quando nao da para ter certeza; quem chamou usa entao o
    nome do arquivo.
    """
    posicoes = {}
    for i, linha in enumerate(cabecalho):
        if len(linha) > 120:
            continue
        posicoes.setdefault(_normalizar(linha), []).append(i)

    repetidos = [(v, k) for k, v in posicoes.items() if len(v) > 1]
    if not repetidos:
        return "", ""

    # O titulo e o ultimo item repetido antes da fala comecar.
    repetidos.sort(key=lambda x: x[0][-1])
    indices = repetidos[-1][0]
    titulo = cabecalho[indices[0]]

    # Entre as duas aparicoes do titulo fica a data. Se houver mais de uma
    # linha ali, nao arriscamos.
    data = ""
    meio = cabecalho[indices[0] + 1:indices[1]]
    if len(meio) == 1:
        data = meio[0]
    return titulo, data


def converter(linhas):
    """Recebe os paragrafos crus e devolve (titulo, data, itens).

    `itens` e uma lista de pares (texto, marca), com marca em NOME, FALA ou
    VAZIO. Quem grava o arquivo decide como cada marca aparece.
    """
    linhas = [_limpar(l or "") for l in (linhas or [])]
    linhas = [l for l in linhas if l]

    inicio = next((i for i, l in enumerate(linhas) if _SO_HORARIO.match(l)), -1)
    if inicio < 1:
        raise ValueError(
            "Nao encontrei nenhuma fala com horario neste texto.\n\n"
            "Confira se voce copiou a pagina da transcricao no TurboScribe "
            "(clique dentro da pagina, Cmd+A e Cmd+C)."
        )

    # A linha logo antes da primeira fala e o primeiro nome de quem fala.
    # Tudo o que vem antes dela e interface.
    cabecalho = linhas[:inicio - 1]
    corpo = linhas[inicio - 1:]
    titulo, data = _titulo_e_data(cabecalho)

    # Descobre os nomes: linha sem horario, curta, seguida de linha com
    # horario. Basta uma ocorrencia para o nome entrar na lista, e dai em
    # diante ele e reconhecido mesmo aparecendo sozinho.
    nomes = set()
    for i, linha in enumerate(corpo[:-1]):
        if _SO_HORARIO.match(linha):
            continue
        if len(linha) <= _LIMITE_NOME and _SO_HORARIO.match(corpo[i + 1]):
            nomes.add(linha)

    itens = []
    comecou = False
    for linha in corpo:
        if _SO_HORARIO.match(linha):
            if comecou:
                itens.append((linha, FALA))
            continue
        if linha in nomes:
            if comecou:
                itens.append(("", VAZIO))
            itens.append((linha, NOME))
            comecou = True
        # Linha sem horario que nao e nome de ninguem e sobra da interface
        # (botao, rodape, nome de pasta). Some.

    if not itens:
        raise ValueError("Achei os horarios, mas nenhuma fala. Texto vazio?")

    return titulo, data, itens


def resumo(itens):
    """Conta blocos e falantes, so para mostrar na tela do programa."""
    falantes = []
    blocos = 0
    for texto, marca in itens:
        if marca == NOME:
            blocos += 1
            if texto not in falantes:
                falantes.append(texto)
    return blocos, sorted(falantes)
