# Normalizador de Figurinhas

Programa com interface gráfica que **normaliza automaticamente vários PNGs para figurinhas**.

## O que faz

- Aceita vários PNGs de uma vez (por seleção individual ou pasta inteira)
- Para **cada imagem**, detecta sozinho a área realmente preenchida (sem transparência) —
  largura e altura do conteúdo
- Monta um canvas **pouco maior** que essa área (margem configurável, padrão 10%) e
  centraliza o conteúdo nele — automaticamente, sem precisar ajustar imagem por imagem
- Cada figurinha sai com o tamanho que o próprio conteúdo pede; não força um tamanho
  único para todas
- Opcional: forçar canvas quadrado (útil se o destino final exigir 1:1) e/ou limitar o
  lado maior a um tamanho máximo em pixels
- Preserva a transparência (PNG com alfa)

## Como rodar

1. **Abra o arquivo `normalizador_figurinhas.py`** com clique duplo (Windows) ou o
   atalho `abrir-normalizador-figurinhas.command` (Mac).
   - **Primeira execução**: o programa prepara o ambiente e instala as dependências
     automaticamente (leva 30 segundos a 1 minuto).
   - No Mac, se aparecer aviso de "desenvolvedor não identificado" ao abrir o
     `.command`: clique com o botão direito nele → **Abrir** → **Abrir**.

2. **Passo 1 — Selecionar PNGs:**
   - Clique em **"Escolher PNGs"** para selecionar arquivos individuais, ou
   - Clique em **"Escolher Pasta"** para processar todos os PNGs de uma pasta de uma vez.

3. **Passo 2 — Configurações (opcional, já vem com padrão bom):**
   - **Margem**: espaço extra ao redor do conteúdo, em % do lado maior da imagem
     (padrão: 10%).
   - **Forçar canvas quadrado**: liga se você precisa que toda figurinha saia 1:1
     (por exemplo, para exigências de WhatsApp). Desligado por padrão — cada imagem
     mantém as proporções do próprio conteúdo.
   - **Limitar o lado maior**: liga se quiser travar um tamanho máximo em pixels
     (por exemplo 512px), reduzindo proporcionalmente quem passar disso.

4. **Conferir antes de processar (opcional):**
   - Dê **duplo clique** em qualquer arquivo na lista para abrir uma pré-visualização
     mostrando o tamanho do conteúdo detectado e o canvas final, antes de rodar tudo.

5. **Passo 3 — Pasta de Saída (opcional):**
   - Se quiser salvar em outro local, clique em **"Escolher Pasta de Saída"**.
   - Caso contrário, as figurinhas ficam na mesma pasta dos PNGs originais.

6. **Clique em "PROCESSAR"** e aguarde.
   - Acompanhe o progresso na barra e os logs na área cinza (mostra o tamanho
     detectado e o canvas final de cada arquivo).
   - Para interromper no meio, clique em **"Cancelar"** — o arquivo atual termina e
     o processamento para.
   - Ao final, uma mensagem confirma quantos arquivos foram processados.

7. **Clique em "Abrir Pasta de Saída"** para acessar os PNGs normalizados.
   - Os arquivos recebem o prefixo `figurinha_` + nome original (ex.: `figurinha_logo.png`).

## Notas técnicas

- **Canvas por imagem**: cada arquivo recebe seu próprio canvas, calculado a partir
  da própria área de conteúdo + margem — não existe mais um tamanho fixo único
  (500×500) aplicado a todas as imagens, a menos que "Forçar canvas quadrado" e/ou
  "Limitar o lado maior" estejam ligados.
- **Margem**: aplicada igualmente nos quatro lados, como percentual do maior lado
  do conteúdo detectado.
- **Transparência**: preservada em todo o processo.
- **Redimensionamento**: só acontece se "Limitar o lado maior" estiver ligado e o
  canvas calculado ultrapassar esse limite — nesse caso reduz proporcionalmente.
- **Formato**: saída sempre em PNG com alfa (RGBA).

## Pré-requisitos

- **Python 3.7+** instalado no computador.
- Nenhuma outra instalação manual — o programa cuida de tudo na primeira execução.
