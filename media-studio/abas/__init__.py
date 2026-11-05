"""As telas do Media Studio, organizadas por familia: video/, audio/,
imagem/, transcricao/ e web/.

Este arquivo garante que a pasta de cima (onde ficam `tema.py`,
`pastas.py` e `media_studio.py`) esteja no caminho de importacao, para que
`import tema` funcione tanto rodando o codigo-fonte quanto dentro do
executavel.
"""

import os
import sys

_PASTA_PAI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PASTA_PAI not in sys.path:
    sys.path.insert(0, _PASTA_PAI)
