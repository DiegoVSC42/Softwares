"""
Cronometro de Tempo de Resposta - Telefone
============================================

Mede quanto tempo a outra pessoa demora para responder numa conversa por
telefone (ou qualquer dialogo entre duas pessoas).

Fluxo de uso:
    0) Voce atende a chamada -> aperte ESPACO (ou o botao "Atendi a chamada").
       Isso apenas marca o inicio da chamada como referencia; nao entra no
       calculo do tempo de resposta.
    1) Voce termina de falar  -> aperte a tecla 1 (ou o botao "Terminei de falar").
       Nesse instante o cronometro comeca a contar.
    2) Voce ouve a voz da outra pessoa -> aperte a tecla 2 (ou o botao
       "Ouvi a outra pessoa"). O tempo de resposta e registrado.

A janela mostra o tempo da ultima medicao, um cronometro ao vivo enquanto
voce aguarda, o historico de todas as medicoes da sessao e as estatisticas
(quantidade, media, menor e maior tempo). Da para exportar tudo em CSV.

Sem dependencias externas: usa apenas Tkinter (ja vem com o Python).
"""

import csv
import time
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk


class CronometroResposta:
    # Estados do cronometro
    OCIOSO = "ocioso"          # nada acontecendo
    AGUARDANDO = "aguardando"  # voce falou, esperando a resposta da outra pessoa

    def __init__(self, root):
        self.root = root
        self.root.title("Cronometro de Tempo de Resposta - Telefone")
        self.root.geometry("560x710")
        self.root.minsize(520, 660)
        self.root.configure(bg="#1e1e2e")

        self.estado = self.OCIOSO
        self.t_inicio = None          # time.perf_counter() quando apertou 1
        self.medicoes = []            # lista de dicts: {n, segundos, hora}
        self._after_id = None         # id do loop do cronometro ao vivo
        self.hora_atendimento = None  # hora em que a chamada foi atendida (espaco)

        self._montar_interface()
        self._vincular_teclas()
        self._atualizar_estatisticas()
        self._atualizar_estado_visual()

    # ------------------------------------------------------------------ UI
    def _montar_interface(self):
        cor_fundo = "#1e1e2e"
        cor_texto = "#cdd6f4"

        # Titulo
        tk.Label(
            self.root, text="Tempo de Resposta", bg=cor_fundo, fg=cor_texto,
            font=("Segoe UI", 18, "bold"),
        ).pack(pady=(16, 2))
        tk.Label(
            self.root,
            text="Espaco = atendi   |   1 = terminei de falar   |   2 = ouvi a pessoa   |   3 = cancelar o 1",
            bg=cor_fundo, fg="#9399b2", font=("Segoe UI", 9),
        ).pack(pady=(0, 6))

        # Marcador da chamada atendida
        self.lbl_atendi = tk.Label(
            self.root, text="Chamada: nao atendida", bg=cor_fundo, fg="#cba6f7",
            font=("Segoe UI", 10, "bold"),
        )
        self.lbl_atendi.pack(pady=(0, 6))

        # Status (estado atual) + cronometro ao vivo
        self.lbl_status = tk.Label(
            self.root, text="", bg=cor_fundo, fg="#f9e2af",
            font=("Segoe UI", 12, "bold"),
        )
        self.lbl_status.pack(pady=(0, 2))

        self.lbl_cronometro = tk.Label(
            self.root, text="0.00 s", bg=cor_fundo, fg="#a6e3a1",
            font=("Consolas", 46, "bold"),
        )
        self.lbl_cronometro.pack(pady=(0, 4))

        self.lbl_ultima = tk.Label(
            self.root, text="Ultima resposta: ---", bg=cor_fundo, fg="#9399b2",
            font=("Segoe UI", 11),
        )
        self.lbl_ultima.pack(pady=(0, 12))

        # Botao de atender a chamada (espaco)
        self.btn_atendi = tk.Button(
            self.root, text="Espaco  Atendi a chamada", width=42, height=2,
            bg="#cba6f7", fg="#11111b", activebackground="#b794e6",
            font=("Segoe UI", 11, "bold"), relief="flat", cursor="hand2",
            takefocus=0, command=self.marcar_atendimento,
        )
        self.btn_atendi.pack(pady=(2, 6))

        # Botoes principais
        frame_botoes = tk.Frame(self.root, bg=cor_fundo)
        frame_botoes.pack(pady=4)

        self.btn1 = tk.Button(
            frame_botoes, text="1  Terminei de falar", width=15, height=2,
            bg="#89b4fa", fg="#11111b", activebackground="#74a0f0",
            font=("Segoe UI", 10, "bold"), relief="flat", cursor="hand2",
            takefocus=0, command=self.marcar_fim_da_fala,
        )
        self.btn1.grid(row=0, column=0, padx=4)

        self.btn2 = tk.Button(
            frame_botoes, text="2  Ouvi a pessoa", width=15, height=2,
            bg="#a6e3a1", fg="#11111b", activebackground="#92d68d",
            font=("Segoe UI", 10, "bold"), relief="flat", cursor="hand2",
            takefocus=0, command=self.marcar_resposta,
        )
        self.btn2.grid(row=0, column=1, padx=4)

        self.btn3 = tk.Button(
            frame_botoes, text="3  Cancelar o 1", width=15, height=2,
            bg="#f38ba8", fg="#11111b", activebackground="#e87a98",
            font=("Segoe UI", 10, "bold"), relief="flat", cursor="hand2",
            takefocus=0, command=self.cancelar_medicao,
        )
        self.btn3.grid(row=0, column=2, padx=4)

        # Botoes secundarios
        frame_sec = tk.Frame(self.root, bg=cor_fundo)
        frame_sec.pack(pady=10)

        tk.Button(
            frame_sec, text="Cancelar medicao", width=16,
            bg="#45475a", fg="#cdd6f4", activebackground="#585b70",
            font=("Segoe UI", 9), relief="flat", cursor="hand2",
            takefocus=0, command=self.cancelar_medicao,
        ).grid(row=0, column=0, padx=4)
        tk.Button(
            frame_sec, text="Limpar historico", width=16,
            bg="#45475a", fg="#cdd6f4", activebackground="#585b70",
            font=("Segoe UI", 9), relief="flat", cursor="hand2",
            takefocus=0, command=self.limpar_historico,
        ).grid(row=0, column=1, padx=4)
        tk.Button(
            frame_sec, text="Exportar CSV", width=16,
            bg="#f9e2af", fg="#11111b", activebackground="#f5d98f",
            font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2",
            takefocus=0, command=self.exportar_csv,
        ).grid(row=0, column=2, padx=4)

        # Estatisticas
        self.lbl_stats = tk.Label(
            self.root, text="", bg=cor_fundo, fg="#cdd6f4",
            font=("Segoe UI", 10),
        )
        self.lbl_stats.pack(pady=(8, 6))

        # Tabela de historico
        frame_tab = tk.Frame(self.root, bg=cor_fundo)
        frame_tab.pack(fill="both", expand=True, padx=16, pady=(0, 14))

        colunas = ("n", "tempo", "hora")
        self.tabela = ttk.Treeview(
            frame_tab, columns=colunas, show="headings", height=8,
        )
        self.tabela.heading("n", text="#")
        self.tabela.heading("tempo", text="Tempo (s)")
        self.tabela.heading("hora", text="Hora")
        self.tabela.column("n", width=50, anchor="center")
        self.tabela.column("tempo", width=120, anchor="center")
        self.tabela.column("hora", width=120, anchor="center")

        scroll = ttk.Scrollbar(frame_tab, orient="vertical", command=self.tabela.yview)
        self.tabela.configure(yscrollcommand=scroll.set)
        self.tabela.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def _vincular_teclas(self):
        # Aceita 1/2 do teclado normal e do teclado numerico
        self.root.bind("1", lambda e: self.marcar_fim_da_fala())
        self.root.bind("<KP_1>", lambda e: self.marcar_fim_da_fala())
        self.root.bind("2", lambda e: self.marcar_resposta())
        self.root.bind("<KP_2>", lambda e: self.marcar_resposta())
        self.root.bind("3", lambda e: self.cancelar_medicao())
        self.root.bind("<KP_3>", lambda e: self.cancelar_medicao())
        self.root.bind("<space>", lambda e: self.marcar_atendimento())
        self.root.bind("<Escape>", lambda e: self.cancelar_medicao())

    # -------------------------------------------------------------- acoes
    def marcar_atendimento(self):
        """Espaco: marca o instante em que a chamada foi atendida.

        E apenas um marco de referencia (inicio da chamada). Nao entra no
        calculo do tempo de resposta. Cancela qualquer contagem em andamento
        e registra uma linha de marcacao no historico.
        """
        # Cancela uma medicao em andamento, se houver (comeca uma chamada nova).
        if self.estado == self.AGUARDANDO:
            self._parar_loop_cronometro()
            self.estado = self.OCIOSO
            self.t_inicio = None

        self.hora_atendimento = datetime.now().strftime("%H:%M:%S")
        self.lbl_atendi.config(text=f"Chamada atendida as {self.hora_atendimento}")
        self.lbl_cronometro.config(text="0.00 s")

        # Linha de marcacao no historico (separa as chamadas).
        self.tabela.insert("", "end", values=(
            ">>", "Atendi a chamada", self.hora_atendimento,
        ))
        self.tabela.yview_moveto(1.0)
        self._atualizar_estado_visual()

    def marcar_fim_da_fala(self):
        """Tecla 1: voce terminou de falar, comeca a contar."""
        self.t_inicio = time.perf_counter()
        self.estado = self.AGUARDANDO
        self._atualizar_estado_visual()
        self._iniciar_loop_cronometro()

    def marcar_resposta(self):
        """Tecla 2: ouviu a outra pessoa, registra o tempo."""
        if self.estado != self.AGUARDANDO or self.t_inicio is None:
            # Apertou 2 sem ter apertado 1 antes: ignora.
            return
        segundos = time.perf_counter() - self.t_inicio
        self._parar_loop_cronometro()

        registro = {
            "n": len(self.medicoes) + 1,
            "segundos": segundos,
            "hora": datetime.now().strftime("%H:%M:%S"),
        }
        self.medicoes.append(registro)
        self.tabela.insert("", "end", values=(
            registro["n"], f"{segundos:.2f}", registro["hora"],
        ))
        self.tabela.yview_moveto(1.0)

        self.lbl_ultima.config(text=f"Ultima resposta: {segundos:.2f} s")
        self.lbl_cronometro.config(text=f"{segundos:.2f} s")
        self.estado = self.OCIOSO
        self.t_inicio = None
        self._atualizar_estado_visual()
        self._atualizar_estatisticas()

    def cancelar_medicao(self):
        """Descarta a contagem em andamento sem registrar."""
        if self.estado == self.AGUARDANDO:
            self._parar_loop_cronometro()
            self.estado = self.OCIOSO
            self.t_inicio = None
            self.lbl_cronometro.config(text="0.00 s")
            self._atualizar_estado_visual()

    def limpar_historico(self):
        if not self.medicoes:
            return
        if not messagebox.askyesno(
            "Limpar historico", "Apagar todas as medicoes desta sessao?"
        ):
            return
        self.medicoes.clear()
        for item in self.tabela.get_children():
            self.tabela.delete(item)
        self.lbl_ultima.config(text="Ultima resposta: ---")
        self.lbl_cronometro.config(text="0.00 s")
        self.hora_atendimento = None
        self.lbl_atendi.config(text="Chamada: nao atendida")
        self._atualizar_estatisticas()

    def exportar_csv(self):
        if not self.medicoes:
            messagebox.showinfo("Exportar CSV", "Nao ha medicoes para exportar.")
            return
        nome_sugerido = "tempos_resposta_" + datetime.now().strftime("%Y%m%d_%H%M") + ".csv"
        caminho = filedialog.asksaveasfilename(
            title="Salvar historico em CSV",
            defaultextension=".csv",
            initialfile=nome_sugerido,
            filetypes=[("Arquivo CSV", "*.csv"), ("Todos os arquivos", "*.*")],
        )
        if not caminho:
            return
        try:
            with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow(["#", "Tempo (s)", "Hora"])
                for m in self.medicoes:
                    writer.writerow([m["n"], f"{m['segundos']:.2f}".replace(".", ","), m["hora"]])
                # Linha de estatisticas
                tempos = [m["segundos"] for m in self.medicoes]
                media = sum(tempos) / len(tempos)
                writer.writerow([])
                writer.writerow(["Medicoes", len(tempos)])
                writer.writerow(["Media (s)", f"{media:.2f}".replace(".", ",")])
                writer.writerow(["Menor (s)", f"{min(tempos):.2f}".replace(".", ",")])
                writer.writerow(["Maior (s)", f"{max(tempos):.2f}".replace(".", ",")])
            messagebox.showinfo("Exportar CSV", f"Arquivo salvo com sucesso:\n{caminho}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Erro ao exportar", str(exc))

    # ----------------------------------------------------- cronometro vivo
    def _iniciar_loop_cronometro(self):
        self._parar_loop_cronometro()
        self._tick()

    def _tick(self):
        if self.estado == self.AGUARDANDO and self.t_inicio is not None:
            decorrido = time.perf_counter() - self.t_inicio
            self.lbl_cronometro.config(text=f"{decorrido:.2f} s")
            self._after_id = self.root.after(50, self._tick)

    def _parar_loop_cronometro(self):
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None

    # ------------------------------------------------------------ visuais
    def _atualizar_estado_visual(self):
        if self.estado == self.AGUARDANDO:
            self.lbl_status.config(text="Aguardando a resposta...  (2 = ouvi  |  3 = cancelar)", fg="#f9e2af")
            self.lbl_cronometro.config(fg="#f9e2af")
            self.btn1.config(state="disabled")
            self.btn2.config(state="normal")
            self.btn3.config(state="normal")
        else:
            self.lbl_status.config(text="Pronto.  Aperte 1 ao terminar de falar.", fg="#9399b2")
            self.lbl_cronometro.config(fg="#a6e3a1")
            self.btn1.config(state="normal")
            self.btn2.config(state="disabled")
            self.btn3.config(state="disabled")

    def _atualizar_estatisticas(self):
        if not self.medicoes:
            self.lbl_stats.config(text="Medicoes: 0   |   Media: ---   |   Min: ---   |   Max: ---")
            return
        tempos = [m["segundos"] for m in self.medicoes]
        media = sum(tempos) / len(tempos)
        self.lbl_stats.config(
            text=(
                f"Medicoes: {len(tempos)}   |   "
                f"Media: {media:.2f} s   |   "
                f"Min: {min(tempos):.2f} s   |   "
                f"Max: {max(tempos):.2f} s"
            )
        )


def main():
    root = tk.Tk()
    CronometroResposta(root)
    root.mainloop()


if __name__ == "__main__":
    main()
