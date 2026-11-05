# ATENCAO: este arquivo e uma COPIA. Nao edite aqui.
# A fonte oficial e `abas-compartilhadas/aba_sincronizar.py`, na pasta Scripts. Mexa la e
# rode `python3 sincronizar.py` para atualizar todos os estudios de uma vez.
# Editar esta copia faz o seu trabalho ser apagado na proxima sincronizacao.

"""Aba "Sincronizar" - video e legenda lado a lado.

Usada em DOIS estudios (Transcript Studio e Media Studio), e por isso mora
aqui, em `abas-compartilhadas/`: uma correcao feita neste arquivo chega aos
dois de uma vez, rodando `python3 sincronizar.py`.

O QUE ELA FAZ

Voce entrega o video e a legenda que saiu da aba "Limpar transcricao", e o
programa abre uma tela de trabalho com o video de um lado e a legenda do
outro: a fala que esta tocando fica acesa, clicar numa fala leva o video ate
ela, e trocar quem esta falando e um clique no nome.

POR QUE A TELA DE TRABALHO ABRE NO NAVEGADOR

Porque o Tkinter nao toca video, e principalmente porque nao toca SOM. Para
conferir quem esta falando e preciso ouvir. As saidas caseiras (desenhar
quadro a quadro com o ffmpeg) entregam imagem muda e engasgada, ou seja,
justamente o que nao serve aqui.

Entao o video toca onde ele ja toca bem, que e o navegador da propria maquina.
Nada sai do computador: o programa sobe um servidor so para ele mesmo, em
127.0.0.1, com uma senha de sessao. O video e lido do disco e a legenda
corrigida volta para ca, para ser gravada em .docx e .txt na pasta de
Downloads, no mesmo formato da aba de limpar.

Esta aba nao cria janela nem define estilo: a janela e o estilo sao do
estudio. O desenho e uma COLUNA ESTREITA centralizada, e nao uma tela que se
espalha, porque ela precisa caber tanto no Transcript Studio (que abre com
470px de largura) quanto no Media Studio (que abre com mais de mil).
"""

import os
import queue
import subprocess
import sys
import threading
import webbrowser
from shutil import which
from tkinter import StringVar, ttk, filedialog, messagebox

import pastas
from compartilhado import legenda as legenda_mod
from compartilhado import servidor_legenda
from documento import ler_paragrafos

TIPOS_VIDEO = [("Vídeos", "*.mp4 *.m4v *.mov *.webm *.MP4 *.M4V *.MOV *.WEBM"),
               ("Todos os arquivos", "*.*")]
TIPOS_LEGENDA = [("Transcrição", "*.docx *.txt *.text *.md"),
                 ("Todos os arquivos", "*.*")]


