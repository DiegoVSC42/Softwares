"""Estudio de Video - as quatro ferramentas de video numa janela so.

Cada aba e um modulo dentro de `abas/`, e cada modulo expoe uma funcao
`montar(pai)` que desenha a tela dentro do quadro daquela aba. Nenhum modulo
cria janela propria nem define estilo: a janela e o estilo sao daqui.

As abas sao montadas so quando a pessoa clica nelas pela primeira vez. Isso
faz o programa abrir rapido (a aba de quadros, por exemplo, liga uma thread de
preview e cria pasta temporaria assim que nasce) e isola problema: se uma aba
falhar, as outras tres continuam funcionando.
"""

import os
import sys
import traceback
import tkinter as tk
from tkinter import ttk, messagebox

import tema
import atualizador  # atualizacao automatica

APP_NAME = "Video Studio"
APP_VERSION = "1.5.0"

# Etiqueta de eventos usada para a roda do mouse (ver `_roda`).
ROLA = "RolaEstudio"

# Widgets que ja sabem rolar sozinhos. Quando o ponteiro esta sobre um deles
# e ele tem para onde rolar, a roda e dele; so quando ele ja esta no fim e que
# o giro passa para a pagina.
ROLAM_SOZINHOS = {"Text", "Listbox", "Treeview", "Canvas"}

# Rotulo da aba, modulo, e uma linha explicando para que serve.
ABAS = [
    ("Baixar",          "abas.baixar",
     "Baixar video ou audio de um link"),
    ("Cortar e dividir", "abas.cortar",
     "Tirar um trecho, partir em varias partes ou juntar os pedacos de volta"),
    ("Extrair quadros", "abas.quadros",
     "Tirar fotos de dentro do video, ja recortadas"),
    ("Extrair audio",   "abas.audio",
     "Tirar o audio de varios videos de uma vez"),
]


