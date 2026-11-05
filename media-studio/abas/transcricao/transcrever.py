"""Aba "Transcrever" do Media Studio: audio ou video em texto, sem internet.

Usa o Whisper rodando no proprio computador. A internet so entra uma vez, no
botao "Preparar", que instala o motor e baixa o modelo (~2 GB). Dali em
diante, tudo acontece aqui dentro: nada do audio sai da maquina.

O resultado sai no MESMO formato da aba "Limpar transcricao":

    Nome do arquivo
    19 de out. de 2026, 08:41

    Palestrante 1
    (0:00) Bom dia. (0:06) Claro, o programa atende...

ou seja, a aba Sincronizar abre direto, para conferir ouvindo e dizer quem
fala em cada trecho (o Whisper escreve o que foi dito, mas nao sabe quem
disse).

Com "Separar quem fala" marcado, um segundo motor, tambem sem internet,
reconhece as vozes, descobre sozinho quantas pessoas sao, e cada trecho sai
com "Palestrante 1", "Palestrante 2"... na ordem em que cada pessoa aparece.
Assim que um arquivo fica pronto, a caixa "Quem e quem" mostra um campo de
nome para cada pessoa, com o que ela disse primeiro para ajudar a reconhecer;
os nomes escritos ali regravam o .docx, o .txt e o .srt daquele arquivo.

O trabalho pesado fica em `transcritor.py` (sem interface) e no
`trabalhador_whisper.py`, que roda num processo a parte. Esta aba so
desenha a tela e conversa com eles por uma fila de recados.

O layout e empilhado, como o das outras abas de transcricao, porque a janela
desta categoria vive estreita, encostada no canto da tela.
"""

import os
import queue
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from tkinter import (StringVar, BooleanVar, END, ttk, filedialog, messagebox,
                     Listbox, Text, SINGLE)

import pastas
import tema
import transcritor
from compartilhado import legenda
from documento import gravar_paragrafos, gravar_texto

APP_NOME = "Media Studio"

TIPOS = [
    ("Áudio e vídeo",
     "*.mp3 *.m4a *.wav *.aac *.ogg *.opus *.flac *.wma *.aif *.aiff "
     "*.mp4 *.mov *.m4v *.mkv *.webm *.avi *.mpg *.mpeg *.3gp"),
    ("Todos os arquivos", "*.*"),
]