def achar_ffmpeg():
    """O ffmpeg embutido no programa, ou o do sistema, ou nada.

    O Media Studio leva o ffmpeg junto; o Transcript Studio, nao. Por isso a
    preparacao do video e oferecida quando da, e apenas avisada quando nao da.
    """
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    base = getattr(sys, "_MEIPASS",
                   os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for cand in (os.path.join(base, exe),
                 os.path.join(base, "ffmpeg", exe),
                 os.path.join(base, "bin", exe)):
        if os.path.isfile(cand):
            return cand
    return which("ffmpeg")


class AbaSincronizar:

    def __init__(self, pai, programa="Transcript Studio"):
        self.pai = pai
        self.programa = programa
        self.raiz = pai.winfo_toplevel()

        self.video = ""
        self.arquivo_legenda = ""
        self.titulo = ""
        self.data = ""
        self.segmentos = []
        self.falantes = []
        self.servidor = None
        self.rodando = False          # nada trabalha em segundo plano aqui
        self.recados = queue.Queue()

        self.var_video = StringVar(value="Nenhum vídeo escolhido.")
        self.var_legenda = StringVar(value="Nenhuma legenda escolhida.")
        self.var_saida = StringVar(value=pastas.pasta_downloads())
        self.var_status = StringVar(
            value="Escolha o vídeo e a legenda para começar.")

        self._montar()
        self.raiz.after(150, self._ler_recados)

    # ------------------------------------------------------------- interface

    def _montar(self):
        # A coluna do meio guarda a tela inteira; as das pontas sao espaco
        # vazio que cresce. E o que mantem o desenho igual nos dois estudios:
        # numa janela larga a tela nao se espalha, so fica centralizada.
        self.pai.columnconfigure(0, weight=1)
        self.pai.columnconfigure(2, weight=1)
        self.pai.rowconfigure(0, weight=1)
        col = ttk.Frame(self.pai)
        col.grid(row=0, column=1, sticky="n")
        self.col = col

        topo = ttk.Frame(col)
        topo.pack(fill="x", padx=12, pady=(12, 2))
        ttk.Label(topo, text="Legenda e vídeo lado a lado",
                  style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(topo,
                  text="A fala que está tocando fica acesa. Clicou na fala,\n"
                       "o vídeo vai até ela. Clicou no nome, troca quem fala.",
                  style="Suave.TLabel", justify="left").pack(anchor="w",
                                                             pady=(3, 0))

        # ---- 1. video
        um = ttk.Labelframe(col, text=" 1. O vídeo ")
        um.pack(fill="x", padx=12, pady=(12, 0))
        ttk.Button(um, text="Escolher o vídeo...",
                   command=self._pegar_video).pack(fill="x", padx=10,
                                                   pady=(10, 6))
        ttk.Label(um, textvariable=self.var_video, style="Suave.TLabel",
                  wraplength=380, justify="left").pack(anchor="w", padx=10,
                                                       pady=(0, 10))

        # ---- 2. legenda
        dois = ttk.Labelframe(col, text=" 2. A legenda ")
        dois.pack(fill="x", padx=12, pady=(10, 0))
        ttk.Button(dois, text="Escolher a legenda...",
                   command=self._pegar_legenda).pack(fill="x", padx=10,
                                                     pady=(10, 6))
        ttk.Label(dois,
                  text="O .docx ou .txt que saiu da aba “Limpar transcrição”.",
                  style="Rodape.TLabel", wraplength=380,
                  justify="left").pack(anchor="w", padx=10)
        ttk.Label(dois, textvariable=self.var_legenda, style="Suave.TLabel",
                  wraplength=380, justify="left").pack(anchor="w", padx=10,
                                                       pady=(4, 10))

        # ---- 3. pasta de saida
        tres = ttk.Labelframe(col, text=" 3. Onde salvar o corrigido ")
        tres.pack(fill="x", padx=12, pady=(10, 0))
        linha = ttk.Frame(tres)
        linha.pack(fill="x", padx=10, pady=10)
        ttk.Button(linha, text="Trocar pasta...",
                   command=self._trocar_pasta).pack(side="left")
        ttk.Label(linha, textvariable=self.var_saida, style="Rodape.TLabel",
                  wraplength=230, justify="left").pack(side="left", padx=(8, 0))

        # ---- abrir
        self.bt_abrir = ttk.Button(col, text="Abrir a tela de trabalho",
                                   style="Acao.TButton", state="disabled",
                                   command=self._abrir)
        self.bt_abrir.pack(fill="x", padx=12, pady=(14, 0))

        ttk.Label(col,
                  text="A tela de trabalho abre no seu navegador, porque é\n"
                       "lá que o vídeo toca com som. Nada sai do computador.",
                  style="Rodape.TLabel", justify="left").pack(anchor="w",
                                                              padx=12,
                                                              pady=(6, 0))

        self.bt_fechar = ttk.Button(col, text="Encerrar a tela de trabalho",
                                    state="disabled", command=self._encerrar)
        self.bt_fechar.pack(fill="x", padx=12, pady=(8, 0))

        ttk.Label(col, textvariable=self.var_status, style="Destaque.TLabel",
                  wraplength=400, justify="left").pack(anchor="w", padx=12,
                                                       pady=(14, 0))

        self.bt_pasta = ttk.Button(col, text="Abrir a pasta dos arquivos",
                                   command=self._abrir_pasta)
        # So aparece depois que algo foi salvo.

    # --------------------------------------------------------------- escolhas

    def _pegar_video(self):
        caminho = filedialog.askopenfilename(title="Escolha o vídeo",
                                             filetypes=TIPOS_VIDEO,
                                             parent=self.raiz)
        if not caminho:
            return
        extensao = os.path.splitext(caminho)[1].lower()
        if extensao not in servidor_legenda.TOCAVEIS:
            if not messagebox.askyesno(
                    self.programa,
                    "O navegador provavelmente não toca arquivos %s.\n\n"
                    "O mais seguro é converter para MP4 antes.\n\n"
                    "Quer tentar assim mesmo?" % extensao,
                    parent=self.raiz):
                return
        self.video = caminho
        self.var_video.set(os.path.basename(caminho))
        self._conferir()
        self._conferir_pulo(caminho)

    # ---------------------------------------------- video pronto para pular?

    def _conferir_pulo(self, caminho):
        """Avisa (e resolve) quando o video demora a pular para o meio.

        Num MP4 gravado sem "faststart", o indice fica no FIM do arquivo. Para
        pular para o minuto 36, o navegador tem que baixar quase o arquivo
        inteiro antes - e a espera parece eternidade, mesmo com o video no
        proprio disco. Nao e lentidao do servidor: e o formato do arquivo, e
        aconteceria em qualquer programa.

        O conserto nao recodifica nada: so move o indice para o comeco. Leva
        segundos e nao perde um pixel de qualidade.
        """
        if servidor_legenda.preparado_para_pular(caminho) is not False:
            return

        ffmpeg = achar_ffmpeg()
        if not ffmpeg:
            messagebox.showwarning(
                self.programa,
                "Este vídeo não está preparado para pular para o meio: o "
                "índice dele está no fim do arquivo.\n\nDá para trabalhar "
                "assim, mas cada pulo vai demorar. Para resolver, abra o "
                "Media Studio (que traz o conversor junto) e escolha o vídeo "
                "por lá.",
                parent=self.raiz)
            return

        if not messagebox.askyesno(
                self.programa,
                "Este vídeo não está preparado para pular para o meio: o "
                "índice dele está no fim do arquivo, então cada pulo vai "
                "demorar bastante.\n\nQuer que eu prepare uma cópia agora? "
                "Não recodifica nada e não perde qualidade: só move o índice "
                "para o começo. Leva alguns segundos.",
                parent=self.raiz):
            return

        destino = os.path.join(
            pastas.garantir(self.var_saida.get()),
            os.path.splitext(os.path.basename(caminho))[0] + " (preparado).mp4")
        self.rodando = True
        self.bt_abrir.configure(state="disabled")
        self.var_status.set("Preparando o vídeo... isso leva alguns segundos.")

        def trabalhar():
            try:
                subprocess.run(
                    [ffmpeg, "-y", "-i", caminho, "-c", "copy",
                     "-movflags", "+faststart", destino],
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                    check=True)
                self.recados.put(("preparado", destino))
            except subprocess.CalledProcessError as e:
                erro = (e.stderr or b"").decode("utf-8", "ignore")[-400:]
                self.recados.put(("erro", erro))
            except Exception as e:
                self.recados.put(("erro", str(e)))

        threading.Thread(target=trabalhar, daemon=True).start()

    def _pegar_legenda(self):
        caminho = filedialog.askopenfilename(title="Escolha a legenda",
                                             filetypes=TIPOS_LEGENDA,
                                             parent=self.raiz)
        if not caminho:
            return
        try:
            paragrafos = ler_paragrafos(caminho)
            titulo, data, segmentos, falantes = legenda_mod.ler(paragrafos)
        except Exception as e:
            messagebox.showerror(self.programa, str(e), parent=self.raiz)
            return

        self.arquivo_legenda = caminho
        self.titulo, self.data = titulo, data
        self.segmentos, self.falantes = segmentos, falantes

        quantas, nomes, fim = legenda_mod.resumo(segmentos)
        self.var_legenda.set(
            "%s\n%d falas · %d falantes · vai até %s"
            % (os.path.basename(caminho), quantas, len(nomes),
               legenda_mod.formatar(fim)))
        self._conferir()

    def _trocar_pasta(self):
        pasta = filedialog.askdirectory(title="Onde salvar",
                                        initialdir=self.var_saida.get(),
                                        parent=self.raiz)
        if pasta:
            self.var_saida.set(pasta)

    def _conferir(self):
        pronto = bool(self.video and self.segmentos)
        self.bt_abrir.configure(state="normal" if pronto else "disabled")
        if pronto:
            self.var_status.set("Pronto. Clique em abrir a tela de trabalho.")
        else:
            falta = "o vídeo" if not self.video else "a legenda"
            self.var_status.set("Falta escolher %s." % falta)

    # ------------------------------------------------------ tela de trabalho

    def _abrir(self):
        if self.servidor is not None:
            webbrowser.open(self.servidor.url)
            self.var_status.set("A tela de trabalho já estava aberta.")
            return

        nome = os.path.splitext(os.path.basename(self.arquivo_legenda))[0]
        sessao = servidor_legenda.Sessao(
            video=self.video, titulo=self.titulo or nome, data=self.data,
            segmentos=self.segmentos, falantes=self.falantes,
            saida=pastas.garantir(self.var_saida.get()), nome=nome)
        try:
            self.servidor = servidor_legenda.Servidor(
                sessao, aviso=lambda caminhos: self.recados.put(caminhos))
        except Exception as e:
            messagebox.showerror(
                self.programa,
                "Não consegui abrir a tela de trabalho.\n\n%s" % e,
                parent=self.raiz)
            return

        webbrowser.open(self.servidor.url)
        self.bt_fechar.configure(state="normal")
        self.var_status.set(
            "Tela de trabalho aberta no navegador. Deixe este programa "
            "aberto enquanto você trabalha: é ele que serve o vídeo.")

    def _encerrar(self):
        if self.servidor is None:
            return
        if not messagebox.askyesno(
                self.programa,
                "Encerrar a tela de trabalho?\n\nO que ainda não foi salvo "
                "no navegador se perde. Salve lá antes, se for o caso.",
                parent=self.raiz):
            return
        self._parar()
        self.var_status.set("Tela de trabalho encerrada.")

    def _parar(self):
        if self.servidor is not None:
            self.servidor.parar()
            self.servidor = None
        try:
            self.bt_fechar.configure(state="disabled")
        except Exception:
            pass      # a janela ja pode estar sendo destruida

    # ------------------------------------------------------------- resultado

    def _ler_recados(self):
        """O servidor avisa por fila quando gravou algo: a interface do Tk so
        pode ser mexida pela thread da janela, nunca pela do servidor."""
        try:
            while True:
                recado = self.recados.get_nowait()

                if isinstance(recado, tuple) and recado[0] == "preparado":
                    self.rodando = False
                    self.video = recado[1]
                    self.var_video.set(os.path.basename(recado[1])
                                       + "\n(cópia preparada para pular rápido)")
                    self.var_status.set("Vídeo preparado. Pode abrir a tela "
                                        "de trabalho.")
                    self._conferir()
                    continue

                if isinstance(recado, tuple) and recado[0] == "auto":
                    # Salvamento automatico: conta discretamente, sem roubar
                    # a tela de quem esta trabalhando no navegador.
                    from time import strftime
                    self.var_status.set(
                        "Salvando sozinho (última vez às %s) em %s"
                        % (strftime("%H:%M"), os.path.dirname(recado[1][0])))
                    self.bt_pasta.pack(fill="x", padx=12, pady=(8, 0))
                    continue

                if isinstance(recado, tuple) and recado[0] == "erro":
                    self.rodando = False
                    self._conferir()
                    messagebox.showerror(
                        self.programa,
                        "Não consegui preparar o vídeo. Dá para trabalhar com "
                        "o original assim mesmo, só que os pulos vão "
                        "demorar.\n\n%s" % recado[1], parent=self.raiz)
                    continue

                caminhos = recado
                # O que foi gravado e ONDE: nome de arquivo sem caminho deixa
                # a pessoa procurando, e caminho sem nome nao diz o que abrir.
                self.var_status.set(
                    "Gravado em %s:\n%s"
                    % (os.path.dirname(caminhos[0]),
                       "\n".join(os.path.basename(c) for c in caminhos)))
                self.bt_pasta.pack(fill="x", padx=12, pady=(8, 0))
        except queue.Empty:
            pass
        try:
            self.raiz.after(400, self._ler_recados)
        except Exception:
            pass      # janela fechada

    def _abrir_pasta(self):
        pasta = self.var_saida.get()
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", pasta])
            elif os.name == "nt":
                os.startfile(pasta)             # noqa: so existe no Windows
            else:
                subprocess.Popen(["xdg-open", pasta])
        except Exception:
            messagebox.showinfo(self.programa, pasta, parent=self.raiz)

    # ------------------------------------------------------------ fechamento

    def ao_fechar(self):
        self._parar()


def montar(pai, programa="Transcript Studio"):
    return AbaSincronizar(pai, programa=programa)
