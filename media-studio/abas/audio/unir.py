"""
Unir Audios - aba do Audio Studio.

Junta varios audios de uma pasta num unico arquivo longo, na ordem certa e com
transicao entre um bloco e o outro.

O que ele resolve:
  - **Ordem humana.** Arquivos como 1_1, 2_1, ..., 10_1, 36_1 entram na ordem
    1, 2, 3 ... 10 ... 36 (e nao 1, 10, 11, 2 como faz a ordem alfabetica);
  - **Transicao.** Pausa curta com fade (bom para fala), crossfade (bom para
    musica) ou corte seco;
  - **Volume igual.** Blocos gravados em dias diferentes ficam no mesmo nivel;
  - **Capitulos.** Grava os marcadores dentro do mp3 e salva um .txt com os
    tempos de cada bloco, para colar na descricao do episodio.

Notas de interface (macOS no modo escuro):
  - as cores vem todas de `tema.py`, que e quem pinta a janela inteira do
    Estudio; esta aba nao define estilo nenhum, so usa a paleta;
  - a lista e a caixa de mensagens sao widgets Tk puros, entao recebem cor na
    mao.

O ffmpeg vem embutido no executavel final (via PyInstaller --add-binary).
Em desenvolvimento, usa o ffmpeg do PATH se existir.
"""

import os
import re
import sys
import queue
import shutil
import subprocess
import tempfile
import threading
from shutil import which
from tkinter import (
    StringVar, BooleanVar, DoubleVar, Listbox, Text, END, SINGLE,
    filedialog, messagebox, ttk,
)

import pastas
import tema
from tema import (COR_FUNDO, COR_PAINEL, COR_CAMPO, COR_BORDA, COR_TEXTO,
                  COR_DESTAQUE)


APP_NAME = "Unir Audios"
APP_VERSION = "1.2.0"

EXTENSOES_AUDIO = {
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus",
    ".wma", ".aiff", ".aif",
}

# Transicoes
TR_PAUSA = "Pausa curta com fade (recomendado para fala)"
TR_CROSSFADE = "Crossfade (um bloco entra por cima do outro)"
TR_SECO = "Corte seco (sem transicao)"
TRANSICOES = [TR_PAUSA, TR_CROSSFADE, TR_SECO]

QUALIDADES = ["128 kbps", "160 kbps", "192 kbps", "256 kbps", "320 kbps"]
QUALIDADE_PADRAO = "192 kbps"

# Alvo de volume usado quando a pessoa pede para igualar os blocos.
# -16 LUFS e o valor usado pelas plataformas de podcast.
LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"

TAXA = 44100
PREVIA_SEGUNDOS = 15.0


# ---------------------------------------------------------------------------
# Localizacao do ffmpeg / ffprobe
# ---------------------------------------------------------------------------
def resource_path(rel: str) -> str:
    """Resolve caminho de arquivo embutido pelo PyInstaller (onefile/onedir).

    A aba mora em `abas/`, entao a pasta de referencia e a de cima, que e onde
    o ffmpeg embutido fica.
    """
    base = getattr(sys, "_MEIPASS",
                   os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, rel)


def _achar_binario(nome: str):
    """Procura um binario embutido junto ao executavel, depois no PATH."""
    exe = f"{nome}.exe" if os.name == "nt" else nome
    candidatos = [
        resource_path(exe),
        resource_path(os.path.join("ffmpeg", exe)),
        resource_path(os.path.join("bin", exe)),
    ]
    for c in candidatos:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c

    achado = which(nome)
    if achado:
        return achado

    # Aplicativo aberto por clique duplo costuma vir com PATH curto: procura
    # nos lugares mais comuns de instalacao no Mac e no Linux.
    for pasta in ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin",
                  "/opt/local/bin"):
        c = os.path.join(pasta, exe)
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def _sem_janela():
    """Impede o piscar do console preto no Windows."""
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {"startupinfo": si, "creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


# ---------------------------------------------------------------------------
# Leitura de duracao
# ---------------------------------------------------------------------------
RE_DURACAO = re.compile(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)")


def duracao_do_audio(caminho: str, ffprobe: str, ffmpeg: str) -> float:
    """Duracao em segundos. Usa o ffprobe; sem ele, le a saida do ffmpeg."""
    if ffprobe:
        try:
            saida = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", caminho],
                capture_output=True, text=True, **_sem_janela()
            ).stdout.strip()
            valor = float(saida)
            if valor > 0:
                return valor
        except Exception:
            pass

    if ffmpeg:
        try:
            proc = subprocess.run(
                [ffmpeg, "-hide_banner", "-i", caminho],
                capture_output=True, text=True, **_sem_janela()
            )
            m = RE_DURACAO.search(proc.stderr or "")
            if m:
                h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
                return h * 3600 + mi * 60 + s
        except Exception:
            pass
    return 0.0


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def chave_natural(nome: str):
    """Ordena '2_1' antes de '10_1' (a ordem alfabetica faria o contrario)."""
    partes = re.split(r"(\d+)", nome.lower())
    return [int(p) if p.isdigit() else p for p in partes]


