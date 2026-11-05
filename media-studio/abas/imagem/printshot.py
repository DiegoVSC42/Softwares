"""
PrintShot - aba do Estudio de Imagem.

Para que serve:
  - a pessoa marca UMA area da tela, arrastando o mouse;
  - dali em diante, cada clique em "Capturar tela" salva exatamente aquela
    mesma area, num arquivo numerado em sequencia;
  - serve para tirar varias capturas padronizadas (a mesma janela, o mesmo
    recorte) sem ficar reenquadrando a cada foto.

Notas de adaptacao para o Estudio:
  - a JANELA principal do programa virou esta aba; as duas janelas auxiliares
    (o seletor de area, que cobre a tela inteira, e a previa da area, um
    contorno vermelho por cima de tudo) continuam sendo janelas proprias,
    porque so assim elas funcionam. Ambas nascem penduradas na janela real do
    Estudio e se destroem sozinhas quando terminam;
  - na hora de marcar a area, quem se esconde agora e a janela do Estudio
    inteiro (antes era so a janela do PrintShot), para o programa nao sair na
    propria foto;
  - as cores vem todas de `tema.py`. A unica excecao e o seletor de area, que
    cobre a tela e precisa das proprias cores de marcacao. Ele NAO usa
    "stipple": o Tk do Mac ignora o stipple e pinta a area de preto solido,
    tapando justamente o que a pessoa quer enquadrar.

No Mac a captura usa o utilitario nativo `screencapture`, que resolve sozinho
a escala da tela Retina. No Windows usa pyautogui, com ImageGrab e mss como
reserva.
"""

import os
import json
import shutil
import subprocess
import platform
import tempfile
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image

import pastas
import tema
from tema import (COR_FUNDO, COR_PAINEL, COR_CAMPO, COR_BOTAO, COR_BORDA,
                  COR_TEXTO, COR_SUAVE, COR_APAGADO, COR_DESTAQUE, COR_OK,
                  COR_ERRO)

VERSION = "1.4.0"
APP_NAME = "Captura de Área"
IS_MAC = platform.system() == "Darwin"
IS_WINDOWS = platform.system() == "Windows"

# Estas duas so existem no Windows (ver o requirements do projeto original).
# A aba precisa abrir no Mac e no Linux mesmo sem elas, entao o import e
# tolerante: quando faltar, a variavel fica None e o codigo usa a reserva.
try:
    import pyautogui
except Exception:
    pyautogui = None

try:
    import mss
except Exception:
    mss = None

# Cor de aviso do rodape de mensagens, por situacao. Como nao se define estilo
# dentro de aba, cada situacao vira um dos estilos ja criados em `tema.py`.
ESTILO_AVISO = {
    "ok": "Ok.TLabel",
    "erro": "Erro.TLabel",
    "atencao": "Destaque.TLabel",
    "neutro": "Suave.TLabel",
}


