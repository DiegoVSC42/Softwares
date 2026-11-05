"""Abas de video do Media Studio.

Garante que a RAIZ do projeto (onde ficam `tema.py`, `pastas.py` e
`compartilhado/`) esteja no caminho de importacao. Como este pacote fica
dois niveis abaixo da raiz (abas/video/), sobe dois niveis.
"""

import os
import sys

_PASTA_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PASTA_RAIZ not in sys.path:
    sys.path.insert(0, _PASTA_RAIZ)
