"""
PrintShot - Captura de tela de área fixa, multiplataforma (Windows e Mac).

Versão consolidada e corrigida do repositório DiegoVSC42/Printshot:
- No Mac, a captura usa o utilitário nativo `screencapture` (resolve tela
  Retina e não depende de bibliotecas extras).
- No Windows, usa pyautogui/ImageGrab/mss como antes.
- Nada de ctypes.windll fora do Windows.
- Configuração salva no home do usuário (funciona dentro de .app/.exe).
"""
import tkinter as tk
from tkinter import ttk, filedialog
import os
import sys
import json
import subprocess
import platform
import tempfile
from datetime import datetime

from PIL import Image

import atualizador  # atualizacao automatica

VERSION = "1.3.1"
APP_NAME = "PrintShot"
IS_MAC = platform.system() == "Darwin"
IS_WINDOWS = platform.system() == "Windows"


# ======================================================================
# Configuração
# ======================================================================
class ConfigManager:
    """Salva as coordenadas no home do usuário (~/.printshot)."""

    def __init__(self):
        config_dir = os.path.join(os.path.expanduser("~"), ".printshot")
        os.makedirs(config_dir, exist_ok=True)
        self.config_file = os.path.join(config_dir, "capture_area.json")

    def load_coords(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    def save_coords(self, coords):
        with open(self.config_file, "w") as f:
            json.dump(coords, f, indent=4)


# ======================================================================
# Captura de tela
# ======================================================================
class ScreenCapture:
    @staticmethod
    def _grab_mac(x, y, width, height):
        """Captura no Mac com o utilitário nativo screencapture.

        O screencapture recebe coordenadas em pontos e cuida sozinho da
        escala Retina, o que evita o recorte errado do pyautogui.
        """
        tmp = tempfile.mktemp(suffix=".png")
        result = subprocess.run(
            ["screencapture", "-x", f"-R{x},{y},{width},{height}", tmp],
            capture_output=True,
        )
        if result.returncode != 0 or not os.path.exists(tmp):
            raise RuntimeError(
                "Falha ao capturar. Verifique a permissão de Gravação de Tela "
                "em Ajustes do Sistema > Privacidade e Segurança."
            )
        img = Image.open(tmp)
        img.load()
        os.remove(tmp)
        return img

    @staticmethod
    def _grab_windows(x, y, width, height):
        """Captura no Windows (pyautogui, com reservas)."""
        screenshot = None
        try:
            import pyautogui
            screenshot = pyautogui.screenshot(region=(x, y, width, height))
        except Exception:
            pass

        if screenshot is None:
            from PIL import ImageGrab
            screenshot = ImageGrab.grab(
                bbox=(x, y, x + width, y + height), all_screens=True
            )

        # Se a imagem veio praticamente preta, tenta o mss como reserva
        try:
            from PIL import ImageStat
            mean = ImageStat.Stat(screenshot.convert("L")).mean[0]
            if mean < 10:
                import mss
                with mss.mss() as sct:
                    monitor = {"top": y, "left": x, "width": width, "height": height}
                    sct_img = sct.grab(monitor)
                    screenshot = Image.frombytes(
                        "RGB", sct_img.size, sct_img.bgra, "raw", "BGRX"
                    )
        except Exception:
            pass

        return screenshot

    @classmethod
    def capture_area(cls, x, y, width, height, save_path, file_name=None):
        os.makedirs(save_path, exist_ok=True)

        if IS_MAC:
            screenshot = cls._grab_mac(x, y, width, height)
        else:
            screenshot = cls._grab_windows(x, y, width, height)

        if file_name and file_name.strip():
            filename = file_name.strip()
            if not filename.lower().endswith(".png"):
                filename += ".png"
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"captura_{timestamp}.png"

        filepath = os.path.join(save_path, filename)
        screenshot.save(filepath)
        return filepath


# ======================================================================
# Utilitário: área virtual da tela (todos os monitores)
# ======================================================================
def get_virtual_screen(window):
    """Retorna (left, top, width, height) cobrindo todos os monitores."""
    if IS_WINDOWS:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            return (
                user32.GetSystemMetrics(76),
                user32.GetSystemMetrics(77),
                user32.GetSystemMetrics(78),
                user32.GetSystemMetrics(79),
            )
        except Exception:
            pass
    return (0, 0, window.winfo_screenwidth(), window.winfo_screenheight())


# ======================================================================
# Seleção de área
# ======================================================================
class AreaSelector:
    def __init__(self, callback):
        self.callback = callback
        self.selection_window = None
        self.start_x = None
        self.start_y = None
        self.rect = None

    def start_selection(self):
        self.selection_window = tk.Toplevel()
        left, top, width, height = get_virtual_screen(self.selection_window)

        self.selection_window.geometry(f"{width}x{height}+{left}+{top}")
        self.selection_window.attributes("-topmost", True)
        self.selection_window.attributes("-alpha", 0.3)
        self.selection_window.configure(background="black")
        # Sobreposição sem borda na MESMA tela (não usar o modo de tela
        # cheia do macOS: ele cria uma mesa nova e esconde o app que se
        # quer capturar).
        self.selection_window.overrideredirect(True)
        self.selection_window.lift()

        self.canvas = tk.Canvas(
            self.selection_window, cursor="cross",
            highlightthickness=0, background="black",
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.canvas.create_text(
            (width // 2), 50,
            text="Arraste o mouse para selecionar a área\nPressione ESC para cancelar",
            fill="white", font=("Arial", 16, "bold"),
        )

        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.selection_window.bind("<Escape>", lambda e: self.cancel_selection())
        self.canvas.bind("<Escape>", lambda e: self.cancel_selection())
        # Garante que a sobreposição fique na frente e receba o mouse
        self.selection_window.after(50, self.selection_window.lift)
        self.selection_window.after(60, self.selection_window.focus_force)

    def on_press(self, event):
        self.start_x = event.x_root
        self.start_y = event.y_root
        self.canvas_start_x = event.x
        self.canvas_start_y = event.y
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y, outline="red", width=3
        )

    def on_drag(self, event):
        if self.rect:
            self.canvas.coords(
                self.rect, self.canvas_start_x, self.canvas_start_y,
                event.x, event.y,
            )

    def on_release(self, event):
        end_x_root = event.x_root
        end_y_root = event.y_root

        x = min(self.start_x, end_x_root)
        y = min(self.start_y, end_y_root)
        width = abs(end_x_root - self.start_x)
        height = abs(end_y_root - self.start_y)

        self.selection_window.destroy()

        if width > 10 and height > 10:
            self.callback(x, y, width, height)
        else:
            self.callback(None, None, None, None)

    def cancel_selection(self):
        if self.selection_window:
            self.selection_window.destroy()
        self.callback(None, None, None, None)


# ======================================================================
# Janela de contorno (preview da área)
# ======================================================================
class PreviewWindow:
    """Mostra um contorno vermelho na tela indicando a área configurada."""

    def __init__(self):
        self.window = None
        self.canvas = None

    def show(self, x, y, width, height):
        if self.window and self.window.winfo_exists():
            self.update(x, y, width, height)
            return

        self.window = tk.Toplevel()
        self.window.attributes("-topmost", True)
        self.window.attributes("-alpha", 0.35)
        self.window.configure(background="red")
        self.window.overrideredirect(True)
        self.update(x, y, width, height)

    def update(self, x, y, width, height):
        if self.window and self.window.winfo_exists():
            self.window.geometry(f"{max(width, 1)}x{max(height, 1)}+{x}+{y}")

    def is_open(self):
        return self.window is not None and self.window.winfo_exists()

    def close(self):
        if self.is_open():
            self.window.destroy()
        self.window = None


# ======================================================================
# Aplicação principal
# ======================================================================
class ScreenCaptureApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} - Captura de Área Fixa")
        self.root.geometry("850x650")
        self.root.minsize(750, 600)

        self.config_manager = ConfigManager()
        self.preview = PreviewWindow()
        self.area_coords = self.config_manager.load_coords()

        self.last_capture_path = None
        self.sequence_counter = 1
        self.sequential_mode = tk.BooleanVar(value=False)
        self.last_folder_path = ""

        self.create_widgets()

        self.save_path_var.trace_add("write", self.on_folder_change)
        self.root.bind("<Configure>", self.on_window_resize)

    # ------------------------------------------------------------------
    def default_save_folder(self):
        home = os.path.expanduser("~")
        downloads = os.path.join(home, "Downloads")
        return downloads if os.path.isdir(downloads) else home

    # ------------------------------------------------------------------
    def create_widgets(self):
        # Rodapé com a versão (empacotado primeiro para ficar no fundo)
        footer = tk.Label(
            self.root, text=f"{APP_NAME} • v{VERSION}",
            fg="#8b949e", font=("Arial", 9), anchor="e",
        )
        footer.pack(side="bottom", fill=tk.X, padx=10, pady=(0, 4))

        container = ttk.Frame(self.root)
        container.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        # Coluna esquerda rolável: em janela reduzida, nada some — é só rolar
        left_outer = ttk.Frame(container, width=415)
        left_outer.pack(side=tk.LEFT, fill=tk.Y, expand=False, padx=(0, 10))
        left_outer.pack_propagate(False)

        self.left_canvas = tk.Canvas(left_outer, highlightthickness=0, width=395)
        left_scroll = ttk.Scrollbar(
            left_outer, orient="vertical", command=self.left_canvas.yview
        )
        self.left_canvas.configure(yscrollcommand=left_scroll.set)
        left_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        left_frame = ttk.Frame(self.left_canvas)
        self._left_window = self.left_canvas.create_window(
            (0, 0), window=left_frame, anchor="nw"
        )
        left_frame.bind(
            "<Configure>",
            lambda e: self.left_canvas.configure(
                scrollregion=self.left_canvas.bbox("all")
            ),
        )
        self.left_canvas.bind(
            "<Configure>",
            lambda e: self.left_canvas.itemconfigure(
                self._left_window, width=e.width
            ),
        )

        # Rolagem com a roda do mouse / trackpad sobre a coluna esquerda
        def _on_mousewheel(event):
            delta = event.delta if IS_MAC else int(event.delta / 120)
            self.left_canvas.yview_scroll(-delta, "units")

        self.left_canvas.bind(
            "<Enter>",
            lambda e: self.left_canvas.bind_all("<MouseWheel>", _on_mousewheel),
        )
        self.left_canvas.bind(
            "<Leave>", lambda e: self.left_canvas.unbind_all("<MouseWheel>")
        )

        separator = ttk.Separator(container, orient=tk.VERTICAL)
        separator.pack(side=tk.LEFT, fill=tk.Y, padx=10)

        right_frame = ttk.LabelFrame(container, text="Última Captura", padding="15")
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # ===== Coluna esquerda =====
        title_label = ttk.Label(
            left_frame, text="Captura de Tela - Área Fixa",
            font=("Arial", 14, "bold"),
        )
        title_label.pack(pady=(0, 8))

        info_frame = ttk.LabelFrame(left_frame, text="Área de Captura", padding="10")
        info_frame.pack(fill=tk.X, pady=(0, 10))

        if self.area_coords:
            coords_text = (
                f"X: {self.area_coords['x']}, Y: {self.area_coords['y']}\n"
                f"Largura: {self.area_coords['width']}px, "
                f"Altura: {self.area_coords['height']}px"
            )
            status_text = "Área configurada"
            status_color = "green"
        else:
            coords_text = "Nenhuma área selecionada"
            status_text = "Configure a área primeiro"
            status_color = "orange"

        self.coords_label = ttk.Label(info_frame, text=coords_text)
        self.coords_label.pack(pady=5)

        self.status_label = ttk.Label(
            info_frame, text=status_text,
            foreground=status_color, font=("Arial", 10, "bold"),
        )
        self.status_label.pack(pady=5)

        # Ajuste fino
        self.adjust_frame = ttk.LabelFrame(left_frame, text="Ajuste Fino", padding="10")
        self.adjust_frame.pack(fill=tk.X, pady=(0, 10))

        adjust_grid = ttk.Frame(self.adjust_frame)
        adjust_grid.pack(fill=tk.X)

        self.x_var = tk.IntVar(value=self.area_coords["x"] if self.area_coords else 0)
        self.y_var = tk.IntVar(value=self.area_coords["y"] if self.area_coords else 0)
        self.width_var = tk.IntVar(
            value=self.area_coords["width"] if self.area_coords else 360
        )
        self.height_var = tk.IntVar(
            value=self.area_coords["height"] if self.area_coords else 740
        )

        ttk.Label(adjust_grid, text="X:").grid(row=0, column=0, sticky=tk.E, padx=(0, 5), pady=5)
        x_spinbox = ttk.Spinbox(
            adjust_grid, from_=-5000, to=5000, textvariable=self.x_var,
            width=12, command=self.on_adjust_change,
        )
        x_spinbox.grid(row=0, column=1, padx=(0, 15), pady=5)
        x_spinbox.bind("<KeyRelease>", lambda e: self.on_adjust_change())

        ttk.Label(adjust_grid, text="Y:").grid(row=0, column=2, sticky=tk.E, padx=(0, 5), pady=5)
        y_spinbox = ttk.Spinbox(
            adjust_grid, from_=-5000, to=5000, textvariable=self.y_var,
            width=12, command=self.on_adjust_change,
        )
        y_spinbox.grid(row=0, column=3, pady=5)
        y_spinbox.bind("<KeyRelease>", lambda e: self.on_adjust_change())

        ttk.Label(adjust_grid, text="Largura:").grid(row=1, column=0, sticky=tk.E, padx=(0, 5), pady=5)
        width_spinbox = ttk.Spinbox(
            adjust_grid, from_=1, to=5000, textvariable=self.width_var,
            width=12, command=self.on_adjust_change,
        )
        width_spinbox.grid(row=1, column=1, padx=(0, 15), pady=5)
        width_spinbox.bind("<KeyRelease>", lambda e: self.on_adjust_change())

        ttk.Label(adjust_grid, text="Altura:").grid(row=1, column=2, sticky=tk.E, padx=(0, 5), pady=5)
        height_spinbox = ttk.Spinbox(
            adjust_grid, from_=1, to=5000, textvariable=self.height_var,
            width=12, command=self.on_adjust_change,
        )
        height_spinbox.grid(row=1, column=3, pady=5)
        height_spinbox.bind("<KeyRelease>", lambda e: self.on_adjust_change())

        adjust_btn_frame = ttk.Frame(self.adjust_frame)
        adjust_btn_frame.pack(pady=(10, 0))

        ttk.Button(
            adjust_btn_frame, text="Visualizar Área",
            command=self.show_preview, width=18,
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            adjust_btn_frame, text="Salvar Ajustes",
            command=self.save_adjustments, width=18,
        ).pack(side=tk.LEFT, padx=5)

        if not self.area_coords:
            self.disable_adjust_controls()

        # Botões principais
        button_frame = ttk.Frame(left_frame)
        button_frame.pack(pady=8)

        ttk.Button(
            button_frame, text="Selecionar Área",
            command=self.start_selection, width=30,
        ).pack(pady=5)

        self.capture_btn = ttk.Button(
            button_frame, text="Capturar Tela",
            command=self.capture_screen, width=30,
        )
        self.capture_btn.pack(pady=5)

        if not self.area_coords:
            self.capture_btn.config(state="disabled")

        # Opções de salvamento
        save_frame = ttk.LabelFrame(left_frame, text="Opções de Salvamento", padding="10")
        save_frame.pack(fill=tk.X, pady=(0, 10))

        self.save_path_var = tk.StringVar(value=self.default_save_folder())

        ttk.Label(save_frame, text="Pasta de destino:").pack(anchor=tk.W, pady=(0, 5))

        path_frame = ttk.Frame(save_frame)
        path_frame.pack(fill=tk.X)

        ttk.Entry(path_frame, textvariable=self.save_path_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5)
        )
        ttk.Button(path_frame, text="...", command=self.choose_folder, width=3).pack(side=tk.LEFT)

        ttk.Label(save_frame, text="Nome do arquivo (opcional):").pack(anchor=tk.W, pady=(10, 5))

        self.file_name_var = tk.StringVar()
        ttk.Entry(save_frame, textvariable=self.file_name_var).pack(fill=tk.X, padx=(0, 5))

        seq_frame = ttk.Frame(save_frame)
        seq_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Checkbutton(
            seq_frame, text="Ativar Numeração Sequencial",
            variable=self.sequential_mode,
        ).pack(side=tk.LEFT)

        ttk.Button(seq_frame, text="Zerar", width=6, command=self.reset_counter).pack(side=tk.RIGHT)

        self.open_folder_btn = ttk.Button(
            save_frame, text="Abrir Pasta de Capturas",
            command=self.open_captures_folder, width=30,
        )
        self.open_folder_btn.pack(pady=(10, 0))

        self.copy_btn = ttk.Button(
            save_frame, text="Copiar Última Captura",
            command=self.copy_last_capture, width=30, state="disabled",
        )
        self.copy_btn.pack(pady=(6, 0))

        self.save_as_btn = ttk.Button(
            save_frame, text="Salvar Como...",
            command=self.save_last_capture_as, width=30, state="disabled",
        )
        self.save_as_btn.pack(pady=(6, 0))

        instructions = (
            "Instruções:\n"
            "1. Selecione a área na tela\n"
            "2. Ajuste fino se necessário\n"
            "3. Capture e veja o preview ao lado"
        )
        inst_label = ttk.Label(
            left_frame, text=instructions, justify=tk.LEFT,
            foreground="gray", font=("Arial", 9),
        )
        inst_label.pack(pady=(6, 0))

        self.status_bar_var = tk.StringVar()
        self.status_bar = ttk.Label(
            left_frame, textvariable=self.status_bar_var,
            foreground="blue", wraplength=380,
        )
        self.status_bar.pack(pady=(8, 0), fill=tk.X)

        # ===== Coluna direita (preview da captura) =====
        preview_container = ttk.Frame(right_frame)
        preview_container.pack(fill=tk.BOTH, expand=True)

        self.preview_canvas = tk.Canvas(
            preview_container, bg="#2b2b2b", highlightthickness=0
        )
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)

        self.preview_text_id = self.preview_canvas.create_text(
            120, 240,
            text="Nenhuma captura ainda\n\nAs capturas\naparecerão aqui",
            font=("Arial", 11), fill="#888888", justify=tk.CENTER,
            tags="initial_text",
        )
        self.preview_image_id = None

    # ------------------------------------------------------------------
    def update_status_bar(self, message, color="black"):
        self.status_bar_var.set(message)
        self.status_bar.config(foreground=color)
        self.root.after(
            5000,
            lambda: self.status_bar_var.set("")
            if self.status_bar_var.get() == message else None,
        )

    def on_folder_change(self, *args):
        current_path = self.save_path_var.get()
        if current_path != self.last_folder_path:
            self.sequence_counter = 1
            self.last_folder_path = current_path

    def reset_counter(self):
        self.sequence_counter = 1
        self.update_status_bar("Contador sequencial zerado (volta ao 1).", "blue")

    def on_window_resize(self, event):
        if event.widget == self.root:
            if self.preview_text_id and not self.preview_image_id:
                try:
                    canvas_width = self.preview_canvas.winfo_width()
                    canvas_height = self.preview_canvas.winfo_height()
                    self.preview_canvas.coords(
                        self.preview_text_id,
                        canvas_width // 2, canvas_height // 2,
                    )
                except Exception:
                    pass

    def on_adjust_change(self):
        if self.preview.is_open():
            self.preview.update(
                self.x_var.get(), self.y_var.get(),
                self.width_var.get(), self.height_var.get(),
            )

    def show_preview(self):
        self.preview.show(
            self.x_var.get(), self.y_var.get(),
            self.width_var.get(), self.height_var.get(),
        )

    def save_adjustments(self):
        self.area_coords = {
            "x": self.x_var.get(),
            "y": self.y_var.get(),
            "width": self.width_var.get(),
            "height": self.height_var.get(),
        }
        self.config_manager.save_coords(self.area_coords)
        self.update_interface()
        self.update_status_bar("Ajustes salvos com sucesso!", "green")
        self.preview.close()

    def start_selection(self):
        self.root.iconify()
        self.root.after(500, self._create_selector)

    def _create_selector(self):
        selector = AreaSelector(self.on_area_selected)
        selector.start_selection()

    def on_area_selected(self, x, y, width, height):
        self.root.deiconify()

        if x is None:
            self.update_status_bar("Seleção cancelada ou área muito pequena!", "orange")
            return

        self.area_coords = {"x": x, "y": y, "width": width, "height": height}
        self.config_manager.save_coords(self.area_coords)

        self.x_var.set(x)
        self.y_var.set(y)
        self.width_var.set(width)
        self.height_var.set(height)

        self.update_status_bar(
            f"Área configurada: {width}x{height}px em ({x}, {y})", "green"
        )
        self.update_interface()

    def update_interface(self):
        if self.area_coords:
            coords_text = (
                f"X: {self.area_coords['x']}, Y: {self.area_coords['y']}\n"
                f"Largura: {self.area_coords['width']}px, "
                f"Altura: {self.area_coords['height']}px"
            )
            self.coords_label.config(text=coords_text)
            self.status_label.config(text="Área configurada", foreground="green")
            self.capture_btn.config(state="normal")
            self.enable_adjust_controls()

    def enable_adjust_controls(self):
        for child in self.adjust_frame.winfo_children():
            self._enable_widget(child)

    def disable_adjust_controls(self):
        for child in self.adjust_frame.winfo_children():
            self._disable_widget(child)

    def _enable_widget(self, widget):
        try:
            widget.config(state="normal")
        except Exception:
            pass
        if isinstance(widget, (ttk.Frame, tk.Frame)):
            for child in widget.winfo_children():
                self._enable_widget(child)

    def _disable_widget(self, widget):
        try:
            widget.config(state="disabled")
        except Exception:
            pass
        if isinstance(widget, (ttk.Frame, tk.Frame)):
            for child in widget.winfo_children():
                self._disable_widget(child)

    def choose_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.save_path_var.set(folder)

    def open_captures_folder(self):
        folder_path = self.save_path_var.get()
        os.makedirs(folder_path, exist_ok=True)
        try:
            if IS_WINDOWS:
                os.startfile(folder_path)
            elif IS_MAC:
                subprocess.run(["open", folder_path])
            else:
                subprocess.run(["xdg-open", folder_path])
        except Exception as e:
            self.update_status_bar(f"Erro ao abrir pasta: {e}", "red")

    def capture_screen(self):
        if not self.area_coords:
            self.update_status_bar("Erro: configure a área antes de capturar!", "red")
            return

        try:
            raw_name = self.file_name_var.get()
            final_name = raw_name

            if self.sequential_mode.get():
                if raw_name and raw_name.strip():
                    final_name = f"{raw_name.strip()}_{self.sequence_counter}"
                else:
                    final_name = str(self.sequence_counter)
                self.sequence_counter += 1

            filepath = ScreenCapture.capture_area(
                self.area_coords["x"],
                self.area_coords["y"],
                self.area_coords["width"],
                self.area_coords["height"],
                self.save_path_var.get(),
                file_name=final_name,
            )

            self.last_capture_path = filepath
            self.copy_btn.config(state="normal")
            self.save_as_btn.config(state="normal")
            self.update_capture_preview(filepath)

            # Copia automaticamente para a área de transferência
            copied = self.copy_image_to_clipboard(filepath)
            if copied:
                self.update_status_bar(
                    f"Captura salva e copiada: {os.path.basename(filepath)}",
                    "green",
                )
            else:
                self.update_status_bar(
                    f"Captura salva: {os.path.basename(filepath)} "
                    "(não consegui copiar para a área de transferência)",
                    "orange",
                )
        except Exception as e:
            self.update_status_bar(f"Erro ao capturar: {e}", "red")

    # ------------------------------------------------------------------
    # Área de transferência
    # ------------------------------------------------------------------
    @staticmethod
    def copy_image_to_clipboard(filepath):
        """Copia a imagem (não o caminho) para a área de transferência."""
        try:
            if IS_MAC:
                script = (
                    'set the clipboard to '
                    f'(read (POSIX file "{filepath}") as «class PNGf»)'
                )
                result = subprocess.run(
                    ["osascript", "-e", script], capture_output=True
                )
                return result.returncode == 0
            if IS_WINDOWS:
                ps = (
                    "Add-Type -AssemblyName System.Windows.Forms; "
                    "Add-Type -AssemblyName System.Drawing; "
                    f"$img=[System.Drawing.Image]::FromFile('{filepath}'); "
                    "[System.Windows.Forms.Clipboard]::SetImage($img); "
                    "$img.Dispose()"
                )
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-STA", "-Command", ps],
                    capture_output=True,
                )
                return result.returncode == 0
            # Linux: tenta xclip, se existir
            with open(filepath, "rb") as f:
                result = subprocess.run(
                    ["xclip", "-selection", "clipboard", "-t", "image/png"],
                    stdin=f, capture_output=True,
                )
            return result.returncode == 0
        except Exception:
            return False

    def save_last_capture_as(self):
        """Salva a última captura em outro lugar, com o nome escolhido."""
        if not self.last_capture_path or not os.path.exists(self.last_capture_path):
            self.update_status_bar("Nenhuma captura para salvar ainda.", "orange")
            return
        destino = filedialog.asksaveasfilename(
            title="Salvar captura como",
            defaultextension=".png",
            filetypes=[("Imagem PNG", "*.png")],
            initialfile=os.path.basename(self.last_capture_path),
        )
        if not destino:
            return
        try:
            import shutil
            shutil.copyfile(self.last_capture_path, destino)
            self.update_status_bar(
                f"Salvo em: {os.path.basename(destino)}", "green"
            )
        except Exception as e:
            self.update_status_bar(f"Erro ao salvar: {e}", "red")

    def copy_last_capture(self):
        if not self.last_capture_path or not os.path.exists(self.last_capture_path):
            self.update_status_bar("Nenhuma captura para copiar ainda.", "orange")
            return
        if self.copy_image_to_clipboard(self.last_capture_path):
            self.update_status_bar(
                "Última captura copiada para a área de transferência.", "green"
            )
        else:
            self.update_status_bar(
                "Não consegui copiar para a área de transferência.", "red"
            )

    def update_capture_preview(self, image_path):
        try:
            from PIL import ImageTk

            img = Image.open(image_path)

            canvas_width = self.preview_canvas.winfo_width()
            canvas_height = self.preview_canvas.winfo_height()
            if canvas_width <= 1:
                canvas_width = 300
            if canvas_height <= 1:
                canvas_height = 500

            img.thumbnail(
                (canvas_width - 40, canvas_height - 40), Image.Resampling.LANCZOS
            )

            self.preview_photo = ImageTk.PhotoImage(img)

            if self.preview_text_id:
                self.preview_canvas.delete(self.preview_text_id)
                self.preview_text_id = None
            if self.preview_image_id:
                self.preview_canvas.delete(self.preview_image_id)

            self.preview_image_id = self.preview_canvas.create_image(
                canvas_width // 2, canvas_height // 2,
                image=self.preview_photo, anchor=tk.CENTER,
            )
        except Exception as e:
            print(f"Erro ao atualizar preview: {e}")


def main():
    root = tk.Tk()
    ScreenCaptureApp(root)
    atualizador.iniciar(root, "printshot", VERSION, "PrintShot")
    root.mainloop()


if __name__ == "__main__":
    main()
