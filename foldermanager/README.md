# Gerenciador de Pastas — Comparar e Copiar

Aplicativo único que junta duas ferramentas que antes eram separadas
(`comparar-pastas` e `copiador-faltantes`):

1. **Comparar** duas pastas (ex.: um Drive de origem e um NAS de destino) para
   conferir se a cópia está completa e correta. **Somente leitura** — nenhum
   arquivo é alterado.
2. **Copiar faltantes**: copia para o destino apenas os arquivos que ainda não
   existem lá. A origem nunca é alterada.

O **relatório é opcional**: só é gerado quando você clica em **"Gerar
relatório..."** e escolhe o formato (**PDF**, **CSV** ou **HTML**). O relatório
cobre a última comparação e, se você tiver feito uma cópia, também a última
cópia realizada.

---

## Como usar (dia a dia)

1. Abra o aplicativo (dois cliques no `.exe`, ou no `Gerenciador de Pastas.bat`).
2. Em **ORIGEM**, escolha a pasta de origem (ex.: o Drive).
3. Em **DESTINO**, escolha a pasta de destino (ex.: o NAS).
4. Ajuste as **opções** se quiser:
   - **Comparar conteúdo com hash SHA-256** — confere byte a byte. Mais lento,
     mais seguro. Sem isso, a comparação usa nome + tamanho.
   - **Tratar diferença de DATA como problema** — desligado por padrão, porque a
     data costuma mudar numa cópia normal.
   - **Sobrescrever divergentes** — ao copiar, regrava arquivos que existem no
     destino com tamanho diferente. Desligado por padrão (nada é sobrescrito).
5. Clique nos botões conforme a necessidade:
   - **1) Analisar** — confere as duas pastas (somente leitura) e mostra o
     resumo no log: o que falta, o que sobra, tamanhos diferentes etc. O número
     de "faltando no destino" é exatamente o que seria copiado.
   - **2) Copiar faltantes** — copia os arquivos que faltam. Ele **reaproveita a
     análise** que você acabou de fazer, sem reler as pastas. Se você mudou a
     origem, o destino ou as opções desde a última análise, ele refaz a leitura
     automaticamente antes de copiar.
   - **Gerar relatório...** — (habilita após uma análise) escolhe o formato e
     salva o arquivo. Se você também copiou, o relatório inclui a cópia.
   - **Cancelar** — interrompe a operação em andamento com segurança.

### Sobre os formatos de relatório

| Formato | Quando usar |
|---------|-------------|
| **HTML** | Para navegar muitos arquivos na tela: tem abas de filtro (só problemas, faltando, etc.) e botão de copiar caminho. Dá para imprimir como PDF pelo navegador. |
| **CSV**  | Para abrir no Excel e tratar/filtrar os dados em planilha. |
| **PDF**  | Opcional. Visual, para imprimir/arquivar. Só funciona na versão completa (ver abaixo). |

> **PDF é opcional.** A versão padrão do app é **leve** (abre rápido e ocupa
> pouco) e gera relatórios em **HTML e CSV**. Se precisar de PDF nativo, use a
> versão completa `FolderManagerWIN-PDF` (gerada pelo `build_exe_com_pdf.bat`).
> Na prática, o HTML já cobre quase tudo: abra e use Imprimir → Salvar como PDF.

---

## Estrutura do projeto

```
gerenciador-pastas/
├── app.py                          # Interface (tela única) — ponto de entrada
├── motor_comparacao.py             # Lógica de comparação (somente leitura)
├── motor_copia.py                  # Lógica de cópia (reaproveita a análise)
├── relatorio.py                    # Gera os relatórios HTML / CSV / PDF
├── requirements.txt                # Dependências (reportlab, pyinstaller)
├── build_exe.bat                   # Gera o .exe LEVE do WINDOWS (CSV/HTML)
├── build_exe_com_pdf.bat           # Gera o .exe COMPLETO com PDF (opcional)
├── build_app_mac.command           # Gera o .app LEVE do MAC (rodar num Mac)
├── subir-foldermanager-no-github.bat # Sobe o projeto para o repo Softwares
├── baixar-da-nuvem.bat             # Baixa os 2 executáveis da nuvem p/ a rede
├── Gerenciador de Pastas.bat       # Abre pelo Python no Windows, sem terminal
├── .github/workflows/build.yml     # Robô que gera .exe e .app na nuvem
├── COMO-GERAR-NA-NUVEM.md          # Guia do GitHub Actions
├── DISTRIBUICAO-REDE.md            # Como os executáveis chegam à pasta de rede
└── README.md
```