class AbaTranscrever:

    def __init__(self, pai):
        self.pai = pai
        self.raiz = pai.winfo_toplevel()

        # Cada item da fila: {"caminho", "nome"}.
        self.fila = []
        self.rodando = False
        self.preparado = False
        self.separador_pronto = False
        # Arquivos ja prontos com quem fala separado, cada um com as suas
        # pessoas e os seus nomes (ver `_novo_resultado`).
        self.resultados = []
        self.res_atual = None
        self.vars_nomes = {}
        self.execucao = None
        self.recados = queue.Queue()

        self.fonte_base, self.fonte_peq, self.fonte_mini = tema.fontes()

        self.var_saida = StringVar(value=pastas.pasta_downloads())
        self.var_docx = BooleanVar(value=True)
        self.var_txt = BooleanVar(value=True)
        self.var_srt = BooleanVar(value=False)
        self.var_idioma = StringVar(value=transcritor.IDIOMAS[0][0])
        self.var_prompt = StringVar()
        self.var_separar = BooleanVar(value=False)
        self.var_arquivo = StringVar()
        self.var_motor = StringVar(value="Conferindo o motor de transcrição...")
        self.var_status = StringVar(
            value="Adicione áudios ou vídeos e clique em Transcrever tudo.")

        self._montar()
        self.raiz.after(120, self._ler_recados)
        threading.Thread(target=self._conferir_motor, daemon=True).start()

    # ------------------------------------------------------------- interface

    def _montar(self):
        # Tudo empilhado e enxuto: com a janela na altura de um notebook, o
        # botao de transcrever e o texto saindo precisam caber sem rolar,
        # porque e para eles que a pessoa olha enquanto espera.
        # ---- motor: uma linha verde quando pronto; explicacao e botao
        # quando ainda falta preparar. (Nao ha titulo: o rodape da janela ja
        # diz o que a aba faz, e cada linha aqui em cima empurra o texto
        # saindo para fora da tela.)
        self.caixa_motor = ttk.Frame(self.pai)
        self.caixa_motor.pack(fill="x", padx=12, pady=(12, 0))
        self.lb_motor = ttk.Label(self.caixa_motor, textvariable=self.var_motor,
                                  style="Suave.TLabel", justify="left",
                                  wraplength=400)
        self.lb_motor.pack(fill="x")
        self.barra_motor = ttk.Progressbar(self.caixa_motor,
                                           mode="determinate", maximum=100)
        self.bt_preparar = ttk.Button(self.caixa_motor,
                                      text="Preparar (uma vez só)",
                                      style="Acao.TButton",
                                      command=self._preparar)
        # O botao e a barra so aparecem quando servem para alguma coisa.

        # ---- fila
        caixa = ttk.Labelframe(self.pai, text=" Fila: o que será transcrito ")
        caixa.pack(fill="x", padx=12, pady=(10, 6))
        self.bt_add = ttk.Button(caixa, text="Adicionar áudios ou vídeos...",
                                 style="Colar.TButton",
                                 command=self._adicionar)
        self.bt_add.pack(fill="x", padx=8, pady=(8, 6))
        linha = ttk.Frame(caixa)
        linha.pack(fill="x", padx=8)
        self.lista = Listbox(
            linha, selectmode=SINGLE, activestyle="none",
            bg=tema.COR_CAMPO, fg=tema.COR_TEXTO, font=self.fonte_peq,
            selectbackground=tema.COR_DESTAQUE, selectforeground="#1a1a1a",
            highlightthickness=1, highlightbackground=tema.COR_BORDA,
            highlightcolor=tema.COR_DESTAQUE, relief="flat", borderwidth=0,
            height=3)
        self.lista.pack(side="left", fill="both", expand=True)
        barra = ttk.Scrollbar(linha, orient="vertical",
                              command=self.lista.yview)
        barra.pack(side="right", fill="y")
        self.lista.configure(yscrollcommand=barra.set)

        botoes = ttk.Frame(caixa)
        botoes.pack(fill="x", padx=8, pady=(6, 8))
        self.bt_tirar = ttk.Button(botoes, text="Tirar", width=7,
                                   command=self._tirar)
        self.bt_tirar.pack(side="left")
        self.bt_limpar = ttk.Button(botoes, text="Esvaziar", width=9,
                                    command=self._limpar_fila)
        self.bt_limpar.pack(side="left", padx=(6, 0))
        self.lb_conta = ttk.Label(botoes, text="fila vazia",
                                  style="Suave.TLabel")
        self.lb_conta.pack(side="right")

        # ---- opcoes e destino, numa caixa so
        opcoes = ttk.Labelframe(self.pai, text=" Como ouvir e onde salvar ")
        opcoes.pack(fill="x", padx=12, pady=(0, 8))
        l1 = ttk.Frame(opcoes)
        l1.pack(fill="x", padx=8, pady=(8, 6))
        ttk.Label(l1, text="Idioma").pack(side="left")
        self.cb_idioma = ttk.Combobox(
            l1, textvariable=self.var_idioma, state="readonly", width=16,
            values=[nome for nome, _codigo in transcritor.IDIOMAS])
        self.cb_idioma.pack(side="right")

        self.chk_separar = ttk.Checkbutton(opcoes, text="Separar quem fala",
                                           variable=self.var_separar)
        self.chk_separar.pack(anchor="w", padx=8, pady=(0, 6))
        # Na variavel, e nao no `command`: assim a tela reage tambem quando
        # o valor muda por codigo.
        self.var_separar.trace_add("write", lambda *a: self._separar_mudou())

        self.lb_dica_prompt = ttk.Label(
            opcoes, style="Suave.TLabel", justify="left", wraplength=400,
            text="Nomes difíceis (opcional), separados por vírgula:")
        self.lb_dica_prompt.pack(anchor="w", padx=8)
        self.ent_prompt = ttk.Entry(opcoes, textvariable=self.var_prompt)
        self.ent_prompt.pack(fill="x", padx=8, pady=(2, 8))

        l3 = ttk.Frame(opcoes)
        l3.pack(fill="x", padx=8, pady=(0, 6))
        self.bt_pasta = ttk.Button(l3, text="Trocar...", width=9,
                                   command=self._trocar_pasta)
        self.bt_pasta.pack(side="right", padx=(6, 0))
        self.ent_saida = ttk.Entry(l3, textvariable=self.var_saida)
        self.ent_saida.pack(side="left", fill="x", expand=True)

        formatos = ttk.Frame(opcoes)
        formatos.pack(fill="x", padx=8, pady=(0, 8))
        self.chk_docx = ttk.Checkbutton(formatos, text="Word",
                                        variable=self.var_docx)
        self.chk_docx.pack(side="left")
        self.chk_txt = ttk.Checkbutton(formatos, text="Texto",
                                       variable=self.var_txt)
        self.chk_txt.pack(side="left", padx=(10, 0))
        self.chk_srt = ttk.Checkbutton(formatos, text="Legenda (.srt)",
                                       variable=self.var_srt)
        self.chk_srt.pack(side="left", padx=(10, 0))

        # ---- acao
        acao = ttk.Frame(self.pai)
        acao.pack(fill="x", padx=12, pady=(0, 0))
        self.bt_cancelar = ttk.Button(acao, text="Cancelar", width=9,
                                      command=self._pedir_cancelar,
                                      state="disabled")
        self.bt_cancelar.pack(side="right", padx=(6, 0))
        self.bt_abrir = ttk.Button(acao, text="Abrir a pasta",
                                   command=self._abrir_pasta)
        self.bt_abrir.pack(side="right", padx=(6, 0))
        self.bt_transcrever = ttk.Button(acao, text="Transcrever tudo",
                                         style="Acao.TButton",
                                         command=self._transcrever,
                                         state="disabled")
        self.bt_transcrever.pack(side="left", fill="x", expand=True)

        self.barra = ttk.Progressbar(self.pai, mode="determinate", maximum=100)
        self.barra.pack(fill="x", padx=12, pady=(8, 0))
        self.lb_status = ttk.Label(self.pai, textvariable=self.var_status,
                                   style="Suave.TLabel", wraplength=400,
                                   justify="left")
        self.lb_status.pack(fill="x", padx=12, pady=(4, 0))

        # ---- quem e quem: so aparece quando sai o primeiro arquivo com as
        # pessoas separadas, e fica acima do texto saindo (que encolhe).
        self.caixa_nomes = ttk.Labelframe(self.pai, text=" Quem é quem ")
        self.lb_nomes_dica = ttk.Label(
            self.caixa_nomes, style="Suave.TLabel", justify="left",
            wraplength=400,
            text="Escreva o nome de cada pessoa. Em cima de cada campo está o "
                 "que ela disse primeiro. Se a mesma pessoa aparecer duas "
                 "vezes, dê o mesmo nome às duas.")
        self.lb_nomes_dica.pack(fill="x", padx=8, pady=(8, 6))
        self.cb_arquivo = ttk.Combobox(self.caixa_nomes, state="readonly",
                                       textvariable=self.var_arquivo)
        self.cb_arquivo.pack(fill="x", padx=8, pady=(0, 6))
        self.cb_arquivo.bind("<<ComboboxSelected>>",
                             lambda e: self._trocar_arquivo())
        self.quadro_falantes = ttk.Frame(self.caixa_nomes)
        self.quadro_falantes.pack(fill="x", padx=8)
        self.rotulos_falas = []
        linha_nomes = ttk.Frame(self.caixa_nomes)
        linha_nomes.pack(fill="x", padx=8, pady=(4, 8))
        self.bt_nomes = ttk.Button(linha_nomes, text="Gravar os nomes",
                                   style="Acao.TButton",
                                   command=self._gravar_nomes)
        self.bt_nomes.pack(side="left")
        self.lb_gravado = ttk.Label(linha_nomes, style="Suave.TLabel",
                                    justify="left", wraplength=220)
        self.lb_gravado.pack(side="left", fill="x", expand=True, padx=(8, 0))

        # ---- o texto saindo, ao vivo, e o que ja ficou pronto
        vivo = ttk.Labelframe(self.pai, text=" Texto saindo ")
        vivo.pack(fill="both", expand=True, padx=12, pady=(8, 6))
        self.caixa_vivo = vivo
        w = ttk.Frame(vivo)
        w.pack(fill="both", expand=True, padx=8, pady=8)
        self.txt_vivo = Text(
            w, height=6, wrap="word", bg=tema.COR_CAMPO, fg=tema.COR_TEXTO,
            font=self.fonte_peq, insertbackground=tema.COR_TEXTO,
            selectbackground=tema.COR_DESTAQUE, selectforeground="#1a1a1a",
            highlightthickness=1, highlightbackground=tema.COR_BORDA,
            highlightcolor=tema.COR_BORDA, relief="flat", borderwidth=0,
            padx=6, pady=4)
        self.txt_vivo.pack(side="left", fill="both", expand=True)
        b1 = ttk.Scrollbar(w, orient="vertical", command=self.txt_vivo.yview)
        b1.pack(side="right", fill="y")
        self.txt_vivo.configure(yscrollcommand=b1.set, state="disabled")
        self.txt_vivo.tag_configure("hora", foreground=tema.COR_APAGADO)

        rel = ttk.Labelframe(self.pai, text=" O que já saiu ")
        rel.pack(fill="x", padx=12, pady=(0, 10))
        wrap = ttk.Frame(rel)
        wrap.pack(fill="both", expand=True, padx=8, pady=8)
        self.log = Listbox(
            wrap, activestyle="none", bg=tema.COR_CAMPO, fg=tema.COR_SUAVE,
            font=self.fonte_mini, selectbackground=tema.COR_CAMPO,
            selectforeground=tema.COR_SUAVE, highlightthickness=1,
            highlightbackground=tema.COR_BORDA, relief="flat", borderwidth=0,
            height=3)
        self.log.pack(side="left", fill="both", expand=True)
        b2 = ttk.Scrollbar(wrap, orient="vertical", command=self.log.yview)
        b2.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=b2.set)

        # Com add="+": o Media Studio ja liga o <Configure> deste quadro a
        # conta da pagina que rola, e substituir a ligacao dele a desligaria.
        self.pai.bind("<Configure>", self._ajustar_quebra, add="+")
        # O que muda de altura depois de montado (o motor, o recado de
        # andamento e a caixa de nomes) pede para a pagina refazer a conta.
        self._remedir_marcado = False
        for w in (self.caixa_motor, self.lb_status, self.caixa_nomes):
            w.bind("<Configure>", lambda e: self._pedir_remedir(), add="+")

    def _ajustar_quebra(self, evento=None):
        largura = self.pai.winfo_width() - 40
        if largura > 120:
            for rotulo in (self.lb_motor, self.lb_status, self.lb_dica_prompt,
                           self.lb_nomes_dica, *self.rotulos_falas):
                rotulo.configure(wraplength=largura - 16)
            self.lb_gravado.configure(wraplength=max(120, largura - 190))

    # ----------------------------------------------------------------- motor

    def _conferir_motor(self):
        self.recados.put(("motor", self._estado_motor()))

    @staticmethod
    def _estado_motor():
        """(Whisper pronto, separador pronto). Demora: so fora da janela."""
        motor = transcritor.qual_motor()
        ok = transcritor.motor_pronto(motor) and transcritor.modelo_pronto(motor)
        return ok, ok and transcritor.separador_pronto(motor)

    def _separar_mudou(self):
        if self.rodando:
            return
        if not self.var_separar.get():
            return
        if self.preparado and not self.separador_pronto:
            self._status(
                "Para separar quem fala, falta uma peça pequena (uns 95 MB). "
                "Ela é baixada uma vez só, com internet, quando você clicar "
                "em Transcrever tudo.")
        else:
            self._status(
                "Ele descobre sozinho quantas pessoas falam. Quando cada "
                "arquivo ficar pronto, aparece um campo para o nome de cada "
                "uma.")

    def _mostrar_motor(self, pronto, texto=None):
        self.preparado = pronto
        self.barra_motor.pack_forget()
        if pronto:
            self.bt_preparar.pack_forget()
            self.var_motor.set(texto or "Motor pronto: funciona sem internet, "
                                        "e o áudio não sai do computador.")
            self.lb_motor.configure(style="Ok.TLabel")
        else:
            self.var_motor.set(
                texto or "Ainda não preparado. Clique abaixo uma vez, com "
                         "internet: ele instala o Whisper e baixa o modelo "
                         "(uns 2 GB, de 1 a 5 minutos). Depois, nunca mais.")
            self.lb_motor.configure(style="Suave.TLabel")
            self.bt_preparar.pack(fill="x", pady=(6, 0))
        self._redesenhar_fila()

    def _preparar(self, depois=None):
        """Prepara o motor numa thread. `depois` roda no fim, se deu certo."""
        if self.rodando:
            return
        self.rodando = True
        self.execucao = transcritor.Execucao()
        self._travar(True)
        self.bt_preparar.pack_forget()
        self.barra_motor.configure(value=0)
        self.barra_motor.pack(fill="x", pady=(6, 0))
        self.lb_motor.configure(style="Suave.TLabel")
        self.var_motor.set("Preparando... (precisa de internet só agora)")
        self._status("Preparando o motor: o andamento aparece logo acima.")

        def trabalhar():
            erro = None
            try:
                transcritor.preparar(
                    self.execucao,
                    lambda texto, fracao: self.recados.put(
                        ("preparo", (texto, fracao))))
            except transcritor.Cancelado:
                erro = "Preparação cancelada. O que já veio fica guardado."
            except RuntimeError as e:
                erro = str(e)
            except Exception:
                erro = ("Falha inesperada ao preparar:\n"
                        + traceback.format_exc().strip().splitlines()[-1])
            # O estado e conferido de novo mesmo com erro: se so a separacao
            # falhou, o Whisper esta pronto e a transcricao continua valendo.
            self.recados.put(("preparo_fim",
                              (erro, depois) + self._estado_motor()))

        threading.Thread(target=trabalhar, daemon=True).start()

    # ----------------------------------------------------------------- fila

    def _redesenhar_fila(self):
        self.lista.delete(0, END)
        for item in self.fila:
            self.lista.insert(END, item["nome"])
        n = len(self.fila)
        self.lb_conta.configure(
            text="fila vazia" if n == 0 else
            ("1 na fila" if n == 1 else "%d na fila" % n))
        if not self.rodando:
            self.bt_transcrever.configure(state="normal" if n else "disabled")

    def _adicionar(self):
        if self.rodando:
            return
        escolhidos = filedialog.askopenfilenames(
            title="Escolha os áudios ou vídeos", filetypes=TIPOS)
        ja = {i["caminho"] for i in self.fila}
        novos = 0
        for caminho in escolhidos:
            if caminho in ja:
                continue
            self.fila.append({"caminho": caminho,
                              "nome": os.path.basename(caminho)})
            novos += 1
        if novos:
            self._redesenhar_fila()
            self._status("%d arquivo(s) na fila." % novos)

    def _tirar(self):
        if self.rodando:
            return
        sel = self.lista.curselection()
        if not sel:
            return
        fora = self.fila.pop(sel[0])
        self._redesenhar_fila()
        self._status("Tirado da fila: %s" % fora["nome"])

    def _limpar_fila(self):
        if self.rodando or not self.fila:
            return
        self.fila = []
        self._redesenhar_fila()
        self._status("Fila vazia.")

    # -------------------------------------------------------------- destino

    def _trocar_pasta(self):
        escolhida = filedialog.askdirectory(
            title="Onde salvar as transcrições",
            initialdir=self.var_saida.get() or pastas.pasta_downloads())
        if escolhida:
            self.var_saida.set(escolhida)

    def _abrir_pasta(self):
        pasta = self.var_saida.get()
        if not os.path.isdir(pasta):
            messagebox.showinfo(APP_NOME, "Essa pasta ainda não existe.")
            return
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", pasta])
            elif os.name == "nt":
                os.startfile(pasta)  # noqa
            else:
                subprocess.Popen(["xdg-open", pasta])
        except Exception:
            pass

    # ------------------------------------------------------------ transcrever

    def _codigo_idioma(self):
        escolhido = self.var_idioma.get()
        for nome, codigo in transcritor.IDIOMAS:
            if nome == escolhido:
                return codigo
        return "pt"

    def _transcrever(self):
        if self.rodando or not self.fila:
            return
        if not (self.var_docx.get() or self.var_txt.get() or
                self.var_srt.get()):
            messagebox.showwarning(
                APP_NOME, "Marque pelo menos um formato de saída: Word, "
                          "Texto ou Legenda.")
            return
        if not self.preparado:
            if not messagebox.askyesno(
                    APP_NOME,
                    "O motor de transcrição ainda não foi preparado.\n\n"
                    "Preparar agora? Precisa de internet só desta vez "
                    "(uns 2 GB). Assim que terminar, a fila começa sozinha.",
                    parent=self.raiz):
                return
            self._preparar(depois=self._transcrever)
            return
        if self.var_separar.get() and not self.separador_pronto:
            if not messagebox.askyesno(
                    APP_NOME,
                    "Para separar quem fala, falta preparar uma peça pequena "
                    "(uns 95 MB), com internet, só desta vez.\n\n"
                    "Preparar agora? Assim que terminar, a fila começa "
                    "sozinha.",
                    parent=self.raiz):
                return
            self._preparar(depois=self._transcrever)
            return

        saida = pastas.garantir(self.var_saida.get().strip() or
                                pastas.pasta_downloads())
        self.var_saida.set(saida)

        self.rodando = True
        self.execucao = transcritor.Execucao()
        self._travar(True)
        self.barra.configure(value=0, maximum=100)
        formatos = (self.var_docx.get(), self.var_txt.get(), self.var_srt.get())
        threading.Thread(
            target=self._trabalhar,
            args=(list(self.fila), saida, formatos, self._codigo_idioma(),
                  self.var_prompt.get(), self.var_separar.get()),
            daemon=True).start()

    def _trabalhar(self, fila, saida, formatos, idioma, prompt, separar):
        salvar_docx, salvar_txt, salvar_srt = formatos
        ok = 0
        total = len(fila)
        for i, item in enumerate(fila):
            self.recados.put(("novo_arquivo", None))
            self.recados.put(("status", "Abrindo %d de %d: %s"
                              % (i + 1, total, item["nome"])))
            inicio = time.monotonic()
            # Separando quem fala, a barra do arquivo reserva o fim para essa
            # etapa. No Mac com chip Apple ela corre junto com o Whisper e
            # quase sempre ja acabou quando ele termina.
            estado = {"duracao": 0.0, "separado": 0.0, "esperando": False,
                      "peso": 0.95 if separar else 1.0}

            def ao_recado(r, i=i, item=item, inicio=inicio, estado=estado):
                tipo = r.get("tipo")
                if tipo == "duracao":
                    # So o recado do Whisper conta: a separacao manda o seu.
                    if not estado["duracao"]:
                        estado["duracao"] = float(r.get("s") or 0)
                        self.recados.put(("status",
                                          "Carregando o modelo para %s..."
                                          % item["nome"]))
                elif tipo == "trecho":
                    self.recados.put(("trecho", r))
                    self.recados.put(("andamento", (
                        i, total, item["nome"], float(r.get("fim") or 0),
                        estado["duracao"], time.monotonic() - inicio,
                        estado["peso"])))
                elif tipo == "separando":
                    estado["separado"] = float(r.get("fracao") or 0)
                    if estado["esperando"]:
                        self.recados.put(("separando", (
                            i, total, item["nome"], estado["separado"])))
                elif tipo == "esperando_separacao":
                    estado["esperando"] = True
                    self.recados.put(("separando", (
                        i, total, item["nome"], estado["separado"])))

            try:
                res = transcritor.transcrever(item["caminho"], idioma, prompt,
                                              self.execucao, ao_recado,
                                              separar=separar)
                segmentos = res.get("segmentos") or []
                if not segmentos:
                    raise RuntimeError("Não ouvi fala nenhuma neste arquivo.")

                nome = os.path.splitext(item["nome"])[0]
                pronto = {
                    "arquivo": item["nome"], "titulo": nome,
                    "data": transcritor.data_do_arquivo(item["caminho"]),
                    "segmentos": segmentos,
                    "caminhos": {
                        ext: self._nome_livre(saida, nome, "." + ext)
                        for ext, quer in (("docx", salvar_docx),
                                          ("txt", salvar_txt),
                                          ("srt", salvar_srt)) if quer},
                    "falas": transcritor.primeiras_falas(segmentos),
                    "gravados": {},
                }
                self._gravar(pronto, {})
                gerados = list(pronto["caminhos"].values())

                ok += 1
                gasto = time.monotonic() - inicio
                n = res.get("pessoas")
                self.recados.put(("saiu", item))
                self.recados.put((
                    "log", "OK  %s   (%s de áudio em %s%s)"
                    % (", ".join(os.path.basename(a) for a in gerados),
                       legenda.formatar(res.get("duracao") or 0),
                       legenda.formatar(gasto),
                       "" if not n else
                       ", 1 pessoa" if n == 1 else ", %d pessoas" % n)))
                if res.get("aviso"):
                    self.recados.put(("log", "      Atenção: " + res["aviso"]))
                if pronto["falas"]:
                    self.recados.put(("resultado", pronto))
            except transcritor.Cancelado:
                self.recados.put(("log", "Cancelado por você em %s."
                                  % item["nome"]))
                break
            except RuntimeError as e:
                self.recados.put(("log", "ERRO  %s  ->  %s"
                                  % (item["nome"], str(e).split("\n")[0])))
            except Exception:
                self.recados.put(("log", "ERRO  %s  ->  falha inesperada"
                                  % item["nome"]))
                self.recados.put(("log", "      " +
                                  traceback.format_exc().strip().split("\n")[-1]))
            self.recados.put(("passo", (i + 1) * 100.0 / total))

        self.recados.put(("fim", (ok, total)))

    def _nome_livre(self, pasta, nome, extensao):
        """Nome de arquivo valido e que nao atropela um que ja existe."""
        limpo = "".join(c for c in nome if c not in '\\/:*?"<>|').strip()
        limpo = limpo or "transcricao"
        alvo = os.path.join(pasta, limpo + extensao)
        n = 2
        while os.path.exists(alvo):
            alvo = os.path.join(pasta, "%s (%d)%s" % (limpo, n, extensao))
            n += 1
        return alvo

    def _pedir_cancelar(self):
        if self.execucao is not None:
            self._status("Cancelando...")
            threading.Thread(target=self.execucao.cancelar,
                             daemon=True).start()

    # --------------------------------------------------------------- recados

    def _ler_recados(self):
        # O reagendamento fica no `finally`: se um recado der erro, a tela
        # continua viva e os proximos recados (inclusive o "fim", que destrava
        # os botoes) ainda chegam. Sem isso, um erro bobo deixaria a aba
        # congelada em "trabalhando" para sempre.
        try:
            while True:
                tipo, valor = self.recados.get_nowait()
                try:
                    self._tratar(tipo, valor)
                except Exception:
                    traceback.print_exc()
        except queue.Empty:
            pass
        finally:
            self.raiz.after(120, self._ler_recados)

    def _tratar(self, tipo, valor):
        if tipo == "status":
            self._status(valor)
        elif tipo == "motor":
            pronto, self.separador_pronto = valor
            self._mostrar_motor(pronto)
        elif tipo == "preparo":
            texto, fracao = valor
            self.var_motor.set(texto)
            if fracao is None:
                if str(self.barra_motor.cget("mode")) != "indeterminate":
                    self.barra_motor.configure(mode="indeterminate")
                    self.barra_motor.start(12)
            else:
                if str(self.barra_motor.cget("mode")) != "determinate":
                    self.barra_motor.stop()
                    self.barra_motor.configure(mode="determinate")
                self.barra_motor.configure(value=fracao * 100)
        elif tipo == "preparo_fim":
            erro, depois, pronto, self.separador_pronto = valor
            self.barra_motor.stop()
            self.barra_motor.configure(mode="determinate")
            self.rodando = False
            self._travar(False)
            if erro and pronto:
                # So a separacao de quem fala nao ficou pronta: transcrever
                # continua funcionando, e a explicacao fica a vista.
                self._mostrar_motor(
                    True, "O motor está pronto, mas a separação de quem fala "
                          "não: " + erro)
                self.lb_motor.configure(style="Erro.TLabel")
            elif erro:
                self._mostrar_motor(False, erro)
                self.lb_motor.configure(style="Erro.TLabel")
            else:
                self._mostrar_motor(True)
                if depois is not None:
                    self.raiz.after(200, depois)
        elif tipo == "novo_arquivo":
            self.txt_vivo.configure(state="normal")
            self.txt_vivo.delete("1.0", END)
            self.txt_vivo.configure(state="disabled")
        elif tipo == "trecho":
            self._escrever_vivo(valor)
        elif tipo == "andamento":
            self._andamento(*valor)
        elif tipo == "separando":
            i, total, nome, fracao = valor
            self.barra.configure(value=(i + 0.95 + 0.05 * fracao) * 100.0
                                 / total)
            self._status("Separando quem fala em %d de %d: %s  •  %d%%"
                         % (i + 1, total, nome, round(fracao * 100)))
        elif tipo == "log":
            self.log.insert(END, valor)
            self.log.see(END)
        elif tipo == "passo":
            self.barra.configure(value=valor)
        elif tipo == "resultado":
            self._novo_resultado(valor)
        elif tipo == "saiu":
            if valor in self.fila:
                self.fila.remove(valor)
        elif tipo == "fim":
            ok, total = valor
            self.rodando = False
            self.execucao = None
            self._travar(False)
            self._redesenhar_fila()
            if ok == total and self.var_separar.get():
                self._status(
                    "Pronto. %d de %d transcrito(s), em %s. Escreva o nome "
                    "de cada pessoa em \u201cQuem é quem\u201d; para conferir "
                    "ouvindo, abra o .docx na aba Sincronizar."
                    % (ok, total, self.var_saida.get()))
            elif ok == total:
                self._status(
                    "Pronto. %d de %d transcrito(s), em %s. Para dizer "
                    "quem fala em cada trecho, abra o .docx na aba "
                    "Sincronizar." % (ok, total, self.var_saida.get()))
            else:
                self._status("Terminou com %d de %d transcrito(s). "
                             "Veja o quadro de baixo." % (ok, total))

    def _escrever_vivo(self, r):
        texto = (r.get("texto") or "").strip()
        if not texto:
            return
        t = self.txt_vivo
        no_fim = t.yview()[1] >= 0.999
        t.configure(state="normal")
        t.insert(END, "(%s) " % legenda.formatar(r.get("ini") or 0), "hora")
        t.insert(END, texto + "\n")
        t.configure(state="disabled")
        # So acompanha o fim se a pessoa nao subiu para reler alguma coisa.
        if no_fim:
            t.see(END)

    def _andamento(self, i, total, nome, ouvido, duracao, gasto, peso=1.0):
        fracao = min(1.0, ouvido / duracao) if duracao > 0 else 0.0
        self.barra.configure(value=(i + fracao * peso) * 100.0 / total)
        texto = "Transcrevendo %d de %d: %s  •  %s de %s" % (
            i + 1, total, nome, legenda.formatar(ouvido),
            legenda.formatar(duracao))
        # A previsao so aparece depois de um pedaco razoavel: no comeco ela
        # oscila demais para servir de alguma coisa.
        if fracao > 0.05 and gasto > 5:
            falta = gasto * (1 - fracao) / fracao
            texto += "  •  %s" % (
                "falta menos de 1 min" if falta < 60 else
                "falta ~%d min" % round(falta / 60))
        self._status(texto)

    def _status(self, texto):
        self.var_status.set(texto)

    def _travar(self, travado):
        estado = "disabled" if travado else "normal"
        for w in (self.bt_add, self.bt_tirar, self.bt_limpar, self.bt_pasta,
                  self.chk_docx, self.chk_txt, self.chk_srt, self.ent_prompt,
                  self.ent_saida, self.chk_separar):
            w.configure(state=estado)
        self.cb_idioma.configure(state="disabled" if travado else "readonly")
        # A caixa "Quem e quem" nao trava: da para dar nome as pessoas do
        # primeiro arquivo enquanto o segundo ainda esta sendo transcrito.
        self.bt_cancelar.configure(state="normal" if travado else "disabled")
        if travado:
            self.bt_transcrever.configure(state="disabled")
        else:
            self._redesenhar_fila()

    def ao_fechar(self):
        if self.execucao is not None:
            self.execucao.cancelar()
        try:
            self._gravar_nomes(sozinho=True)
        except Exception:
            pass

    # ------------------------------------------------------------ quem e quem

    @staticmethod
    def _gravar(pronto, nomes):
        """(Re)grava os arquivos de um resultado com os `nomes` de agora.

        Sempre no mesmo formato que a aba Sincronizar le: trocar o nome
        depois nao muda nada alem do nome.
        """
        caminhos = pronto["caminhos"]
        itens = transcritor.montar_itens(pronto["segmentos"], nomes=nomes)
        if "docx" in caminhos:
            gravar_paragrafos(caminhos["docx"], itens, pronto["titulo"],
                              pronto["data"])
        if "txt" in caminhos:
            gravar_texto(caminhos["txt"], itens, pronto["titulo"],
                         pronto["data"])
        if "srt" in caminhos:
            transcritor.gravar_srt(caminhos["srt"], pronto["segmentos"], nomes)

    def _rotulo_resultado(self, pronto):
        n = len(pronto["falas"])
        rotulo = "%s  ·  %s" % (pronto["arquivo"],
                                "1 pessoa" if n == 1 else "%d pessoas" % n)
        iguais = sum(1 for r in self.resultados
                     if r["arquivo"] == pronto["arquivo"])
        if iguais > 1:
            rotulo += "  (%d)" % (self.resultados.index(pronto) + 1)
        return rotulo

    def _novo_resultado(self, pronto):
        self.resultados.append(pronto)
        self.cb_arquivo.configure(
            values=[self._rotulo_resultado(r) for r in self.resultados])
        if not self.caixa_nomes.winfo_ismapped():
            self.caixa_nomes.pack(fill="x", padx=12, pady=(8, 0),
                                  before=self.caixa_vivo)
        # O arquivo novo so toma o lugar do que esta na tela se ninguem esta
        # escrevendo nele: senao, a pessoa perderia o fio no meio de um nome.
        escrevendo = (self.res_atual is not None and (
            any(v.get().strip() for v in self.vars_nomes.values()) or
            str(self.raiz.focus_get() or "").startswith(
                str(self.quadro_falantes))))
        if not escrevendo:
            self._mostrar_resultado(pronto)

    def _trocar_arquivo(self):
        i = self.cb_arquivo.current()
        if 0 <= i < len(self.resultados):
            self._gravar_nomes(sozinho=True)
            self._mostrar_resultado(self.resultados[i])

    def _mostrar_resultado(self, pronto):
        self.res_atual = pronto
        self.var_arquivo.set(self._rotulo_resultado(pronto))
        for w in self.quadro_falantes.winfo_children():
            w.destroy()
        self.rotulos_falas = []
        self.vars_nomes = {}
        largura = max(200, self.pai.winfo_width() - 56)
        for numero, _ini, fala in pronto["falas"]:
            rotulo = ttk.Label(
                self.quadro_falantes, style="Suave.TLabel", justify="left",
                wraplength=largura,
                text="%s  ·  %s" % (transcritor.NOME_FALANTE % numero, fala))
            rotulo.pack(fill="x", pady=(4, 2))
            self.rotulos_falas.append(rotulo)
            var = StringVar(value=pronto["gravados"].get(numero, ""))
            campo = ttk.Entry(self.quadro_falantes, textvariable=var)
            campo.pack(fill="x", pady=(0, 4))
            # Enter ou sair do campo grava sozinho; o botao fica para quem
            # prefere clicar.
            campo.bind("<Return>", lambda e: self._gravar_nomes(sozinho=True))
            campo.bind("<FocusOut>",
                       lambda e: self._gravar_nomes(sozinho=True))
            self.vars_nomes[numero] = var
        self._mostrar_gravado()
        self._pedir_remedir()

    def _mostrar_gravado(self, quando=None):
        pronto = self.res_atual
        if pronto is None:
            return
        arquivos = ", ".join(os.path.basename(c)
                             for c in pronto["caminhos"].values())
        if quando:
            self.lb_gravado.configure(
                style="Ok.TLabel",
                text="Nomes gravados às %s em %s." % (quando, arquivos))
        elif any(pronto["gravados"].values()):
            self.lb_gravado.configure(style="Suave.TLabel",
                                      text="Nomes gravados em %s." % arquivos)
        else:
            self.lb_gravado.configure(
                style="Suave.TLabel",
                text="Por enquanto, %s %s com \u201cPalestrante 1, 2...\u201d."
                     % (arquivos, "estão" if len(pronto["caminhos"]) > 1
                        else "está"))

    def _gravar_nomes(self, sozinho=False):
        """Regrava os arquivos do resultado na tela, se algum nome mudou."""
        pronto = self.res_atual
        if pronto is None:
            return
        nomes = {n: transcritor.limpar_nome(v.get())
                 for n, v in self.vars_nomes.items()}
        nomes = {n: nome for n, nome in nomes.items() if nome}
        if nomes == pronto["gravados"]:
            if not sozinho and not nomes:
                self.lb_gravado.configure(
                    style="Suave.TLabel",
                    text="Escreva pelo menos um nome nos campos acima.")
            elif not sozinho:
                self.lb_gravado.configure(
                    style="Ok.TLabel",
                    text="Esses nomes já estão gravados nos arquivos.")
            return
        try:
            self._gravar(pronto, nomes)
        except OSError as e:
            messagebox.showerror(
                APP_NOME, "Não consegui gravar os nomes nos arquivos.\n\n%s"
                % e, parent=self.raiz)
            return
        pronto["gravados"] = nomes
        self._mostrar_gravado(datetime.now().strftime("%H:%M"))
        self.log.insert(END, "Nomes gravados em %s: %s" % (
            pronto["arquivo"], ", ".join(
                "%s = %s" % (transcritor.NOME_FALANTE % n, nome)
                for n, nome in sorted(nomes.items())) or "nenhum"))
        self.log.see(END)

    def _pedir_remedir(self):
        """Refaz a conta da pagina uma vez so, quando a tela sossegar."""
        if not self._remedir_marcado:
            self._remedir_marcado = True
            self.raiz.after_idle(self._remedir_pagina)

    def _remedir_pagina(self):
        """O Media Studio poe cada aba numa pagina que rola. Quando esta aba
        cresce depois de montada (a caixa de nomes, um recado mais comprido),
        a pagina precisa refazer a conta da altura, senao o fim fica
        escondido e sem barra de rolagem. Quem refaz a conta e o <Configure>
        da tela que rola, que e quem esta logo acima deste quadro."""
        self._remedir_marcado = False
        try:
            self.pai.master.event_generate("<Configure>")
        except Exception:
            pass


def montar(pai):
    return AbaTranscrever(pai)