def hms(segundos: float, com_centesimos: bool = False) -> str:
    if segundos < 0:
        segundos = 0
    total = int(segundos)
    h, resto = divmod(total, 3600)
    m, s = divmod(resto, 60)
    if com_centesimos:
        return f"{h:02d}:{m:02d}:{s:02d}.{int((segundos - total) * 100):02d}"
    return f"{h:02d}:{m:02d}:{s:02d}"


def duracao_amigavel(segundos: float) -> str:
    total = int(round(segundos))
    h, resto = divmod(total, 3600)
    m, s = divmod(resto, 60)
    if h:
        return f"{h} h {m:02d} min"
    if m:
        return f"{m} min {s:02d} s"
    return f"{s} s"


def escapar_metadata(texto: str) -> str:
    """Escapa os caracteres reservados do formato ffmetadata."""
    for c in ("\\", "=", ";", "#", "\n"):
        texto = texto.replace(c, "\\" + c if c != "\n" else " ")
    return texto


# ---------------------------------------------------------------------------
# Montagem do filtro do ffmpeg
# ---------------------------------------------------------------------------
FORMATO = f"aresample={TAXA},aformat=sample_fmts=fltp:channel_layouts=stereo"


def _cadeia_entrada(indice: int, normalizar: bool) -> str:
    cadeia = f"[{indice}:a]{FORMATO}"
    if normalizar:
        # O loudnorm reamostra internamente, por isso o formato e reaplicado.
        cadeia += f",{LOUDNORM},{FORMATO}"
    return cadeia


def montar_filtro(duracoes, transicao: str, fade: float, pausa: float,
                  normalizar: bool):
    """Devolve (texto_do_filtro, duracao_final, inicios_dos_blocos)."""
    n = len(duracoes)

    if n == 1:
        d = duracoes[0]
        cadeia = _cadeia_entrada(0, normalizar)
        f = min(fade, d / 2) if transicao != TR_SECO else 0.0
        if f > 0.05:
            cadeia += (f",afade=t=in:st=0:d={f:.3f}"
                       f",afade=t=out:st={max(0.0, d - f):.3f}:d={f:.3f}")
        return cadeia + "[aout]", d, [0.0]

    if transicao == TR_CROSSFADE:
        # Os blocos se sobrepoem: a duracao final encurta a cada juncao.
        partes = [f"{_cadeia_entrada(i, normalizar)}[a{i}]" for i in range(n)]
        anterior = "[a0]"
        for i in range(1, n):
            saida = "[aout_bruto]" if i == n - 1 else f"[x{i}]"
            partes.append(
                f"{anterior}[a{i}]acrossfade=d={fade:.3f}:c1=tri:c2=tri{saida}"
            )
            anterior = saida

        total = sum(duracoes) - fade * (n - 1)
        inicios, acumulado = [], 0.0
        for i, d in enumerate(duracoes):
            inicios.append(acumulado)
            acumulado += d - (fade if i < n - 1 else 0.0)

        # Fade nas duas pontas do episodio inteiro.
        remate = min(fade, total / 2)
        partes.append(
            f"[aout_bruto]afade=t=in:st=0:d={remate:.3f}"
            f",afade=t=out:st={max(0.0, total - remate):.3f}:d={remate:.3f}[aout]"
        )
        return ";".join(partes), total, inicios

    # Pausa com fade, ou corte seco: os blocos entram inteiros, em sequencia.
    usa_fade = transicao == TR_PAUSA
    gap = pausa if usa_fade else 0.0

    partes, rotulos = [], []
    for i, d in enumerate(duracoes):
        cadeia = _cadeia_entrada(i, normalizar)
        if usa_fade:
            f = min(fade, d / 2)
            if f > 0.05:
                cadeia += (f",afade=t=in:st=0:d={f:.3f}"
                           f",afade=t=out:st={max(0.0, d - f):.3f}:d={f:.3f}")
        partes.append(f"{cadeia}[a{i}]")
        rotulos.append(f"[a{i}]")

        if gap > 0 and i < len(duracoes) - 1:
            partes.append(
                f"anullsrc=r={TAXA}:cl=stereo,atrim=duration={gap:.3f},"
                f"aformat=sample_fmts=fltp:channel_layouts=stereo[s{i}]"
            )
            rotulos.append(f"[s{i}]")

    partes.append(
        "".join(rotulos) + f"concat=n={len(rotulos)}:v=0:a=1[aout]"
    )

    total = sum(duracoes) + gap * (n - 1)
    inicios, acumulado = [], 0.0
    for d in duracoes:
        inicios.append(acumulado)
        acumulado += d + gap
    return ";".join(partes), total, inicios


def texto_ffmetadata(titulo: str, nomes, inicios, duracoes, total: float) -> str:
    linhas = [";FFMETADATA1"]
    if titulo:
        linhas.append(f"title={escapar_metadata(titulo)}")
        linhas.append(f"album={escapar_metadata(titulo)}")
    linhas.append("genre=Podcast")
    for i, nome in enumerate(nomes):
        inicio_ms = int(round(inicios[i] * 1000))
        fim = inicios[i + 1] if i + 1 < len(inicios) else total
        fim_ms = max(inicio_ms + 1, int(round(fim * 1000)))
        linhas += [
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={inicio_ms}",
            f"END={fim_ms}",
            f"title={escapar_metadata(nome)}",
        ]
    return "\n".join(linhas) + "\n"


