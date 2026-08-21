# Entrada pronta para o índice do repositório

Este arquivo **não** faz parte do programa. Ele guarda o texto que precisa
entrar no índice do repositório `DiegoVSC42/Softwares` **no dia em que o Montar
Podcast for publicado**. Enquanto ele não for publicado, o texto fica aqui: os
links abaixo apontam para um Release que ainda não existe, e colocá-los no
índice antes da publicação deixaria dois downloads quebrados na página inicial.

Na hora de publicar, três coisas a fazer, todas na máquina Windows, dentro da
pasta `publicar-todos`:

1. Em `README-repositorio.md`, acrescentar a linha da tabela e a seção abaixo
   (as duas em ordem alfabética: depois de "Instagram Coletor", antes de
   "PrintShot").
2. Em `publicar-todos.bat`, acrescentar a linha:
   `call :publish "montar-podcast" "montar-podcast" "montar-podcast-build.yml"`
3. Rodar o `publicar-todos.bat` (ou o `publicar-montar-podcast.command`, no Mac,
   que publica só este software).

---

## 1. Linha da tabela do topo

```
| Montar Podcast | Juntar vários áudios num episódio único e longo, com transição | [.exe](https://github.com/DiegoVSC42/Softwares/releases/download/montar-podcast/MontarPodcast.exe) | [.zip](https://github.com/DiegoVSC42/Softwares/releases/download/montar-podcast/MontarPodcast-mac.zip) |
```

## 2. Seção própria

```markdown
## Montar Podcast

**Caso de uso:**

Junta vários áudios de uma pasta num episódio único e longo, na ordem certa e com transição entre um bloco e o outro.

- **Windows:** <https://github.com/DiegoVSC42/Softwares/releases/download/montar-podcast/MontarPodcast.exe>
- **Mac:** <https://github.com/DiegoVSC42/Softwares/releases/download/montar-podcast/MontarPodcast-mac.zip>

**Nota (como usar):**

1. Abra o programa.
2. Clique em Escolher pasta e aponte para a pasta com os áudios. A lista aparece já na ordem certa (o arquivo 2 vem antes do 10), com a duração de cada um e a duração prevista do episódio.
3. Se quiser mudar a ordem, use Subir, Descer e Remover.
4. Escolha a transição: pausa curta com o volume baixando e subindo (a mais natural para conversa), um bloco entrando por cima do outro (boa para música), ou corte seco.
5. Clique em Ouvir a prévia da transição. O programa toca só a emenda entre os dois primeiros blocos, para você conferir antes de esperar o episódio inteiro.
6. Escreva um título, escolha a qualidade e diga onde salvar.
7. Deixe marcado Deixar todos os blocos no mesmo volume se os áudios foram gravados em dias ou lugares diferentes.
8. Clique em Montar podcast e acompanhe a barra (dá para cancelar a qualquer momento).
9. No fim saem dois arquivos: o episódio e um bloco de notas com o tempo em que cada parte começa, pronto para colar na descrição do episódio.
```