def resource_path(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


class Estudio:
    def __init__(self, raiz: tk.Tk):
        self.raiz = raiz
        raiz.title(f"{APP_NAME} v{APP_VERSION}")
        # A janela nasce do tamanho que a tela da pessoa permite, ate um teto
        # confortavel. Assim, num monitor grande a tela inteira aparece de uma
        # vez; num notebook pequeno a janela encolhe e a aba rola (ver
        # `_area_rolavel`), em vez de ficar maior que a tela.
        raiz.update_idletasks()
        larg = min(1260, max(900, raiz.winfo_screenwidth() - 120))
        alt = min(1060, max(560, raiz.winfo_screenheight() - 140))
        raiz.geometry(f"{larg}x{alt}")
        raiz.minsize(900, 560)
        raiz.configure(bg=tema.COR_FUNDO)

        tema.aplicar_estilo(raiz)
        self._icone()

        # Guarda o objeto de cada aba ja montada, para avisa-lo no fechamento.
        self.montadas = {}
        # Areas que rolam, por caminho do widget. Preenchido em `_area_rolavel`
        # e consultado por `_roda`.
        self._rolaveis = {}

        # A roda do mouse. Ela e ligada de DOIS jeitos de proposito:
        #
        # 1) numa etiqueta propria (`ROLA`), que e colocada na frente da lista
        #    de etiquetas de cada widget das abas. E o unico jeito garantido:
        #    varios widgets (caixa de texto, lista, tabela) ja tratam a roda
        #    por conta propria, e nesses o evento morria antes de chegar aqui;
        # 2) na etiqueta "all", como rede de seguranca para widget que tenha
        #    nascido depois da ultima marcacao.
        for gesto in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            raiz.bind_class(ROLA, gesto, self._roda)
            raiz.bind_all(gesto, self._roda)

        # Teclado tambem rola, para quem prefere ou para trackpad teimoso.
        for tecla in ("<Prior>", "<Next>", "<Home>", "<End>"):
            raiz.bind_all(tecla, self._tecla_rola)

        # Rodape primeiro, para ficar de fato no fundo da janela: quem e
        # empacotado antes em "bottom" fica mais embaixo.
        rodape = ttk.Frame(raiz)
        rodape.pack(side="bottom", fill="x", padx=14, pady=(0, 8))
        self.lbl_dica = ttk.Label(rodape, text="", style="Apagado.TLabel")
        self.lbl_dica.pack(side="left")
        ttk.Label(rodape, text=f"{APP_NAME} • v{APP_VERSION}",
                  style="Suave.TLabel").pack(side="right")

        self.abas = ttk.Notebook(raiz)
        self.abas.pack(fill="both", expand=True, padx=10, pady=(10, 6))

        self.quadros = []
        for rotulo, modulo, dica in ABAS:
            fora, quadro, ajustar = self._area_rolavel(self.abas)
            self.abas.add(fora, text=f"  {rotulo}  ")
            self.quadros.append({"quadro": quadro, "modulo": modulo,
                                 "rotulo": rotulo, "dica": dica,
                                 "ajustar": ajustar, "pronta": False})

        self.abas.bind("<<NotebookTabChanged>>", self._trocou_de_aba)
        # A primeira aba nao dispara o evento sozinha em todo sistema.
        raiz.after(60, lambda: self._garantir(0))

    # ------------------------------------------------------------- rolagem
    def _area_rolavel(self, pai):
        """Cria uma aba que rola quando o conteudo nao cabe.

        Por que isso e necessario: cada tela veio de um programa que tinha a
        propria janela, desenhada com a fonte pequena do Windows. No Mac a
        fonte base e maior, e a fila de abas mais o rodape ainda comem altura;
        assim, numa janela baixa, o fim de algumas telas simplesmente sumia.
        Com a rolagem, nada mais some: o que nao couber desce.

        Devolve (container, quadro, ajustar): `container` vai para o Notebook,
        `quadro` e onde a tela e desenhada, e `ajustar` refaz a conta. `quadro` e um `tk.Frame` (Tk puro,
        nao ttk) porque as telas chamam `configure(bg=...)` no proprio pai.

        Enquanto o conteudo couber, o quadro recebe a altura inteira da area
        visivel e a barra de rolagem nem aparece -- ou seja, telas que usam
        `side="bottom"` para ancorar botoes continuam funcionando como antes.
        """
        fora = tk.Frame(pai, bg=tema.COR_FUNDO)

        tela = tk.Canvas(fora, bg=tema.COR_FUNDO, highlightthickness=0,
                         bd=0, takefocus=0)
        barra = ttk.Scrollbar(fora, orient="vertical", command=tela.yview)
        tela.configure(yscrollcommand=barra.set)
        tela.pack(side="left", fill="both", expand=True)

        quadro = tk.Frame(tela, bg=tema.COR_FUNDO)
        janela = tela.create_window((0, 0), window=quadro, anchor="nw")

        def ajustar(_evento=None):
            larg = tela.winfo_width()
            alt = tela.winfo_height()
            pedida = quadro.winfo_reqheight()
            # O quadro sempre tem a largura da area visivel; a altura so cresce
            # alem dela quando o conteudo realmente precisa.
            tela.itemconfigure(janela, width=larg,
                               height=max(alt, pedida))
            tela.configure(scrollregion=(0, 0, larg, max(alt, pedida)))

            precisa = pedida > alt + 2
            if precisa and not barra.winfo_ismapped():
                barra.pack(side="right", fill="y")
            elif not precisa and barra.winfo_ismapped():
                barra.pack_forget()
                tela.yview_moveto(0)

        tela.bind("<Configure>", ajustar)
        quadro.bind("<Configure>", ajustar)

        # A roda do mouse e tratada em um lugar so, na janela (ver `_roda`).
        # Este dicionario diz, para cada area rolavel, qual e a sua tela.
        self._rolaveis[str(fora)] = tela

        # `ajustar` precisa ser chamado de fora tambem: depois que a aba
        # recebe o conteudo, o quadro ja esta com altura fixada por
        # `itemconfigure`, entao ganhar filhos NAO dispara <Configure> nele e
        # a medida ficaria congelada no tamanho de quando estava vazio.
        return fora, quadro, ajustar

    def _roda(self, evento):
        """Roda do mouse: rola a area em que o ponteiro esta.

        Por que em um lugar so, e nao em cada aba: a tentativa obvia e ligar a
        roda no <Enter> da aba e desligar no <Leave>. Nao funciona. O Tk manda
        <Leave> no quadro assim que o ponteiro entra em QUALQUER widget filho
        dele -- ou seja, a roda era desligada no instante em que o mouse
        passava por cima do conteudo, que e justamente onde a pessoa rola.

        Aqui a ligacao e permanente, na janela, e a cada giro descobrimos de
        quem e a vez: sobe-se do widget que recebeu o evento ate achar uma das
        areas rolaveis registradas.
        """
        passos = self._passos_da_roda(evento)
        if passos == 0:
            return None

        alvo = self._widget_do_evento(evento)
        if alvo is None:
            return None

        # Se o ponteiro esta sobre algo que rola sozinho (o registro de
        # mensagens, uma lista, a tabela) e esse algo ainda tem para onde ir,
        # a roda e dele. So quando ele chega ao fim e que a pagina anda.
        interno = self._rolavel_proprio(alvo, passos)
        if interno is not None:
            interno.yview_scroll(passos, "units")
            return "break"

        tela = self._tela_da_aba(alvo)
        if tela is None:
            return None
        try:
            inicio, fim = tela.yview()
        except Exception:
            return None
        if inicio <= 0.0 and fim >= 1.0:
            return None          # tudo ja cabe: nao ha o que rolar

        tela.yview_scroll(passos, "units")
        return "break"

    def _widget_do_evento(self, evento):
        """Widget sob o ponteiro, custe o que custar.

        `evento.widget` normalmente resolve, mas em alguns casos vem como
        texto (o caminho do widget) ou aponta para a janela em vez do widget.
        Nesses casos perguntamos ao Tk quem esta debaixo do ponteiro.
        """
        alvo = getattr(evento, "widget", None)
        if isinstance(alvo, str):
            try:
                alvo = self.raiz.nametowidget(alvo)
            except Exception:
                alvo = None
        if alvo is None or alvo is self.raiz:
            try:
                alvo = self.raiz.winfo_containing(evento.x_root, evento.y_root)
            except Exception:
                alvo = None
        return alvo

    def _passos_da_roda(self, evento):
        """Quantas linhas rolar, positivo para baixo.

        Cada sistema manda a roda de um jeito, e nao da para confiar num
        numero fixo: o Linux manda botao 4 e 5 (sem `delta`), o Windows manda
        passos de 120, o Mac manda passos de 1 em algumas versoes do Tk e de
        120 em outras, e o trackpad manda muitos eventos pequenos seguidos.
        Por isso olhamos o SINAL e limitamos o tamanho, em vez de aplicar o
        numero cru -- que, sendo 120, jogaria a pagina inteira de uma vez.
        """
        num = getattr(evento, "num", 0)
        if num == 4:
            return -3
        if num == 5:
            return 3

        delta = getattr(evento, "delta", 0) or 0
        if delta == 0:
            return 0
        if abs(delta) >= 120:            # Windows, e o Mac no Tk mais novo
            linhas = max(1, min(5, int(round(abs(delta) / 120)) * 3))
        else:                            # Mac no Tk classico, e trackpad
            linhas = max(1, min(5, abs(delta)))
        return -linhas if delta > 0 else linhas

    def _tela_da_aba(self, alvo):
        """Sobe a arvore ate achar a area rolavel a que o widget pertence."""
        while alvo is not None:
            tela = self._rolaveis.get(str(alvo))
            if tela is not None:
                return tela
            alvo = getattr(alvo, "master", None)
        return None

    def _rolavel_proprio(self, alvo, passos):
        """Devolve o widget que deve ficar com a roda, se houver um.

        Procura, do ponteiro para cima, uma caixa de texto, lista ou tabela
        que ainda tenha conteudo para o lado em que a pessoa esta girando.
        Devolve None quando nao ha nenhuma -- e a pagina que rola.
        """
        passo = alvo
        while passo is not None:
            if str(passo) in self._rolaveis:
                return None          # chegou na propria pagina
            try:
                classe = passo.winfo_class()
            except Exception:
                return None
            if classe in ROLAM_SOZINHOS:
                try:
                    inicio, fim = passo.yview()
                except Exception:
                    inicio, fim = 0.0, 1.0
                if passos > 0 and fim < 1.0:
                    return passo
                if passos < 0 and inicio > 0.0:
                    return passo
            passo = getattr(passo, "master", None)
        return None

    def _tecla_rola(self, evento):
        """Page Up, Page Down, Home e End rolam a aba que esta na tela."""
        alvo = self._widget_do_evento(evento)
        tela = self._tela_da_aba(alvo) if alvo is not None else None
        if tela is None:
            try:
                i = self.abas.index(self.abas.select())
                tela = self._rolaveis.get(str(self.abas.winfo_children()[i]))
            except Exception:
                return None
        if tela is None:
            return None
        tecla = getattr(evento, "keysym", "")
        if tecla == "Prior":
            tela.yview_scroll(-1, "pages")
        elif tecla == "Next":
            tela.yview_scroll(1, "pages")
        elif tecla == "Home":
            tela.yview_moveto(0.0)
        elif tecla == "End":
            tela.yview_moveto(1.0)
        return None

    def _marcar_rolagem(self, w, prof=0):
        """Poe a etiqueta da roda na frente da lista de etiquetas do widget.

        Sem isto, um widget que trata a roda por conta propria (caixa de
        texto, lista, tabela) consome o evento e a pagina nao anda. Com a
        etiqueta na frente, o giro passa primeiro por `_roda`, que decide de
        quem e a vez.
        """
        try:
            etiquetas = list(w.bindtags())
            if ROLA not in etiquetas:
                w.bindtags(tuple([ROLA] + etiquetas))
        except Exception:
            pass
        if prof > 12:
            return
        try:
            filhos = w.winfo_children()
        except Exception:
            return
        for f in filhos:
            self._marcar_rolagem(f, prof + 1)

    # ------------------------------------------------------------------ icone
    def _icone(self):
        try:
            caminho = resource_path("icon.png")
            if os.path.isfile(caminho):
                self._img_icone = tk.PhotoImage(file=caminho)
                self.raiz.iconphoto(True, self._img_icone)
        except Exception:
            pass

    # ------------------------------------------------------------------- abas
    def _trocou_de_aba(self, _evento=None):
        try:
            i = self.abas.index(self.abas.select())
        except Exception:
            return
        self._garantir(i)
        self.lbl_dica.config(text=self.quadros[i]["dica"])
        # Remede a aba que acabou de aparecer: enquanto ela estava escondida,
        # o Tk devolve tamanhos que nao valem nada. E remarca a roda, porque
        # a tela pode ter criado widgets novos desde a ultima passagem (uma
        # linha na lista, um campo que so aparece em certo formato).
        self.raiz.after(40, lambda: self._remedir(i))
        self.raiz.after(60, lambda: self._marcar_rolagem(self.quadros[i]["quadro"]))

    def _garantir(self, i: int):
        """Monta a aba `i` se ainda nao estiver montada."""
        info = self.quadros[i]
        if info["pronta"]:
            return
        info["pronta"] = True

        quadro = info["quadro"]
        aviso = ttk.Label(quadro, text="Preparando...", style="Suave.TLabel")
        aviso.pack(pady=30)
        quadro.update_idletasks()

        try:
            modulo = __import__(info["modulo"], fromlist=["montar"])
            aviso.destroy()
            app = modulo.montar(quadro)
            if app is not None:
                self.montadas[info["rotulo"]] = app
        except Exception:
            aviso.destroy()
            self._mostrar_falha(quadro, info["rotulo"], traceback.format_exc())

        # Agora que a aba tem conteudo, refaz a conta da rolagem e poe a
        # etiqueta da roda em cada widget recem-criado.
        self._marcar_rolagem(quadro)
        self._remedir(i)
        self.raiz.after(120, lambda: (self._remedir(i),
                                      self._marcar_rolagem(quadro)))

    def _remedir(self, i: int):
        """Refaz a conta de altura da aba `i` (mostra ou esconde a barra)."""
        try:
            self.quadros[i]["ajustar"]()
        except Exception:
            pass

    def _mostrar_falha(self, quadro, rotulo, detalhe):
        caixa = ttk.Frame(quadro)
        caixa.pack(fill="both", expand=True, padx=20, pady=20)
        ttk.Label(caixa, text=f"A aba \"{rotulo}\" nao pode ser aberta.",
                  style="Erro.TLabel").pack(anchor="w")
        ttk.Label(caixa, text="As outras abas continuam funcionando "
                              "normalmente.",
                  style="Suave.TLabel").pack(anchor="w", pady=(4, 10))
        texto = tk.Text(caixa, height=14, bg=tema.COR_CAMPO,
                        fg=tema.COR_SUAVE, insertbackground=tema.COR_TEXTO,
                        selectbackground=tema.COR_DESTAQUE,
                        highlightbackground=tema.COR_BORDA, relief="flat",
                        wrap="word")
        texto.pack(fill="both", expand=True)
        texto.insert("1.0", detalhe)
        texto.configure(state="disabled")

    # -------------------------------------------------------------- fechamento
    def ao_fechar(self):
        rodando = []
        for rotulo, app in self.montadas.items():
            if getattr(app, "rodando", False):
                rodando.append(rotulo)

        if rodando:
            lista = ", ".join(rodando)
            if not messagebox.askyesno(
                    "Ainda tem trabalho em andamento",
                    f"A aba {lista} ainda esta trabalhando.\n\n"
                    "Fechar agora interrompe o que esta em andamento. "
                    "Quer fechar mesmo assim?",
                    parent=self.raiz):
                return

        for app in self.montadas.values():
            for nome in ("ao_fechar", "encerrar", "parar"):
                metodo = getattr(app, nome, None)
                if callable(metodo):
                    try:
                        metodo()
                    except Exception:
                        pass
                    break
        try:
            self.raiz.destroy()
        except Exception:
            pass


def main():
    # Faz a pasta do programa entrar no caminho de importacao, para que
    # `abas.*` seja encontrado tanto rodando o .py quanto dentro do executavel.
    pasta = os.path.dirname(os.path.abspath(__file__))
    if pasta not in sys.path:
        sys.path.insert(0, pasta)

    raiz = tk.Tk()
    app = Estudio(raiz)
    raiz.protocol("WM_DELETE_WINDOW", app.ao_fechar)
    # Confere, em segundo plano, se saiu versao nova publicada. Se saiu,
    # pergunta se a pessoa quer atualizar. Qualquer falha e ignorada em
    # silencio, e rodando pelo codigo-fonte ele nao faz nada.
    atualizador.iniciar(raiz, "estudio-video", APP_VERSION, "Video Studio")
    raiz.mainloop()


if __name__ == "__main__":
    main()
