"""
Extrair Audio de Video - interface grafica (Tkinter).

Extrai a faixa de audio de um ou varios videos de uma vez (lote),
nos formatos:
  - MP3 (com bitrate ajustavel)
  - WAV (PCM 16-bit, sem perdas)
  - M4A / AAC (com bitrate ajustavel)

Recursos:
  - selecao de varios arquivos OU de uma pasta inteira;
  - escolha da pasta de destino;
  - progresso em tempo real por arquivo e por lote;
  - botao Cancelar (operacao roda em thread separada);
  - log de status.

O ffmpeg vem embutido no executavel final (via PyInstaller --add-binary).
Em desenvolvimento, usa o ffmpeg do PATH se existir.
"""

import os
import queue
import re
import subprocess
import sys
import threading
from pathlib import Path
from shutil import which
from tkinter import (
    Tk, StringVar, END, DISABLED, NORMAL,
    filedialog, messagebox, ttk, scrolledtext,
)


APP_NAME = "Extrair Audio de Video"
APP_VERSION = "1.0.0"

# Extensoes de video aceitas ao varrer uma pasta
EXTENSOES_VIDEO = {
    ".mp4", ".mkv", ".mov", ".avi", ".wmv", ".flv", ".webm",
    ".m4v", ".mpg", ".mpeg", ".3gp", ".ts", ".m2ts",
}

# Formatos de saida -> rotulo amigavel
FORMATO_MP3 = "MP3 (com bitrate)"
FORMATO_WAV = "WAV (sem perdas)"
FORMATO_M4A = "M4A / AAC (com bitrate)"
FORMATOS = [FORMATO_MP3, FORMATO_WAV, FORMATO_M4A]

BITRATES = ["96k", "128k", "192k", "256k", "320k"]