Rodar direto pelo Python (para desenvolvimento):

```bash
pip install reportlab
python app.py
```

---

## Como transformar em executável

> **Importante:** o empacotador (PyInstaller) **não cruza sistemas**. Ele gera o
> binário do sistema onde roda. Para ter os dois executáveis, rode o build em
> cada sistema:
>
> | Executável | Onde gerar | Script | Resultado |
> |------------|-----------|--------|-----------|
> | Windows | num PC Windows | `build_exe.bat` | `FolderManagerWIN.exe` |
> | Mac | num Mac | `build_app_mac.command` | `FolderManagerMAC.app` |
>
> O mesmo código-fonte serve para os dois; muda só a máquina onde você empacota.
> Se você não tem as duas máquinas à mão, dá para gerar ambos automaticamente
> com um serviço de CI (ex.: GitHub Actions) — posso preparar isso se precisar.

### Windows — gerar o `.exe`

A ideia é gerar **um único arquivo `.exe`** que roda em qualquer PC Windows da
rede **sem precisar instalar Python nem nada**.

#### Passo a passo (no PC onde você desenvolve)

1. Tenha o **Python 3.8 ou superior** instalado (em <https://python.org>, marque
   *"Add Python to PATH"* na instalação).
2. Dê **dois cliques em `build_exe.bat`**.
   - Ele instala `reportlab` e `pyinstaller` automaticamente.
   - Depois gera o executável (leva 1–2 minutos).
3. O arquivo final aparece em:

   ```
   gerenciador-pastas\dist\Gerenciador de Pastas.exe
   ```

Se preferir rodar o comando à mão (em vez do `.bat`):

```bash
pip install reportlab pyinstaller
pyinstaller --onefile --windowed --name "Gerenciador de Pastas" --hidden-import reportlab app.py
```

- `--onefile` → tudo em um único `.exe`.
- `--windowed` → abre só a janela, sem terminal preto atrás.
- `--hidden-import reportlab` → garante que o gerador de PDF entre no pacote.

---

## Como rodar em outros dispositivos da rede

Você tem **duas formas**, dependendo do que prefere:

### Opção A — Copiar o executável para cada máquina (mais simples e robusto)

1. Gere o `FolderManagerWIN.exe` (Windows) ou o `FolderManagerMAC.app` (Mac).
2. Copie esse arquivo único para os outros computadores (pen drive, pasta
   compartilhada, e-mail interno etc.).
3. Em cada máquina, dê **dois cliques** para abrir. Não precisa instalar nada.

Como o executável é independente, ele roda mesmo em máquinas sem Python.

### Opção B — Deixar o executável numa pasta compartilhada da rede

1. Coloque o `FolderManagerWIN.exe` numa pasta compartilhada
   (ex.: `\\servidor\ferramentas\`).
2. Cada pessoa abre o `.exe` direto pela rede ou cria um atalho na área de
   trabalho apontando para ele.

> Observação: rodar um `.exe` direto de um caminho de rede tende a abrir um
> pouco mais devagar (o Windows carrega o arquivo pela rede a cada execução) e
> pode disparar avisos de segurança do Windows na primeira vez. Para uso
> frequente, a **Opção A** (copiar para cada PC) costuma ser mais confortável.

### Acessando as pastas (Drive/NAS) pela rede

Dentro do app, em ORIGEM/DESTINO, você pode apontar tanto para uma letra de
unidade (ex.: `Z:\backup`) quanto para um caminho de rede no formato UNC:

```
\\NAS\compartilhamento\pasta
```

O motor de cópia já trata caminhos longos (> 260 caracteres) e nomes de arquivo
inválidos para Windows/NAS automaticamente.

---

## Garantias de segurança

- A **ORIGEM é sempre apenas lida** — nada é criado, movido, renomeado ou
  apagado nela.
- A **comparação não altera nada** em lado nenhum.
- Na **cópia**, por padrão **nada é sobrescrito** no destino: só são gravados
  arquivos novos. Sobrescrever divergentes é uma opção que você liga
  manualmente.
- Nomes ilegais para Windows/NAS (`/ : * ? " < > |` etc.) são saneados
  automaticamente ao gravar no destino, sem mexer no nome da origem.

---

## Observações

- Os projetos antigos (`comparar-pastas` e `copiador-faltantes`) podem ser
  mantidos como referência ou removidos — toda a funcionalidade deles está aqui.
- Para gerar PDF é preciso ter o `reportlab` (já incluído no executável). CSV e
  HTML funcionam só com o Python padrão.
