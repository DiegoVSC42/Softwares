#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Baixador de Vídeos — interface gráfica (Tkinter) para baixar vídeos com yt-dlp.

Recursos:
  - Seleção de qualidade (melhor, 1080p, 720p, 480p, 360p)
  - Download somente do áudio em MP3
  - Suporte a playlists (baixar todos os vídeos da lista)
  - Escolha da pasta de destino
  - Barra de progresso, status, log e botão Cancelar

yt-dlp é usado como biblioteca (import yt_dlp), então o PyInstaller o embute
automaticamente no executável. O ffmpeg (necessário para juntar vídeo+áudio e
para converter em MP3) é procurado primeiro embutido no executável e, em
seguida, no PATH do sistema.
"""

import os
import sys
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_NAME = "Baixador de Vídeos"
APP_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Localização de recursos embutidos (yt-dlp + ffmpeg)
# ---------------------------------------------------------------------------
def resource_path(rel: str) -> str:
    """Resolve caminho de arquivo embutido pelo PyInstaller (onefile/onedir)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def find_ffmpeg_dir():
    """Retorna a pasta que contém o ffmpeg, ou None se não encontrado.

    Procura, nesta ordem:
      1. ffmpeg embutido junto ao executável (via PyInstaller --add-binary)
      2. ffmpeg disponível no PATH do sistema
    """
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"

    # 1) Embutido
    candidates = [
        resource_path(exe),
        resource_path(os.path.join("ffmpeg", exe)),
        resource_path(os.path.join("bin", exe)),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return os.path.dirname(c)

    # 2) No PATH
    from shutil import which
    found = which("ffmpeg")
    if found:
        return os.path.dirname(found)

    return None


# ---------------------------------------------------------------------------
# Mapeamento de qualidade -> format string do yt-dlp
# ---------------------------------------------------------------------------
QUALIDADES = {
    "Melhor qualidade": "bv*+ba/b",
    "1080p (Full HD)": "bv*[height<=1080]+ba/b[height<=1080]",
    "720p (HD)": "bv*[height<=720]+ba/b[height<=720]",
    "480p": "bv*[height<=480]+ba/b[height<=480]",
    "360p": "bv*[height<=360]+ba/b[height<=360]",
}


# ---------------------------------------------------------------------------
# Exceção usada para cancelar o download em andamento
# ---------------------------------------------------------------------------
class DownloadCancelado(Exception):
    pass


# ---------------------------------------------------------------------------
# Aplicação
# ---------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("680x560")
        self.minsize(620, 520)

        self.fila = queue.Queue()          # mensagens da thread -> GUI
        self.cancelar_flag = threading.Event()
        self.thread = None

        self.pasta_destino = tk.StringVar(
            value=os.path.join(os.path.expanduser("~"), "Downloads")
        )
        self.qualidade = tk.StringVar(value="Melhor qualidade")
        self.somente_audio = tk.BooleanVar(value=False)
        self.baixar_playlist = tk.BooleanVar(value=False)

        self._montar_ui()
        self._verificar_ffmpeg()
        self.after(100, self._processar_fila)
        self.protocol("WM_DELETE_WINDOW", self._ao_fechar)

    # ----- UI -----------------------------------------------------------
    def _montar_ui(self):
        pad = {"padx": 12, "pady": 6}

        topo = ttk.Frame(self)
        topo.pack(fill="x", **pad)
        ttk.Label(topo, text="URL do vídeo ou playlist:").pack(anchor="w")
        self.url_entry = ttk.Entry(topo)
        self.url_entry.pack(fill="x", pady=(2, 0))

        # Opções
        opc = ttk.LabelFrame(self, text="Opções")
        opc.pack(fill="x", **pad)

        linha1 = ttk.Frame(opc)
        linha1.pack(fill="x", padx=10, pady=8)
        ttk.Label(linha1, text="Qualidade:").pack(side="left")
        self.combo_qual = ttk.Combobox(
            linha1, textvariable=self.qualidade,
            values=list(QUALIDADES.keys()), state="readonly", width=22,
        )
        self.combo_qual.pack(side="left", padx=(6, 20))

        self.chk_audio = ttk.Checkbutton(
            linha1, text="Somente áudio (MP3)",
            variable=self.somente_audio, command=self._toggle_audio,
        )
        self.chk_audio.pack(side="left")

        self.chk_playlist = ttk.Checkbutton(
            linha1, text="Baixar playlist inteira",
            variable=self.baixar_playlist,
        )
        self.chk_playlist.pack(side="left", padx=(20, 0))

        # Pasta de destino
        linha2 = ttk.Frame(opc)
        linha2.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Label(linha2, text="Salvar em:").pack(side="left")
        self.entry_pasta = ttk.Entry(linha2, textvariable=self.pasta_destino)
        self.entry_pasta.pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(linha2, text="Escolher…",
                   command=self._escolher_pasta).pack(side="left")

        # Botões de ação
        acoes = ttk.Frame(self)
        acoes.pack(fill="x", **pad)
        self.btn_baixar = ttk.Button(acoes, text="⬇  Baixar",
                                     command=self._iniciar_download)
        self.btn_baixar.pack(side="left")
        self.btn_cancelar = ttk.Button(acoes, text="Cancelar",
                                       command=self._cancelar, state="disabled")
        self.btn_cancelar.pack(side="left", padx=8)

        # Progresso (barra + porcentagem sobreposta)
        prog = ttk.Frame(self)
        prog.pack(fill="x", **pad)

        barra_wrap = ttk.Frame(prog)
        barra_wrap.pack(fill="x")
        self.barra = ttk.Progressbar(barra_wrap, mode="determinate", maximum=100)
        self.barra.pack(fill="x", ipady=8)
        # Rótulo de porcentagem centralizado sobre a barra
        self.lbl_pct = ttk.Label(barra_wrap, text="0%", anchor="center")
        self.lbl_pct.place(relx=0.5, rely=0.5, anchor="center")

        self.status = ttk.Label(prog, text="Pronto.")
        self.status.pack(anchor="w", pady=(4, 0))

        # Log
        logf = ttk.LabelFrame(self, text="Registro")
        logf.pack(fill="both", expand=True, **pad)
        self.log = tk.Text(logf, height=10, wrap="word", state="disabled")
        self.log.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        sb = ttk.Scrollbar(logf, command=self.log.yview)
        sb.pack(side="right", fill="y", pady=8, padx=(0, 8))
        self.log.config(yscrollcommand=sb.set)

    def _toggle_audio(self):
        # Qualidade de vídeo não faz sentido quando só áudio
        estado = "disabled" if self.somente_audio.get() else "readonly"
        self.combo_qual.config(state=estado)

    def _escolher_pasta(self):
        d = filedialog.askdirectory(initialdir=self.pasta_destino.get() or ".")
        if d:
            self.pasta_destino.set(d)

    def _verificar_ffmpeg(self):
        if find_ffmpeg_dir() is None:
            self._logar(
                "AVISO: ffmpeg não foi encontrado. Juntar vídeo+áudio e "
                "converter em MP3 podem falhar. No executável final o ffmpeg "
                "vem embutido."
            )

    # ----- Download -----------------------------------------------------
    def _iniciar_download(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning(APP_NAME, "Cole a URL do vídeo.")
            return
        destino = self.pasta_destino.get().strip()
        if not destino:
            messagebox.showwarning(APP_NAME, "Escolha a pasta de destino.")
            return
        try:
            os.makedirs(destino, exist_ok=True)
        except OSError as e:
            messagebox.showerror(APP_NAME, f"Não foi possível usar a pasta:\n{e}")
            return

        self.cancelar_flag.clear()
        self.btn_baixar.config(state="disabled")
        self.btn_cancelar.config(state="normal")
        self.barra.config(value=0)
        self.lbl_pct.config(text="0%")
        self._set_status("Iniciando…")

        opcoes = {
            "url": url,
            "destino": destino,
            "format": QUALIDADES.get(self.qualidade.get(), "bv*+ba/b"),
            "somente_audio": self.somente_audio.get(),
            "playlist": self.baixar_playlist.get(),
        }
        self.thread = threading.Thread(target=self._worker, args=(opcoes,),
                                       daemon=True)
        self.thread.start()

    def _worker(self, opc):
        """Roda em thread separada. Comunica-se com a GUI via self.fila."""
        try:
            import yt_dlp
        except Exception as e:
            self.fila.put(("erro", f"yt-dlp não disponível: {e}"))
            self.fila.put(("fim", None))
            return

        ffmpeg_dir = find_ffmpeg_dir()

        outtmpl = os.path.join(opc["destino"], "%(title)s.%(ext)s")

        ydl_opts = {
            "outtmpl": outtmpl,
            "noplaylist": not opc["playlist"],
            "ignoreerrors": opc["playlist"],   # continua a lista se 1 falhar
            "progress_hooks": [self._hook],
            "noprogress": True,
            "quiet": True,
            "no_warnings": True,
        }
        if ffmpeg_dir:
            ydl_opts["ffmpeg_location"] = ffmpeg_dir

        if opc["somente_audio"]:
            ydl_opts["format"] = "ba/b"
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        else:
            ydl_opts["format"] = opc["format"]
            ydl_opts["merge_output_format"] = "mp4"

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([opc["url"]])
            if self.cancelar_flag.is_set():
                self.fila.put(("status", "Cancelado."))
            else:
                self.fila.put(("ok", "Download concluído com sucesso!"))
        except DownloadCancelado:
            self.fila.put(("status", "Cancelado pelo usuário."))
        except Exception as e:
            self.fila.put(("erro", str(e)))
        finally:
            self.fila.put(("fim", None))

    def _hook(self, d):
        """progress_hook do yt-dlp (roda na thread de download)."""
        if self.cancelar_flag.is_set():
            raise DownloadCancelado()

        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            baixado = d.get("downloaded_bytes", 0)
            if total:
                pct = baixado * 100.0 / total
                self.fila.put(("progresso", pct))
            velocidade = d.get("_speed_str", "").strip()
            eta = d.get("_eta_str", "").strip()
            nome = os.path.basename(d.get("filename", ""))
            self.fila.put(("status", f"Baixando {nome}  {velocidade}  ETA {eta}"))
        elif status == "finished":
            self.fila.put(("progresso", 100.0))
            self.fila.put(("status", "Processando (ffmpeg)…"))
            self.fila.put(("log", f"Baixado: {os.path.basename(d.get('filename',''))}"))

    def _cancelar(self):
        self.cancelar_flag.set()
        self._set_status("Cancelando…")

    # ----- Comunicação thread -> GUI ------------------------------------
    def _processar_fila(self):
        try:
            while True:
                tipo, valor = self.fila.get_nowait()
                if tipo == "progresso":
                    self.barra.config(value=valor)
                    self.lbl_pct.config(text=f"{valor:.1f}%")
                elif tipo == "status":
                    self._set_status(valor)
                elif tipo == "log":
                    self._logar(valor)
                elif tipo == "ok":
                    self._set_status(valor)
                    self._logar(valor)
                elif tipo == "erro":
                    self._set_status("Erro.")
                    self._logar("ERRO: " + valor)
                    messagebox.showerror(APP_NAME, valor)
                elif tipo == "fim":
                    self.btn_baixar.config(state="normal")
                    self.btn_cancelar.config(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._processar_fila)

    def _set_status(self, txt):
        self.status.config(text=txt)

    def _logar(self, txt):
        self.log.config(state="normal")
        self.log.insert("end", txt + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def _ao_fechar(self):
        if self.thread and self.thread.is_alive():
            if not messagebox.askyesno(
                APP_NAME, "Há um download em andamento. Fechar mesmo assim?"
            ):
                return
            self.cancelar_flag.set()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
