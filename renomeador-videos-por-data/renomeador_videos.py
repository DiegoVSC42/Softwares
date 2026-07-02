import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import threading
import os
import re
from datetime import datetime
from pathlib import Path

class RenomeadorVideosApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Renomeador de Vídeos por Data")
        self.root.geometry("900x700")
        self.pasta_selecionada = None
        self.thread_ativa = None

        # Frame superior com seleção de pasta
        frame_pasta = tk.Frame(root, bg="#f0f0f0", padx=10, pady=10)
        frame_pasta.pack(fill=tk.X)

        tk.Label(frame_pasta, text="Pasta:", font=("Arial", 10, "bold"), bg="#f0f0f0").pack(side=tk.LEFT, padx=5)
        self.label_pasta = tk.Label(frame_pasta, text="Nenhuma pasta selecionada", font=("Arial", 9), bg="#f0f0f0", fg="#666")
        self.label_pasta.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        tk.Button(frame_pasta, text="Selecionar Pasta", command=self.selecionar_pasta, bg="#4CAF50", fg="white", padx=15).pack(side=tk.RIGHT, padx=5)

        # Frame central com preview
        frame_preview = tk.Frame(root, padx=10, pady=10)
        frame_preview.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame_preview, text="Preview dos Renomeamentos:", font=("Arial", 10, "bold")).pack(anchor=tk.W)

        self.text_preview = scrolledtext.ScrolledText(frame_preview, height=20, font=("Courier", 9), bg="#f9f9f9")
        self.text_preview.pack(fill=tk.BOTH, expand=True, pady=5)

        # Frame inferior com botões
        frame_botoes = tk.Frame(root, bg="#f0f0f0", padx=10, pady=10)
        frame_botoes.pack(fill=tk.X)

        tk.Button(frame_botoes, text="Atualizar Preview", command=self.gerar_preview, bg="#2196F3", fg="white", padx=15, width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(frame_botoes, text="Executar Renomeação", command=self.executar_renomeacao, bg="#FF9800", fg="white", padx=15, width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(frame_botoes, text="Cancelar", command=self.cancelar_operacao, bg="#f44336", fg="white", padx=15, width=15).pack(side=tk.LEFT, padx=5)

        # Label de status
        self.label_status = tk.Label(root, text="Pronto", font=("Arial", 9), bg="#e8f5e9", fg="#2e7d32", padx=10, pady=5)
        self.label_status.pack(fill=tk.X)

        self.cancelado = False

    def selecionar_pasta(self):
        pasta = filedialog.askdirectory(title="Selecione a pasta com os vídeos")
        if pasta:
            self.pasta_selecionada = pasta
            self.label_pasta.config(text=pasta)
            self.gerar_preview()

    def extrair_data_sufixo(self, nome_arquivo):
        """Extrai a data do sufixo no formato DD-MM-YYYY"""
        # Padrão: DD-MM-YYYY no final do nome (antes da extensão)
        match = re.search(r'(\d{2})-(\d{2})-(\d{4})(?=\.[^.]+$)', nome_arquivo)
        if match:
            dia, mes, ano = match.groups()
            return {
                'original': match.group(0),
                'dia': dia,
                'mes': mes,
                'ano': ano,
                'ordenavel': f"{ano}-{mes}-{dia}"  # YYYY-MM-DD para ordenação (ISO 8601)
            }
        return None

    def gerar_novo_nome(self, nome_arquivo):
        """Gera o novo nome com prefixo de data para ordenação"""
        nome_base, extensao = os.path.splitext(nome_arquivo)
        data_info = self.extrair_data_sufixo(nome_arquivo)

        if data_info:
            # Remove a data do final do nome
            novo_base = nome_base[:-(len(data_info['original']))].rstrip('_').rstrip('-')
            # Adiciona prefixo YYYY-MM-DD para ordenação (ISO 8601)
            novo_nome = f"{data_info['ordenavel']}-{novo_base}{extensao}"
            return novo_nome, data_info

        return None, None

    def gerar_preview(self):
        """Gera preview dos renomeamentos"""
        self.text_preview.config(state=tk.NORMAL)
        self.text_preview.delete(1.0, tk.END)

        if not self.pasta_selecionada:
            self.text_preview.insert(tk.END, "⚠️  Selecione uma pasta primeiro!\n")
            self.text_preview.config(state=tk.DISABLED)
            self.atualizar_status("Selecione uma pasta", "#fff3cd")
            return

        arquivos = sorted([f for f in os.listdir(self.pasta_selecionada)
                          if os.path.isfile(os.path.join(self.pasta_selecionada, f))])

        arquivos_renomeados = []
        arquivos_ignorados = []

        for arquivo in arquivos:
            novo_nome, data_info = self.gerar_novo_nome(arquivo)
            if novo_nome and novo_nome != arquivo:
                arquivos_renomeados.append((arquivo, novo_nome, data_info))
            else:
                arquivos_ignorados.append(arquivo)

        # Ordena pelos arquivos renomeados (que já estarão em ordem)
        arquivos_renomeados.sort(key=lambda x: x[1])

        if arquivos_renomeados:
            self.text_preview.insert(tk.END, f"✅ {len(arquivos_renomeados)} arquivos serão renomeados:\n\n", "titulo")
            for original, novo, data_info in arquivos_renomeados:
                data_formatada = f"{data_info['dia']}/{data_info['mes']}/{data_info['ano']}"
                self.text_preview.insert(tk.END, f"📅 {data_formatada}\n", "data")
                self.text_preview.insert(tk.END, f"  De: {original}\n", "de")
                self.text_preview.insert(tk.END, f"  Para: {novo}\n\n", "para")

        if arquivos_ignorados:
            self.text_preview.insert(tk.END, f"\n⚠️  {len(arquivos_ignorados)} arquivo(s) sem data no sufixo (não serão alterados):\n\n", "aviso")
            for arquivo in arquivos_ignorados:
                self.text_preview.insert(tk.END, f"  • {arquivo}\n")

        # Tags para colorização
        self.text_preview.tag_config("titulo", foreground="#2e7d32", font=("Arial", 9, "bold"))
        self.text_preview.tag_config("data", foreground="#1976d2", font=("Arial", 9, "bold"))
        self.text_preview.tag_config("de", foreground="#666")
        self.text_preview.tag_config("para", foreground="#2e7d32", font=("Arial", 9, "bold"))
        self.text_preview.tag_config("aviso", foreground="#d32f2f", font=("Arial", 9, "bold"))

        self.text_preview.config(state=tk.DISABLED)
        self.atualizar_status(f"Preview gerado: {len(arquivos_renomeados)} arquivos para renomear", "#e8f5e9")

    def executar_renomeacao(self):
        """Executa a renomeação em thread separada"""
        if not self.pasta_selecionada:
            messagebox.showwarning("Aviso", "Selecione uma pasta primeiro!")
            return

        if messagebox.askyesno("Confirmar", "Deseja realmente renomear os arquivos?"):
            self.cancelado = False
            self.thread_ativa = threading.Thread(target=self._renomear_thread, daemon=True)
            self.thread_ativa.start()

    def _renomear_thread(self):
        """Executa a renomeação em thread"""
        try:
            self.atualizar_status("Renomeando arquivos...", "#fff3cd")

            arquivos = sorted([f for f in os.listdir(self.pasta_selecionada)
                              if os.path.isfile(os.path.join(self.pasta_selecionada, f))])

            # Primeiro, filtra e ordena apenas os arquivos que serão renomeados
            arquivos_para_renomear = []
            for arquivo in arquivos:
                novo_nome, data_info = self.gerar_novo_nome(arquivo)
                if novo_nome and novo_nome != arquivo:
                    arquivos_para_renomear.append((arquivo, novo_nome, data_info))

            # Ordena pela data
            arquivos_para_renomear.sort(key=lambda x: x[2]['ordenavel'])

            total = len(arquivos_para_renomear)
            processados = 0

            for arquivo, novo_nome, _ in arquivos_para_renomear:
                if self.cancelado:
                    break

                caminho_antigo = os.path.join(self.pasta_selecionada, arquivo)
                caminho_novo = os.path.join(self.pasta_selecionada, novo_nome)

                try:
                    os.rename(caminho_antigo, caminho_novo)
                    processados += 1
                    self.atualizar_status(f"Renomeando... {processados}/{total}", "#fff3cd")
                    self.root.update_idletasks()
                except Exception as e:
                    print(f"Erro ao renomear {arquivo}: {e}")

            if self.cancelado:
                self.atualizar_status("Operação cancelada", "#ffebee")
                messagebox.showinfo("Cancelado", "Renomeação cancelada pelo usuário")
            else:
                self.atualizar_status(f"✅ Concluído! {processados} arquivos renomeados", "#c8e6c9")
                messagebox.showinfo("Sucesso", f"{processados} arquivos renomeados com sucesso!")
                self.gerar_preview()

        except Exception as e:
            self.atualizar_status(f"❌ Erro: {str(e)}", "#ffcdd2")
            messagebox.showerror("Erro", f"Erro durante a renomeação:\n{str(e)}")

    def cancelar_operacao(self):
        """Cancela a operação em andamento"""
        if self.thread_ativa and self.thread_ativa.is_alive():
            self.cancelado = True
            self.atualizar_status("Cancelando...", "#fff3cd")
        else:
            self.root.quit()

    def atualizar_status(self, mensagem, cor="#e8f5e9"):
        """Atualiza o label de status"""
        self.label_status.config(text=mensagem, bg=cor)

if __name__ == "__main__":
    root = tk.Tk()
    app = RenomeadorVideosApp(root)
    root.mainloop()
