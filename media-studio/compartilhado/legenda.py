# ATENCAO: este arquivo e uma COPIA. Nao edite aqui.
# A fonte oficial e `abas-compartilhadas/legenda.py`, na pasta Scripts. Mexa la e
# rode `python3 sincronizar.py` para atualizar todos os estudios de uma vez.
# Editar esta copia faz o seu trabalho ser apagado na proxima sincronizacao.

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Le a transcricao que sai da aba "Limpar transcricao" e a devolve em SEGMENTOS,
que e o formato de que a aba de sincronizar precisa para casar cada fala com o
momento do video.

O que entra (o .docx ou .txt gravado pela outra aba):

    Diamante maximo 01
    25 de jul. de 2026, 12:11

    Dr. Fernando Maximo
    (0:00) E isso, por favor. (0:04) Pode comecar.

    Entrevistador NM
    (0:06) A levinha lateral ta de boa?

O que sai:

    titulo = "Diamante maximo 01"
    data   = "25 de jul. de 2026, 12:11"
    segmentos = [
        {"t": 0.0, "f": "Dr. Fernando Maximo", "x": "E isso, por favor."},
        {"t": 4.0, "f": "Dr. Fernando Maximo", "x": "Pode comecar."},
        {"t": 6.0, "f": "Entrevistador NM",    "x": "A levinha lateral ta de boa?"},
    ]

Cada horario vira um segmento proprio DE PROPOSITO: e no horario que o video
e a legenda se encontram, e e por segmento que a pessoa troca quem esta
falando. Um paragrafo inteiro seria grosso demais para corrigir diarizacao.

Na volta, `montar_itens` refaz exatamente o formato de origem: falas seguidas
do mesmo falante voltam a ser um paragrafo so, com os horarios no meio. Assim
o arquivo corrigido continua servindo a todo o resto da casa, e pode ser
reaberto aqui quantas vezes for preciso.

Este arquivo nao tem interface e so usa a biblioteca padrao do Python.
"""

import re

# (0:00), (12:34) ou (1:07:50). O mesmo formato que o conversor preserva.
_HORARIO = re.compile(r"\((\d{1,2}):(\d{2})(?::(\d{2}))?\)")
_COMECA_COM_HORARIO = re.compile(r"^\s*\(\d{1,2}:\d{2}(?::\d{2})?\)")

# Um nome de quem fala e curto. Acima disso e paragrafo de fala sem horario.
_LIMITE_NOME = 60


def segundos(m):
    """Converte o casamento do horario em segundos."""
    a, b, c = m.group(1), m.group(2), m.group(3)
    if c is None:                       # (m:ss)
        return int(a) * 60 + int(b)
    return int(a) * 3600 + int(b) * 60 + int(c)   # (h:mm:ss)


def formatar(t):
    """Segundos de volta ao formato da tela: 18:16 e 1:13:09."""
    t = max(0, int(round(t)))
    h, resto = divmod(t, 3600)
    m, s = divmod(resto, 60)
    if h:
        return "%d:%02d:%02d" % (h, m, s)
    return "%d:%02d" % (m, s)


def ler(paragrafos):
    """Recebe os paragrafos do arquivo e devolve (titulo, data, segmentos).

    Levanta ValueError quando o arquivo nao tem horario nenhum, que e o caso
    em que nao da para sincronizar com video nenhum.
    """
    linhas = [(l or "").replace(" ", " ").strip()
              for l in (paragrafos or [])]

    # Onde a transcricao comeca: a primeira linha com horario. A linha logo
    # antes dela e o primeiro nome de quem fala; o que vier antes e cabecalho.
    inicio = next((i for i, l in enumerate(linhas)
                   if _COMECA_COM_HORARIO.match(l)), -1)
    if inicio < 0:
        raise ValueError(
            "Este arquivo nao tem horarios entre parenteses, como (0:00).\n\n"
            "Use um arquivo gerado pela aba \"Limpar transcricao\": e ele que "
            "guarda os horarios, e sao eles que casam a legenda com o video."
        )

    cabecalho = [l for l in linhas[:max(0, inicio - 1)] if l]
    titulo = cabecalho[0] if cabecalho else ""
    data = cabecalho[1] if len(cabecalho) > 1 else ""

    segmentos = []
    falante = ""
    for linha in linhas[max(0, inicio - 1):]:
        if not linha:
            continue
        if _COMECA_COM_HORARIO.match(linha):
            segmentos.extend(_quebrar(linha, falante))
        elif len(linha) <= _LIMITE_NOME:
            falante = linha
        else:
            # Paragrafo longo sem horario: fala solta. Entra colada na
            # anterior para nao sumir do documento.
            if segmentos:
                segmentos[-1]["x"] = (segmentos[-1]["x"] + " " + linha).strip()

    if not segmentos:
        raise ValueError("Achei os horarios, mas nenhuma fala neste arquivo.")

    falantes = []
    for s in segmentos:
        if s["f"] and s["f"] not in falantes:
            falantes.append(s["f"])

    return titulo, data, segmentos, falantes


def _quebrar(linha, falante):
    """Quebra um paragrafo de fala em um segmento por horario."""
    saida = []
    marcas = list(_HORARIO.finditer(linha))
    for i, m in enumerate(marcas):
        fim = marcas[i + 1].start() if i + 1 < len(marcas) else len(linha)
        texto = linha[m.end():fim].strip()
        if not texto:
            continue
        saida.append({"t": float(segundos(m)), "f": falante, "x": texto})
    return saida


def montar_itens(segmentos, titulo="", data="", deslocamento=0.0):
    """Refaz o formato de origem, pronto para gravar em .docx ou .txt.

    `deslocamento` soma segundos a todos os horarios: e o ajuste fino feito na
    tela quando a legenda estava adiantada ou atrasada em relacao ao video.
    Zero deixa os horarios como estavam.

    Devolve a lista de pares (texto, marca) que `documento.gravar_*` espera.
    """
    itens = []
    atual = None
    pedacos = []

    def fechar():
        if atual is not None and pedacos:
            itens.append((" ".join(pedacos), "fala"))

    for s in segmentos:
        nome = (s.get("f") or "").strip()
        if nome != atual:
            fechar()
            pedacos = []
            if itens:
                itens.append(("", "vazio"))
            itens.append((nome or "Sem identificacao", "nome"))
            atual = nome
        texto = (s.get("x") or "").strip()
        if texto:
            pedacos.append("(%s) %s" % (
                formatar(float(s.get("t") or 0) + deslocamento), texto))
    fechar()
    return itens


def resumo(segmentos):
    """Conta falas e falantes, so para mostrar na tela."""
    falantes = []
    for s in segmentos:
        if s.get("f") and s["f"] not in falantes:
            falantes.append(s["f"])
    fim = max((float(s.get("t") or 0) for s in segmentos), default=0)
    return len(segmentos), falantes, fim
