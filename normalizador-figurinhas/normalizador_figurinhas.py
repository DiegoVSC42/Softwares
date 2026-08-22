#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import threading
from pathlib import Path
import numpy as np
import os
import platform
import subprocess

VERSION = "2.0.0"


def detectar_conteudo(img):
    """Retorna (x_min, y_min, x_max_excl, y_max_excl) da área não transparente."""
    array = np.array(img)
    alpha = array[:, :, 3]
    rows = np.any(alpha > 0, axis=1)
    cols = np.any(alpha > 0, axis=0)

    if not rows.any() or not cols.any():
        return None

    y_min, y_max = np.where(rows)[0][[0, -1]]
    x_min, x_max = np.where(cols)[0][[0, -1]]
    return (int(x_min), int(y_min), int(x_max) + 1, int(y_max) + 1)


def montar_figurinha(img, margem_percent, forcar_quadrado, limite_lado):
    """
    Recorta a área preenchida da imagem e monta um canvas 'pouco maior' que
    o conteúdo, com o conteúdo centralizado. Retorna (canvas_final, info_dict).
    """
    img = img.convert("RGBA")
    box = detectar_conteudo(img)
    if box is None:
        raise ValueError("Imagem totalmente transparente (sem conteúdo detectável)")

    x0, y0, x1, y1 = box
    content_w = x1 - x0
    content_h = y1 - y0
    cropped = img.crop((x0, y0, x1, y1))

    margem_px = round(max(content_w, content_h) * (margem_percent / 100))
    canvas_w = content_w + 2 * margem_px
    canvas_h = content_h + 2 * margem_px

    if forcar_quadrado:
        lado = max(canvas_w, canvas_h)
        canvas_w = canvas_h = lado

    escalado = False
    if limite_lado and max(canvas_w, canvas_h) > limite_lado:
        escala = limite_lado / max(canvas_w, canvas_h)
        canvas_w = max(1, round(canvas_w * escala))
        canvas_h = max(1, round(canvas_h * escala))
        novo_cw = max(1, round(cropped.width * escala))
        novo_ch = max(1, round(cropped.height * escala))
        cropped = cropped.resize((novo_cw, novo_ch), Image.Resampling.LANCZOS)
        escalado = True

    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    off_x = (canvas_w - cropped.width) // 2
    off_y = (canvas_h - cropped.height) // 2
    canvas.paste(cropped, (off_x, off_y), cropped)

    info = {
        "content_w": content_w,
        "content_h": content_h,
        "canvas_w": canvas_w,
        "canvas_h": canvas_h,
        "margem_px": margem_px,
        "escalado": escalado,
    }
    return canvas, info


class PreviewFigurinha(tk.Toplevel):
    """Janela somente-leitura: mostra como a figurinha vai ficar, sem exigir ajuste manual."""

    def __init__(self, parent, file_path, margem_percent, forcar_quadrado, limite_lado):
        super().__init__(parent)
        self.title(f"Pré-visualizar - {Path(file_path).name}")
        self.resizable(False, False)
        self.transient(parent)

        original = Image.open(file_path)
        canvas_img, info = montar_figurinha(
            original, margem_percent, forcar_quadrado, limite_lado
        )

        frame = ttk.Frame(self, padding=15)
        frame.pack(fill="both", expand=True)

        preview_size = 320
        display = canvas_img.copy()
        display.thumbnail((preview_size, preview_size), Image.Resampling.LANCZOS)

        board = Image.new("RGBA", (preview_size, preview_size), (235, 235, 235, 255))
        px = (preview_size - display.width) // 2
        py = (preview_size - display.height) // 2
        board.paste(display, (px, py), display)

        self.photo = ImageTk.PhotoImage(board)
        canvas_widget = tk.Canvas(frame, width=preview_size, height=preview_size,
                                   highlightthickness=1, highlightbackground="gray")
        canvas_widget.pack(pady=(0, 10))
        canvas_widget.create_image(0, 0, image=self.photo, anchor="nw")

        texto = (
            f"Área preenchida detectada: {info['content_w']}×{info['content_h']}px\n"
            f"Margem aplicada: {info['margem_px']}px por lado\n"
            f"Canvas final: {info['canvas_w']}×{info['canvas_h']}px"
        )
        if info["escalado"]:
            texto += "\n(reduzido para respeitar o limite de tamanho)"

        ttk.Label(frame, text=texto, justify="left").pack(fill="x", pady=(0, 10))
        ttk.Button(frame, text="Fechar", command=self.destroy).pack()


