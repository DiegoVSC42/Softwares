# Guia de teste — Instagram Coletor

Roteiro para testar tudo o que a ferramenta faz. Siga na ordem. Cada teste diz o
que colar, onde clicar e o que deve acontecer.

Todos os links abaixo foram conferidos e são reconhecidos pela ferramenta.

---

## Antes de começar (obrigatório)

1. Abra o **Chrome** e entre em `instagram.com`. Confirme que você está **logado**.
2. Abra o Instagram Coletor.
3. Em **Pasta de destino**, clique em "Escolher..." e crie uma pasta nova, por
   exemplo `Downloads/teste-instagram`. Assim fica fácil conferir o resultado.
4. Em **Login**, selecione **Chrome**.
5. Clique em **Testar login**.

**O que deve acontecer:** uma janela dizendo "Login OK". Se o Mac pedir a senha
do Chaveiro, clique em **Permitir Sempre** (é o sistema liberando a leitura dos
cookies do Chrome).

Se não der "Login OK", pare aqui. Nada mais vai funcionar. Volte ao Chrome,
confirme o login no Instagram e teste de novo.

---

## Teste 1 — Foto avulsa (o mais simples)

**Aba:** Links
**Opções:** marque "Baixar mídia" e "Gerar planilha de metadados"

Cole este link:

```
https://www.instagram.com/academiavitorinoemendonca/p/Dafo8t1ltU-/
```

Clique em **Coletar**.

**O que esperar:** um arquivo de imagem na subpasta
`instagram/academiavitorinoemendonca`, mais um `.xlsx` com uma linha só.

---

## Teste 2 — Carrossel (o teste que mais importa)

**Aba:** Links

Cole este link. É um carrossel de verdade, com várias imagens:

```
https://www.instagram.com/academiavitorinoemendonca/p/DZgHZvmFudM/
```

**O que esperar:** ele baixa **todas** as imagens do carrossel, não só a
primeira. É o comportamento que diferencia a ferramenta de salvar na mão. Na
planilha aparece **uma linha por imagem**, todas com o mesmo link de post.

Outro carrossel, se quiser confirmar:

```
https://www.instagram.com/academiavitorinoemendonca/p/DZYGOpAFvpb/
```

---

## Teste 3 — Reel (vídeo)

**Aba:** Links

```
https://www.instagram.com/academiavitorinoemendonca/reel/Dap8dIAttBs/
```

**O que esperar:** um arquivo `.mp4`. Na planilha, a coluna Tipo mostra que é
vídeo.

---

## Teste 4 — Vários links de uma vez

**Aba:** Links

Cole os quatro juntos, um por linha. São uma foto, um carrossel e dois reels:

```
https://www.instagram.com/academiavitorinoemendonca/p/DaTaCXcllq-/
https://www.instagram.com/academiavitorinoemendonca/p/DZYGOpAFvpb/
https://www.instagram.com/academiavitorinoemendonca/reel/Dak82LFt2kE/
https://www.instagram.com/academiavitorinoemendonca/reel/DanX4-Hth5i/
```

**O que esperar:** a barra anda uma vez por link e tudo cai na mesma pasta. A
planilha junta tudo, com uma linha por arquivo.

---

## Teste 5 — Perfil inteiro, com limite

**Aba:** Perfil inteiro
**Perfil:** `academiavitorinoemendonca`
**Marque:** apenas "Feed (posts e carrosséis)"
**Limite de posts:** `5`

Clique em **Coletar**.

**O que esperar:** ele baixa só os 5 posts mais recentes e para. Serve para
testar sem gastar tempo nem correr risco de bloqueio. Depois pode subir o limite.

---

## Teste 6 — Só os Reels do perfil

**Aba:** Perfil inteiro
**Perfil:** `academiavitorinoemendonca`
**Marque:** apenas "Reels"
**Limite:** `3`

**O que esperar:** só vídeos de reels, nenhuma foto.

---

## Teste 7 — Stories e Destaques

**Aba:** Perfil inteiro
**Perfil:** um perfil que **tenha story no ar agora**
**Marque:** "Stories (24h)" e "Destaques"

**O que esperar:** os stories das últimas 24 horas e as capas dos destaques. Se o
perfil não tiver story ativo, o registro avisa que não achou nada. Isso é normal,
não é erro.

---

## Teste 8 — Foto de perfil e Marcados

**Aba:** Perfil inteiro
**Perfil:** `academiavitorinoemendonca`
**Marque:** "Foto de perfil (alta resolução)" e "Marcados"

**O que esperar:** a foto de perfil em tamanho grande, e as fotos em que o perfil
foi marcado por outras pessoas.

---

## Teste 9 — Só a planilha, sem baixar nada

**Aba:** Perfil inteiro
**Perfil:** `academiavitorinoemendonca`
**Limite:** `20`
**Opções:** **desmarque** "Baixar mídia", deixe só "Gerar planilha de metadados"

**O que esperar:** nenhum arquivo de foto ou vídeo, só o `.xlsx`. É rápido. Esse
é o modo para analisar um concorrente sem encher o disco.

Abra a planilha e confira as colunas: usuário, data, tipo, link do post, legenda,
curtidas, hashtags, menções, localização, arquivo e código.

---

## Teste 10 — Filtros de tipo

Repita o Teste 5, mas marque **"Só imagens"**. Depois repita marcando **"Só
vídeos"**.

**O que esperar:** na primeira vez, nenhum `.mp4`. Na segunda, só `.mp4`.

---

## Teste 11 — Hashtag

**Aba:** Links (não é na aba Perfil)

Cole o link da hashtag direto:

```
https://www.instagram.com/explore/tags/marketingpolitico
```

**O que esperar:** ele baixa mídia de posts daquela hashtag. Use com o limite
baixo, porque hashtag popular tem muita coisa.

---

## Teste 12 — Seus posts salvos

**Aba:** Links

```
https://www.instagram.com/academiavitorinoemendonca/saved
```

**O que esperar:** os posts que **você** salvou. Só funciona para a conta que
está logada no Chrome.

---

## Teste 13 — Cancelar no meio

Comece o Teste 5 com limite `0` (baixar tudo) e, depois de uns segundos, clique
em **Cancelar**.

**O que esperar:** ele termina o arquivo que está no meio e para. O botão
"Coletar" volta a ficar disponível. O programa não trava.

---

## Teste 14 — Arquivo .json por post

Repita o Teste 2 (o carrossel) marcando também **"Salvar .json de cada post"**.

**O que esperar:** ao lado de cada foto ou vídeo aparece um arquivo `.json` com
todos os dados brutos daquele post. Serve para quem quer os dados completos, além
da planilha.

---

## O que NÃO dá para fazer

- **Comentários.** A ferramenta não baixa comentários. Não existe essa opção.
- **Perfil privado que você não segue.** Se a conta logada não segue, não passa.
- **Safari.** Foi tirado da lista. No Mac o sistema protege os cookies dele e a
  leitura falha.

## Se der erro

O quadro **Registro**, embaixo, mostra o erro real. Copie o texto de lá e me
mande. Erros comuns:

- *"login FALHOU"* — você não está logado no Chrome, ou usou o navegador errado.
- *"429" ou "rate limit"* — você baixou muita coisa rápido demais. Espere de 30
  minutos a algumas horas e volte com limite menor.
- *"não encontrado"* — o post foi apagado, ou o perfil é privado.

## Recomendação para não tomar bloqueio

Comece sempre com limite baixo (5 a 30 posts). A ferramenta já espera de 1 a 2
segundos entre cada arquivo de propósito. Se precisar de um perfil inteiro, faça
em lotes, ao longo do dia.
