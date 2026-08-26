#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Espelhar Celular — assista ao celular (YouTube etc.) no computador via scrcpy.

Recursos:
- Conexão por cabo USB (principal) e Wi-Fi (opcional)
- Som sai no computador
- Tela do celular apaga sozinha ao conectar
- Seletor de qualidade: Máxima ou Equilibrada
- Abre em janela (amplie com o botão verde do Mac se quiser)
"""

import os
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import atualizador  # atualizacao automatica

VERSION = "1.3.1"
APP_NAME = "Espelhar Celular"

# Caminhos comuns do Homebrew/instalações no Mac e Windows
EXTRA_PATHS = [
    "/opt/homebrew/bin",
    "/usr/local/bin",
    os.path.expanduser("~/scrcpy"),
    r"C:\scrcpy",
]


def _env_with_paths():
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join(EXTRA_PATHS + [env.get("PATH", "")])
    return env


def _find(cmd):
    env = _env_with_paths()
    for d in env["PATH"].split(os.pathsep):
        p = os.path.join(d, cmd)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
        if sys.platform.startswith("win") and os.path.isfile(p + ".exe"):
            return p + ".exe"
    return None


def _run(args, timeout=20):
    """Roda um comando e devolve (código, saída)."""
    kw = {}
    if sys.platform.startswith("win"):
        kw["creationflags"] = 0x08000000  # sem janela de console
    try:
        r = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout,
            env=_env_with_paths(), **kw
        )
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return 1, str(e)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("480x640")
        self.minsize(450, 560)
        self.resizable(True, True)
        self.proc = None
        self.scrcpy = _find("scrcpy")
        self.adb = _find("adb")

        self._build_ui()
        self._refresh_status()

    # ---------- interface ----------
    def _build_ui(self):
        # Rodapé primeiro, para ficar ancorado embaixo
        footer = tk.Label(
            self, text=f"{APP_NAME} \u2022 v{VERSION}",
            fg="#8b949e", font=("Helvetica", 10), anchor="e"
        )
        footer.pack(side="bottom", fill="x", padx=10, pady=(0, 6))

        main = ttk.Frame(self, padding=14)
        main.pack(side="top", fill="both", expand=True)

        ttk.Label(main, text="Espelhar o celular no computador",
                  font=("Helvetica", 15, "bold")).pack(anchor="w")
        ttk.Label(
            main,
            text="Som no computador \u2022 tela do celular apaga sozinha",
            foreground="#555"
        ).pack(anchor="w", pady=(2, 10))

        # Status do celular
        box = ttk.LabelFrame(main, text="Celular", padding=10)
        box.pack(fill="x")
        self.lbl_device = ttk.Label(box, text="Verificando...")
        self.lbl_device.pack(side="left")
        ttk.Button(box, text="Verificar de novo",
                   command=self._refresh_status).pack(side="right")

        # Qualidade
        qbox = ttk.LabelFrame(main, text="Qualidade da imagem", padding=10)
        qbox.pack(fill="x", pady=(10, 0))
        self.quality = tk.StringVar(value="maxima")
        ttk.Radiobutton(
            qbox, text="M\u00e1xima (mais n\u00edtida, ideal com cabo)",
            variable=self.quality, value="maxima"
        ).pack(anchor="w")
        ttk.Radiobutton(
            qbox, text="Equilibrada (mais leve)",
            variable=self.quality, value="equilibrada"
        ).pack(anchor="w")
        ttk.Radiobutton(
            qbox, text="Econômica (para Wi-Fi lento)",
            variable=self.quality, value="economica"
        ).pack(anchor="w")

        # Opções extras
        obox = ttk.LabelFrame(main, text="Opções", padding=10)
        obox.pack(fill="x", pady=(10, 0))
        self.opt_record = tk.BooleanVar(value=False)
        self.opt_ontop = tk.BooleanVar(value=False)
        self.opt_mini = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            obox, text="Gravar em vídeo (salva em Downloads)",
            variable=self.opt_record
        ).pack(anchor="w")
        ttk.Checkbutton(
            obox, text="Janela sempre por cima das outras",
            variable=self.opt_ontop
        ).pack(anchor="w")
        ttk.Checkbutton(
            obox, text="Mini janela (canto da tela, estilo mini-player)",
            variable=self.opt_mini
        ).pack(anchor="w")

        # Botões principais
        bbox = ttk.Frame(main)
        bbox.pack(fill="x", pady=(14, 0))
        self.btn_start = ttk.Button(
            bbox, text="\u25b6  Conectar e espelhar",
            command=lambda: self.start_mirror("tela")
        )
        self.btn_start.pack(fill="x", ipady=6)

        mbox = ttk.Frame(bbox)
        mbox.pack(fill="x", pady=(6, 0))
        self.btn_yt = ttk.Button(
            mbox, text="\u25b6  S\u00f3 o YouTube",
            command=lambda: self.start_mirror("youtube")
        )
        self.btn_yt.pack(side="left", expand=True, fill="x", padx=(0, 3))
        self.btn_cam = ttk.Button(
            mbox, text="C\u00e2mera do celular",
            command=lambda: self.start_mirror("camera")
        )
        self.btn_cam.pack(side="left", expand=True, fill="x", padx=(3, 0))

        self.btn_stop = ttk.Button(
            bbox, text="\u25a0  Parar", command=self.stop_mirror,
            state="disabled"
        )
        self.btn_stop.pack(fill="x", pady=(6, 0))

        # Tela do celular durante o espelhamento
        tbox = ttk.Frame(main)
        tbox.pack(fill="x", pady=(6, 0))
        self.btn_screen_off = ttk.Button(
            tbox, text="\u263e Apagar tela do celular",
            command=lambda: self._phone_screen(False), state="disabled"
        )
        self.btn_screen_off.pack(side="left", expand=True, fill="x",
                                 padx=(0, 3))
        self.btn_screen_on = ttk.Button(
            tbox, text="\u2600 Acender tela",
            command=lambda: self._phone_screen(True), state="disabled"
        )
        self.btn_screen_on.pack(side="left", expand=True, fill="x",
                                padx=(3, 0))

        # Wi-Fi opcional
        wbox = ttk.LabelFrame(main, text="Sem cabo (opcional)", padding=10)
        wbox.pack(fill="x", pady=(10, 0))
        ttk.Label(
            wbox, foreground="#555", wraplength=380, justify="left",
            text="Conecte o cabo uma vez, clique abaixo e depois "
                 "pode soltar o cabo. Celular e computador precisam "
                 "estar no mesmo Wi-Fi."
        ).pack(anchor="w")
        self.btn_wifi = ttk.Button(
            wbox, text="Ativar conex\u00e3o por Wi-Fi",
            command=self.enable_wifi
        )
        self.btn_wifi.pack(anchor="w", pady=(6, 0))

        # Status geral
        self.lbl_status = ttk.Label(main, text="", foreground="#0a6")
        self.lbl_status.pack(anchor="w", pady=(10, 0))

    def _set_status(self, text, ok=True):
        self.lbl_status.config(text=text, foreground="#0a6" if ok else "#c00")

    # ---------- verificação ----------
    def _refresh_status(self):
        self.scrcpy = _find("scrcpy")
        self.adb = _find("adb")
        if not self.scrcpy or not self.adb:
            self.lbl_device.config(text="Programa de espelhamento ausente")
            self._offer_install()
            return
        threading.Thread(target=self._check_device, daemon=True).start()

    def _check_device(self):
        code, out = _run([self.adb, "devices"])
        lines = [l for l in out.splitlines()[1:] if l.strip()]
        connected = [l for l in lines if "\tdevice" in l]
        unauthorized = [l for l in lines if "unauthorized" in l]

        def update():
            if connected:
                self.lbl_device.config(text="\u2705 Celular conectado")
            elif unauthorized:
                self.lbl_device.config(
                    text="\u26a0\ufe0f Autorize no celular (aceite o aviso)")
            else:
                self.lbl_device.config(text="\u274c Nenhum celular encontrado")
        self.after(0, update)

    def _offer_install(self):
        if sys.platform == "darwin" and shutil.which("brew"):
            if messagebox.askyesno(
                APP_NAME,
                "O programa de espelhamento (scrcpy) ainda n\u00e3o est\u00e1 "
                "instalado.\n\nQuer instalar agora? Demora alguns minutos, "
                "s\u00f3 na primeira vez."
            ):
                self._set_status("Instalando... aguarde (pode demorar).")
                threading.Thread(target=self._brew_install,
                                 daemon=True).start()
        else:
            messagebox.showwarning(
                APP_NAME,
                "O programa de espelhamento (scrcpy) n\u00e3o foi encontrado.\n"
                "No Mac: instale o Homebrew (brew.sh) e rode este aplicativo "
                "de novo.\nNo Windows: baixe o scrcpy e extraia em C:\\scrcpy."
            )

    def _brew_install(self):
        code, out = _run(["brew", "install", "scrcpy"], timeout=1800)
        def done():
            if code == 0:
                self._set_status("Instala\u00e7\u00e3o conclu\u00edda.")
            else:
                self._set_status("Falha na instala\u00e7\u00e3o.", ok=False)
            self._refresh_status()
        self.after(0, done)

    # ---------- espelhamento ----------
    def start_mirror(self, mode="tela"):
        if not self.scrcpy:
            self._refresh_status()
            return
        # Nome da opção de qualidade mudou na versão 2 do scrcpy
        _, vout = _run([self.scrcpy, "--version"])
        m = re.search(r"scrcpy\s+(\d+)", vout)
        old_scrcpy = bool(m) and int(m.group(1)) < 2
        bitrate_flag = "--bit-rate" if old_scrcpy else "--video-bit-rate"

        if mode == "camera":
            args = [
                self.scrcpy,
                "--video-source=camera",
                "--camera-facing=front",
                "--no-audio",
                "--window-title", "Camera do Celular",
            ]
        elif mode == "youtube":
            args = [
                self.scrcpy,
                "--new-display",
                "--start-app=com.google.android.youtube",
                "--turn-screen-off",
                "--stay-awake",
                "--window-title", "YouTube",
            ]
        else:
            args = [
                self.scrcpy,
                "--turn-screen-off",   # apaga a tela do celular
                "--stay-awake",        # não deixa o celular travar
                "--window-title", "Celular",
            ]

        # Se o celular aparecer duas vezes (cabo + Wi-Fi), prefere o cabo.
        _, dout = _run([self.adb, "devices"]) if self.adb else (1, "")
        dlines = [l for l in dout.splitlines()[1:] if "\tdevice" in l]
        usb = [l for l in dlines if ":" not in l.split("\t")[0]]
        tcpip = [l for l in dlines if ":" in l.split("\t")[0]]
        if usb:
            args += ["-d"]      # usa o celular do cabo
        elif tcpip:
            args += ["-e"]      # usa o celular do Wi-Fi
        q = self.quality.get()
        if q == "maxima":
            args += [bitrate_flag, "20M"]
        elif q == "equilibrada":
            args += [bitrate_flag, "8M", "--max-size", "1600"]
        else:
            args += [bitrate_flag, "4M", "--max-size", "1280"]

        # Opções extras
        if self.opt_ontop.get():
            args += ["--always-on-top"]
        if self.opt_mini.get():
            args += ["--window-width", "420"]
        self._record_path = None
        if self.opt_record.get():
            import datetime
            nome = datetime.datetime.now().strftime(
                "Celular-%Y%m%d-%H%M%S.mp4")
            self._record_path = os.path.join(
                os.path.expanduser("~/Downloads"), nome)
            args += ["--record", self._record_path]

        self.btn_start.config(state="disabled")
        self.btn_yt.config(state="disabled")
        self.btn_cam.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.btn_screen_off.config(state="normal")
        self.btn_screen_on.config(state="normal")
        self._set_status("Espelhando... feche a janela do v\u00eddeo ou "
                         "clique em Parar para encerrar.")
        threading.Thread(target=self._run_scrcpy, args=(args,),
                         daemon=True).start()

    def _run_scrcpy(self, args):
        kw = {}
        if sys.platform.startswith("win"):
            kw["creationflags"] = 0x08000000
        try:
            self.proc = subprocess.Popen(
                args, env=_env_with_paths(),
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, **kw
            )
            _, err = self.proc.communicate()
            code = self.proc.returncode
        except Exception as e:
            code, err = 1, str(e).encode()
        self.proc = None

        def done():
            self.btn_start.config(state="normal")
            self.btn_yt.config(state="normal")
            self.btn_cam.config(state="normal")
            self.btn_stop.config(state="disabled")
            self.btn_screen_off.config(state="disabled")
            self.btn_screen_on.config(state="disabled")
            if code == 0:
                if getattr(self, "_record_path", None):
                    self._set_status(
                        "Encerrado. Vídeo salvo em Downloads: "
                        + os.path.basename(self._record_path))
                else:
                    self._set_status("Espelhamento encerrado.")
            else:
                msg = (err or b"").decode(errors="ignore") if isinstance(err, bytes) else str(err or "")
                low = msg.lower()
                if "no device" in low or "device not found" in low:
                    self._set_status(
                        "Nenhum celular encontrado. Confira o cabo e a "
                        "depura\u00e7\u00e3o USB.", ok=False)
                else:
                    self._set_status("O espelhamento parou. Veja o motivo "
                                     "na janela.", ok=False)
                    detalhe = "\n".join(
                        [l for l in msg.splitlines() if l.strip()][-15:]
                    ) or "Sem detalhes."
                    messagebox.showerror(
                        APP_NAME,
                        "O espelhamento n\u00e3o abriu. Mensagem t\u00e9cnica "
                        "(copie e envie se precisar de ajuda):\n\n" + detalhe
                    )
            self._check_device()
        self.after(0, done)

    def _phone_screen(self, ligar):
        """Apaga ou acende a tela do celular durante o espelhamento.

        No Mac, envia o atalho do scrcpy (Option+O / Option+Shift+O) para a
        janela do vídeo. Na primeira vez o macOS pede permissão de
        Acessibilidade — basta autorizar.
        """
        if sys.platform == "darwin":
            tecla = ('keystroke "o" using {option down, shift down}'
                     if ligar else 'keystroke "o" using {option down}')
            script = (
                'tell application "System Events"\n'
                '  set frontmost of first process whose name is "scrcpy" '
                'to true\n'
                f'  {tecla}\n'
                'end tell'
            )
            threading.Thread(
                target=lambda: _run(["osascript", "-e", script]),
                daemon=True
            ).start()
        else:
            # Outros sistemas: comando direto ao celular
            key = "224" if ligar else "223"  # acordar / dormir
            if self.adb:
                threading.Thread(
                    target=lambda: _run(
                        [self.adb, "shell", "input", "keyevent", key]),
                    daemon=True
                ).start()

    def stop_mirror(self):
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:
                pass

    # ---------- wi-fi ----------
    def enable_wifi(self):
        if not self.adb:
            self._refresh_status()
            return
        self.btn_wifi.config(state="disabled")
        self._set_status("Ativando Wi-Fi... mantenha o cabo por enquanto.")
        threading.Thread(target=self._do_wifi, daemon=True).start()

    def _do_wifi(self):
        ok, msg = False, ""
        code, out = _run([self.adb, "shell", "ip", "route"])
        m = re.search(r"src (\d+\.\d+\.\d+\.\d+)", out)
        if not m:
            msg = ("N\u00e3o achei o endere\u00e7o do celular. Confira se ele "
                   "est\u00e1 no Wi-Fi e conectado pelo cabo.")
        else:
            ip = m.group(1)
            _run([self.adb, "tcpip", "5555"])
            import time
            time.sleep(2)
            code, out = _run([self.adb, "connect", f"{ip}:5555"])
            if "connected" in out.lower():
                ok = True
                msg = (f"Pronto! Pode soltar o cabo. "
                       f"Celular no Wi-Fi ({ip}).")
            else:
                msg = "N\u00e3o consegui conectar pelo Wi-Fi."

        def done():
            self.btn_wifi.config(state="normal")
            self._set_status(msg, ok=ok)
            self._check_device()
        self.after(0, done)

    def destroy(self):
        self.stop_mirror()
        super().destroy()


if __name__ == "__main__":
    app = App()
    atualizador.iniciar(app, "espelhar-celular", VERSION, "Espelhar Celular")
    app.mainloop()
