#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
motor_copia.py
==============

Motor de CÓPIA dos arquivos faltantes da pasta de ORIGEM para a de DESTINO.
Copia apenas o que ainda não existe no destino. A comparação é por NOME +
TAMANHO.

Garantias de segurança:
  - A ORIGEM é apenas LIDA. Nada é alterado, movido ou apagado lá.
  - Por padrão NADA é sobrescrito no destino. Só são gravados arquivos novos.
  - Arquivos que existem no destino com tamanho diferente NÃO são tocados;
    apenas ficam registrados (a menos que a opção de recopiar divergentes seja
    marcada, que é opt-in e fica desligada por padrão).
  - Nomes ilegais para Windows/NAS (com / : * ? " < > | etc.) são saneados
    automaticamente ao gravar no destino, sem mexer no nome da origem.
"""

import os
import shutil
import unicodedata


ILLEGAL_CHARS = '<>:"/\\|?*'
RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def sanitize_component(name):
    """Torna UM componente de caminho (pasta ou arquivo) válido no Windows/NAS."""
    # Categorias Unicode invisiveis/problematicas: Cc=controle, Cf=formatacao
    # (zero-width, BOM), Co=uso privado (icones de fonte colados sem querer),
    # Cs=substituto isolado. Tudo isso passa despercebido ao olho mas quebra o
    # Windows/NAS ao criar a pasta/arquivo (WinError 87 com caminho \\?\).
    INVISIBLE_CATEGORIES = {"Cc", "Cf", "Co", "Cs"}
    chars = []
    for ch in name:
        if ch in ILLEGAL_CHARS or unicodedata.category(ch) in INVISIBLE_CATEGORIES:
            chars.append("_")
        else:
            chars.append(ch)
    safe = "".join(chars).strip(" .")  # Windows não aceita espaço/ponto no início/fim
    if not safe:
        safe = "_"
    stem = safe.split(".")[0].upper()
    if stem in RESERVED:
        safe = "_" + safe
    return safe


def sanitize_relpath(relpath):
    """Aplica o saneamento a cada parte de um caminho relativo."""
    parts = [p for p in relpath.replace("\\", "/").split("/") if p != ""]
    return os.path.join(*[sanitize_component(p) for p in parts]) if parts else ""


def long_path(path):
    r"""Prefixo \\?\ para suportar caminhos > 260 caracteres no Windows."""
    if os.name != "nt":
        return path
    p = os.path.abspath(path)
    if p.startswith("\\\\?\\"):
        return p
    if p.startswith("\\\\"):  # caminho de rede UNC: \\servidor\share
        return "\\\\?\\UNC\\" + p[2:]
    return "\\\\?\\" + p


def _size(path):
    try:
        return os.path.getsize(long_path(path))
    except OSError:
        return None


class Cancelado(Exception):
    """Levantada quando o usuário cancela a operação."""


def build_plan(origem, destino, overwrite_diff=False, progress_cb=None,
               deve_cancelar=None):
    """
    Varre a origem e decide o que fazer.

    Retorna (acoes, ignorados):
      acoes     -> lista de dicts {src, dst, rel, dst_rel, size, motivo}
      ignorados -> lista de dicts {rel, motivo}
    """
    acoes, ignorados = [], []
    for root, _dirs, files in os.walk(origem):
        for fname in files:
            if deve_cancelar is not None and deve_cancelar():
                raise Cancelado()
            src = os.path.join(root, fname)
            rel = os.path.relpath(src, origem)
            dst_rel = sanitize_relpath(rel)
            dst = os.path.join(destino, dst_rel)

            if progress_cb:
                progress_cb(rel)

            src_size = _size(src)
            if src_size is None:
                ignorados.append({"rel": rel, "motivo": "erro ao ler arquivo na origem"})
                continue

            saneado = (os.path.normpath(dst_rel) != os.path.normpath(rel))

            if os.path.exists(long_path(dst)):
                dst_size = _size(dst)
                if dst_size == src_size:
                    continue  # já existe idêntico em nome+tamanho -> nada a fazer
                if overwrite_diff:
                    acoes.append({
                        "src": src, "dst": dst, "rel": rel, "dst_rel": dst_rel,
                        "size": src_size,
                        "motivo": f"tamanho difere (destino={dst_size}, origem={src_size}) -> sobrescrever",
                    })
                else:
                    ignorados.append({
                        "rel": rel,
                        "motivo": f"existe no destino com tamanho diferente "
                                  f"(destino={dst_size}, origem={src_size}) -> NÃO copiado",
                    })
                continue

            motivo = "novo"
            if saneado:
                motivo = f"novo (nome saneado -> {dst_rel})"
            acoes.append({
                "src": src, "dst": dst, "rel": rel, "dst_rel": dst_rel,
                "size": src_size, "motivo": motivo,
            })
    return acoes, ignorados


def acoes_da_comparacao(dados, overwrite_diff=False):
    """
    Deriva a lista de cópia A PARTIR do resultado da comparação
    (motor_comparacao.comparar), SEM varrer as pastas de novo.

    A comparação já leu as duas árvores e sabe o tamanho de cada arquivo. Aqui
    só decidimos, item a item, o que copiar:
      - OK / DATA_DIFERENTE  -> já existe no destino com mesmo tamanho: pula.
      - EXTRA / ERRO_LEITURA -> não é candidato (não existe na origem): pula.
      - TAMANHO_DIFERENTE    -> existe nos dois com tamanhos diferentes:
                                copia (sobrescreve) só se overwrite_diff; senão
                                fica como ignorado.
      - FALTANDO             -> existe na origem e não no destino: copia (novo).
                                Quando o nome precisa ser saneado, faz um stat
                                pontual no destino saneado para não duplicar.

    Retorna (acoes, ignorados) no mesmo formato de build_plan.
    """
    destino = dados["destino"]
    acoes, ignorados = [], []

    for l in dados["linhas"]:
        status = l["status"]
        rel = l["caminho"]
        src = l.get("abs_origem")

        if status in ("OK", "DATA_DIFERENTE", "EXTRA", "ERRO_LEITURA"):
            continue
        if not src:
            continue

        try:
            src_size = int(l["tam_origem"])
        except (ValueError, TypeError):
            src_size = _size(src)

        if status == "TAMANHO_DIFERENTE":
            # mesmo caminho relativo nos dois lados (nome legal)
            dst = os.path.join(destino, rel)
            try:
                dst_size = int(l["tam_destino"])
            except (ValueError, TypeError):
                dst_size = _size(dst)
            if overwrite_diff:
                acoes.append({
                    "src": src, "dst": dst, "rel": rel, "dst_rel": rel,
                    "size": src_size,
                    "motivo": f"tamanho difere (destino={dst_size}, origem={src_size}) -> sobrescrever",
                })
            else:
                ignorados.append({
                    "rel": rel,
                    "motivo": f"existe no destino com tamanho diferente "
                              f"(destino={dst_size}, origem={src_size}) -> NÃO copiado",
                })
            continue

        # status == "FALTANDO"
        dst_rel = sanitize_relpath(rel)
        dst = os.path.join(destino, dst_rel)
        saneado = (os.path.normpath(dst_rel) != os.path.normpath(rel))

        if saneado and os.path.exists(long_path(dst)):
            # o nome saneado pode já existir de uma cópia anterior
            dst_size = _size(dst)
            if dst_size == src_size:
                continue
            if overwrite_diff:
                acoes.append({
                    "src": src, "dst": dst, "rel": rel, "dst_rel": dst_rel,
                    "size": src_size,
                    "motivo": f"tamanho difere (destino={dst_size}, origem={src_size}) -> sobrescrever",
                })
            else:
                ignorados.append({
                    "rel": rel,
                    "motivo": f"existe no destino (nome saneado) com tamanho diferente "
                              f"(destino={dst_size}, origem={src_size}) -> NÃO copiado",
                })
            continue

        motivo = "novo" if not saneado else f"novo (nome saneado -> {dst_rel})"
        acoes.append({
            "src": src, "dst": dst, "rel": rel, "dst_rel": dst_rel,
            "size": src_size, "motivo": motivo,
        })

    return acoes, ignorados


def copy_one(action):
    """Copia um arquivo preservando data/metadados. Lê a origem, nunca a altera."""
    dst = action["dst"]
    os.makedirs(os.path.dirname(long_path(dst)), exist_ok=True)
    shutil.copy2(long_path(action["src"]), long_path(dst))


def copy_one_progress(action, callback=None, deve_cancelar=None,
                      bloco=4 * 1024 * 1024):
    """
    Copia UM arquivo em blocos, chamando callback(bytes_copiados_deste_arquivo)
    a cada bloco — assim dá para mostrar progresso DENTRO de um arquivo grande.

    Preserva data/metadados (como copy2). Lê a origem, nunca a altera.
    Se deve_cancelar() virar True no meio, apaga o arquivo parcial e levanta
    Cancelado.
    """
    src = long_path(action["src"])
    dst = long_path(action["dst"])
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    copiado = 0
    try:
        with open(src, "rb") as fi, open(dst, "wb") as fo:
            while True:
                if deve_cancelar is not None and deve_cancelar():
                    raise Cancelado()
                pedaco = fi.read(bloco)
                if not pedaco:
                    break
                fo.write(pedaco)
                copiado += len(pedaco)
                if callback is not None:
                    callback(copiado)
    except BaseException:
        # erro/cancelamento DURANTE os dados: remove o parcial para nao deixar lixo
        try:
            os.remove(dst)
        except OSError:
            pass
        raise
    # Os dados ja estao 100% copiados. Copiar data/permissoes e secundario:
    # alguns destinos (NAS, exFAT, nomes com caracteres especiais) recusam o
    # carimbo de data e levantam [Errno 22]. Nesse caso NAO falhamos o arquivo —
    # ele ja foi copiado corretamente; so ignoramos os metadados.
    try:
        shutil.copystat(src, dst)
    except OSError:
        pass


def human(n):
    if n is None:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"
