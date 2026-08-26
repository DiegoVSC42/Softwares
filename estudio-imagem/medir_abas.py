"""Confere se as abas cabem na tela sem precisar rolar.

Nao faz parte do programa: e uma ferramenta de conferencia, para rodar depois
de mexer no layout de qualquer aba.

Ele abre o Estudio de Imagem num monitor de mentira, forca a fonte do Mac (13pt, que e
maior que a do Windows e por isso o caso mais apertado) e mede, aba por aba,
quanto o conteudo pede e quanto cabe.

Como rodar (no sandbox Linux):

    xvfb-run -a --server-args="-screen 0 1512x982x24" \
        uv run --python 3.12 --with certifi python medir_abas.py

Sai com codigo 1 se alguma aba nao couber, para dar para usar em conferencia
automatica.
"""

import sys
import time
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tema
# Forca a fonte do Mac: e a maior, e portanto o pior caso de altura.
tema.fontes = lambda: (("Helvetica", 13), ("Helvetica", 11))

import tkinter as tk
import estudio_imagem

# Folga que exigimos de sobra, para o layout nao ficar no limite.
FOLGA = 12


def main():
    raiz = tk.Tk()
    app = estudio_imagem.Estudio(raiz)
    raiz.geometry("1260x842")

    def bombear(n=45):
        for _ in range(n):
            raiz.update()
            time.sleep(0.03)

    bombear(60)

    apertadas = []
    print(f"{'Aba':18s} {'pede':>6s} {'cabe':>6s}   situacao")
    print("-" * 56)
    for i, (rotulo, _, _) in enumerate(estudio_imagem.ABAS):
        app.abas.select(i)
        bombear(70)
        quadro = app.quadros[i]["quadro"]
        fora = app.abas.winfo_children()[i]
        tela = [f for f in fora.winfo_children()
                if f.winfo_class() == "Canvas"][0]
        pede = quadro.winfo_reqheight()
        cabe = tela.winfo_height()
        sobra = cabe - pede
        if sobra >= FOLGA:
            situacao = f"cabe, com {sobra}px de sobra"
        else:
            situacao = f"NAO CABE: faltam {FOLGA - sobra}px"
            apertadas.append((rotulo, FOLGA - sobra))
        print(f"{rotulo:18s} {pede:6d} {cabe:6d}   {situacao}")

    print()
    if apertadas:
        print("Ainda precisam encolher:")
        for rotulo, falta in apertadas:
            print(f"  - {rotulo}: {falta}px")
    else:
        print("Todas as abas cabem inteiras, sem precisar rolar.")

    try:
        app.ao_fechar()
    except Exception:
        pass
    return 1 if apertadas else 0


if __name__ == "__main__":
    sys.exit(main())