# ======================================================================
# Configuracao
# ======================================================================
class ConfigManager:
    """Salva as coordenadas no home do usuario (~/.printshot).

    Fica no home, e nao junto do programa, para continuar funcionando quando
    o Estudio roda de dentro de um .app ou .exe empacotado (essa pasta e
    somente leitura).
    """

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
        """Captura no Mac com o utilitario nativo screencapture.

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
                "Falha ao capturar. Verifique a permissao de Gravacao de Tela "
                "em Ajustes do Sistema > Privacidade e Seguranca."
            )
        img = Image.open(tmp)
        img.load()
        os.remove(tmp)
        return img

    @staticmethod
    def _grab_windows(x, y, width, height):
        """Captura no Windows (pyautogui, com reservas)."""
        screenshot = None
        if pyautogui is not None:
            try:
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
            if mean < 10 and mss is not None:
                with mss.mss() as sct:
                    monitor = {"top": y, "left": x,
                               "width": width, "height": height}
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
# Utilitario: area virtual da tela (todos os monitores)
# ======================================================================
def _virtual_screen_mac():
    """Uniao de todos os monitores no Mac, via CoreGraphics.

    `winfo_screenwidth()/height()` do Tk so enxerga UM monitor (o principal).
    Com duas telas, o overlay de selecao nascia do tamanho de uma tela so, e
    a segunda ficava fora dele -- por isso so dava para selecionar numa.

    CoreGraphics ja vem no sistema (nao precisa instalar nada): pede a lista
    de monitores ativos e soma os retangulos de cada um. As coordenadas sao
    na mesma origem (canto superior esquerdo do monitor principal) que o
    Tk usa para `x_root`/`y_root` e que o `screencapture -R` espera, entao
    nao precisa converter nada depois.
    """
    try:
        import ctypes

        cg = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")

        class CGRect(ctypes.Structure):
            _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double),
                       ("width", ctypes.c_double), ("height", ctypes.c_double)]

        cg.CGDisplayBounds.restype = CGRect
        cg.CGDisplayBounds.argtypes = [ctypes.c_uint32]
        cg.CGGetActiveDisplayList.argtypes = [
            ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_uint32)]

        MAX_TELAS = 16
        ids = (ctypes.c_uint32 * MAX_TELAS)()
        contagem = ctypes.c_uint32(0)
        erro = cg.CGGetActiveDisplayList(MAX_TELAS, ids, ctypes.byref(contagem))
        if erro != 0 or contagem.value == 0:
            return None

        esq = topo = float("inf")
        dir_ = base = float("-inf")
        for i in range(contagem.value):
            r = cg.CGDisplayBounds(ids[i])
            esq = min(esq, r.x)
            topo = min(topo, r.y)
            dir_ = max(dir_, r.x + r.width)
            base = max(base, r.y + r.height)

        if dir_ <= esq or base <= topo:
            return None
        return (int(esq), int(topo), int(dir_ - esq), int(base - topo))
    except Exception:
        return None


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
    if IS_MAC:
        virtual = _virtual_screen_mac()
        if virtual is not None:
            return virtual
    # Reserva: so a tela que o Tk enxerga (um monitor so).
    return (0, 0, window.winfo_screenwidth(), window.winfo_screenheight())


# ======================================================================
# Selecao de area (janela propria, de proposito: cobre a tela inteira)
# ======================================================================
class AreaSelector:
    """Sobreposicao escura sobre a tela toda, para arrastar e marcar a area.

    Esta continua sendo uma janela propria porque so assim ela consegue cobrir
    a tela inteira e receber o arrasto do mouse em qualquer canto. Ela nasce
    pendurada na janela real do Estudio (`mestre`) e se destroi sozinha ao
    terminar. Nunca chama mainloop.
    """

    def __init__(self, callback, mestre=None):
        self.callback = callback
        self.mestre = mestre
        self.selection_window = None
        self.start_x = None
        self.start_y = None
        self.rect = None

    def start_selection(self):
        self.selection_window = tk.Toplevel(self.mestre)
        left, top, width, height = get_virtual_screen(self.selection_window)

        self.selection_window.geometry(f"{width}x{height}+{left}+{top}")
        self.selection_window.attributes("-topmost", True)
        self.selection_window.attributes("-alpha", 0.3)
        self.selection_window.configure(background="black")
        # Sobreposicao sem borda na MESMA tela (nao usar o modo de tela
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
            text="Arraste o mouse para selecionar a area\n"
                 "Pressione ESC para cancelar",
            fill="white", font=("Arial", 16, "bold"),
        )

        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.selection_window.bind("<Escape>", lambda e: self.cancel_selection())
        self.canvas.bind("<Escape>", lambda e: self.cancel_selection())
        # Garante que a sobreposicao fique na frente e receba o mouse
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
        self.selection_window = None

        if width > 10 and height > 10:
            self.callback(x, y, width, height)
        else:
            self.callback(None, None, None, None)

    def cancel_selection(self):
        self.fechar()
        self.callback(None, None, None, None)

    def fechar(self):
        """Fecha a sobreposicao, se ainda estiver aberta."""
        janela, self.selection_window = self.selection_window, None
        if janela is not None:
            try:
                janela.destroy()
            except Exception:
                pass


# ======================================================================
# Janela de contorno (previa da area) - tambem janela propria, de proposito
# ======================================================================
class PreviewWindow:
    """Mostra um retangulo vermelho na tela indicando a area configurada.

    Antes esta janela se posicionava com `geometry("WxH+X+Y")`, do tamanho
    exato da area. No Mac, um Toplevel sem borda posicionado assim as vezes
    nasce um pouco deslocado do pedido (o contorno aparecia um pouco mais
    para baixo do que a area de verdade). O arrasto do AreaSelector nunca
    tinha esse problema porque o retangulo dele e desenhado dentro de um
    canvas, em coordenada RELATIVA a uma janela que ja cobre a tela inteira
    -- nunca reposicionando uma janela pequena.

    Por isso a previa passou a usar a mesma tecnica: uma janela transparente
    cobrindo a tela inteira (como o AreaSelector), com o contorno desenhado
    no canvas em coordenada relativa. Assim ela nunca pode "nascer
    deslocada" -- so pode estar exatamente onde o retangulo foi desenhado.
    """

    def __init__(self, mestre=None):
        self.mestre = mestre
        self.window = None
        self.canvas = None
        self.rect = None
        self.left = 0
        self.top = 0

    def _cor_vazia(self):
        # No Mac, "systemTransparent" e uma cor de sistema de verdade: o que
        # for pintado com ela fica INVISIVEL e clicavel atraves (nao so
        # translucido). No Windows a mesma ideia usa uma cor-chave qualquer,
        # rara o bastante para nunca aparecer sozinha na tela.
        return "systemTransparent" if IS_MAC else "#010203"

    def _garantir_janela(self):
        if self.window and self.window.winfo_exists():
            return
        self.window = tk.Toplevel(self.mestre)
        self.left, self.top, largura, altura = get_virtual_screen(self.window)
        self.window.geometry(f"{largura}x{altura}+{self.left}+{self.top}")
        self.window.attributes("-topmost", True)
        cor_vazia = self._cor_vazia()
        self.window.configure(background=cor_vazia)
        try:
            if IS_MAC:
                self.window.attributes("-transparent", True)
            else:
                self.window.attributes("-transparentcolor", cor_vazia)
        except Exception:
            # Tk sem esse atributo: cai para uma sobreposicao bem fraca, em
            # vez de travar a previa por causa de um efeito cosmetico.
            self.window.attributes("-alpha", 0.35)
        self.window.overrideredirect(True)
        self.canvas = tk.Canvas(self.window, highlightthickness=0,
                                bd=0, background=cor_vazia)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.rect = None

    def show(self, x, y, width, height):
        self._garantir_janela()
        self.update(x, y, width, height)
        self.window.lift()

    def update(self, x, y, width, height):
        if not (self.window and self.window.winfo_exists()):
            return
        # Coordenada RELATIVA a esta janela (que cobre a tela inteira a
        # partir de `left, top`), nunca um novo posicionamento de janela.
        x1, y1 = x - self.left, y - self.top
        x2, y2 = x1 + max(width, 1), y1 + max(height, 1)
        if self.rect is None:
            self.rect = self.canvas.create_rectangle(
                x1, y1, x2, y2, outline="red", width=3)
        else:
            self.canvas.coords(self.rect, x1, y1, x2, y2)

    def is_open(self):
        return self.window is not None and self.window.winfo_exists()

    def close(self):
        if self.is_open():
            try:
                self.window.destroy()
            except Exception:
                pass
        self.window = None
        self.canvas = None
        self.rect = None


# ======================================================================
# Aplicacao principal (agora, a aba)
# ======================================================================
class ScreenCaptureApp:
    def __init__(self, pai):
        self.root = pai
        self.root.configure(bg=COR_FUNDO)

        # Captura e instantanea: nao existe trabalho longo em andamento que o
        # Estudio precise esperar antes de fechar.
        self.rodando = False

        self.config_manager = ConfigManager()
        self.preview = PreviewWindow(self._janela())
        self.area_coords = self.config_manager.load_coords()

        self.selector = None
        self.last_capture_path = None
        self.sequence_counter = 1
        self.sequential_mode = tk.BooleanVar(value=False)
        self.last_folder_path = ""

        # Os widgets Tk puros (o canvas da previa) nao pegam a fonte do tema
        # sozinhos; por isso a aba pede as fontes ao `tema`.
        self.fonte_base, self.fonte_peq, self.fonte_mini = tema.fontes()

        self.create_widgets()

        self.save_path_var.trace_add("write", self.on_folder_change)
        self.last_folder_path = self.save_path_var.get()

    # ------------------------------------------------------------------
    def _janela(self):
        """A janela de verdade do Estudio (nao o quadro desta aba)."""
        return self.root.winfo_toplevel()

    def default_save_folder(self):
        """Regra da casa: o ponto de partida e sempre a pasta de Downloads."""
        return pastas.garantir(pastas.pasta_downloads())

    # ------------------------------------------------------------------
    def create_widgets(self):
        # O rodape de mensagens e ancorado no fundo ANTES de tudo: no Tk, quem
        # e empacotado primeiro em "bottom" fica mais embaixo e nunca some
        # quando falta altura.
        self.status_bar_var = tk.StringVar()
        self.status_bar = ttk.Label(
            self.root, textvariable=self.status_bar_var,
            style="Suave.TLabel", wraplength=1100, anchor="w",
        )
        self.status_bar.pack(side="bottom", fill="x", padx=14, pady=(4, 8))

        container = ttk.Frame(self.root)
        container.pack(fill="both", expand=True, padx=14, pady=(10, 2))

        # ===== Coluna esquerda: os controles =====
        left_frame = ttk.Frame(container)
        left_frame.pack(side="left", fill="y")

        # --- area configurada
        info_frame = ttk.LabelFrame(left_frame, text="Area de captura ")
        info_frame.pack(fill="x")

        if self.area_coords:
            coords_text = (
                f"X: {self.area_coords['x']}, Y: {self.area_coords['y']}  •  "
                f"{self.area_coords['width']} x {self.area_coords['height']} px"
            )
            status_text = "Area configurada"
            status_style = "Ok.TLabel"
        else:
            coords_text = "Nenhuma area selecionada"
            status_text = "Configure a area primeiro"
            status_style = "Destaque.TLabel"

        self.coords_label = ttk.Label(info_frame, text=coords_text,
                                      style="Suave.TLabel")
        self.coords_label.pack(anchor="w", padx=12, pady=(6, 2))

        self.status_label = ttk.Label(info_frame, text=status_text,
                                      style=status_style)
        self.status_label.pack(anchor="w", padx=12, pady=(0, 6))

        # --- ajuste fino
        self.adjust_frame = ttk.LabelFrame(left_frame, text="Ajuste fino ")
        self.adjust_frame.pack(fill="x", pady=(8, 0))

        # Sem `fill="x"`: com o quadro esticado, as colunas dos rotulos
        # cresciam junto e "X:" / "Largura:" acabavam empurrados para longe
        # dos campos. Encolhido ao conteudo, tudo fica encostado a esquerda.
        adjust_grid = ttk.Frame(self.adjust_frame)
        adjust_grid.pack(anchor="w", padx=12, pady=(6, 2))

        self.x_var = tk.IntVar(value=self.area_coords["x"] if self.area_coords else 0)
        self.y_var = tk.IntVar(value=self.area_coords["y"] if self.area_coords else 0)
        self.width_var = tk.IntVar(
            value=self.area_coords["width"] if self.area_coords else 360
        )
        self.height_var = tk.IntVar(
            value=self.area_coords["height"] if self.area_coords else 740
        )

        ttk.Label(adjust_grid, text="X:").grid(row=0, column=0, sticky="e",
                                               padx=(0, 6), pady=3)
        ttk.Spinbox(adjust_grid, from_=-5000, to=5000, textvariable=self.x_var,
                    width=8).grid(row=0, column=1, padx=(0, 14), pady=3)

        ttk.Label(adjust_grid, text="Y:").grid(row=0, column=2, sticky="e",
                                               padx=(0, 6), pady=3)
        ttk.Spinbox(adjust_grid, from_=-5000, to=5000, textvariable=self.y_var,
                    width=8).grid(row=0, column=3, pady=3)

        ttk.Label(adjust_grid, text="Largura:").grid(row=1, column=0, sticky="e",
                                                    padx=(0, 6), pady=3)
        ttk.Spinbox(adjust_grid, from_=1, to=5000, textvariable=self.width_var,
                    width=8).grid(row=1, column=1, padx=(0, 14), pady=3)

        ttk.Label(adjust_grid, text="Altura:").grid(row=1, column=2, sticky="e",
                                                   padx=(0, 6), pady=3)
        ttk.Spinbox(adjust_grid, from_=1, to=5000, textvariable=self.height_var,
                    width=8).grid(row=1, column=3, pady=3)

        # A reacao fica presa na VARIAVEL, nunca no `command=` do Spinbox: o
        # command so dispara quando a pessoa clica naquela setinha, e estes
        # valores tambem mudam por codigo (ao marcar a area com o mouse) e
        # pelo teclado. Com o trace, a previa reage nos tres casos.
        for var in (self.x_var, self.y_var, self.width_var, self.height_var):
            var.trace_add("write", lambda *a: self.on_adjust_change())

        adjust_btn_frame = ttk.Frame(self.adjust_frame)
        adjust_btn_frame.pack(fill="x", padx=12, pady=(2, 8))

        ttk.Button(adjust_btn_frame, text="Ver area na tela",
                   command=self.show_preview).pack(side="left")
        ttk.Button(adjust_btn_frame, text="Salvar ajustes",
                   command=self.save_adjustments).pack(side="left", padx=8)

        if not self.area_coords:
            self.disable_adjust_controls()

        # --- botoes principais
        button_frame = ttk.Frame(left_frame)
        button_frame.pack(fill="x", pady=(10, 0))

        ttk.Button(button_frame, text="Selecionar area",
                   command=self.start_selection).pack(side="left")

        self.capture_btn = ttk.Button(button_frame, text="Capturar tela",
                                      style="Acao.TButton",
                                      command=self.capture_screen)
        self.capture_btn.pack(side="left", padx=8)

        if not self.area_coords:
            self.capture_btn.config(state="disabled")

        # --- salvamento
        save_frame = ttk.LabelFrame(left_frame, text="Onde salvar ")
        save_frame.pack(fill="x", pady=(10, 0))

        self.save_path_var = tk.StringVar(value=self.default_save_folder())

        path_frame = ttk.Frame(save_frame)
        path_frame.pack(fill="x", padx=12, pady=(6, 2))
        ttk.Label(path_frame, text="Pasta:", width=7).pack(side="left")
        ttk.Entry(path_frame, textvariable=self.save_path_var, width=30).pack(
            side="left", fill="x", expand=True)
        ttk.Button(path_frame, text="...", width=3,
                   command=self.choose_folder).pack(side="left", padx=(6, 0))

        name_frame = ttk.Frame(save_frame)
        name_frame.pack(fill="x", padx=12, pady=2)
        ttk.Label(name_frame, text="Nome:", width=7).pack(side="left")
        self.file_name_var = tk.StringVar()
        ttk.Entry(name_frame, textvariable=self.file_name_var, width=30).pack(
            side="left", fill="x", expand=True)
        ttk.Label(name_frame, text="opcional", style="Apagado.TLabel").pack(
            side="left", padx=(8, 0))

        seq_frame = ttk.Frame(save_frame)
        seq_frame.pack(fill="x", padx=12, pady=(6, 2))
        ttk.Checkbutton(seq_frame, text="Numerar em sequencia",
                        variable=self.sequential_mode).pack(side="left")
        ttk.Button(seq_frame, text="Zerar", width=6,
                   command=self.reset_counter).pack(side="left", padx=10)

        acoes = ttk.Frame(save_frame)
        acoes.pack(fill="x", padx=12, pady=(4, 8))

        self.open_folder_btn = ttk.Button(acoes, text="Abrir pasta",
                                          command=self.open_captures_folder)
        self.open_folder_btn.pack(side="left")

        self.copy_btn = ttk.Button(acoes, text="Copiar ultima",
                                   command=self.copy_last_capture,
                                   state="disabled")
        self.copy_btn.pack(side="left", padx=8)

        self.save_as_btn = ttk.Button(acoes, text="Salvar como...",
                                      command=self.save_last_capture_as,
                                      state="disabled")
        self.save_as_btn.pack(side="left")

        ttk.Label(left_frame,
                  text="Marque a area uma vez; depois e so clicar em "
                       "Capturar tela.",
                  style="Apagado.TLabel").pack(anchor="w", pady=(8, 0))

        # ===== Coluna direita: a previa da ultima captura =====
        right_frame = ttk.LabelFrame(container, text="Ultima captura ")
        right_frame.pack(side="left", fill="both", expand=True, padx=(16, 0))

        self.preview_canvas = tk.Canvas(
            right_frame, bg=COR_CAMPO, highlightthickness=0, bd=0,
            width=360, height=380,
        )
        self.preview_canvas.pack(fill="both", expand=True, padx=10, pady=10)

        self.preview_text_id = self.preview_canvas.create_text(
            180, 190,
            text="Nenhuma captura ainda.\n\nAs capturas aparecem aqui.",
            font=self.fonte_peq, fill=COR_APAGADO, justify="center",
            tags="initial_text",
        )
        self.preview_image_id = None

        # Recentraliza o aviso quando a coluna muda de tamanho. O evento e
        # ouvido NO PROPRIO canvas, e nao na janela: a janela agora e a do
        # Estudio inteiro, e ela dispara <Configure> tambem por causa das
        # outras abas.
        self.preview_canvas.bind("<Configure>", self.on_preview_resize)

    # ------------------------------------------------------------------
    def update_status_bar(self, message, situacao="neutro"):
        self.status_bar_var.set(message)
        self.status_bar.configure(
            style=ESTILO_AVISO.get(situacao, "Suave.TLabel"))
        self.root.after(
            5000,
            lambda: self.status_bar_var.set("")
            if self.status_bar_var.get() == message else None,
        )

    def on_folder_change(self, *args):
        """Trocou de pasta: a numeracao recomeca do 1 na pasta nova."""
        current_path = self.save_path_var.get()
        if current_path != self.last_folder_path:
            self.sequence_counter = 1
            self.last_folder_path = current_path

    def reset_counter(self):
        self.sequence_counter = 1
        self.update_status_bar("Contador sequencial zerado (volta ao 1).",
                               "neutro")

    def on_preview_resize(self, _evento=None):
        if self.preview_text_id and not self.preview_image_id:
            try:
                largura = self.preview_canvas.winfo_width()
                altura = self.preview_canvas.winfo_height()
                self.preview_canvas.coords(
                    self.preview_text_id, largura // 2, altura // 2)
            except Exception:
                pass

    def _valores_area(self):
        """Le os quatro campos do ajuste fino, tolerando campo vazio."""
        try:
            return (self.x_var.get(), self.y_var.get(),
                    self.width_var.get(), self.height_var.get())
        except Exception:
            return None

    def on_adjust_change(self):
        if self.preview.is_open():
            valores = self._valores_area()
            if valores:
                self.preview.update(*valores)

    def show_preview(self):
        valores = self._valores_area()
        if not valores:
            self.update_status_bar("Preencha os quatro numeros da area.",
                                   "atencao")
            return
        self.preview.show(*valores)

    def save_adjustments(self):
        valores = self._valores_area()
        if not valores:
            self.update_status_bar("Preencha os quatro numeros da area.",
                                   "atencao")
            return
        x, y, largura, altura = valores
        self.area_coords = {"x": x, "y": y, "width": largura, "height": altura}
        self.config_manager.save_coords(self.area_coords)
        self.update_interface()
        self.update_status_bar("Ajustes salvos com sucesso.", "ok")
        self.preview.close()

    # ------------------------------------------------------------------
    # Selecao da area
    # ------------------------------------------------------------------
    def start_selection(self):
        """Esconde o Estudio inteiro e abre a sobreposicao de selecao.

        Quem se esconde e a janela de verdade (`winfo_toplevel`), e nao o
        quadro desta aba: se o Estudio ficasse na tela, ele apareceria na
        propria area marcada.
        """
        janela = self._janela()
        try:
            janela.iconify()
        except Exception:
            pass
        janela.after(500, self._create_selector)

    def _create_selector(self):
        self.selector = AreaSelector(self.on_area_selected, self._janela())
        self.selector.start_selection()

    def on_area_selected(self, x, y, width, height):
        self.selector = None
        try:
            self._janela().deiconify()
        except Exception:
            pass

        if x is None:
            self.update_status_bar(
                "Selecao cancelada ou area muito pequena.", "atencao")
            return

        self.area_coords = {"x": x, "y": y, "width": width, "height": height}
        self.config_manager.save_coords(self.area_coords)

        self.x_var.set(x)
        self.y_var.set(y)
        self.width_var.set(width)
        self.height_var.set(height)

        self.update_status_bar(
            f"Area configurada: {width} x {height} px em ({x}, {y})", "ok")
        self.update_interface()

    def update_interface(self):
        if self.area_coords:
            coords_text = (
                f"X: {self.area_coords['x']}, Y: {self.area_coords['y']}  •  "
                f"{self.area_coords['width']} x {self.area_coords['height']} px"
            )
            self.coords_label.config(text=coords_text)
            self.status_label.config(text="Area configurada", style="Ok.TLabel")
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

    # ------------------------------------------------------------------
    # Pasta
    # ------------------------------------------------------------------
    def choose_folder(self):
        folder = filedialog.askdirectory(
            title="Onde salvar as capturas",
            initialdir=self.save_path_var.get() or pastas.pasta_downloads(),
            parent=self._janela())
        if folder:
            self.save_path_var.set(folder)

    def open_captures_folder(self):
        folder_path = pastas.garantir(self.save_path_var.get())
        try:
            if IS_WINDOWS:
                os.startfile(folder_path)  # noqa
            elif IS_MAC:
                subprocess.run(["open", folder_path])
            else:
                subprocess.run(["xdg-open", folder_path])
        except Exception as e:
            self.update_status_bar(f"Erro ao abrir a pasta: {e}", "erro")

    # ------------------------------------------------------------------
    # Captura
    # ------------------------------------------------------------------
    def capture_screen(self):
        if not self.area_coords:
            self.update_status_bar(
                "Configure a area antes de capturar.", "erro")
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

            # Copia automaticamente para a area de transferencia
            copied = self.copy_image_to_clipboard(filepath)
            if copied:
                self.update_status_bar(
                    f"Captura salva e copiada: {os.path.basename(filepath)}",
                    "ok")
            else:
                self.update_status_bar(
                    f"Captura salva: {os.path.basename(filepath)} "
                    "(nao consegui copiar para a area de transferencia)",
                    "atencao")
        except Exception as e:
            self.update_status_bar(f"Erro ao capturar: {e}", "erro")

    # ------------------------------------------------------------------
    # Area de transferencia
    # ------------------------------------------------------------------
    @staticmethod
    def copy_image_to_clipboard(filepath):
        """Copia a imagem (nao o caminho) para a area de transferencia."""
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
        """Salva a ultima captura em outro lugar, com o nome escolhido."""
        if not self.last_capture_path or not os.path.exists(self.last_capture_path):
            self.update_status_bar("Nenhuma captura para salvar ainda.",
                                   "atencao")
            return
        destino = filedialog.asksaveasfilename(
            title="Salvar captura como",
            defaultextension=".png",
            filetypes=[("Imagem PNG", "*.png")],
            initialfile=os.path.basename(self.last_capture_path),
            parent=self._janela(),
        )
        if not destino:
            return
        try:
            shutil.copyfile(self.last_capture_path, destino)
            self.update_status_bar(
                f"Salvo em: {os.path.basename(destino)}", "ok")
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Nao consegui salvar:\n{e}",
                                 parent=self._janela())
            self.update_status_bar(f"Erro ao salvar: {e}", "erro")

    def copy_last_capture(self):
        if not self.last_capture_path or not os.path.exists(self.last_capture_path):
            self.update_status_bar("Nenhuma captura para copiar ainda.",
                                   "atencao")
            return
        if self.copy_image_to_clipboard(self.last_capture_path):
            self.update_status_bar(
                "Ultima captura copiada para a area de transferencia.", "ok")
        else:
            self.update_status_bar(
                "Nao consegui copiar para a area de transferencia.", "erro")

    def update_capture_preview(self, image_path):
        try:
            from PIL import ImageTk

            img = Image.open(image_path)

            canvas_width = self.preview_canvas.winfo_width()
            canvas_height = self.preview_canvas.winfo_height()
            if canvas_width <= 1:
                canvas_width = 360
            if canvas_height <= 1:
                canvas_height = 380

            img.thumbnail(
                (max(40, canvas_width - 40), max(40, canvas_height - 40)),
                Image.Resampling.LANCZOS,
            )

            self.preview_photo = ImageTk.PhotoImage(img)

            if self.preview_text_id:
                self.preview_canvas.delete(self.preview_text_id)
                self.preview_text_id = None
            if self.preview_image_id:
                self.preview_canvas.delete(self.preview_image_id)

            self.preview_image_id = self.preview_canvas.create_image(
                canvas_width // 2, canvas_height // 2,
                image=self.preview_photo, anchor="center",
            )
        except Exception as e:
            self.update_status_bar(f"Erro ao mostrar a previa: {e}", "erro")

    # ------------------------------------------------------------------
    def ao_fechar(self):
        """Limpeza no fechamento do Estudio: nao destroi janela nenhuma.

        As duas janelas auxiliares, sim, sao fechadas se ainda estiverem
        abertas -- elas sao desta aba, e ficariam orfas na tela.
        """
        try:
            self.preview.close()
        except Exception:
            pass
        if self.selector is not None:
            try:
                self.selector.fechar()
            except Exception:
                pass
            self.selector = None


def montar(pai):
    """Desenha a aba do PrintShot dentro de `pai` e devolve o aplicativo."""
    return ScreenCaptureApp(pai)
