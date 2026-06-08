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


ILLEGAL_CHARS = '<>:"/\\|?*'
RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def sanitize_component(name):
    """Torna UM componente de caminho (pasta ou arquivo) válido no Windows/NAS."""
    chars = []
    for ch in name:
        if ch in ILLEGAL_CHARS or ord(ch) < 32:
            chars.append("_")
        else:
            chars.append(ch)
    safe = "".join(chars).rstrip(" .")  # Windows não aceita espaço/ponto no fim
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


def copy_one(action):
    """Copia um arquivo preservando data/metadados. Lê a origem, nunca a altera."""
    dst = action["dst"]
    os.makedirs(os.path.dirname(long_path(dst)), exist_ok=True)
    shutil.copy2(long_path(action["src"]), long_path(dst))


def human(n):
    if n is None:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"