class NormalizadorFigurinhas:
    def __init__(self, root):
        self.root = root
        self.root.title("Normalizador de Figurinhas")
        self.root.geometry("1000x820")

        self.root.state('zoomed')  # Windows
        try:
            self.root.attributes('-zoomed', True)  # macOS/Linux alternativo
        except Exception:
            pass

        self.processing = False
        self.cancel_event = threading.Event()
        self.files_selected = []
        self.output_dir = None

        self._build_ui()

    def _build_ui(self):
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill="both", expand=True)

        title = ttk.Label(main_frame, text="Normalizador de Figurinhas",
                           font=("Arial", 16, "bold"))
        title.pack(pady=(0, 5))
        subtitle = ttk.Label(
            main_frame,
            text="Cada PNG ganha automaticamente um canvas do tamanho do seu próprio conteúdo, "
                 "com uma margem pequena, centralizado.",
            foreground="#555555"
        )
        subtitle.pack(pady=(0, 15))

        # 1. Seleção de arquivos
        file_frame = ttk.LabelFrame(main_frame, text="1. Selecionar PNGs", padding="10")
        file_frame.pack(fill="x", pady=(0, 10))

        btn_frame = ttk.Frame(file_frame)
        btn_frame.pack(fill="x", expand=True)

        ttk.Button(btn_frame, text="Escolher PNGs",
                   command=self._select_files).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Escolher Pasta",
                   command=self._select_folder).pack(side="left", padx=5)

        self.files_label = ttk.Label(file_frame, text="Nenhum arquivo selecionado",
                                      foreground="gray")
        self.files_label.pack(fill="x", pady=(10, 0))

        # 2. Configurações automáticas
        config_frame = ttk.LabelFrame(main_frame, text="2. Configurações", padding="10")
        config_frame.pack(fill="x", pady=(0, 10))

        margem_frame = ttk.Frame(config_frame)
        margem_frame.pack(fill="x", pady=3)
        ttk.Label(margem_frame, text="Margem ao redor do conteúdo:").pack(side="left", padx=(0, 8))
        self.margem_var = tk.DoubleVar(value=10.0)
        margem_spin = ttk.Spinbox(margem_frame, from_=0, to=50, increment=1,
                                   textvariable=self.margem_var, width=6)
        margem_spin.pack(side="left")
        ttk.Label(margem_frame, text="% do lado maior do conteúdo").pack(side="left", padx=(6, 0))

        self.quadrado_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            config_frame, variable=self.quadrado_var,
            text="Forçar canvas quadrado (útil se o destino exigir figurinha 1:1, ex. WhatsApp)"
        ).pack(fill="x", pady=3)

        limite_frame = ttk.Frame(config_frame)
        limite_frame.pack(fill="x", pady=3)
        self.limite_ativo_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(limite_frame, variable=self.limite_ativo_var,
                        text="Limitar o lado maior do canvas a").pack(side="left")
        self.limite_var = tk.IntVar(value=512)
        ttk.Spinbox(limite_frame, from_=64, to=4096, increment=32,
                    textvariable=self.limite_var, width=6).pack(side="left", padx=6)
        ttk.Label(limite_frame, text="px (reduz proporcionalmente se passar disso)").pack(side="left")

        dica = ttk.Label(
            config_frame,
            text="Dica: dê um duplo clique num arquivo na lista abaixo para pré-visualizar "
                 "o resultado antes de processar tudo.",
            foreground="#777777", font=("Arial", 9)
        )
        dica.pack(fill="x", pady=(6, 0))

        # 3. Lista de arquivos (só visualização/preview, sem edição manual obrigatória)
        list_frame = ttk.LabelFrame(main_frame, text="3. Arquivos Selecionados", padding="10")
        list_frame.pack(fill="both", expand=True, pady=(0, 10))

        self.listbox = tk.Listbox(list_frame, height=8, font=("Arial", 10))
        self.listbox.pack(side="left", fill="both", expand=True)
        self.listbox.bind("<Double-Button-1>", self._on_preview_file)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=scrollbar.set)

        # 4. Pasta de saída
        output_frame = ttk.LabelFrame(main_frame, text="4. Pasta de Saída", padding="10")
        output_frame.pack(fill="x", pady=(0, 10))

        ttk.Button(output_frame, text="Escolher Pasta de Saída",
                   command=self._select_output).pack(fill="x")

        self.output_label = ttk.Label(output_frame, text="Padrão: mesma pasta dos PNGs",
                                       foreground="gray")
        self.output_label.pack(fill="x", pady=(10, 0))

        # 5. Progresso
        progress_frame = ttk.LabelFrame(main_frame, text="5. Processar", padding="10")
        progress_frame.pack(fill="both", expand=True, pady=(0, 10))

        self.progress_var = tk.IntVar(value=0)
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var,
                                             maximum=100)
        self.progress_bar.pack(fill="x", pady=5)

        self.status_text = tk.Text(progress_frame, height=8, width=120, state="disabled",
                                    wrap="word", font=("Courier", 9))
        self.status_text.pack(fill="both", expand=True, pady=5)

        # Botões
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=(0, 10))

        self.process_btn = ttk.Button(button_frame, text="PROCESSAR",
                                       command=self._start_processing)
        self.process_btn.pack(side="left", padx=5)

        self.cancel_btn = ttk.Button(button_frame, text="Cancelar",
                                      command=self._cancel_processing, state="disabled")
        self.cancel_btn.pack(side="left", padx=5)

        ttk.Button(button_frame, text="Limpar", command=self._clear).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Abrir Pasta de Saída",
                   command=self._open_output).pack(side="left", padx=5)

        # Footer
        footer_frame = ttk.Frame(main_frame)
        footer_frame.pack(fill="x", side="bottom")
        ttk.Label(footer_frame, text=f"Normalizador de Figurinhas • v{VERSION}",
                  foreground="#8b949e", font=("Arial", 9)).pack(side="right")

    # ---------- Seleção de arquivos ----------

    def _select_files(self):
        files = filedialog.askopenfilenames(
            filetypes=[("PNG files", "*.png"), ("All files", "*.*")]
        )
        if files:
            self.files_selected = list(files)
            self._update_file_label()
            self._update_listbox()

    def _select_folder(self):
        folder = filedialog.askdirectory(title="Escolher pasta com PNGs")
        if folder:
            png_files = sorted(Path(folder).glob("*.png"))
            if png_files:
                self.files_selected = [str(f) for f in png_files]
                self._update_file_label()
                self._update_listbox()
            else:
                messagebox.showwarning("Aviso", "Nenhum PNG encontrado nessa pasta.")

    def _update_file_label(self):
        count = len(self.files_selected)
        if count == 1:
            self.files_label.config(text="1 arquivo selecionado", foreground="black")
        else:
            self.files_label.config(text=f"{count} arquivos selecionados", foreground="black")

    def _update_listbox(self):
        self.listbox.delete(0, tk.END)
        for f in self.files_selected:
            self.listbox.insert(tk.END, Path(f).name)

    def _on_preview_file(self, event):
        if not self.listbox.curselection():
            return
        idx = self.listbox.curselection()[0]
        file_path = self.files_selected[idx]
        try:
            PreviewFigurinha(
                self.root, file_path,
                self.margem_var.get(),
                self.quadrado_var.get(),
                self.limite_var.get() if self.limite_ativo_var.get() else None
            )
        except Exception as e:
            messagebox.showerror("Erro na pré-visualização", str(e))

    def _select_output(self):
        folder = filedialog.askdirectory(title="Escolher pasta de saída")
        if folder:
            self.output_dir = folder
            self.output_label.config(text=f"Saída: {folder}", foreground="black")

    def _clear(self):
        self.files_selected = []
        self.output_dir = None
        self.files_label.config(text="Nenhum arquivo selecionado", foreground="gray")
        self.output_label.config(text="Padrão: mesma pasta dos PNGs", foreground="gray")
        self.listbox.delete(0, tk.END)
        self.progress_var.set(0)
        self.status_text.config(state="normal")
        self.status_text.delete("1.0", "end")
        self.status_text.config(state="disabled")

    def _log(self, message):
        self.status_text.config(state="normal")
        self.status_text.insert("end", message + "\n")
        self.status_text.see("end")
        self.status_text.config(state="disabled")
        self.root.update()

    # ---------- Processamento ----------

    def _start_processing(self):
        if not self.files_selected:
            messagebox.showwarning("Aviso", "Selecione pelo menos um PNG.")
            return

        self.processing = True
        self.cancel_event.clear()
        self.process_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.status_text.config(state="normal")
        self.status_text.delete("1.0", "end")
        self.status_text.config(state="disabled")

        thread = threading.Thread(target=self._process_files, daemon=True)
        thread.start()

    def _cancel_processing(self):
        self.cancel_event.set()
        self.cancel_btn.config(state="disabled")
        self._log(">> Cancelamento solicitado, aguardando o arquivo atual terminar...")

    def _process_files(self):
        try:
            margem_percent = self.margem_var.get()
            forcar_quadrado = self.quadrado_var.get()
            limite_lado = self.limite_var.get() if self.limite_ativo_var.get() else None

            total = len(self.files_selected)
            self._log(f"Processando {total} arquivo(s)...")
            self._log(f"Margem: {margem_percent}% | Quadrado forçado: {'sim' if forcar_quadrado else 'não'} | "
                       f"Limite de lado: {limite_lado if limite_lado else 'sem limite'}\n")

            processados = 0
            cancelado = False

            for idx, file_path in enumerate(self.files_selected, 1):
                if self.cancel_event.is_set():
                    cancelado = True
                    break

                try:
                    name = Path(file_path).name
                    self._log(f"[{idx}/{total}] {name}")

                    original = Image.open(file_path)
                    final_img, info = montar_figurinha(
                        original, margem_percent, forcar_quadrado, limite_lado
                    )

                    output_dir = self.output_dir or str(Path(file_path).parent)
                    output_path = Path(output_dir) / f"figurinha_{Path(file_path).stem}.png"
                    final_img.save(output_path, "PNG")

                    self._log(
                        f"  conteúdo {info['content_w']}×{info['content_h']}px -> "
                        f"canvas {info['canvas_w']}×{info['canvas_h']}px"
                    )
                    self._log(f"✓ Salvo como: {output_path.name}\n")
                    processados += 1

                except Exception as e:
                    self._log(f"✗ Erro em {Path(file_path).name}: {str(e)}\n")

                progress = int((idx / total) * 100)
                self.progress_var.set(progress)

            self._log("=" * 70)
            if cancelado:
                self._log(f"Cancelado pelo usuário. {processados}/{total} arquivo(s) processado(s).")
                messagebox.showinfo("Cancelado", f"Processamento cancelado. {processados}/{total} concluídos.")
            else:
                self._log(f"Processamento concluído! {processados}/{total} arquivo(s) processado(s).")
                self.progress_var.set(100)
                messagebox.showinfo("Sucesso", "Todas as figurinhas foram normalizadas!")

        except Exception as e:
            self._log(f"Erro geral: {str(e)}")
            messagebox.showerror("Erro", f"Erro durante processamento: {str(e)}")

        finally:
            self.processing = False
            self.process_btn.config(state="normal")
            self.cancel_btn.config(state="disabled")

    def _open_output(self):
        if not self.output_dir and not self.files_selected:
            messagebox.showinfo("Info", "Nenhuma pasta de saída definida.")
            return

        folder = self.output_dir or str(Path(self.files_selected[0]).parent)

        if platform.system() == "Darwin":  # macOS
            subprocess.Popen(["open", folder])
        elif platform.system() == "Windows":
            os.startfile(folder)
        else:  # Linux
            subprocess.Popen(["xdg-open", folder])


if __name__ == "__main__":
    root = tk.Tk()
    app = NormalizadorFigurinhas(root)
    root.mainloop()
