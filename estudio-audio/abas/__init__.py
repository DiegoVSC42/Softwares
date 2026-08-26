"""As telas do Estudio de Video, uma por arquivo.

Cada modulo daqui expoe `montar(pai)`, que desenha a tela dentro do quadro
recebido e devolve o objeto do aplicativo.

Este arquivo tambem garante que a pasta de cima (onde ficam `tema.py` e
`estudio_video.py`) esteja no caminho de importacao, para que `import tema`
funcione tanto rodando o codigo-fonte quanto dentro do executavel.
"""

import os
import sys

_PASTA_PAI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PASTA_PAI not in sys.path:
    sys.path.insert(0, _PASTA_PAI)
