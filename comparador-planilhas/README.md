# Comparador de Planilhas

Programa com janela (interface gráfica) para comparar duas planilhas (CSV
ou Excel) e gerar uma terceira com o resultado.

O que ele faz:

1. Carrega a Planilha A e a Planilha B (CSV ou XLSX). **As duas não
   precisam ter o mesmo cabeçalho** — dá para comparar, por exemplo, a
   coluna "E-mail" da A com a coluna "Email do contato" da B.
2. Mostra critérios de comparação: cada linha liga uma coluna da A a uma
   coluna da B. Colunas com nome igual (ignorando acento e
   maiúsculas/minúsculas) já vêm pareadas automaticamente ao carregar; para
   as demais, ou se quiser trocar algum par, use os menus de cada linha ou
   o botão "+ Adicionar critério". Com dois ou mais critérios marcados, uma
   linha só é considerada repetida se bater em todos eles ao mesmo tempo.
3. Aplica a operação escolhida:
   - **União**: junta as duas, sem repetir quem já está na A.
   - **Interseção**: só quem aparece nas duas planilhas.
   - **Remoção**: pega a A e tira quem também está na B. Tem uma opção para
     também acrescentar, no final, quem só existe na B.
4. Ignora, por padrão, diferença de maiúsculas/minúsculas e espaços na
   comparação (ex.: "Ana@X.com" e " ana@x.com " contam como o mesmo).
5. Para colunas de telefone, dá para marcar o tipo "Telefone (Brasil)". Aí o
   programa normaliza os números antes de comparar (tira parênteses, traços e
   espaços, trata o "55" na frente, completa o 9º dígito de celular), então
   duas planilhas com telefone em formatos diferentes (com ou sem DDI, com ou
   sem o 9, com ou sem formatação) são comparadas corretamente mesmo assim.
   Colunas com nome "Telefone", "Celular", "WhatsApp" etc. já vêm marcadas
   como telefone automaticamente. Se algum número não tiver DDD, informe um
   "DDD padrão" na tela para ele ser completado.
6. Célula vazia ou com um valor que não dá pra reconhecer (ex.: telefone
   sem nenhum dígito) nunca conta como igual a outra célula vazia da outra
   planilha — cada uma é tratada como única, para não remover ou juntar
   linhas por engano só porque os dois estão em branco.
7. O botão "Pré-visualizar contagem" mostra, antes de salvar, quantas
   linhas bateriam em cada operação — quantas de A também estão em B (as
   que seriam removidas), quantas de B são exclusivas, e o total estimado
   da operação escolhida.
8. Ao final, pede onde salvar o resultado (CSV ou Excel).

## Como rodar no Mac

1. Clique duas vezes em `abrir-comparador-planilhas.command`.
2. Na primeira vez, o Mac pode bloquear ("não é possível verificar o
   desenvolvedor"). Clique com o botão direito no arquivo, escolha Abrir e
   confirme em Abrir. Ainda na primeira vez, o programa demora 1 a 2 minutos
   preparando o ambiente.
3. Na janela, clique em Procurar para escolher a Planilha A e a Planilha B.
4. Clique em Carregar planilhas.
5. Confira os critérios de comparação: em cada linha, escolha a coluna de A
   e a coluna de B correspondentes (colunas com nome igual já vêm
   preenchidas). Use "+ Adicionar critério" se quiser comparar por mais de
   uma coluna (ex.: nome e telefone juntos), ou Remover para tirar alguma.
   Se for telefone, confira se o tipo ao lado está como "Telefone (Brasil)".
6. Escolha a operação (União, Interseção ou Remoção).
7. Antes de salvar, clique em Pré-visualizar contagem para ver quantas
   linhas seriam removidas, adicionadas ou mantidas, e conferir se o número
   faz sentido para o seu caso.
8. Clique em Processar e salvar resultado e escolha onde salvar o arquivo.

## Como testar

Para conferir se está tudo funcionando, crie dois arquivos CSV pequenos, por
exemplo:

`teste_a.csv`
```
nome,email
Ana Silva,ana@x.com
Bruno Costa,bruno@x.com
Carla Souza,carla@x.com
```

`teste_b.csv`
```
nome,email
Bruno Costa,bruno@x.com
Daniela Reis,daniela@x.com
```

Carregue os dois (a coluna "email" já vem pareada automaticamente) e teste
cada operação. O resultado esperado é:

- **União**: 4 linhas (Ana, Bruno, Carla, Daniela).
- **Interseção**: 1 linha (Bruno).
- **Remoção**: 2 linhas (Ana, Carla).
- **Remoção com "incluir exclusivos de B" marcado**: 3 linhas (Ana, Carla,
  Daniela).

Para testar a normalização de telefone, use:

`teste_tel_a.csv`
```
nome,telefone
Ana Silva,(62) 99999-0001
Bruno Costa,62 3999-0002
Carla Souza,55 62 99999-0003
```

`teste_tel_b.csv`
```
nome,telefone
Bruno Costa,6239990002
Ana Silva,62999990001
Elisa Nunes,62988880009
```

Carregue os dois, deixe a coluna "telefone" marcada com o tipo "Telefone
(Brasil)" e rode a Interseção: o resultado deve trazer Ana e Bruno (2
linhas), mesmo os números estando escritos de formas diferentes nas duas
planilhas.

Para testar com cabeçalhos diferentes entre as duas planilhas, use:

`teste_hdr_a.csv`
```
Nome Completo,E-mail,Celular
Ana Silva,ana@x.com,(62) 99999-0001
Bruno Costa,bruno@x.com,62 3999-0002
Carla Souza,carla@x.com,55 62 99999-0003
```

`teste_hdr_b.csv`
```
nome,Email do contato,Telefone
Bruno Costa,bruno@x.com,6239990002
Daniela Reis,daniela@x.com,62999990004
```

Ao carregar, nenhuma coluna vem pareada automaticamente (os nomes são todos
diferentes). Adicione manualmente os três critérios: "Nome Completo" com
"nome", "E-mail" com "Email do contato", e "Celular" com "Telefone" (tipo
Telefone (Brasil)). Rode a Interseção: o resultado deve trazer só Bruno
Costa (1 linha).

Para conferir que células vazias/inválidas não se misturam por engano
(esse era um bug já corrigido), use:

`teste_vazio_a.csv`
```
nome,telefone
Ana,
Bruno,62999990001
Carla,abc
```

`teste_vazio_b.csv`
```
nome,telefone
X1,
X2,n/a
X3,62988880000
X4,
```

Carregue os dois, deixe "telefone" com o tipo Telefone (Brasil) e rode a
Interseção: o resultado deve vir vazio (0 linhas), já que nenhum telefone
de verdade se repete — os campos em branco ou inválidos de A e B não devem
contar como iguais entre si.

## Publicação

Ainda não configurada. Quando quiser enviar este software para o GitHub
(para gerar o `.exe` do Windows e o `.app` do Mac automaticamente), é só
pedir.