# ---------------------------------------------------------------------------
# Aplicativo
# ---------------------------------------------------------------------------
class Aplicativo:

    def __init__(self, pai):
        self.raiz = pai
        self.raiz.configure(bg=COR_FUNDO)

        self.ffmpeg = _achar_binario("ffmpeg")
        self.ffprobe = _achar_binario("ffprobe")

        self.arquivos = []      # caminhos, na ordem de montagem
        self.duracoes = {}      # caminho -> segundos
        self.pasta = ""
        self.rodando = False
        self.cancelar = threading.Event()
        self.processo = None
        self.fila = queue.Queue()
        self._vivo = True

        # O estilo e global, aplicado uma vez pelo Estudio; aqui so se pegam
        # as fontes para os widgets Tk puros (a lista e a caixa de mensagens).
        self.fonte_base, self.fonte_peq, self.fonte_mini = tema.fontes()

        self._montar()
        self.raiz.after(100, self._consumir_fila)

        if not self.ffmpeg:
            self.log("ATENCAO: o ffmpeg nao foi encontrado nesta maquina. "
                     "Sem ele o programa nao processa audio. No executavel "
                     "publicado o ffmpeg ja vem junto.")

        # Regra da casa: o arquivo final nasce na pasta de Downloads.
        self.var_saida.set(os.path.join(pastas.pasta_downloads(),
                                        "audios-unidos.mp3"))

        # A aba NAO carrega pasta nenhuma sozinha. Isso ja assustou: ela
        # varria a pasta de Downloads e a lista aparecia cheia de arquivos que
        # a pessoa nao tinha pedido, dando a impressao de que o programa ia
        # mexer neles. Quem escolhe o que entra e a pessoa, no botao.

    # ------------------------------------------------------------- montagem
    def _montar(self):
        # Os botoes de acao e o registro de mensagens sao ancorados no FUNDO e
        # empacotados ANTES do resto: no Tk, quando falta altura, quem foi
        # empacotado por ultimo e cortado primeiro. Assim a lista de blocos e
        # que cede espaco, e o botao de montar nunca some da tela.
        registro = ttk.Frame(self.raiz)
        registro.pack(side="bottom", fill="x", padx=14, pady=(4, 10))

        self.texto = Text(registro, height=4, wrap="word", relief="flat",
                          borderwidth=0, highlightthickness=1,
                          bg=COR_PAINEL, fg=COR_TEXTO,
                          insertbackground=COR_TEXTO,
                          selectbackground=COR_DESTAQUE,
                          selectforeground="#1a1a1a",
                          highlightbackground=COR_BORDA,
                          highlightcolor=COR_BORDA,
                          font=self.fonte_peq)
        self.texto.pack(fill="both", expand=True)

        acoes = ttk.Frame(self.raiz)
        acoes.pack(side="bottom", fill="x", padx=14, pady=(6, 0))

        self.bt_montar = ttk.Button(acoes, text="Unir audios",
                                    style="Acao.TButton", command=self.montar)
        self.bt_montar.pack(side="left")
        self.bt_cancelar = ttk.Button(acoes, text="Cancelar",
                                      command=self.pedir_cancelamento,
                                      state="disabled")
        self.bt_cancelar.pack(side="left", padx=8)

        self.var_status = StringVar(value="Pronto.")
        ttk.Label(acoes, textvariable=self.var_status,
                  style="Suave.TLabel").pack(side="right")

        self.barra = ttk.Progressbar(acoes, mode="determinate", maximum=100)
        self.barra.pack(side="left", fill="x", expand=True, padx=(12, 12))

        # ------------------------------------------------------- 1. a pasta
        topo = ttk.Frame(self.raiz)
        topo.pack(fill="x", padx=14, pady=(8, 0))

        ttk.Label(topo, text="Pasta com os audios:").pack(side="left")
        self.var_pasta = StringVar()
        ttk.Entry(topo, textvariable=self.var_pasta).pack(
            side="left", fill="x", expand=True, padx=(8, 0))
        ttk.Button(topo, text="Escolher...", command=self.escolher_pasta
                   ).pack(side="left", padx=(8, 0))
        ttk.Button(topo, text="Recarregar", command=self.recarregar
                   ).pack(side="left", padx=(6, 0))

        self.var_resumo = StringVar(value="Nenhuma pasta carregada.")
        ttk.Label(self.raiz, textvariable=self.var_resumo,
                  style="Suave.TLabel").pack(anchor="w", padx=14, pady=(4, 0))

        corpo = ttk.Frame(self.raiz)
        corpo.pack(fill="both", expand=True, padx=14, pady=(6, 0))

        # ---------- esquerda: a ordem dos blocos
        cx2 = ttk.LabelFrame(corpo, text="Ordem dos blocos ")
        cx2.pack(side="left", fill="both", expand=True, padx=(0, 12))

        interno = ttk.Frame(cx2)
        interno.pack(fill="both", expand=True, padx=10, pady=8)

        self.lista = Listbox(interno, selectmode=SINGLE, activestyle="none",
                             height=8, relief="flat", borderwidth=0,
                             highlightthickness=1,
                             bg=COR_CAMPO, fg=COR_TEXTO,
                             selectbackground=COR_DESTAQUE,
                             selectforeground="#1a1a1a",
                             highlightbackground=COR_BORDA,
                             highlightcolor=COR_BORDA,
                             font=("Menlo" if sys.platform == "darwin"
                                   else "Consolas", 11))
        self.lista.pack(side="left", fill="both", expand=True)
        barra = ttk.Scrollbar(interno, orient="vertical",
                              command=self.lista.yview)
        barra.pack(side="left", fill="y")
        self.lista.configure(yscrollcommand=barra.set)

        botoes = ttk.Frame(interno)
        botoes.pack(side="left", fill="y", padx=(10, 0))
        for texto, acao in (("Subir", self.subir), ("Descer", self.descer),
                            ("Remover", self.remover),
                            ("Ordem original", self.recarregar)):
            ttk.Button(botoes, text=texto, width=14, command=acao).pack(pady=2)

        # ---------- direita: transicao e arquivo final
        dir_ = ttk.Frame(corpo)
        dir_.pack(side="left", fill="y")

        cx3 = ttk.LabelFrame(dir_, text="Transicao entre os blocos ")
        cx3.pack(fill="x")

        self.var_transicao = StringVar(value=TR_PAUSA)
        ttk.Combobox(cx3, textvariable=self.var_transicao, values=TRANSICOES,
                     state="readonly", width=44).pack(anchor="w", padx=10,
                                                      pady=(8, 0))
        # A reacao fica presa na VARIAVEL, e nao no evento do Combobox: assim
        # ela dispara tambem quando o valor muda por codigo.
        self.var_transicao.trace_add(
            "write", lambda *a: self._atualizar_estimativa())

        tempos = ttk.Frame(cx3)
        tempos.pack(fill="x", padx=10, pady=(6, 8))

        ttk.Label(tempos, text="Fade (s):").pack(side="left")
        self.var_fade = DoubleVar(value=1.5)
        ttk.Spinbox(tempos, from_=0.0, to=10.0, increment=0.5, width=5,
                    textvariable=self.var_fade).pack(side="left", padx=(6, 14))

        ttk.Label(tempos, text="Pausa (s):").pack(side="left")
        self.var_pausa = DoubleVar(value=0.8)
        ttk.Spinbox(tempos, from_=0.0, to=10.0, increment=0.1, width=5,
                    textvariable=self.var_pausa).pack(side="left", padx=(6, 14))

        # Mesmo motivo do Combobox acima: o `command` do Spinbox so dispara
        # quando a pessoa clica nas setinhas, e o valor tambem muda quando ela
        # digita dentro do campo.
        for v in (self.var_fade, self.var_pausa):
            v.trace_add("write", lambda *a: self._atualizar_estimativa())

        ttk.Button(tempos, text="Ouvir a previa",
                   command=self.previa).pack(side="left")

        cx4 = ttk.LabelFrame(dir_, text="Arquivo final ")
        cx4.pack(fill="x", pady=(10, 0))

        l1 = ttk.Frame(cx4)
        l1.pack(fill="x", padx=10, pady=(8, 0))
        ttk.Label(l1, text="Titulo:", width=9).pack(side="left")
        self.var_titulo = StringVar(value="Audios unidos")
        ttk.Entry(l1, textvariable=self.var_titulo, width=20).pack(side="left")
        ttk.Label(l1, text="Qualidade:").pack(side="left", padx=(12, 6))
        self.var_qualidade = StringVar(value=QUALIDADE_PADRAO)
        ttk.Combobox(l1, textvariable=self.var_qualidade, values=QUALIDADES,
                     state="readonly", width=10).pack(side="left")

        l2 = ttk.Frame(cx4)
        l2.pack(fill="x", padx=10, pady=(6, 0))
        ttk.Label(l2, text="Salvar em:", width=9).pack(side="left")
        self.var_saida = StringVar()
        ttk.Entry(l2, textvariable=self.var_saida).pack(
            side="left", fill="x", expand=True)
        ttk.Button(l2, text="Escolher...", command=self.escolher_saida).pack(
            side="left", padx=(8, 0))

        self.var_normalizar = BooleanVar(value=True)
        ttk.Checkbutton(cx4, text="Deixar todos os blocos no mesmo volume",
                        variable=self.var_normalizar).pack(
            anchor="w", padx=10, pady=(6, 0))
        self.var_capitulos = BooleanVar(value=True)
        ttk.Checkbutton(cx4, text="Gravar capitulos no arquivo",
                        variable=self.var_capitulos).pack(anchor="w", padx=10)
        self.var_txt = BooleanVar(value=True)
        ttk.Checkbutton(cx4, text="Salvar a lista de tempos em .txt",
                        variable=self.var_txt).pack(anchor="w", padx=10,
                                                    pady=(0, 8))

    # ------------------------------------------------------------- mensagens
    def log(self, msg: str):
        self.texto.insert(END, msg.rstrip() + "\n")
        self.texto.see(END)

    def _consumir_fila(self):
        if not self._vivo:
            return
        try:
            while True:
                tipo, valor = self.fila.get_nowait()
                if tipo == "log":
                    self.log(valor)
                elif tipo == "status":
                    self.var_status.set(valor)
                elif tipo == "progresso":
                    self.barra.configure(value=valor)
                elif tipo == "resumo":
                    # Recalculado aqui, na thread da janela: ler as variaveis
                    # do Tkinter fora dela quebra o Tcl.
                    self.var_resumo.set(self._texto_resumo())
                elif tipo == "lista":
                    self._pintar_lista()
                elif tipo == "fim":
                    self._destravar()
                elif tipo == "erro":
                    messagebox.showerror(
                        APP_NAME, valor,
                        parent=self.raiz.winfo_toplevel())
                elif tipo == "ok":
                    messagebox.showinfo(
                        APP_NAME, valor,
                        parent=self.raiz.winfo_toplevel())
        except queue.Empty:
            pass
        self.raiz.after(100, self._consumir_fila)

    def enviar(self, tipo, valor=None):
        self.fila.put((tipo, valor))

    # ----------------------------------------------------------- a pasta
    def escolher_pasta(self):
        if self.rodando:
            return
        pasta = filedialog.askdirectory(
            title="Escolha a pasta com os audios",
            initialdir=self.var_pasta.get() or pastas.pasta_downloads(),
            parent=self.raiz.winfo_toplevel())
        if pasta:
            self.carregar_pasta(pasta)

    def recarregar(self):
        if self.pasta:
            self.carregar_pasta(self.pasta)

    def carregar_pasta(self, pasta: str):
        if self.rodando:
            return
        if not os.path.isdir(pasta):
            messagebox.showerror(APP_NAME, "Essa pasta nao existe.",
                                 parent=self.raiz.winfo_toplevel())
            return

        self.pasta = pasta
        self.var_pasta.set(pasta)

        if not self.var_saida.get():
            self.var_saida.set(os.path.join(pastas.pasta_downloads(),
                                            "audios-unidos.mp3"))

        # O episodio final pode estar na mesma pasta dos blocos. Ele fica fora
        # da lista: sem isso, na segunda montagem o podcast anterior entraria
        # como se fosse mais um bloco.
        proprio = os.path.abspath(self.var_saida.get())

        nomes = [n for n in os.listdir(pasta)
                 if not n.startswith(".")
                 and os.path.splitext(n)[1].lower() in EXTENSOES_AUDIO
                 and os.path.isfile(os.path.join(pasta, n))
                 and os.path.abspath(os.path.join(pasta, n)) != proprio]
        nomes.sort(key=chave_natural)
        self.arquivos = [os.path.join(pasta, n) for n in nomes]

        if not self.arquivos:
            self.var_resumo.set("Nenhum audio encontrado nessa pasta.")
            self.lista.delete(0, END)
            return

        self.log(f"{len(self.arquivos)} audios encontrados em {pasta}")
        self._pintar_lista()
        self.var_resumo.set(f"{len(self.arquivos)} audios — lendo as duracoes...")
        threading.Thread(target=self._ler_duracoes,
                         args=(list(self.arquivos),), daemon=True).start()

    def _ler_duracoes(self, arquivos):
        for i, caminho in enumerate(arquivos, 1):
            if caminho not in self.duracoes:
                self.duracoes[caminho] = duracao_do_audio(
                    caminho, self.ffprobe, self.ffmpeg)
            self.enviar("status", f"Lendo as duracoes... {i}/{len(arquivos)}")
        self.enviar("lista")
        self.enviar("status", "Pronto.")
        self.enviar("resumo")

    def _texto_resumo(self) -> str:
        n = len(self.arquivos)
        soma = sum(self.duracoes.get(c, 0.0) for c in self.arquivos)
        if soma <= 0:
            return f"{n} audios na fila."
        total, _ = self._estimativa()
        return (f"{n} audios • {duracao_amigavel(soma)} de audio • "
                f"episodio final de aproximadamente {duracao_amigavel(total)}")

    def _estimativa(self):
        """(duracao final estimada, duracao mais curta da fila)."""
        duracoes = [self.duracoes.get(c, 0.0) for c in self.arquivos]
        if not duracoes:
            return 0.0, 0.0
        n = len(duracoes)
        transicao = self.var_transicao.get()
        if transicao == TR_CROSSFADE:
            total = sum(duracoes) - self._num(self.var_fade) * (n - 1)
        elif transicao == TR_PAUSA:
            total = sum(duracoes) + self._num(self.var_pausa) * (n - 1)
        else:
            total = sum(duracoes)
        return max(0.0, total), min(d for d in duracoes) if duracoes else 0.0

    def _atualizar_estimativa(self):
        if self.arquivos:
            self.var_resumo.set(self._texto_resumo())

    @staticmethod
    def _num(var) -> float:
        try:
            return max(0.0, float(var.get()))
        except Exception:
            return 0.0

    def _ajustes(self) -> dict:
        """Fotografa o que esta marcado na tela.

        Toda a leitura das variaveis do Tkinter acontece aqui, na thread da
        janela. As threads de trabalho recebem este dicionario pronto: ler um
        widget de outra thread quebra o Tcl ("main thread is not in main
        loop").
        """
        return {
            "transicao": self.var_transicao.get(),
            "fade": self._num(self.var_fade),
            "pausa": self._num(self.var_pausa),
            "normalizar": bool(self.var_normalizar.get()),
            "capitulos": bool(self.var_capitulos.get()),
            "txt": bool(self.var_txt.get()),
            "titulo": self.var_titulo.get().strip(),
            "kbps": self.var_qualidade.get().split()[0],
        }

    # ------------------------------------------------------------- a ordem
    def _pintar_lista(self):
        guardada = self.lista.curselection()
        self.lista.delete(0, END)
        for i, caminho in enumerate(self.arquivos, 1):
            dur = self.duracoes.get(caminho)
            marca = hms(dur) if dur else "  --:--  "
            self.lista.insert(
                END, f"{i:>3}.  {marca}   {os.path.basename(caminho)}")
        if guardada:
            indice = min(guardada[0], self.lista.size() - 1)
            if indice >= 0:
                self.lista.selection_set(indice)
                self.lista.activate(indice)

    def _selecionado(self):
        sel = self.lista.curselection()
        return sel[0] if sel else None

    def _mover(self, passo: int):
        if self.rodando:
            return
        i = self._selecionado()
        if i is None:
            return
        j = i + passo
        if j < 0 or j >= len(self.arquivos):
            return
        self.arquivos[i], self.arquivos[j] = self.arquivos[j], self.arquivos[i]
        self._pintar_lista()
        self.lista.selection_clear(0, END)
        self.lista.selection_set(j)
        self.lista.activate(j)

    def subir(self):
        self._mover(-1)

    def descer(self):
        self._mover(1)

    def remover(self):
        if self.rodando:
            return
        i = self._selecionado()
        if i is None:
            return
        fora = self.arquivos.pop(i)
        self.log(f"Fora da montagem: {os.path.basename(fora)}")
        self._pintar_lista()
        self.var_resumo.set(self._texto_resumo())

    def escolher_saida(self):
        if self.rodando:
            return
        atual = self.var_saida.get()
        destino = filedialog.asksaveasfilename(
            title="Salvar o podcast como",
            defaultextension=".mp3",
            filetypes=[("MP3", "*.mp3")],
            initialdir=os.path.dirname(atual) or pastas.pasta_downloads(),
            initialfile=os.path.basename(atual) or "audios-unidos.mp3",
            parent=self.raiz.winfo_toplevel())
        if destino:
            self.var_saida.set(destino)

    # -------------------------------------------------------- verificacoes
    def _conferir(self):
        """Devolve uma mensagem de erro, ou None quando esta tudo certo."""
        if not self.ffmpeg:
            return ("O ffmpeg nao foi encontrado nesta maquina, e sem ele nao "
                    "da para processar audio.")
        if not self.arquivos:
            return "Nenhum audio na fila. Escolha a pasta primeiro."
        faltando = [c for c in self.arquivos if not self.duracoes.get(c)]
        if faltando:
            return ("Ainda estou lendo a duracao dos audios (ou nao consegui "
                    f"ler {len(faltando)} deles). Espere um instante e tente "
                    "de novo.")
        if self.var_transicao.get() == TR_CROSSFADE:
            fade = self._num(self.var_fade)
            _, menor = self._estimativa()
            if fade <= 0:
                return ("Para o crossfade o fade tem de ser maior que zero. "
                        "Use o corte seco se nao quiser transicao.")
            if fade >= menor:
                curto = min(self.arquivos,
                            key=lambda c: self.duracoes.get(c, 0.0))
                return (f"O fade de {fade:g} s e maior que o audio mais curto "
                        f"da fila ({os.path.basename(curto)}, "
                        f"{duracao_amigavel(menor)}). Diminua o fade ou tire "
                        "esse arquivo da fila.")
        return None

    # ------------------------------------------------------------- a previa
    def previa(self):
        if self.rodando:
            return
        erro = self._conferir()
        if erro:
            messagebox.showwarning(APP_NAME, erro,
                                   parent=self.raiz.winfo_toplevel())
            return
        if len(self.arquivos) < 2:
            messagebox.showwarning(
                APP_NAME, "A previa precisa de pelo menos dois audios na fila.",
                parent=self.raiz.winfo_toplevel())
            return
        self._travar()
        self.enviar("status", "Preparando a previa...")
        threading.Thread(target=self._rodar_previa, args=(self._ajustes(),),
                         daemon=True).start()

    def _rodar_previa(self, aj: dict):
        temporaria = tempfile.mkdtemp(prefix="previa_podcast_")
        try:
            primeiro, segundo = self.arquivos[0], self.arquivos[1]
            d1 = self.duracoes.get(primeiro, 0.0)
            corte = min(PREVIA_SEGUNDOS, d1)
            a = os.path.join(temporaria, "a.wav")
            b = os.path.join(temporaria, "b.wav")

            self._rodar([self.ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                         "-ss", f"{max(0.0, d1 - corte):.3f}", "-i", primeiro,
                         "-ac", "2", "-ar", str(TAXA), a])
            self._rodar([self.ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                         "-t", f"{PREVIA_SEGUNDOS:.3f}", "-i", segundo,
                         "-ac", "2", "-ar", str(TAXA), b])

            dur_a = duracao_do_audio(a, self.ffprobe, self.ffmpeg)
            dur_b = duracao_do_audio(b, self.ffprobe, self.ffmpeg)
            filtro, _total, _inicios = montar_filtro(
                [dur_a, dur_b], aj["transicao"],
                min(aj["fade"], max(0.5, min(dur_a, dur_b) / 2)),
                aj["pausa"], aj["normalizar"])

            arquivo_filtro = os.path.join(temporaria, "filtro.txt")
            with open(arquivo_filtro, "w", encoding="utf-8") as fh:
                fh.write(filtro)

            destino = os.path.join(temporaria, "previa-da-transicao.mp3")
            self._rodar([self.ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                         "-i", a, "-i", b,
                         "-filter_complex_script", arquivo_filtro,
                         "-map", "[aout]", "-c:a", "libmp3lame", "-b:a", "192k",
                         destino])

            self.enviar("status", "Previa aberta no player do sistema.")
            self.enviar("log", "Previa: os ultimos segundos do primeiro bloco "
                               "com os primeiros do segundo.")
            self._abrir_no_sistema(destino)
        except Exception as e:
            self.enviar("erro", f"Nao consegui gerar a previa.\n\n{e}")
            self.enviar("status", "Pronto.")
        finally:
            self.enviar("fim")

    @staticmethod
    def _abrir_no_sistema(caminho: str):
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", caminho])
            elif os.name == "nt":
                os.startfile(caminho)  # noqa: S606
            else:
                subprocess.Popen(["xdg-open", caminho])
        except Exception:
            pass

    def _rodar(self, comando):
        """Roda um comando curto do ffmpeg e estoura se der erro."""
        proc = subprocess.run(comando, capture_output=True, text=True,
                              **_sem_janela())
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or "").strip()[-800:])

    # ------------------------------------------------------------ a montagem
    def montar(self):
        if self.rodando:
            return
        erro = self._conferir()
        if erro:
            messagebox.showwarning(APP_NAME, erro,
                                   parent=self.raiz.winfo_toplevel())
            return

        destino = self.var_saida.get().strip()
        if not destino:
            messagebox.showwarning(APP_NAME, "Diga onde salvar o arquivo final.",
                                   parent=self.raiz.winfo_toplevel())
            return
        if not destino.lower().endswith(".mp3"):
            destino += ".mp3"
            self.var_saida.set(destino)
        if os.path.abspath(destino) in {os.path.abspath(c)
                                        for c in self.arquivos}:
            messagebox.showwarning(
                APP_NAME, "O arquivo final nao pode ser um dos audios da fila.",
                parent=self.raiz.winfo_toplevel())
            return
        if os.path.exists(destino) and not messagebox.askyesno(
                APP_NAME, f"O arquivo\n\n{destino}\n\nja existe. Substituir?",
                parent=self.raiz.winfo_toplevel()):
            return

        # A pasta de destino pode ainda nao existir (a de Downloads e o padrao,
        # mas a pessoa pode ter digitado outra).
        pastas.garantir(os.path.dirname(os.path.abspath(destino)))

        total, _ = self._estimativa()
        self.cancelar.clear()
        self._travar()
        self.barra.configure(value=0)
        self.log("")
        self.log(f"Montando {len(self.arquivos)} blocos "
                 f"({duracao_amigavel(total)} de episodio)...")
        threading.Thread(target=self._rodar_montagem,
                         args=(destino, list(self.arquivos), self._ajustes()),
                         daemon=True).start()

    def _rodar_montagem(self, destino, arquivos, aj: dict):
        temporaria = tempfile.mkdtemp(prefix="montar_podcast_")
        parcial = destino + ".parcial.mp3"
        try:
            duracoes = [self.duracoes[c] for c in arquivos]
            filtro, total, inicios = montar_filtro(
                duracoes, aj["transicao"], aj["fade"], aj["pausa"],
                aj["normalizar"])

            arquivo_filtro = os.path.join(temporaria, "filtro.txt")
            with open(arquivo_filtro, "w", encoding="utf-8") as fh:
                fh.write(filtro)

            nomes = [os.path.splitext(os.path.basename(c))[0] for c in arquivos]
            titulo = aj["titulo"]

            # Lista de tempos: serve para colar na descricao do episodio.
            if aj["txt"]:
                caminho_txt = os.path.splitext(destino)[0] + "-capitulos.txt"
                with open(caminho_txt, "w", encoding="utf-8") as fh:
                    if titulo:
                        fh.write(f"{titulo}\n\n")
                    for inicio, nome in zip(inicios, nomes):
                        fh.write(f"{hms(inicio)} {nome}\n")
                self.enviar("log", f"Lista de tempos: {caminho_txt}")

            metadados = None
            if aj["capitulos"]:
                metadados = os.path.join(temporaria, "capitulos.ffmeta")
                with open(metadados, "w", encoding="utf-8") as fh:
                    fh.write(texto_ffmetadata(titulo, nomes, inicios,
                                              duracoes, total))

            kbps = aj["kbps"]

            ok = self._renderizar(arquivos, arquivo_filtro, metadados, titulo,
                                  kbps, parcial, total)
            if not ok and metadados and not self.cancelar.is_set():
                # Alguns builds do ffmpeg recusam gravar capitulos em mp3.
                # Nesse caso o episodio sai igual, so sem os marcadores.
                self.enviar("log", "Nao deu para gravar os capitulos dentro do "
                                   "arquivo; refazendo sem eles (o .txt com os "
                                   "tempos continua valendo).")
                self.enviar("progresso", 0)
                ok = self._renderizar(arquivos, arquivo_filtro, None, titulo,
                                      kbps, parcial, total)

            if self.cancelar.is_set():
                self.enviar("status", "Cancelado.")
                self.enviar("log", "Cancelado. Nada foi salvo.")
                return
            if not ok:
                self.enviar("status", "Falhou.")
                return

            shutil.move(parcial, destino)
            tamanho = os.path.getsize(destino) / (1024 * 1024)
            self.enviar("progresso", 100)
            self.enviar("status", f"Pronto: {os.path.basename(destino)}")
            self.enviar("log", f"Salvo em {destino} "
                               f"({tamanho:.1f} MB, {duracao_amigavel(total)})")
            self.enviar("ok", f"Podcast montado.\n\n{destino}\n\n"
                              f"{len(arquivos)} blocos • "
                              f"{duracao_amigavel(total)} • {tamanho:.1f} MB")
        except Exception as e:
            self.enviar("erro", f"Deu erro ao montar o podcast.\n\n{e}")
            self.enviar("status", "Falhou.")
        finally:
            for lixo in (parcial,):
                if os.path.exists(lixo):
                    try:
                        os.remove(lixo)
                    except OSError:
                        pass
            shutil.rmtree(temporaria, ignore_errors=True)
            self.processo = None
            self.enviar("fim")

    def _renderizar(self, arquivos, arquivo_filtro, metadados, titulo,
                    kbps, destino, total) -> bool:
        comando = [self.ffmpeg, "-y", "-hide_banner", "-nostats",
                   "-loglevel", "error", "-progress", "pipe:1"]
        for caminho in arquivos:
            comando += ["-i", caminho]
        if metadados:
            comando += ["-i", metadados]

        comando += ["-filter_complex_script", arquivo_filtro, "-map", "[aout]"]
        if metadados:
            comando += ["-map_metadata", str(len(arquivos)),
                        "-id3v2_version", "3", "-write_id3v1", "1"]
        if titulo:
            comando += ["-metadata", f"title={titulo}",
                        "-metadata", f"album={titulo}",
                        "-metadata", "genre=Podcast"]
        comando += ["-c:a", "libmp3lame", "-b:a", f"{kbps}k",
                    "-ar", str(TAXA), "-ac", "2", destino]

        self.processo = subprocess.Popen(
            comando, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, **_sem_janela())

        ultimas = []
        re_tempo = re.compile(r"out_time=(\d+):(\d+):(\d+\.?\d*)")
        for linha in self.processo.stdout:
            if self.cancelar.is_set():
                self._matar()
                break
            linha = linha.strip()
            m = re_tempo.search(linha)
            if m:
                feito = (int(m.group(1)) * 3600 + int(m.group(2)) * 60
                         + float(m.group(3)))
                if total > 0:
                    self.enviar("progresso", min(99.0, feito / total * 100))
                self.enviar("status", f"Montando... {hms(feito)} de "
                                      f"{hms(total)}")
            elif linha and "=" not in linha:
                ultimas.append(linha)
                del ultimas[:-12]

        codigo = self.processo.wait()
        if self.cancelar.is_set():
            return False
        if codigo != 0:
            self.enviar("log", "ffmpeg: " + " | ".join(ultimas[-4:]))
            return False
        return True

    def _matar(self):
        proc = self.processo
        if not proc:
            return
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        except Exception:
            pass

    def pedir_cancelamento(self):
        if not self.rodando:
            return
        self.cancelar.set()
        self.var_status.set("Cancelando...")
        self._matar()

    # ------------------------------------------------------------- travas
    def _travar(self):
        self.rodando = True
        self.bt_montar.configure(state="disabled")
        self.bt_cancelar.configure(state="normal")

    def _destravar(self):
        self.rodando = False
        self.bt_montar.configure(state="normal")
        self.bt_cancelar.configure(state="disabled")

    def ao_fechar(self):
        """Limpeza no fechamento do Estudio: nao destroi janela nenhuma.

        Manda parar o trabalho, derruba o ffmpeg que ainda estiver rodando e
        para de consultar a fila. Quem fecha a janela e o programa principal.
        """
        self._vivo = False
        self.cancelar.set()
        self._matar()


def montar(pai):
    """Desenha a aba de unir audios dentro de `pai` e devolve o aplicativo."""
    return Aplicativo(pai)
