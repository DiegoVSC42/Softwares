"""Aba "Limpar transcricao" do Transcript Studio.

Pega o texto que voce copia da tela do TurboScribe (Cmd+A, Cmd+C) e devolve a
transcricao exatamente como esta na tela, so que sem o resto da pagina:

    Dr. Fernando Maximo
    (0:00) E isso, por favor.

    Entrevistador NM
    (0:01) A levinha lateral ta de boa? (0:04) E porque ele ta de mais.

Os horarios no meio da fala ficam: sao eles que servem para achar o corte.
O que sai fora e a interface do site (menu, pastas, botoes, player).

O programa trabalha por FILA. Voce vai ao TurboScribe, copia, volta e clica em
"Colar da área de transferência": a transcricao entra na fila, ja conferida,
mas nada e gravado ainda. Repete quantas vezes quiser, e no fim clica uma
unica vez em "Converter tudo". Arquivos ja salvos entram na mesma fila.

Esta aba nao cria janela nem define estilo: a janela e o estilo sao da
`transcript_studio.py`. O layout e empilhado, e nao lado a lado, porque a
janela do estudio vive estreita, encostada no canto da tela.
"""

import os
import queue
import subprocess
import sys
import threading
import traceback
from tkinter import (Toplevel, StringVar, BooleanVar, END, ttk, filedialog,
                     messagebox, Listbox, SINGLE)

import pastas
import tema
from conversor import converter, resumo
from documento import ler_paragrafos, gravar_paragrafos, gravar_texto

APP_NOME = "Transcript Studio"

# Apelidos da paleta, para o corpo da aba continuar lendo como antes.
COR_FUNDO = tema.COR_FUNDO
COR_PAINEL = tema.COR_PAINEL
COR_CAMPO = tema.COR_CAMPO
COR_BOTAO = tema.COR_BOTAO
COR_BOTAO_HOVER = tema.COR_BOTAO_HOVER
COR_BORDA = tema.COR_BORDA
COR_TEXTO = tema.COR_TEXTO
COR_SUAVE = tema.COR_SUAVE
COR_APAGADO = tema.COR_APAGADO
COR_DESTAQUE = tema.COR_DESTAQUE
COR_ERRO = tema.COR_ERRO
COR_OK = tema.COR_OK

TIPOS = [("Documentos do Word", "*.docx"),
         ("Arquivos de texto", "*.txt *.text *.md"),
         ("Todos os arquivos", "*.*")]


