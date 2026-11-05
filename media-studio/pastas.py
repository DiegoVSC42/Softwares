"""Pastas padrao do Estudio de Video.

Regra da casa: TODA aba salva, por padrao, na pasta de Downloads do usuario.
A pessoa pode trocar em cada aba, mas o ponto de partida e sempre o mesmo,
para ninguem ficar procurando onde o arquivo foi parar.
"""

import os
import sys
from pathlib import Path


def pasta_downloads() -> str:
    """Caminho da pasta de Downloads do usuario, com plano B.

    No Windows a pasta pode ter sido movida pelo dono da maquina, e o nome
    muda com o idioma do sistema; por isso perguntamos ao proprio Windows
    antes de chutar. Se nada der certo, cai na pasta pessoal, que sempre
    existe.
    """
    if os.name == "nt":
        try:
            import winreg
            chave = (r"SOFTWARE\Microsoft\Windows\CurrentVersion"
                     r"\Explorer\Shell Folders")
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, chave) as k:
                # Identificador da pasta Downloads no registro do Windows.
                caminho, _ = winreg.QueryValueEx(
                    k, "{374DE290-123F-4565-9164-39C4925E467B}")
            if caminho and os.path.isdir(caminho):
                return caminho
        except Exception:
            pass

    casa = Path.home()
    for nome in ("Downloads", "Transferencias", "Transferências"):
        cand = casa / nome
        if cand.is_dir():
            return str(cand)

    # Nao existe ainda: cria a pasta em ingles, que e o nome que os dois
    # sistemas usam por baixo.
    try:
        alvo = casa / "Downloads"
        alvo.mkdir(parents=True, exist_ok=True)
        return str(alvo)
    except Exception:
        return str(casa)


def garantir(pasta: str) -> str:
    """Cria a pasta se ela nao existir e devolve o caminho.

    Se nao der para criar (disco cheio, permissao), devolve a de Downloads,
    para o programa nunca ficar sem lugar para gravar.
    """
    try:
        os.makedirs(pasta, exist_ok=True)
        return pasta
    except Exception:
        return pasta_downloads()


if __name__ == "__main__":
    print(pasta_downloads())
    sys.exit(0)
