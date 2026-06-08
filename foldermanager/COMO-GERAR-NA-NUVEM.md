# Como gerar os executáveis na nuvem (Windows e Mac)

Este guia usa o **GitHub Actions**: um robô gratuito do GitHub monta o
`FolderManagerWIN.exe` (Windows) e o `FolderManagerMAC.app` (Mac) para você,
**sem precisar ter um Mac**. Você só sobe o código uma vez.

> Tempo: ~15 min na primeira vez. Depois, é só clicar e baixar.

---

## Parte 1 — Criar a conta e o repositório (só na primeira vez)

1. Crie uma conta gratuita em <https://github.com> (se ainda não tiver).
2. Clique no **+** no canto superior direito → **New repository**.
3. Dê um nome (ex.: `gerenciador-pastas`), deixe como **Private** se quiser, e
   clique em **Create repository**.

---

## Parte 2 — Subir o projeto

A forma mais fácil, sem instalar nada:

1. No repositório recém-criado, clique em **uploading an existing file**
   (ou **Add file → Upload files**).
2. **Arraste todos os arquivos da pasta `gerenciador-pastas`** para a área de
   upload — inclusive a pasta `.github` (ela contém as instruções do robô).
   - Se o navegador não deixar arrastar a pasta `.github`, veja a observação no
     fim deste guia.
3. Clique em **Commit changes** (botão verde).

> Importante: o arquivo `.github/workflows/build.yml` precisa estar lá. É ele
> que manda o robô gerar os executáveis.

---

## Parte 3 — Rodar o robô e baixar os executáveis

1. No repositório, abra a aba **Actions** (no menu de cima).
2. Você verá o fluxo **"Gerar executaveis (Windows e Mac)"**.
   - Se já rodou sozinho após o upload, ótimo.
   - Se não, clique nele → botão **Run workflow** → **Run workflow**.
3. Espere terminar (aparece um ✓ verde; leva uns 2–4 minutos).
4. Clique na execução que terminou. Lá embaixo, em **Artifacts**, estarão:
   - **FolderManagerWIN** → contém o `FolderManagerWIN.exe`
   - **FolderManagerMAC** → contém o `FolderManagerMAC-mac.zip`
5. Clique em cada um para **baixar**.

No Mac, descompacte o `FolderManagerMAC-mac.zip` para obter o
`FolderManagerMAC.app`.

---

## Depois: toda vez que mudar o código

Sempre que você atualizar um arquivo no repositório (**Add file → Upload
files**, ou editar pelo próprio site), o robô roda de novo sozinho e gera os
executáveis atualizados. É só voltar na aba **Actions** e baixar.

---

## (Opcional) Publicar uma versão com Release

Se quiser uma página de download fixa, crie uma **tag de versão**:

1. No repositório: **Releases** (lado direito) → **Create a new release**.
2. Em **Choose a tag**, digite `v1.0` → **Create new tag**.
3. Clique em **Publish release**.

O robô anexa automaticamente o `.exe` e o `.zip` do Mac nessa release, e
qualquer pessoa baixa por um link só.

---

## Avisos ao abrir nos outros computadores

- **Windows:** na primeira execução pode aparecer "O Windows protegeu o seu PC".
  Clique em **Mais informações → Executar assim mesmo**. (Acontece porque o
  arquivo não é assinado digitalmente; é normal para apps internos.)
- **Mac:** ao abrir o `.app` pela primeira vez, o macOS pode bloquear por não
  ser assinado. Libere em **Ajustes do Sistema → Privacidade e Segurança →
  "Abrir mesmo assim"**.

---

## Observação — enviando a pasta `.github`

Alguns navegadores não arrastam pastas que começam com ponto. Se isso acontecer:

- **Jeito A (recomendado):** no GitHub, clique em **Add file → Create new file**.
  No nome do arquivo digite exatamente:
  `.github/workflows/build.yml`
  (o GitHub cria as pastas automaticamente ao digitar as barras). Cole o
  conteúdo do `build.yml` que está na sua pasta do projeto e clique em
  **Commit changes**.
- **Jeito B:** instale o **GitHub Desktop** (<https://desktop.github.com>), que
  envia a pasta inteira de uma vez, incluindo a `.github`.