class AbaLimpar:

    def __init__(self, pai):
        self.pai = pai
        # Dialogos, area de transferencia e agendamentos precisam da JANELA,
        # nao do quadro da aba.
        self.raiz = pai.winfo_toplevel()

        # A fila. Cada item e um dicionario:
        #   tipo      "colado" ou "arquivo"
        #   nome      nome do arquivo de saida, sem extensao
        #   data      a data da gravacao, lida da tela
        #   itens     ja convertido (so nos colados)
        #   caminho   arquivo de origem (so nos de arquivo)
        #   resumo    texto curto mostrado na lista
        self.fila = []
        self.rodando = False
        self.cancelar = False
        self.recados = queue.Queue()

        self.fonte_base, self.fonte_peq, self.fonte_mini = tema.fontes()

        self.var_saida = StringVar(value=pastas.pasta_downloads())
        # As duas caixas comecam marcadas: por padrao sai Word E Texto, sem
        # a pessoa ter que escolher. Desmarcar uma so entrega a outra.
        self.var_docx = BooleanVar(value=True)
        self.var_txt = BooleanVar(value=True)
        self.var_status = StringVar(
            value="Copie a transcrição no TurboScribe e clique em Colar.")

        self._montar()
        self.raiz.after(120, self._ler_recados)

    # ------------------------------------------------------------- interface

    def _montar(self):
        # Tudo empilhado, de cima para baixo. Numa janela estreita, controle
        # lado a lado ou e cortado ou obriga a alargar a janela.
        topo = ttk.Frame(self.pai)
        topo.pack(fill="x", padx=12, pady=(12, 2))
        ttk.Label(topo, text="Transcrição do TurboScribe, sem o lixo da tela",
                  style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(topo,
                  text="1. No TurboScribe: clique na página, Cmd+A, Cmd+C.\n"
                       "2. Aqui: Colar.  3. Repita quantas quiser.\n"
                       "4. No fim: Converter tudo.",
                  style="Suave.TLabel", justify="left").pack(anchor="w",
                                                             pady=(3, 0))

        # ---- juntar (os dois jeitos de por coisa na fila)
        juntar = ttk.Frame(self.pai)
        juntar.pack(fill="x", padx=12, pady=(10, 0))
        self.bt_colar = ttk.Button(juntar, text="Colar da área de transferência",
                                   style="Colar.TButton", command=self._colar)
        self.bt_colar.pack(fill="x")

        linha2 = ttk.Frame(self.pai)
        linha2.pack(fill="x", padx=12, pady=(6, 0))
        self.bt_add = ttk.Button(linha2, text="Adicionar arquivos salvos...",
                                 command=self._adicionar)
        self.bt_add.pack(side="left")
        self.lb_conta = ttk.Label(linha2, text="fila vazia",
                                  style="Suave.TLabel")
        self.lb_conta.pack(side="right")

        # ---- a fila
        caixa = ttk.Labelframe(self.pai, text=" Fila: o que será convertido ")
        caixa.pack(fill="both", expand=True, padx=12, pady=(10, 6))

        linha = ttk.Frame(caixa)
        linha.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        self.lista = Listbox(
            linha, selectmode=SINGLE, activestyle="none",
            bg=COR_CAMPO, fg=COR_TEXTO, font=self.fonte_peq,
            selectbackground=COR_DESTAQUE, selectforeground="#1a1a1a",
            highlightthickness=1, highlightbackground=COR_BORDA,
            highlightcolor=COR_DESTAQUE, relief="flat", borderwidth=0,
            height=6)
        self.lista.pack(side="left", fill="both", expand=True)
        barra = ttk.Scrollbar(linha, orient="vertical",
                              command=self.lista.yview)
        barra.pack(side="right", fill="y")
        self.lista.configure(yscrollcommand=barra.set)
        # Clique duplo na linha tambem renomeia: e o gesto que a pessoa tenta
        # antes de procurar o botao.
        self.lista.bind("<Double-Button-1>", lambda e: self._renomear())

        botoes = ttk.Frame(caixa)
        botoes.pack(fill="x", padx=8, pady=(0, 6))
        self.bt_renomear = ttk.Button(botoes, text="Renomear", width=10,
                                      command=self._renomear)
        self.bt_renomear.pack(side="left")
        self.bt_tirar = ttk.Button(botoes, text="Tirar", width=7,
                                   command=self._tirar)
        self.bt_tirar.pack(side="left", padx=(6, 0))
        self.bt_limpar = ttk.Button(botoes, text="Esvaziar", width=9,
                                    command=self._limpar_fila)
        self.bt_limpar.pack(side="left", padx=(6, 0))
        ttk.Label(caixa, text="clique duplo na linha troca o nome de saída",
                  style="Suave.TLabel").pack(anchor="w", padx=8, pady=(0, 8))

        # ---- destino
        destino = ttk.Labelframe(self.pai, text=" Onde salvar ")
        destino.pack(fill="x", padx=12, pady=(0, 8))
        self.ent_saida = ttk.Entry(destino, textvariable=self.var_saida)
        self.ent_saida.pack(fill="x", padx=8, pady=(8, 6))
        d2 = ttk.Frame(destino)
        d2.pack(fill="x", padx=8, pady=(0, 8))
        self.bt_pasta = ttk.Button(d2, text="Trocar...", width=10,
                                   command=self._trocar_pasta)
        self.bt_pasta.pack(side="left")

        formatos = ttk.Frame(d2)
        formatos.pack(side="right")
        self.chk_docx = ttk.Checkbutton(formatos, text="Word (.docx)",
                                        variable=self.var_docx)
        self.chk_docx.pack(side="left")
        self.chk_txt = ttk.Checkbutton(formatos, text="Texto (.txt)",
                                       variable=self.var_txt)
        self.chk_txt.pack(side="left", padx=(10, 0))

        # ---- acao
        acao = ttk.Frame(self.pai)
        acao.pack(fill="x", padx=12, pady=(0, 4))
        # Nasce desligado: so acende quando ha algo na fila.
        self.bt_converter = ttk.Button(acao, text="Converter tudo",
                                       style="Acao.TButton",
                                       command=self._converter,
                                       state="disabled")
        self.bt_converter.pack(fill="x")

        acao2 = ttk.Frame(self.pai)
        acao2.pack(fill="x", padx=12, pady=(6, 0))
        self.bt_cancelar = ttk.Button(acao2, text="Cancelar", width=11,
                                      command=self._pedir_cancelar,
                                      state="disabled")
        self.bt_cancelar.pack(side="left")
        self.bt_abrir = ttk.Button(acao2, text="Abrir a pasta",
                                   command=self._abrir_pasta)
        self.bt_abrir.pack(side="right")

        self.barra = ttk.Progressbar(self.pai, mode="determinate", maximum=100)
        self.barra.pack(fill="x", padx=12, pady=(8, 0))

        self.lb_status = ttk.Label(self.pai, textvariable=self.var_status,
                                   style="Suave.TLabel", wraplength=380,
                                   justify="left")
        self.lb_status.pack(fill="x", padx=12, pady=(6, 0))
        # A quebra de linha do recado acompanha a largura real da janela.
        self.pai.bind("<Configure>", self._ajustar_quebra)

        # ---- relatorio
        rel = ttk.Labelframe(self.pai, text=" O que já saiu ")
        rel.pack(fill="both", expand=True, padx=12, pady=(8, 10))
        wrap = ttk.Frame(rel)
        wrap.pack(fill="both", expand=True, padx=8, pady=8)
        self.log = Listbox(
            wrap, activestyle="none", bg=COR_CAMPO, fg=COR_SUAVE,
            font=self.fonte_mini, selectbackground=COR_CAMPO,
            selectforeground=COR_SUAVE, highlightthickness=1,
            highlightbackground=COR_BORDA, relief="flat", borderwidth=0,
            height=4)
        self.log.pack(side="left", fill="both", expand=True)
        b2 = ttk.Scrollbar(wrap, orient="vertical", command=self.log.yview)
        b2.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=b2.set)

    def _ajustar_quebra(self, evento=None):
        largura = self.pai.winfo_width() - 40
        if largura > 120:
            self.lb_status.configure(wraplength=largura)

    # ----------------------------------------------------------------- fila

    def _rotulo(self, item):
        return "%s      %s" % (item["nome"], item["resumo"])

    def _redesenhar_fila(self):
        self.lista.delete(0, END)
        for item in self.fila:
            self.lista.insert(END, self._rotulo(item))
        n = len(self.fila)
        self.lb_conta.configure(
            text="fila vazia" if n == 0 else
            ("1 na fila" if n == 1 else "%d na fila" % n))
        if not self.rodando:
            self.bt_converter.configure(state="normal" if n else "disabled")

    def _nome_unico(self, desejado):
        """Evita dois itens da fila com o mesmo nome de saida."""
        usados = {i["nome"].lower() for i in self.fila}
        if desejado.lower() not in usados:
            return desejado
        n = 2
        while ("%s %d" % (desejado, n)).lower() in usados:
            n += 1
        return "%s %d" % (desejado, n)

    def _colar(self):
        """Poe na fila o que esta copiado. NAO grava nada ainda."""
        if self.rodando:
            return
        try:
            colado = self.raiz.clipboard_get()
        except Exception:
            colado = ""
        if not colado.strip():
            messagebox.showinfo(
                APP_NOME,
                "Não há nada copiado.\n\n"
                "Abra a transcrição no TurboScribe, clique dentro da página, "
                "aperte Cmd+A e Cmd+C, e volte aqui.")
            return

        # Converte agora so para conferir e ja saber titulo, blocos e quem
        # fala. Assim, se voce copiou a pagina errada, descobre na hora, e nao
        # meia hora depois, na hora de converter tudo.
        try:
            titulo, data, itens = converter(colado.splitlines())
        except ValueError as e:
            messagebox.showwarning(APP_NOME, str(e))
            return
        except Exception:
            messagebox.showwarning(
                APP_NOME, "Não consegui entender o texto copiado.")
            return

        blocos, falantes = resumo(itens)
        nome = self._nome_unico(titulo or "transcricao")
        self.fila.append({
            "tipo": "colado",
            "nome": nome,
            "data": data,
            "itens": itens,
            "caminho": None,
            "resumo": "colado  •  %d blocos  •  %s"
                      % (blocos, ", ".join(falantes)),
        })
        self._redesenhar_fila()
        self.lista.see(END)
        self._status("Na fila: %s (%d blocos). Copie a próxima no TurboScribe, "
                     "ou clique em Converter tudo." % (nome, blocos))

    def _adicionar(self):
        if self.rodando:
            return
        escolhidos = filedialog.askopenfilenames(
            title="Escolha os arquivos já salvos", filetypes=TIPOS)
        ja = {i["caminho"] for i in self.fila if i["caminho"]}
        novos = 0
        for caminho in escolhidos:
            if caminho in ja:
                continue
            base = os.path.splitext(os.path.basename(caminho))[0]
            self.fila.append({
                "tipo": "arquivo",
                "nome": self._nome_unico(base),
                "data": "",
                "itens": None,
                "caminho": caminho,
                "resumo": "arquivo  •  %s" % os.path.basename(caminho),
            })
            novos += 1
        if novos:
            self._redesenhar_fila()
            self._status("%d arquivo(s) na fila." % novos)

    def _selecionado(self):
        sel = self.lista.curselection()
        return sel[0] if sel else None

    def _renomear(self):
        if self.rodando:
            return
        i = self._selecionado()
        if i is None:
            messagebox.showinfo(
                APP_NOME, "Clique primeiro na linha que você quer renomear.")
            return
        item = self.fila[i]
        novo = self._perguntar_nome(item["nome"], item["resumo"])
        if not novo or novo == item["nome"]:
            return
        outros = {x["nome"].lower() for j, x in enumerate(self.fila) if j != i}
        if novo.lower() in outros:
            messagebox.showinfo(
                APP_NOME, "Já existe outro item da fila com esse nome.")
            return
        item["nome"] = novo
        self._redesenhar_fila()
        self.lista.selection_set(i)
        self._status("Renomeado para %s." % novo)

    def _tirar(self):
        if self.rodando:
            return
        i = self._selecionado()
        if i is None:
            return
        fora = self.fila.pop(i)
        self._redesenhar_fila()
        self._status("Tirado da fila: %s" % fora["nome"])

    def _limpar_fila(self):
        if self.rodando or not self.fila:
            return
        if not messagebox.askyesno(
                APP_NOME, "Esvaziar a fila? Nada do que está aí foi gravado "
                          "ainda, e as colagens se perdem."):
            return
        self.fila = []
        self._redesenhar_fila()
        self._status("Fila vazia.")

    # -------------------------------------------------------------- destino

    def _trocar_pasta(self):
        escolhida = filedialog.askdirectory(
            title="Onde salvar as transcrições limpas",
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

    # ------------------------------------------------------------- conversao

    def _converter(self):
        if self.rodando or not self.fila:
            return
        if not (self.var_docx.get() or self.var_txt.get()):
            messagebox.showwarning(
                APP_NOME, "Marque pelo menos um formato de saída: "
                          "Word ou Texto.")
            return
        saida = pastas.garantir(self.var_saida.get().strip() or
                                pastas.pasta_downloads())
        self.var_saida.set(saida)

        self.rodando = True
        self.cancelar = False
        self._travar(True)
        self.barra.configure(value=0, maximum=len(self.fila))

        t = threading.Thread(target=self._trabalhar,
                             args=(list(self.fila), saida,
                                   self.var_docx.get(), self.var_txt.get()),
                             daemon=True)
        t.start()

    def _trabalhar(self, fila, saida, salvar_docx, salvar_txt):
        ok = 0
        for i, item in enumerate(fila, start=1):
            if self.cancelar:
                self.recados.put(("log", "Cancelado por você."))
                break
            self.recados.put(("status", "Convertendo %d de %d: %s"
                              % (i, len(fila), item["nome"])))
            try:
                itens = item["itens"]
                data = item.get("data", "")
                if itens is None:           # veio de arquivo: converte agora
                    _titulo, data, itens = converter(
                        ler_paragrafos(item["caminho"]))
                blocos, falantes = resumo(itens)

                # As duas caixas sao independentes: com as duas marcadas
                # (o padrao), cada item sai duas vezes, uma em cada formato.
                gerados = []
                if salvar_docx:
                    alvo = self._nome_livre(saida, item["nome"], ".docx")
                    gravar_paragrafos(alvo, itens, item["nome"], data)
                    gerados.append(alvo)
                if salvar_txt:
                    alvo = self._nome_livre(saida, item["nome"], ".txt")
                    gravar_texto(alvo, itens, item["nome"], data)
                    gerados.append(alvo)

                ok += 1
                # Avisa QUAL item saiu, para ele deixar a fila. Sem isso, uma
                # falha parcial faria o ja convertido sair de novo, duplicado,
                # no clique seguinte.
                self.recados.put(("saiu", item))
                self.recados.put((
                    "log", "OK  %s   (%d blocos, %d participantes: %s)"
                    % (", ".join(os.path.basename(a) for a in gerados),
                       blocos, len(falantes), ", ".join(falantes))))
            except ValueError as e:
                self.recados.put(("log", "ERRO  %s  ->  %s"
                                  % (item["nome"], str(e).split("\n")[0])))
            except Exception:
                self.recados.put(("log", "ERRO  %s  ->  falha inesperada"
                                  % item["nome"]))
                self.recados.put(("log", "      " +
                                  traceback.format_exc().strip().split("\n")[-1]))
            self.recados.put(("passo", i))

        self.recados.put(("fim", (ok, len(fila))))

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
        self.cancelar = True
        self._status("Cancelando depois do item atual...")

    # ------------------------------------------------------- janela do nome

    def _perguntar_nome(self, atual, detalhe):
        """Janelinha que pergunta o nome do arquivo de saida.

        Nao usamos a caixa pronta do Tk (`simpledialog`) porque ela sai com
        fundo claro no modo escuro do Mac, que e o cenario desta casa. Esta
        aqui e pintada igual ao resto do programa.

        Devolve o nome escolhido, ou None se a pessoa desistiu.
        """
        janela = Toplevel(self.raiz)
        janela.title("Nome do arquivo")
        janela.configure(bg=COR_FUNDO)
        janela.resizable(False, False)
        janela.transient(self.raiz)

        escolha = {"nome": None}
        var = StringVar(value=atual)

        corpo = ttk.Frame(janela)
        corpo.pack(fill="both", expand=True, padx=18, pady=16)

        ttk.Label(corpo, text="Como chamar este arquivo?",
                  font=(self.fonte_base[0], self.fonte_base[1] + 1,
                        "bold")).pack(anchor="w")
        ttk.Label(corpo, text=detalhe, style="Suave.TLabel", wraplength=420,
                  justify="left").pack(anchor="w", pady=(4, 10))

        campo = ttk.Entry(corpo, textvariable=var, width=44)
        campo.pack(fill="x")
        ttk.Label(corpo, text="A extensão entra sozinha.",
                  style="Suave.TLabel").pack(anchor="w", pady=(6, 0))

        botoes = ttk.Frame(corpo)
        botoes.pack(fill="x", pady=(14, 0))

        def confirmar(*_):
            nome = var.get().strip()
            if not nome:
                return
            escolha["nome"] = nome
            janela.destroy()

        def desistir(*_):
            janela.destroy()

        ttk.Button(botoes, text="Salvar", style="Acao.TButton",
                   command=confirmar).pack(side="right")
        ttk.Button(botoes, text="Cancelar",
                   command=desistir).pack(side="right", padx=(0, 8))

        janela.bind("<Return>", confirmar)
        janela.bind("<KP_Enter>", confirmar)
        janela.bind("<Escape>", desistir)
        janela.protocol("WM_DELETE_WINDOW", desistir)

        # Abre com o texto ja selecionado: quem quiser o nome de agora so
        # aperta Enter; quem quiser outro so comeca a digitar.
        campo.focus_set()
        campo.select_range(0, END)
        self._centralizar(janela)
        janela.grab_set()
        self.raiz.wait_window(janela)
        return escolha["nome"]

    def _centralizar(self, janela):
        """Poe a janelinha no meio da janela principal."""
        try:
            janela.update_idletasks()
            lx = self.raiz.winfo_rootx()
            ly = self.raiz.winfo_rooty()
            lw = self.raiz.winfo_width()
            lh = self.raiz.winfo_height()
            jw = janela.winfo_width()
            jh = janela.winfo_height()
            janela.geometry("+%d+%d" % (lx + (lw - jw) // 2,
                                        ly + (lh - jh) // 3))
        except Exception:
            pass

    # --------------------------------------------------------------- recados

    def _ler_recados(self):
        try:
            while True:
                tipo, valor = self.recados.get_nowait()
                if tipo == "status":
                    self._status(valor)
                elif tipo == "log":
                    self.log.insert(END, valor)
                    self.log.see(END)
                elif tipo == "passo":
                    self.barra.configure(value=valor)
                elif tipo == "saiu":
                    # O que converteu deixa a fila na hora; o que falhou fica,
                    # para voce tentar de novo sem recomecar tudo e sem gerar
                    # copia repetida do que ja deu certo.
                    if valor in self.fila:
                        self.fila.remove(valor)
                elif tipo == "fim":
                    ok, total = valor
                    self.rodando = False
                    self._redesenhar_fila()
                    self._travar(False)
                    if ok == total:
                        self._status("Pronto. %d de %d convertido(s), em %s"
                                     % (ok, total, self.var_saida.get()))
                    else:
                        self._status("Terminou com problema: %d de %d "
                                     "convertido(s). Veja o quadro de baixo."
                                     % (ok, total))
        except queue.Empty:
            pass
        self.raiz.after(120, self._ler_recados)

    def _status(self, texto):
        self.var_status.set(texto)

    def _travar(self, travado):
        estado = "disabled" if travado else "normal"
        for b in (self.bt_colar, self.bt_add, self.bt_renomear, self.bt_tirar,
                  self.bt_limpar, self.bt_pasta, self.chk_docx, self.chk_txt):
            b.configure(state=estado)
        self.bt_cancelar.configure(state="normal" if travado else "disabled")
        if travado:
            self.bt_converter.configure(state="disabled")
        else:
            self._redesenhar_fila()   # so reacende se ainda houver fila

    def ao_fechar(self):
        self.cancelar = True


def montar(pai):
    return AbaLimpar(pai)