# ---------------------------------------------------------------------------
# Localizacao do ffmpeg embutido
# ---------------------------------------------------------------------------
def resource_path(rel: str) -> str:
    """Resolve caminho de arquivo embutido pelo PyInstaller (onefile/onedir)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def find_ffmpeg() -> str | None:
    """Retorna o caminho do executavel ffmpeg, ou None se nao encontrado.

    Procura, nesta ordem:
      1. ffmpeg embutido junto ao executavel (via PyInstaller --add-binary)
      2. ffmpeg disponivel no PATH do sistema
    """
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"

    candidates = [
        resource_path(exe),
        resource_path(os.path.join("ffmpeg", exe)),
        resource_path(os.path.join("bin", exe)),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c

    found = which("ffmpeg")
    if found:
        return found

    return None


# ---------------------------------------------------------------------------
# Helpers de parsing de tempo do ffmpeg
# ---------------------------------------------------------------------------
RE_DURACAO = re.compile(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)")
RE_TEMPO = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")


def _hms_para_seg(h: str, m: str, s: str) -> float:
    return int(h) * 3600 + int(m) * 60 + float(s)


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
class ExtrairAudioGUI:
    NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    def __init__(self, root: Tk) -> None:
        self.root = root
        root.title(f"{APP_NAME} v{APP_VERSION}")
        root.geometry("760x640")
        root.minsize(680, 560)

        # Estado
        self.arquivos: list[Path] = []
        self.pasta_saida = StringVar(value=str(Path.home() / "Music" / "audios-extraidos"))
        self.formato = StringVar(value=FORMATO_MP3)
        self.bitrate = StringVar(value="192k")

        self.fila: queue.Queue = queue.Queue()
        self.processo: subprocess.Popen | None = None
        self.cancelar = False
        self.rodando = False

        self.ffmpeg = find_ffmpeg()

        self._montar_ui()
        self._verificar_ffmpeg()
        self.root.after(100, self._processar_fila)

    # ------------------------------------------------------------------ UI
    def _montar_ui(self) -> None:
        pad = {"padx": 8, "pady": 4}

        # --- Arquivos ---
        frm_arq = ttk.LabelFrame(self.root, text="1) Videos de entrada")
        frm_arq.pack(fill="both", expand=False, **pad)

        barra = ttk.Frame(frm_arq)
        barra.pack(fill="x", padx=6, pady=6)
        ttk.Button(barra, text="Adicionar videos...",
                   command=self._add_arquivos).pack(side="left", padx=2)
        ttk.Button(barra, text="Adicionar pasta...",
                   command=self._add_pasta).pack(side="left", padx=2)
        ttk.Button(barra, text="Remover selecionado",
                   command=self._remover_selecionado).pack(side="left", padx=2)
        ttk.Button(barra, text="Limpar lista",
                   command=self._limpar).pack(side="left", padx=2)

        self.lista = ttk.Treeview(frm_arq, columns=("arquivo",), show="headings",
                                  height=7, selectmode="extended")
        self.lista.heading("arquivo", text="Arquivo")
        self.lista.column("arquivo", anchor="w")
        self.lista.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        # --- Opcoes ---
        frm_opt = ttk.LabelFrame(self.root, text="2) Formato de saida")
        frm_opt.pack(fill="x", **pad)

        linha = ttk.Frame(frm_opt)
        linha.pack(fill="x", padx=6, pady=6)
        ttk.Label(linha, text="Formato:").pack(side="left")
        cb_fmt = ttk.Combobox(linha, textvariable=self.formato, values=FORMATOS,
                              state="readonly", width=22)
        cb_fmt.pack(side="left", padx=(4, 16))
        cb_fmt.bind("<<ComboboxSelected>>", self._on_formato)

        self.lbl_bitrate = ttk.Label(linha, text="Bitrate:")
        self.lbl_bitrate.pack(side="left")
        self.cb_bitrate = ttk.Combobox(linha, textvariable=self.bitrate, values=BITRATES,
                                       state="readonly", width=8)
        self.cb_bitrate.pack(side="left", padx=4)

        # --- Destino ---
        frm_dest = ttk.LabelFrame(self.root, text="3) Pasta de destino")
        frm_dest.pack(fill="x", **pad)
        linha_d = ttk.Frame(frm_dest)
        linha_d.pack(fill="x", padx=6, pady=6)
        ttk.Entry(linha_d, textvariable=self.pasta_saida).pack(
            side="left", fill="x", expand=True)
        ttk.Button(linha_d, text="Escolher...",
                   command=self._escolher_destino).pack(side="left", padx=(6, 0))

        # --- Acao ---
        frm_acao = ttk.Frame(self.root)
        frm_acao.pack(fill="x", **pad)
        self.btn_extrair = ttk.Button(frm_acao, text="Extrair audio",
                                      command=self._iniciar)
        self.btn_extrair.pack(side="left")
        self.btn_cancelar = ttk.Button(frm_acao, text="Cancelar",
                                       command=self._cancelar, state=DISABLED)
        self.btn_cancelar.pack(side="left", padx=6)

        # --- Progresso ---
        frm_prog = ttk.LabelFrame(self.root, text="Progresso")
        frm_prog.pack(fill="both", expand=True, **pad)

        self.lbl_atual = ttk.Label(frm_prog, text="Pronto.")
        self.lbl_atual.pack(fill="x", padx=6, pady=(6, 0))
        self.prog_arquivo = ttk.Progressbar(frm_prog, mode="determinate", maximum=100)
        self.prog_arquivo.pack(fill="x", padx=6, pady=2)

        self.lbl_lote = ttk.Label(frm_prog, text="Lote: 0/0")
        self.lbl_lote.pack(fill="x", padx=6)
        self.prog_lote = ttk.Progressbar(frm_prog, mode="determinate", maximum=100)
        self.prog_lote.pack(fill="x", padx=6, pady=2)

        self.log = scrolledtext.ScrolledText(frm_prog, height=8, state=DISABLED)
        self.log.pack(fill="both", expand=True, padx=6, pady=6)

    # ------------------------------------------------------- ffmpeg check
    def _verificar_ffmpeg(self) -> None:
        if not self.ffmpeg:
            self._logar("AVISO: ffmpeg nao encontrado. No executavel final ele "
                        "vem embutido. Em desenvolvimento, instale o ffmpeg e "
                        "coloque-o no PATH.")
            self.btn_extrair.config(state=DISABLED)
        else:
            self._logar(f"ffmpeg: {self.ffmpeg}")

    # --------------------------------------------------------- callbacks
    def _on_formato(self, _evt=None) -> None:
        wav = self.formato.get() == FORMATO_WAV
        estado = DISABLED if wav else NORMAL
        self.cb_bitrate.config(state="disabled" if wav else "readonly")
        self.lbl_bitrate.config(state=estado)

    def _add_arquivos(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Selecione os videos",
            filetypes=[("Videos", "*.mp4 *.mkv *.mov *.avi *.wmv *.flv *.webm "
                                   "*.m4v *.mpg *.mpeg *.3gp *.ts *.m2ts"),
                       ("Todos os arquivos", "*.*")],
        )
        for p in paths:
            self._adicionar(Path(p))

    def _add_pasta(self) -> None:
        d = filedialog.askdirectory(title="Selecione a pasta com videos")
        if not d:
            return
        encontrados = 0
        for p in sorted(Path(d).iterdir()):
            if p.is_file() and p.suffix.lower() in EXTENSOES_VIDEO:
                if self._adicionar(p):
                    encontrados += 1
        self._logar(f"Pasta varrida: {encontrados} video(s) adicionado(s).")

    def _adicionar(self, p: Path) -> bool:
        if p in self.arquivos:
            return False
        self.arquivos.append(p)
        self.lista.insert("", END, values=(str(p),))
        return True

    def _remover_selecionado(self) -> None:
        for item in self.lista.selection():
            valor = self.lista.item(item, "values")[0]
            try:
                self.arquivos.remove(Path(valor))
            except ValueError:
                pass
            self.lista.delete(item)

    def _limpar(self) -> None:
        self.arquivos.clear()
        for item in self.lista.get_children():
            self.lista.delete(item)

    def _escolher_destino(self) -> None:
        d = filedialog.askdirectory(title="Pasta de destino")
        if d:
            self.pasta_saida.set(d)

    # ------------------------------------------------------------ extrair
    def _iniciar(self) -> None:
        if self.rodando:
            return
        if not self.ffmpeg:
            messagebox.showerror(APP_NAME, "ffmpeg nao encontrado.")
            return
        if not self.arquivos:
            messagebox.showwarning(APP_NAME, "Adicione pelo menos um video.")
            return

        destino = Path(self.pasta_saida.get().strip() or ".")
        try:
            destino.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            messagebox.showerror(APP_NAME, f"Nao foi possivel criar a pasta de destino:\n{e}")
            return

        self.cancelar = False
        self.rodando = True
        self.btn_extrair.config(state=DISABLED)
        self.btn_cancelar.config(state=NORMAL)
        self.prog_lote.config(value=0)
        self.prog_arquivo.config(value=0)

        t = threading.Thread(target=self._worker,
                             args=(list(self.arquivos), destino,
                                   self.formato.get(), self.bitrate.get()),
                             daemon=True)
        t.start()

    def _cancelar(self) -> None:
        self.cancelar = True
        if self.processo and self.processo.poll() is None:
            try:
                self.processo.terminate()
            except Exception:
                pass
        self.fila.put(("log", "Cancelando..."))

    def _comando(self, entrada: Path, saida: Path, formato: str, bitrate: str) -> list[str]:
        cmd = [self.ffmpeg, "-y", "-hide_banner", "-i", str(entrada), "-vn"]
        if formato == FORMATO_MP3:
            cmd += ["-c:a", "libmp3lame", "-b:a", bitrate]
        elif formato == FORMATO_WAV:
            cmd += ["-c:a", "pcm_s16le"]
        else:  # M4A / AAC
            cmd += ["-c:a", "aac", "-b:a", bitrate]
        cmd.append(str(saida))
        return cmd

    def _extensao(self, formato: str) -> str:
        return {FORMATO_MP3: ".mp3", FORMATO_WAV: ".wav", FORMATO_M4A: ".m4a"}[formato]

    def _worker(self, arquivos: list[Path], destino: Path,
                formato: str, bitrate: str) -> None:
        total = len(arquivos)
        ok = 0
        falhas = 0
        ext = self._extensao(formato)

        for i, entrada in enumerate(arquivos, start=1):
            if self.cancelar:
                break

            saida = destino / (entrada.stem + ext)
            n = 1
            while saida.exists():
                saida = destino / f"{entrada.stem} ({n}){ext}"
                n += 1

            self.fila.put(("atual", f"[{i}/{total}] {entrada.name}"))
            self.fila.put(("arquivo", 0))
            self.fila.put(("log", f"Extraindo: {entrada.name} -> {saida.name}"))

            try:
                erro = self._rodar_ffmpeg(self._comando(entrada, saida, formato, bitrate))
            except Exception as e:
                erro = str(e)

            if self.cancelar:
                if saida.exists():
                    try:
                        saida.unlink()
                    except OSError:
                        pass
                break

            if erro is None:
                ok += 1
                self.fila.put(("log", f"  OK: {saida.name}"))
            else:
                falhas += 1
                self.fila.put(("log", f"  FALHA: {entrada.name} ({erro})"))

            self.fila.put(("lote", (i, total)))

        self.fila.put(("fim", (ok, falhas, self.cancelar)))

    def _rodar_ffmpeg(self, cmd: list[str]) -> str | None:
        """Roda o ffmpeg, atualiza o progresso e retorna None se sucesso
        ou uma mensagem de erro curta em caso de falha."""
        self.processo = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            encoding="utf-8",
            errors="replace",
            creationflags=self.NO_WINDOW,
        )

        duracao = None
        ultimas = []
        for linha in self.processo.stderr:
            ultimas.append(linha)
            if len(ultimas) > 12:
                ultimas.pop(0)

            if duracao is None:
                m = RE_DURACAO.search(linha)
                if m:
                    duracao = _hms_para_seg(*m.groups())

            m = RE_TEMPO.search(linha)
            if m and duracao:
                atual = _hms_para_seg(*m.groups())
                pct = max(0, min(100, atual / duracao * 100))
                self.fila.put(("arquivo", pct))

        self.processo.wait()
        codigo = self.processo.returncode
        self.processo = None

        if codigo == 0:
            self.fila.put(("arquivo", 100))
            return None

        if self.cancelar:
            return "cancelado"

        texto = "".join(ultimas).strip().replace("\n", " ")
        return texto[-160:] if texto else f"codigo {codigo}"

    # ------------------------------------------------------- fila / log
    def _processar_fila(self) -> None:
        try:
            while True:
                tipo, dado = self.fila.get_nowait()
                if tipo == "atual":
                    self.lbl_atual.config(text=dado)
                elif tipo == "arquivo":
                    self.prog_arquivo.config(value=dado)
                elif tipo == "lote":
                    i, total = dado
                    self.lbl_lote.config(text=f"Lote: {i}/{total}")
                    self.prog_lote.config(value=i / total * 100)
                elif tipo == "log":
                    self._logar(dado)
                elif tipo == "fim":
                    self._finalizar(*dado)
        except queue.Empty:
            pass
        self.root.after(100, self._processar_fila)

    def _finalizar(self, ok: int, falhas: int, cancelado: bool) -> None:
        self.rodando = False
        self.btn_extrair.config(state=NORMAL)
        self.btn_cancelar.config(state=DISABLED)
        if cancelado:
            self.lbl_atual.config(text="Cancelado.")
            self._logar(f"Cancelado. Concluidos: {ok}, falhas: {falhas}.")
        else:
            self.lbl_atual.config(text="Concluido.")
            self.prog_arquivo.config(value=100)
            self.prog_lote.config(value=100)
            self._logar(f"Concluido. Sucesso: {ok}, falhas: {falhas}.")
            messagebox.showinfo(APP_NAME,
                                f"Extracao concluida.\nSucesso: {ok}\nFalhas: {falhas}")

    def _logar(self, msg: str) -> None:
        self.log.config(state=NORMAL)
        self.log.insert(END, msg + "\n")
        self.log.see(END)
        self.log.config(state=DISABLED)


def main() -> None:
    root = Tk()
    ExtrairAudioGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
