#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
motor_comparacao.py
===================

Motor de COMPARAÇÃO entre duas pastas raiz (ex.: um Drive de origem x um NAS de
destino), para conferir se a cópia está completa e correta SEM alterar nenhum
arquivo.

A comparação é feita por:
  - caminho relativo à raiz  (a estrutura de pastas deve ser idêntica)
  - existência em cada lado
  - tamanho em bytes
  - data de modificação (com tolerância configurável)
  - (opcional) hash do conteúdo, para garantir igualdade byte a byte

Este módulo é SOMENTE LEITURA: nunca cria, move, renomeia ou apaga arquivos.
Ele apenas devolve a estrutura de dados da comparação, que é usada pela
interface (app.py) e pelo gerador de relatórios (relatorio.py).
"""

import datetime as dt
import hashlib
import os
import sys


# --------------------------------------------------------------------------- #
# Coleta de arquivos
# --------------------------------------------------------------------------- #
class Cancelado(Exception):
    """Levantada quando o usuário cancela a operação."""


def coletar_arquivos(raiz, rotulo="", progresso_scan=None, deve_cancelar=None):
    """
    Percorre a árvore de 'raiz' e devolve um dicionário:
        { caminho_relativo : {"tamanho": int, "mtime": float, "abs": str} }

    O caminho relativo usa '/' como separador para ficar igual nos dois lados,
    independentemente do sistema operacional.
    """
    raiz = os.path.abspath(raiz)
    arquivos = {}
    erros = []
    qtd = 0

    for pasta_atual, _subpastas, nomes in os.walk(raiz):
        for nome in nomes:
            if deve_cancelar is not None and deve_cancelar():
                raise Cancelado()
            caminho_abs = os.path.join(pasta_atual, nome)
            try:
                st = os.stat(caminho_abs)
            except OSError as e:
                erros.append((caminho_abs, str(e)))
                continue
            rel = os.path.relpath(caminho_abs, raiz).replace(os.sep, "/")
            arquivos[rel] = {
                "tamanho": st.st_size,
                "mtime": st.st_mtime,
                "abs": caminho_abs,
            }
            qtd += 1
            if progresso_scan is not None and qtd % 100 == 0:
                progresso_scan(rotulo, qtd)
    if progresso_scan is not None:
        progresso_scan(rotulo, qtd)
    return arquivos, erros


def calcular_hash(caminho, algoritmo="sha256", bloco=1024 * 1024):
    """Calcula o hash do conteúdo de um arquivo, lendo em blocos."""
    h = hashlib.new(algoritmo)
    with open(caminho, "rb") as f:
        for pedaco in iter(lambda: f.read(bloco), b""):
            h.update(pedaco)
    return h.hexdigest()


def formatar_tamanho(n):
    """Formata bytes de forma legível (KB, MB, GB...)."""
    unidades = ["B", "KB", "MB", "GB", "TB", "PB"]
    valor = float(n)
    for u in unidades:
        if valor < 1024 or u == unidades[-1]:
            return f"{valor:.0f} {u}" if u == "B" else f"{valor:.2f} {u}"
        valor /= 1024


def formatar_data(mtime):
    return dt.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")


def subpasta_principal(rel):
    """Devolve a primeira pasta do caminho relativo, usada para filtragem.

    Ex.: 'Vídeos/Depoimentos/.../foto.jpg' -> 'Vídeos'.
    Arquivos na raiz (sem '/') retornam '(raiz)'.
    """
    rel = (rel or "").replace("\\", "/").strip("/")
    if "/" in rel:
        return rel.split("/", 1)[0]
    return "(raiz)"


def separar_data_hora(texto):
    """Separa 'AAAA-MM-DD HH:MM:SS' em (data, hora). Vazio -> ('', '')."""
    if not texto:
        return "", ""
    partes = texto.split(" ", 1)
    if len(partes) == 2:
        return partes[0], partes[1]
    return texto, ""


# --------------------------------------------------------------------------- #
# Comparação
# --------------------------------------------------------------------------- #
# Categorias possíveis de cada item:
#   OK                  -> igual nos dois lados (tamanho e, se pedido, hash)
#   FALTANDO            -> existe na origem, não existe no destino  (CRÍTICO)
#   EXTRA               -> existe no destino, não existe na origem
#   TAMANHO_DIFERENTE   -> existe nos dois, tamanhos diferentes      (CRÍTICO)
#   HASH_DIFERENTE      -> mesmo tamanho, conteúdo diferente         (CRÍTICO)
#   DATA_DIFERENTE      -> conteúdo igual, data de modificação difere (AVISO)

CRITICAS = {"FALTANDO", "TAMANHO_DIFERENTE", "HASH_DIFERENTE"}

CORES = {
    "OK": "#1a7f37",
    "FALTANDO": "#cf222e",
    "TAMANHO_DIFERENTE": "#cf222e",
    "HASH_DIFERENTE": "#cf222e",
    "EXTRA": "#9a6700",
    "DATA_DIFERENTE": "#9a6700",
    "ERRO_LEITURA": "#cf222e",
}

ROTULOS = {
    "OK": "OK (confere)",
    "FALTANDO": "Faltando no destino",
    "TAMANHO_DIFERENTE": "Tamanho diferente",
    "HASH_DIFERENTE": "Conteúdo diferente (hash)",
    "EXTRA": "Sobrando no destino",
    "DATA_DIFERENTE": "Data diferente",
    "ERRO_LEITURA": "Erro de leitura",
}


def comparar(origem, destino, usar_hash=False, tolerancia=2.0, progresso=None,
             progresso_scan=None, deve_cancelar=None, considerar_data=False):
    """
    progresso: callback opcional progresso(i, total) durante a comparação.
    progresso_scan: callback opcional progresso_scan(rotulo, qtd) durante a
        leitura das pastas (fase anterior à comparação).
    deve_cancelar: callable que retorna True para interromper. Quando isso
        acontece, levanta a exceção Cancelado.
    considerar_data: se True, marca como DATA_DIFERENTE arquivos com conteúdo
        igual mas data de modificação diferente. PADRÃO False, porque a data
        normalmente muda numa cópia e não é um parâmetro confiável de erro.
    """
    arq_origem, erros_o = coletar_arquivos(
        origem, "origem", progresso_scan, deve_cancelar)
    arq_destino, erros_d = coletar_arquivos(
        destino, "destino", progresso_scan, deve_cancelar)

    todos = sorted(set(arq_origem) | set(arq_destino))
    linhas = []

    total = len(todos)
    for i, rel in enumerate(todos, 1):
        if deve_cancelar is not None and deve_cancelar():
            raise Cancelado()
        if progresso is not None:
            progresso(i, total)
        if total > 200 and i % 200 == 0:
            print(f"  ... comparando {i}/{total}", file=sys.stderr)

        o = arq_origem.get(rel)
        d = arq_destino.get(rel)

        linha = {
            "caminho": rel,
            "status": "",
            "detalhe": "",
            "tam_origem": o["tamanho"] if o else "",
            "tam_destino": d["tamanho"] if d else "",
            "data_origem": formatar_data(o["mtime"]) if o else "",
            "data_destino": formatar_data(d["mtime"]) if d else "",
            "abs_origem": o["abs"] if o else "",
            "abs_destino": d["abs"] if d else "",
            "presenca": "Origem + Destino" if (o and d)
                        else ("Só origem" if o else "Só destino"),
        }

        if o and not d:
            linha["status"] = "FALTANDO"
            linha["detalhe"] = "Existe na origem, não foi encontrado no destino."
        elif d and not o:
            linha["status"] = "EXTRA"
            linha["detalhe"] = "Existe no destino, mas não existe na origem."
        else:
            # existe nos dois lados
            if o["tamanho"] != d["tamanho"]:
                linha["status"] = "TAMANHO_DIFERENTE"
                linha["detalhe"] = (
                    f"Tamanhos diferentes: origem {formatar_tamanho(o['tamanho'])} "
                    f"x destino {formatar_tamanho(d['tamanho'])}."
                )
            elif usar_hash:
                try:
                    ho = calcular_hash(o["abs"])
                    hd = calcular_hash(d["abs"])
                except OSError as e:
                    linha["status"] = "ERRO_LEITURA"
                    linha["detalhe"] = f"Não foi possível ler para hash: {e}"
                    linhas.append(linha)
                    continue
                if ho != hd:
                    linha["status"] = "HASH_DIFERENTE"
                    linha["detalhe"] = "Mesmo tamanho, mas conteúdo diferente (hash)."
                else:
                    linha = _avaliar_data(linha, o, d, tolerancia, considerar_data,
                                          conferido_hash=True)
            else:
                linha = _avaliar_data(linha, o, d, tolerancia, considerar_data)

        linhas.append(linha)

    return {
        "linhas": linhas,
        "erros": erros_o + erros_d,
        "qtd_origem": len(arq_origem),
        "qtd_destino": len(arq_destino),
        "origem": os.path.abspath(origem),
        "destino": os.path.abspath(destino),
        "usar_hash": usar_hash,
        "tolerancia": tolerancia,
        "considerar_data": considerar_data,
    }


def _avaliar_data(linha, o, d, tolerancia, considerar_data=False,
                  conferido_hash=False):
    """
    Para arquivos que batem em tamanho (e em hash, se conferido), decide entre
    OK e DATA_DIFERENTE. A data só vira problema quando considerar_data=True;
    caso contrário fica apenas como informação na coluna de datas.
    """
    base = "Arquivo confere (tamanho" + (" e conteúdo)" if conferido_hash else ")") + "."
    if considerar_data and abs(o["mtime"] - d["mtime"]) > tolerancia:
        linha["status"] = "DATA_DIFERENTE"
        linha["detalhe"] = (
            "Conteúdo igual, mas a data de modificação difere além da tolerância."
        )
    else:
        linha["status"] = "OK"
        linha["detalhe"] = base
    return linha


def resumo(linhas):
    contagem = {}
    for l in linhas:
        contagem[l["status"]] = contagem.get(l["status"], 0) + 1
    return contagem


def contar_criticos(linhas):
    cont = resumo(linhas)
    return sum(cont.get(c, 0) for c in CRITICAS)
