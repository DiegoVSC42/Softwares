# ATENCAO: este arquivo e uma COPIA. Nao edite aqui.
# A fonte oficial e `abas-compartilhadas/editor_legenda.py`, na pasta Scripts. Mexa la e
# rode `python3 sincronizar.py` para atualizar todos os estudios de uma vez.
# Editar esta copia faz o seu trabalho ser apagado na proxima sincronizacao.

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A tela de trabalho da aba "Sincronizar com video", escrita como uma pagina que
o navegador da propria maquina mostra.

Ela e servida pelo `servidor_legenda.py`, em 127.0.0.1, e nunca sai da maquina.
Nada aqui vai para a internet: o video e lido do disco, a legenda vem do
arquivo que a pessoa escolheu, e o resultado volta para o Python gravar.

O desenho segue a paleta do Transcript Studio (fundo #0d1117, destaque
laranja), para o editor parecer parte do programa e nao uma pagina qualquer.

Como a pagina e montada: um arquivo so, sem nada baixado de fora, porque ela
tem que abrir mesmo com a maquina sem internet.
"""

_PAGINA = r"""<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sincronizar legenda — Transcript Studio</title>
<style>
  :root{
    --fundo:#0d1117; --painel:#161b22; --campo:#21262d; --botao:#30363d;
    --borda:#3d444d; --texto:#e6edf3; --suave:#a8b3bf; --apagado:#6e7681;
    --destaque:#ff9d3d; --ok:#7ee787; --erro:#ff7b72;
  }
  *{box-sizing:border-box}
  html,body{height:100%}
  body{
    margin:0; background:var(--fundo); color:var(--texto);
    font:15px/1.5 -apple-system,BlinkMacSystemFont,"Helvetica Neue",Arial,sans-serif;
    overflow:hidden;
    /* Coluna: a barra de cima em cima, sempre visível, e o trabalho ocupando
       todo o resto. Se a barra precisar de duas linhas numa janela estreita,
       ela cresce e o resto encolhe, sem nada ser cortado. */
    display:flex; flex-direction:column; height:100vh;
  }
  button{font:inherit; cursor:pointer; border-radius:7px; border:1px solid var(--borda);
    background:var(--botao); color:var(--texto); padding:6px 11px}
  button:hover{background:var(--borda)}
  button.acao{background:var(--destaque); color:#1a1a1a; border-color:var(--destaque); font-weight:600}
  button.acao:hover{background:#ffb066}
  button.ligado{border-color:var(--destaque); color:var(--destaque)}
  input[type=text],input[type=number]{
    font:inherit; background:var(--campo); color:var(--texto);
    border:1px solid var(--borda); border-radius:7px; padding:6px 9px}
  input:focus{outline:none; border-color:var(--destaque)}

  /* ------------------------------------------------ esqueleto da tela */
  /* A barra de cima (salvar, painel, contagem) NUNCA rola: ela é fixa no topo
     da janela, em qualquer largura. */
  #topo{display:flex; align-items:center; gap:14px; padding:10px 16px;
    background:var(--painel); border-bottom:1px solid var(--borda);
    min-height:56px; flex:0 0 auto; flex-wrap:wrap; row-gap:6px; z-index:40}
  #topo h1{font-size:15px; margin:0; font-weight:600; white-space:nowrap;
    overflow:hidden; text-overflow:ellipsis; max-width:38vw; cursor:pointer;
    border-bottom:1px dashed transparent; padding-bottom:1px}
  #topo h1:hover{border-bottom-color:var(--borda)}
  /* O painel de título e nome do arquivo. */
  #menu .campo{display:block; margin-bottom:10px}
  #menu .campo span{display:block; font-size:12px; color:var(--suave);
    margin-bottom:4px}
  #menu .campo input{width:100%}
  #menu .extensao{font-size:12px; color:var(--apagado); margin-top:-6px;
    margin-bottom:10px}
  #topo .conta{color:var(--apagado); font-size:12.5px; white-space:nowrap}
  #estado{margin-left:auto; font-size:13px; color:var(--suave); white-space:nowrap}

  #tela{display:flex; flex:1 1 auto; min-height:0}
  /* `min-height:0` NÃO é detalhe: sem ele, um filho de flex se recusa a ficar
     menor que o próprio conteúdo. Com 1500 falas, a coluna inteira estufava
     para além da janela, empurrando a barra da busca para fora da tela e
     matando a rolagem de dentro da lista. */
  #legenda{flex:1 1 auto; min-width:0; min-height:0;
    display:flex; flex-direction:column}
  #palco{flex:0 0 clamp(380px, 38vw, 620px); border-left:1px solid var(--borda);
    background:var(--painel); display:flex; flex-direction:column; overflow-y:auto}

  /* Vídeo grande: o painel engorda e some com tudo o que não é o vídeo, que
     então ocupa a altura inteira. É a alternativa a jogar o vídeo para outra
     janela, para quem trabalha numa tela só. */
  #palco.sovideo{flex:0 0 clamp(420px, 55vw, 72%); overflow:hidden}
  #palco.sovideo .caixa{display:none}
  #palco.sovideo .caixavideo{display:flex; flex-direction:column;
    flex:1 1 auto; min-height:0; border-bottom:none}
  #palco.sovideo video{flex:1 1 auto; min-height:0; height:auto;
    object-fit:contain; border-radius:0}

  /* A divisória: dois pixels de linha e uma faixa larga de pegada, porque
     acertar uma linha fina com o mouse é irritante. */
  #divisor{flex:0 0 9px; cursor:col-resize; background:transparent;
    position:relative}
  #divisor::after{content:""; position:absolute; inset:0 4px; background:var(--borda)}
  #divisor:hover::after,#divisor.arrastando::after{background:var(--destaque)}
  body.arrastando{user-select:none; cursor:col-resize}
  body.arrastando iframe,body.arrastando video{pointer-events:none}

  /* Quando o vídeo vai para outra janela, fica este aviso no lugar dele. */
  #fora{display:none; text-align:center; padding:26px 14px; border:1px dashed var(--borda);
    border-radius:10px; color:var(--suave); font-size:13.5px}
  #fora button{margin-top:10px}

  /* ------------------------------------------------------ lado da legenda */
  /* A busca fica logo abaixo e também não sai de vista: quem rola é só a
     lista de falas, nunca o cabeçalho de trabalho. */
  #barra{display:flex; align-items:center; gap:8px; padding:8px 14px;
    border-bottom:1px solid var(--borda); background:var(--fundo);
    flex:0 0 auto; flex-wrap:wrap; row-gap:6px}
  #busca{flex:1 1 auto; min-width:120px}
  #lista{flex:1 1 auto; min-height:0; overflow-y:auto;
    padding:6px 6px 40vh 6px; scroll-behavior:smooth}

  .fala{display:grid; grid-template-columns:16px 56px 1fr; gap:9px; align-items:start;
    padding:7px 10px; border-radius:9px; border:1px solid transparent}
  .fala:hover{background:#12171f}
  .fala.agora{background:#1d2530; border-color:#3a2a14}
  .fala.agora .txt{color:#fff}
  .fala.achado{border-color:var(--destaque)}
  /* A marca de selecionar. Fica discreta até o ponteiro passar por cima, para
     não poluir a leitura de mil falas seguidas. */
  .marca{width:14px; height:14px; margin-top:4px; border-radius:4px;
    border:1.5px solid var(--borda); cursor:pointer; opacity:.3}
  .fala:hover .marca{opacity:.85}
  .fala.marcada .marca{background:var(--destaque); border-color:var(--destaque); opacity:1}
  .fala.marcada{background:#1b2331; border-color:var(--destaque)}

  /* O trecho que está em repetição fica com um filete verde na lateral. */
  .fala.emlaco{box-shadow:inset 3px 0 0 var(--ok)}
  /* O aviso de gravado FICA na tela: dizer "salvo" e sumir em dois segundos
     não conta o que interessa, que é o nome do arquivo e onde ele foi parar. */
  #salvo{display:none; gap:12px; align-items:flex-start; padding:10px 14px;
    background:#122019; border-bottom:1px solid var(--ok); font-size:13px}
  #salvo.mostra{display:flex}
  #salvo .marcaok{color:var(--ok); font-weight:600; white-space:nowrap}
  #salvo .quais{min-width:0; flex:1 1 auto}
  #salvo .quais b{display:block; color:var(--texto); font-weight:600;
    word-break:break-all}
  #salvo .quais span{color:var(--suave); font-size:12.5px; word-break:break-all}
  #selecao{display:none; align-items:center; gap:10px; padding:8px 14px;
    background:#1b2331; border-bottom:1px solid var(--destaque); font-size:13.5px}
  #selecao.mostra{display:flex}
  #selecao b{color:var(--destaque)}
  .hora{color:var(--apagado); font-size:12px; font-variant-numeric:tabular-nums;
    text-align:right; padding-top:3px; cursor:pointer; user-select:none}
  .hora:hover{color:var(--destaque)}
  .fala.agora .hora{color:var(--destaque)}
  .corpo{min-width:0}
  .quem{display:inline-flex; align-items:center; gap:6px; font-size:12.5px;
    font-weight:600; padding:1px 8px; border-radius:20px; cursor:pointer;
    border:1px solid transparent; margin-bottom:2px}
  .quem:hover{border-color:currentColor}
  .quem .seta{opacity:.55; font-size:10px}
  .fala{cursor:pointer}
  .txt{cursor:text; display:block; color:var(--texto); outline:none; padding:1px 2px;
    border-radius:5px; white-space:pre-wrap; word-break:break-word}
  .txt.editando{cursor:text; background:var(--campo);
    box-shadow:0 0 0 1px var(--destaque)}
  .txt:focus{background:var(--campo); box-shadow:0 0 0 1px var(--borda)}

  /* --------------------------------------------------------- lado do video */
  #palco .caixa{padding:12px 14px; border-bottom:1px solid var(--borda)}
  video{width:100%; background:#000; border-radius:10px; display:block}
  .linha{display:flex; align-items:center; gap:8px; flex-wrap:wrap}
  .linha + .linha{margin-top:8px}
  .rotulo{font-size:12px; color:var(--suave); text-transform:uppercase;
    letter-spacing:.06em; margin:0 0 7px 0}
  .dica{font-size:12.5px; color:var(--apagado); margin:7px 0 0 0; line-height:1.45}
  .dica b{color:var(--suave); font-weight:600}
  #chips{display:flex; flex-wrap:wrap; gap:6px}
  .chip{display:inline-flex; align-items:center; gap:6px; font-size:12.5px;
    padding:3px 9px; border-radius:20px; cursor:pointer; border:1px solid transparent}
  .chip:hover{border-color:currentColor}
  .chip{cursor:grab}
  .chip.arrastando{opacity:.4; cursor:grabbing}
  /* A linha que mostra onde a pessoa vai cair ao soltar. */
  .chip.alvo{box-shadow:-3px 0 0 var(--texto)}
  .chip b{font-weight:600}
  .chip span{color:var(--apagado); font-size:11px}
  kbd{background:var(--campo); border:1px solid var(--borda); border-radius:5px;
    padding:0 5px; font-size:11px; font-family:inherit; color:var(--suave)}

  /* A dica que aparece ao passar o mouse. É feita aqui, e não com o `title` do
     navegador, por dois motivos: o `title` demora mais de um segundo para
     aparecer, e não deixa destacar a tecla de atalho. */
  [data-dica]{position:relative}
  [data-dica]:hover::after{
    content:attr(data-dica);
    position:absolute; top:calc(100% + 7px); left:0; z-index:70;
    background:#0b0f14; color:var(--texto); border:1px solid var(--borda);
    padding:5px 9px; border-radius:7px; font-size:12px; font-weight:400;
    white-space:nowrap; letter-spacing:0; text-transform:none;
    box-shadow:0 10px 24px rgba(0,0,0,.6); pointer-events:none;
    opacity:0; animation:aparecerDica .12s .3s forwards;
  }
  @keyframes aparecerDica{to{opacity:1}}
  /* Botões encostados na direita mostram a dica alinhada pela direita, senão
     ela sai da janela. */
  #topo [data-dica]:hover::after,
  #palco [data-dica]:hover::after{left:auto; right:0}

  /* ------------------------------------------------------------- o popup */
  #menu{position:fixed; z-index:50; background:var(--painel); border:1px solid var(--borda);
    border-radius:11px; padding:8px; min-width:250px; display:none;
    box-shadow:0 14px 40px rgba(0,0,0,.6)}
  #menu .modo{display:flex; gap:5px; margin-bottom:8px}
  #menu .modo button{flex:1; font-size:12px; padding:5px 4px}
  #menu.largo{min-width:min(92vw, 560px)}
  #menu .nomes{display:grid; grid-template-columns:1fr; gap:3px;
    max-height:56vh; overflow-y:auto}
  #menu .nomes.duas{grid-template-columns:1fr 1fr}
  #menu .quem{display:flex; width:100%; margin:0; justify-content:flex-start;
    min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis}
  #menu .novo{width:100%; margin-top:6px; font-size:13px}
  #menu .tituloMenu{font-size:12px; color:var(--suave); padding:2px 4px 8px 4px}
  /* A paleta: oito por linha, duas linhas. Quadrado grande o bastante para
     acertar com o mouse sem mira. */
  #menu .cores{display:grid; grid-template-columns:repeat(8, 30px); gap:6px}
  #menu .amostra{width:30px; height:30px; border-radius:8px; cursor:pointer;
    border:2px solid transparent; box-shadow:inset 0 0 0 1px rgba(0,0,0,.35)}
  #menu .amostra:hover{border-color:var(--texto)}
  #menu .amostra.atual{border-color:var(--texto)}
  #aviso{position:fixed; inset:auto 0 22px 0; display:flex; justify-content:center;
    pointer-events:none; z-index:60}
  #aviso div{background:var(--painel); border:1px solid var(--destaque); color:var(--texto);
    padding:9px 16px; border-radius:24px; font-size:13.5px; opacity:0;
    transition:opacity .25s; box-shadow:0 10px 30px rgba(0,0,0,.5)}
  #aviso.mostra div{opacity:1}
  /* JANELA ESTREITA (meia tela, com o vídeo em outra janela ou não).
     Antes, aqui a PÁGINA INTEIRA passava a rolar, e o cabeçalho com o botão de
     salvar e a busca subia junto: para salvar era preciso voltar ao topo de
     uma entrevista de mil falas. Agora a estrutura é a mesma da tela larga -
     cabeçalho parado, lista rolando por dentro - e o vídeo, quando está nesta
     janela, ocupa uma faixa em cima. */
  @media (max-width:900px){
    #tela{flex-direction:column-reverse; overflow:hidden}
    #palco{flex:0 0 auto; max-height:46vh; border-left:none;
      border-bottom:1px solid var(--borda)}
    #palco.sovideo{flex:0 0 auto; max-height:64vh}
    #divisor{display:none}
    #topo h1{max-width:100%}
  }
</style>
</head>
<body>

<header id="topo">
  <h1 id="titulo">Sincronizar legenda</h1>
  <span class="conta" id="conta"></span>
  <span id="estado"></span>
  <button id="btVoltarTopo" style="display:none" title="Trazer o vídeo de volta para esta janela">⧉ Trazer o vídeo</button>
  <button id="btPainel" title="Esconder a coluna da direita e usar a tela toda para a legenda">Ocultar painel ⟩</button>
  <button id="btSalvar" class="acao">Salvar corrigido</button>
</header>

<div id="tela">
  <section id="legenda">
    <div id="barra">
      <button id="btSeguir" class="ligado" title="A lista acompanha o vídeo sozinha">Acompanhar</button>
      <button id="btLaco" title="R — repete sem parar a fala selecionada (ou o trecho selecionado)">↻ Repetir</button>
      <button id="btDividir" title="⌘+Enter — parte a fala em duas, no ponto do cursor e no momento do vídeo">✂ Dividir</button>
      <button id="btVideoGrande" title="O vídeo ocupa toda a direita, sem os controles embaixo">⤢ Vídeo grande</button>
      <button id="btDesfazer" title="⌘Z — desfaz a última divisão, junção ou troca de falante" disabled>⤾ Desfazer</button>
      <input type="text" id="busca" placeholder="Procurar uma palavra e pular até ela (Enter)">
      <span id="achados" style="font-size:12.5px;color:var(--apagado)"></span>
    </div>
    <div id="salvo">
      <span class="marcaok">✓ Gravado</span>
      <span class="quais"><b id="salvoNomes"></b><span id="salvoPasta"></span></span>
      <button id="btMostrar">Mostrar no Finder</button>
      <button id="btFecharSalvo" title="Esconder este aviso">✕</button>
    </div>
    <div id="selecao">
      <span><b id="quantas">0</b> falas selecionadas</span>
      <button id="btTrocarMarcadas" class="acao">Trocar quem fala nelas</button>
      <button id="btJuntar">⤿ Juntar numa fala só</button>
      <button id="btLacoMarcadas">↻ Repetir as selecionadas</button>
      <button id="btLimparMarcas">Limpar seleção</button>
      <span style="color:var(--apagado);font-size:12.5px">
        ⌘+clique soma uma &nbsp;·&nbsp; shift+clique vai até aqui &nbsp;·&nbsp; Esc limpa</span>
    </div>
    <div id="lista"></div>
  </section>

  <div id="divisor" title="Arraste para mudar a largura"></div>

  <aside id="palco">
    <div class="caixa caixavideo">
      <video id="v" controls preload="metadata" playsinline></video>
      <div id="fora">
        O vídeo está tocando na outra janela.<br>
        Arraste aquela janela para o monitor que quiser.
        <br><button id="btVoltarVideo">Trazer o vídeo de volta</button>
      </div>
      <div class="linha" style="margin-top:9px">
        <button id="btOutraJanela" style="flex:1">Abrir o vídeo em outra janela</button>
      </div>
      <div class="linha">
        <button id="btVoltar" title="J">◀ 5s</button>
        <button id="btTocar" title="Espaço">Tocar</button>
        <button id="btAvancar" title="L">5s ▶</button>
        <span style="flex:1"></span>
        <span class="conta">Velocidade</span>
        <button class="vel" data-v="0.75">0,75×</button>
        <button class="vel ligado" data-v="1">1×</button>
        <button class="vel" data-v="1.5">1,5×</button>
        <button class="vel" data-v="2">2×</button>
      </div>
    </div>

    <div class="caixa">
      <p class="rotulo">Sincronia</p>
      <div class="linha">
        <button id="btMenos">− 0,5s</button>
        <input type="number" id="desloc" value="0" step="0.1" style="width:92px">
        <span class="conta">segundos</span>
        <button id="btMais">+ 0,5s</button>
      </div>
      <div class="linha">
        <button id="btAlinhar" style="flex:1">Alinhar a fala selecionada ao ponto atual do vídeo</button>
      </div>
      <p class="dica">Se a legenda estiver adiantada ou atrasada em relação ao vídeo,
        pare o vídeo <b>exatamente</b> onde uma fala começa, clique nessa fala na lista
        e use o botão acima. O ajuste vale para a legenda inteira.</p>
    </div>

    <div class="caixa">
      <p class="rotulo">Quem fala</p>
      <div id="chips"></div>
      <p class="dica"><b>Arraste os nomes</b> para colocá-los na ordem que você
        quiser: é essa ordem que o menu de troca de falante usa, e ela fica
        guardada para as próximas vezes.
        Clique num nome aqui para <b>escolher a cor</b> dele — dá
        para casar com a roupa de cada um, e a escolha fica guardada para as
        próximas vezes — ou para renomeá-lo em toda a legenda.
        Para trocar quem fala numa fala específica, clique no nome dentro dela.</p>
    </div>

    <div class="caixa" style="border-bottom:none">
      <p class="rotulo">Atalhos</p>
      <p class="dica">
        <kbd>espaço</kbd> tocar e pausar &nbsp; <kbd>J</kbd> voltar 5s &nbsp;
        <kbd>L</kbd> avançar 5s<br>
        <kbd>↑</kbd> <kbd>↓</kbd> andar pelas falas &nbsp; <kbd>Enter</kbd> levar o vídeo até a fala<br>
        <b>um clique</b> em qualquer lugar da fala seleciona ela e leva o vídeo
        até ali; no texto, ainda deixa o cursor pronto para corrigir a escrita
        (com o vídeo parado, clicar no texto não mexe nele: é o que permite
        dividir a fala no instante exato em que você pausou)<br>
        <b>⌘+clique</b> soma outra fala à seleção &nbsp; <b>shift+clique</b>
        seleciona até ali &nbsp; e a troca de falante vale para tudo o que
        estiver selecionado<br>
        escrevendo numa fala: <kbd>Enter</kbd> confirma &nbsp;
        <kbd>Esc</kbd> desfaz o que você digitou nela<br>
        <kbd>R</kbd> repetir sem parar &nbsp; <kbd>⌘+Enter</kbd> dividir a fala
        no ponto do cursor &nbsp; <kbd>⌘S</kbd> salvar<br><br>
        <b>Dividir:</b> quando uma fala junta duas pessoas, pare o vídeo no
        instante em que a segunda começa, clique no texto no ponto do corte e
        use <b>✂ Dividir</b>. O texto se parte ali, a segunda metade ganha o
        horário em que o vídeo está, e aí é só dizer quem fala em cada parte.<br><br>
        <b>Errou?</b> <kbd>⌘Z</kbd> (ou <b>⤾ Desfazer</b>) volta atrás na
        última divisão, junção ou troca de falante. Para juntar duas falas numa
        só, selecione as duas com ⌘+clique e use <b>⤿ Juntar numa fala
        só</b>.<br><br>
        <b>Largura:</b> arraste a divisória entre a legenda e o vídeo. Ela
        guarda o tamanho que você deixar; dois cliques nela voltam ao normal.
        O botão <b>⤢ Vídeo grande</b> engorda o painel e deixa só o vídeo nele,
        para quem trabalha numa tela só.<br><br>
        <b>Dois monitores:</b> use “abrir o vídeo em outra janela” e arraste
        aquela janela para a outra tela. É o mesmo vídeo, não uma cópia: ele
        continua de onde estava e tudo aqui continua funcionando. Esta coluna
        se recolhe sozinha nessa hora, e a legenda fica com a tela inteira; o
        botão <b>Mostrar painel</b>, lá em cima, a traz de volta quando você
        precisar da sincronia ou dos falantes.<br><br>
        <b>Título e nome do arquivo:</b> clique no título, no alto da tela, para
        trocar os dois. O título é a primeira linha do documento; o nome é como
        o .docx e o .txt vão se chamar na pasta.<br><br>
        <b>Não precisa ficar salvando:</b> a cada 20 segundos, o que você
        mudou vai sozinho para o .docx e o .txt na pasta escolhida. O botão
        Salvar continua ali para quando você quiser fechar a conta na hora.
        Se o navegador fechar, ao reabrir ele ainda volta de onde parou.
      </p>
    </div>
  </aside>
</div>

<div id="menu"></div>
<div id="aviso"><div></div></div>

<script>
const TOKEN = "__TOKEN__";
const U = (c) => c + (c.includes("?") ? "&" : "?") + "t=" + TOKEN;

/* Dezesseis cores com NOME, escolhidas para (a) se distinguirem umas das
   outras no fundo escuro e (b) casarem com a roupa de quem fala, que é como a
   pessoa identifica os participantes num grupo gravado: "a de blusa vinho",
   "o de camiseta preta". A lista antiga tinha dez tons parecidos - quatro
   rosas - e dois falantes viravam a mesma cor a olho nu. */
const PALETA = [
  {nome: "Vermelho",    cor: "#ff6b63"},
  {nome: "Vinho",       cor: "#c9566f"},
  {nome: "Rosa",        cor: "#ff9ecb"},
  {nome: "Laranja",     cor: "#ff9d3d"},
  {nome: "Amarelo",     cor: "#ffd866"},
  {nome: "Bege",        cor: "#e3cfa0"},
  {nome: "Marrom",      cor: "#c08457"},
  {nome: "Verde",       cor: "#7ee787"},
  {nome: "Verde-água",  cor: "#4fd1a5"},
  {nome: "Ciano",       cor: "#56d4dd"},
  {nome: "Azul",        cor: "#79c0ff"},
  {nome: "Azul-escuro", cor: "#6b8afd"},
  {nome: "Roxo",        cor: "#d2a8ff"},
  {nome: "Lilás",       cor: "#a371f7"},
  {nome: "Chumbo",      cor: "#9aa7b4"},
  {nome: "Branco",      cor: "#f0f6fc"},
];
const CORES = PALETA.map(p => p.cor);

let DADOS = null, SEG = [], FALANTES = [], DESLOC = 0;
// O título que vai na primeira linha do documento e o nome do arquivo gravado.
let TITULO = "", ARQUIVO = "";
let atual = -1, escolhida = -1, sujo = false, modoTroca = "selecao";
// Onde estava o cursor da última vez que você mexeu no texto de uma fala.
// Guardado porque CLICAR NO BOTÃO tira o foco do texto e apaga a seleção do
// navegador: sem esta memória, o ✂ Dividir nunca saberia o ponto do corte e
// cortaria sempre no meio, que foi exatamente o defeito relatado.
let corteLembrado = {i: -1, pos: -1};
// A SELEÇÃO é o centro de tudo: clicar numa fala seleciona só ela, e é sobre a
// seleção que a troca de falante e a repetição agem. ⌘+clique soma outra fala,
// shift+clique vai até ela. `ultimaMarcada` é a âncora do shift.
const marcadas = new Set();
let ultimaMarcada = -1;
let rolagemManual = 0;
// Última tecla digitada dentro de uma fala. O "Acompanhar" só se segura
// enquanto você ESTÁ escrevendo; parou de digitar, ele volta a seguir o vídeo.
let ultimaDigitacao = 0;

const $ = (s) => document.querySelector(s);
const video = $("#v"), lista = $("#lista"), menu = $("#menu");

/* ------------------------------------------------------------------ apoio */
function hhmmss(t){
  t = Math.max(0, Math.round(t || 0));
  const h = Math.floor(t/3600), m = Math.floor((t%3600)/60), s = t%60;
  const dois = (n) => String(n).padStart(2,"0");
  return h ? h + ":" + dois(m) + ":" + dois(s) : m + ":" + dois(s);
}
/* A cor de cada falante e decidida na primeira vez que ele aparece e nao muda
   mais. Se ela viesse da posicao na lista, uma correcao que zerasse um
   falante trocaria a cor de todos os outros no meio do trabalho. */
const CORMAP = {};

function cor(nome){
  if (!nome) return "#a8b3bf";
  if (!CORMAP[nome]) CORMAP[nome] = CORES[Object.keys(CORMAP).length % CORES.length];
  return CORMAP[nome];
}

/* A cor que VOCÊ escolheu para cada pessoa fica guardada neste navegador, por
   entrevista. Na próxima vez que abrir a mesma legenda, cada um volta com a
   cor da roupa dele. */
function chaveCores(){ return "cores:" + (DADOS ? DADOS.nome : ""); }
function chaveOrdem(){ return "ordem:" + (DADOS ? DADOS.nome : ""); }
function chaveArquivo(){ return "arquivo:" + (DADOS ? DADOS.nome : ""); }

function mostrarTitulo(){
  document.title = TITULO + " — sincronizar";
  $("#titulo").textContent = TITULO;
  $("#titulo").dataset.dica = "Clique para mudar o título e o nome do arquivo";
}

function guardarArquivo(){
  try{
    localStorage.setItem(chaveArquivo(),
                         JSON.stringify({titulo: TITULO, arquivo: ARQUIVO}));
  }catch(e){}
}

/* Painel do título e do nome do arquivo, aberto pelo título lá em cima. */
function menuArquivo(evento){
  evento.stopPropagation();
  menu.innerHTML = "";
  menu.classList.remove("largo");

  const campoTitulo = document.createElement("label");
  campoTitulo.className = "campo";
  campoTitulo.innerHTML = "<span>Título, na primeira linha do documento</span>";
  const et = document.createElement("input");
  et.type = "text"; et.value = TITULO;
  campoTitulo.appendChild(et);
  menu.appendChild(campoTitulo);

  const campoArquivo = document.createElement("label");
  campoArquivo.className = "campo";
  campoArquivo.innerHTML = "<span>Nome do arquivo gravado</span>";
  const ea = document.createElement("input");
  ea.type = "text"; ea.value = ARQUIVO;
  campoArquivo.appendChild(ea);
  menu.appendChild(campoArquivo);

  const extensao = document.createElement("div");
  extensao.className = "extensao";
  extensao.textContent = "sai como .docx e .txt, em " + DADOS.saida;
  menu.appendChild(extensao);

  const pronto = document.createElement("button");
  pronto.className = "novo acao";
  pronto.textContent = "Pronto";
  const aplicar = () => {
    TITULO = et.value.trim() || DADOS.nome;
    ARQUIVO = ea.value.trim() || (DADOS.nome + " (falantes conferidos)");
    guardarArquivo();
    mostrarTitulo();
    marcarSujo();          // o próximo salvamento grava com o nome novo
    fecharMenu();
    recado("Vai gravar como “" + ARQUIVO + "”.");
  };
  pronto.onclick = (e) => { e.stopPropagation(); aplicar(); };
  [et, ea].forEach(campo => {
    campo.onclick = (e) => e.stopPropagation();
    campo.onkeydown = (e) => {
      e.stopPropagation();
      if (e.key === "Enter") aplicar();
      if (e.key === "Escape") fecharMenu();
    };
  });
  menu.appendChild(pronto);

  const r = evento.currentTarget.getBoundingClientRect();
  menu.style.display = "block";
  menu.style.minWidth = "min(92vw, 420px)";
  menu.style.left = Math.min(r.left, window.innerWidth - menu.offsetWidth - 14) + "px";
  menu.style.top = (r.bottom + 6) + "px";
  et.focus();
  et.select();
}

$("#titulo").onclick = menuArquivo;

/* A ORDEM da lista de falantes também é sua: você arrasta os nomes para onde
   quiser, e é essa ordem que o menu de troca de falante usa. Quem passa o dia
   corrigindo aprende a mão - "o segundo da esquerda é o Carlos" - e a lista
   mudar de lugar sozinha custa caro. */
function guardarOrdem(){
  try{ localStorage.setItem(chaveOrdem(), JSON.stringify(FALANTES)); }catch(e){}
}

function lerOrdem(){
  let guardada = [];
  try{ guardada = JSON.parse(localStorage.getItem(chaveOrdem()) || "[]"); }catch(e){}
  if (!guardada.length) return;
  // Primeiro quem já tinha lugar marcado, na ordem que você deixou; depois os
  // que apareceram depois, no fim.
  const naOrdem = guardada.filter(x => FALANTES.includes(x));
  FALANTES = naOrdem.concat(FALANTES.filter(x => !naOrdem.includes(x)));
}

function moverFalante(quem, antesDe){
  if (!quem || quem === antesDe) return;
  const de = FALANTES.indexOf(quem);
  if (de < 0) return;
  FALANTES.splice(de, 1);
  const para = antesDe === null ? FALANTES.length : FALANTES.indexOf(antesDe);
  FALANTES.splice(para < 0 ? FALANTES.length : para, 0, quem);
  guardarOrdem();
  chips();
}

function guardarCores(){
  try{ localStorage.setItem(chaveCores(), JSON.stringify(CORMAP)); }catch(e){}
}

function lerCores(){
  try{
    Object.assign(CORMAP, JSON.parse(localStorage.getItem(chaveCores()) || "{}"));
  }catch(e){}
}

function pintarDeNovo(){
  const rolagem = lista.scrollTop;
  desenhar();
  lista.scrollTop = rolagem;
  pintarMarcas();
  pintarLaco();
  chips();
}
function recado(texto){
  const caixa = $("#aviso");
  caixa.firstElementChild.textContent = texto;
  caixa.classList.add("mostra");
  clearTimeout(recado.tempo);
  recado.tempo = setTimeout(() => caixa.classList.remove("mostra"), 2600);
}
function marcarSujo(){
  sujo = true;
  $("#estado").textContent = "alterações não salvas";
  $("#estado").style.color = "var(--destaque)";
}

/* --------------------------------------------------------------- montagem */
async function comecar(){
  DADOS = await fetch(U("/dados.json")).then(r => r.json());
  SEG = DADOS.segmentos;
  FALANTES = DADOS.falantes.slice();
  // Título do documento e nome do arquivo: os dois começam como vieram, e os
  // dois podem ser trocados na tela (clique no título, lá em cima).
  TITULO = DADOS.titulo || DADOS.nome;
  ARQUIVO = DADOS.arquivo || (DADOS.nome + " (falantes conferidos)");
  try{
    const guardado = JSON.parse(localStorage.getItem(chaveArquivo()) || "{}");
    if (guardado.titulo) TITULO = guardado.titulo;
    if (guardado.arquivo) ARQUIVO = guardado.arquivo;
  }catch(e){}
  mostrarTitulo();
  video.src = U("/video");

  if (DADOS.tem_rascunho){
    const r = await fetch(U("/rascunho")).then(x => x.json()).catch(() => ({}));
    if (r && r.segmentos && r.segmentos.length === SEG.length &&
        confirm("Encontrei um trabalho em andamento nesta legenda, guardado " +
                "automaticamente.\n\nRetomar de onde você parou?")){
      SEG = r.segmentos;
      DESLOC = Number(r.deslocamento) || 0;
      $("#desloc").value = DESLOC.toFixed(1);
      marcarSujo();
    }
  }
  lerCores();
  lerOrdem();
  refazerFalantes();
  desenhar();
  contar();
}

function refazerFalantes(){
  // Só ACRESCENTA nomes; nunca tira. Se tirasse os que ficaram sem nenhuma
  // fala, trocar dois falantes um pelo outro seria impossível: ao corrigir a
  // última fala de alguém, esse alguém sumiria da lista de opções.
  for (const s of SEG) if (s.f && !FALANTES.includes(s.f)) FALANTES.push(s.f);
  chips();
}

let arrastando = null;

function chips(){
  const quantos = {};
  for (const s of SEG) quantos[s.f] = (quantos[s.f] || 0) + 1;
  $("#chips").innerHTML = "";
  for (const nome of FALANTES){
    const el = document.createElement("span");
    el.className = "chip";
    el.style.color = cor(nome);
    el.style.background = cor(nome) + "1f";
    el.innerHTML = "<b></b> <span></span>";
    el.querySelector("b").textContent = nome;
    el.querySelector("span").textContent = (quantos[nome] || 0) + " falas";
    el.onclick = (e) => menuDoFalante(e, nome);
    el.dataset.dica = "Clique para a cor ou o nome · arraste para mudar de lugar";

    // Arrastar e soltar para reordenar.
    el.draggable = true;
    el.ondragstart = (e) => {
      arrastando = nome;
      el.classList.add("arrastando");
      try{ e.dataTransfer.effectAllowed = "move";
           e.dataTransfer.setData("text/plain", nome); }catch(err){}
    };
    el.ondragend = () => { el.classList.remove("arrastando"); arrastando = null; };
    el.ondragover = (e) => {
      if (!arrastando || arrastando === nome) return;
      e.preventDefault();
      try{ e.dataTransfer.dropEffect = "move"; }catch(err){}
      el.classList.add("alvo");
    };
    el.ondragleave = () => el.classList.remove("alvo");
    el.ondrop = (e) => {
      e.preventDefault();
      el.classList.remove("alvo");
      moverFalante(arrastando, nome);
    };

    $("#chips").appendChild(el);
  }
}

function desenhar(){
  const pedaco = document.createDocumentFragment();
  SEG.forEach((s, i) => pedaco.appendChild(linhaFala(s, i)));
  lista.innerHTML = "";
  lista.appendChild(pedaco);
}

function linhaFala(s, i){
  const el = document.createElement("div");
  el.className = "fala";
  el.dataset.i = i;

  const marca = document.createElement("span");
  marca.className = "marca";
  marca.title = "Somar (ou tirar) esta fala da seleção";
  marca.onclick = (e) => { e.stopPropagation(); alternarMarca(i, e.shiftKey); };

  const hora = document.createElement("div");
  hora.className = "hora";
  hora.textContent = hhmmss(s.t);
  hora.title = "Levar o vídeo até aqui";
  hora.onclick = () => { selecionarSo(i); irPara(i); };

  const corpo = document.createElement("div");
  corpo.className = "corpo";

  const quem = document.createElement("span");
  quem.className = "quem";
  quem.style.color = cor(s.f);
  quem.style.background = cor(s.f) + "1f";
  quem.innerHTML = "<b></b><span class='seta'>▾</span>";
  quem.querySelector("b").textContent = s.f || "sem nome";
  quem.onclick = (e) => abrirMenu(e, i);

  // Um clique no texto faz as DUAS coisas de uma vez: leva o vídeo até a fala
  // e abre o texto para escrever, com o cursor no ponto clicado. A edição é
  // ligada no "mousedown", ANTES de o navegador posicionar o cursor, que é o
  // que permite escrever direto, sem um segundo clique.
  const txt = document.createElement("span");
  txt.className = "txt";
  txt.spellcheck = false;
  txt.textContent = s.x;
  txt.onfocus = () => { escolhida = i; };
  // Uma fala é UMA linha. Se alguma quebra de linha entrar (Enter mal dado,
  // texto colado de outro lugar), ela vira espaço antes de ir para o arquivo:
  // no formato da transcrição, linha sem horário viraria fala perdida.
  txt.oninput = () => {
    SEG[i].x = txt.textContent.replace(/\s*\n+\s*/g, " ");
    ultimaDigitacao = Date.now();
    marcarSujo();
  };
  // Colar traz formatação junto. Aqui só entra texto puro.
  txt.onpaste = (e) => {
    e.preventDefault();
    const cru = (e.clipboardData || window.clipboardData).getData("text");
    document.execCommand("insertText", false, cru.replace(/\s*\n+\s*/g, " "));
  };

  let antes = s.x;
  txt.onkeydown = (e) => {
    e.stopPropagation();
    ultimaDigitacao = Date.now();
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)){
      // Escrevendo: ⌘+Enter parte a fala exatamente onde está o cursor.
      e.preventDefault();
      dividir();
      return;
    }
    if (e.key === "Enter"){
      // Enter CONFIRMA. Sem isto ele quebraria a fala em duas linhas, que é o
      // contrário do que a pessoa quer ao terminar de corrigir uma palavra.
      e.preventDefault();
      txt.blur();
    } else if (e.key === "Escape"){
      // Esc desfaz o que foi digitado nesta fala e sai.
      e.preventDefault();
      SEG[i].x = antes;
      txt.textContent = antes;
      txt.blur();
    }
  };

  function lembrarCursor(){
    const pos = posicaoDoCursor(txt);
    if (pos >= 0) corteLembrado = {i: i, pos: pos};
  }
  txt.onkeyup = lembrarCursor;
  txt.onmouseup = lembrarCursor;

  let abriuAgora = false;
  txt.onmousedown = (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey) return;   // isso é marcação
    if (txt.classList.contains("editando")){ abriuAgora = false; return; }
    abriuAgora = true;
    antes = SEG[i].x;                    // ponto de volta do Esc
    txt.contentEditable = "true";
    txt.classList.add("editando");
    escolhida = i;
    // Rede de segurança: se o navegador não der o foco sozinho, damos nós.
    setTimeout(() => { if (document.activeElement !== txt) txt.focus(); }, 0);
  };
  txt.onclick = (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey) return;   // deixa marcar
    e.stopPropagation();
    if (!abriuAgora) return;          // já estava escrevendo: só mudou o cursor
    abriuAgora = false;
    selecionarSo(i);
    // Com o vídeo PARADO, clicar no texto não mexe nele: você parou ali de
    // propósito (para dividir a fala no instante da troca de voz, por
    // exemplo), e rebobinar jogaria esse trabalho fora. Com o vídeo rodando,
    // ele acompanha, que é o uso do dia a dia. O horário e o resto da linha
    // levam o vídeo sempre.
    if (!video.paused) irPara(i, false);
  };
  txt.onblur = () => {
    txt.contentEditable = "false";
    txt.classList.remove("editando");
    // Deixa na tela exatamente o que será gravado (sem quebras de linha).
    if (txt.textContent !== SEG[i].x) txt.textContent = SEG[i].x;
  };

  corpo.appendChild(quem);
  corpo.appendChild(document.createElement("br"));
  corpo.appendChild(txt);
  el.appendChild(marca);
  el.appendChild(hora);
  el.appendChild(corpo);
  // Clicar em QUALQUER lugar da fala (horario, texto ou o espaco em volta)
  // leva o video ate ela. Duas excecoes: o nome de quem fala, que abre o seu
  // proprio menu, e o texto enquanto esta sendo editado, senao o video pularia
  // a cada clique dentro da palavra.
  el.onclick = (e) => {
    if (e.target.closest && e.target.closest(".quem")) return;
    // Com Command (ou Ctrl) e com Shift, o clique MARCA em vez de levar o
    // vídeo: é o gesto que todo mundo já conhece de lista de arquivos.
    if (e.metaKey || e.ctrlKey){ alternarMarca(i, false); return; }
    if (e.shiftKey){ alternarMarca(i, true); return; }
    selecionarSo(i);
    irPara(i);
  };
  if (marcadas.has(i)) el.classList.add("marcada");
  if (laco && i >= laco.a && i <= laco.b) el.classList.add("emlaco");
  return el;
}

function atualizarLinha(i){
  const velha = lista.querySelector('.fala[data-i="' + i + '"]');
  if (!velha) return;
  const nova = linhaFala(SEG[i], i);
  if (velha.classList.contains("agora")) nova.classList.add("agora");
  if (marcadas.has(i)) nova.classList.add("marcada");
  velha.replaceWith(nova);
}

/* ------------------------------------------------- marcar várias falas */
function alternarMarca(i, intervalo){
  if (intervalo && ultimaMarcada >= 0 && ultimaMarcada !== i){
    const de = Math.min(i, ultimaMarcada), ate = Math.max(i, ultimaMarcada);
    for (let j = de; j <= ate; j++) marcadas.add(j);
  } else if (marcadas.has(i)){
    marcadas.delete(i);
  } else {
    marcadas.add(i);
  }
  ultimaMarcada = i;
  pintarMarcas();
}

function selecionarSo(i){
  // Clique simples: a seleção passa a ser ESTA fala, e só ela.
  if (marcadas.size === 1 && marcadas.has(i)) return;
  marcadas.clear();
  marcadas.add(i);
  ultimaMarcada = i;
  pintarMarcas();
}

function limparMarcas(){
  marcadas.clear();
  ultimaMarcada = -1;
  pintarMarcas();
}

function pintarMarcas(){
  lista.querySelectorAll(".fala").forEach(el => {
    el.classList.toggle("marcada", marcadas.has(Number(el.dataset.i)));
  });
  $("#quantas").textContent = marcadas.size;
  // A barra só aparece quando há MAIS DE UMA: com uma só, ela seria um aviso
  // permanente na tela dizendo o óbvio.
  $("#selecao").classList.toggle("mostra", marcadas.size > 1);
}

// Soltar no espaço vazio da caixa manda a pessoa para o fim da lista.
$("#chips").addEventListener("dragover", (e) => { if (arrastando) e.preventDefault(); });
$("#chips").addEventListener("drop", (e) => {
  if (!arrastando) return;
  e.preventDefault();
  if (e.target === $("#chips")) moverFalante(arrastando, null);
});

$("#btLimparMarcas").onclick = limparMarcas;
$("#btTrocarMarcadas").onclick = (e) => {
  if (!marcadas.size) return;
  modoTroca = "marcadas";
  abrirMenu(e, Math.min(...marcadas));
};

function contar(){
  $("#conta").textContent = SEG.length + " falas · " + FALANTES.length + " falantes";
}

/* ------------------------------------------------------- trocar quem fala */
function abrirMenu(evento, i){
  evento.stopPropagation();
  // Abrir o menu de uma fala fora da seleção seleciona ela: assim o que você
  // vê marcado é sempre o que a troca vai atingir.
  if (!marcadas.has(i)) selecionarSo(i);
  // O menu sempre abre no modo normal (a seleção). "Desta em diante" é uma
  // escolha daquela vez: se ela ficasse grudada, a próxima troca pegaria um
  // bloco inteiro sem você ter pedido.
  if (!abrirMenu.mantendoModo) modoTroca = "selecao";
  abrirMenu.mantendoModo = false;
  menu.innerHTML = "";

  const modo = document.createElement("div");
  modo.className = "modo";
  const modos = [
    ["selecao", marcadas.size > 1 ? "Nas " + marcadas.size + " selecionadas"
                                  : "Só esta fala"],
    ["diante", "Desta em diante"],
  ];
  modos.forEach(([chave, rotulo]) => {
    const b = document.createElement("button");
    b.textContent = rotulo;
    if (modoTroca === chave) b.classList.add("ligado");
    b.onclick = (e) => {
      e.stopPropagation();
      modoTroca = chave;
      abrirMenu.mantendoModo = true;    // redesenha o menu sem zerar a escolha
      abrirMenu(evento, i);
    };
    modo.appendChild(b);
  });
  menu.appendChild(modo);

  // Em duas colunas quando a lista cresce, senão o menu passa da tela.
  const nomes = document.createElement("div");
  nomes.className = "nomes" + (FALANTES.length > 6 ? " duas" : "");
  menu.classList.toggle("largo", FALANTES.length > 6);
  for (const nome of FALANTES){
    const b = document.createElement("span");
    b.className = "quem";
    b.style.color = cor(nome);
    b.style.background = cor(nome) + "1f";
    b.textContent = nome + (SEG[i].f === nome ? "  ✓" : "");
    b.title = nome;
    b.onclick = (e) => { e.stopPropagation(); trocar(i, nome); fecharMenu(); };
    nomes.appendChild(b);
  }
  menu.appendChild(nomes);

  const novo = document.createElement("button");
  novo.className = "novo";
  novo.textContent = "+ Novo falante…";
  novo.onclick = (e) => {
    e.stopPropagation();
    const nome = (prompt("Nome de quem está falando:") || "").trim();
    if (nome){ if (!FALANTES.includes(nome)) FALANTES.push(nome); trocar(i, nome); }
    fecharMenu();
  };
  menu.appendChild(novo);

  const r = evento.target.getBoundingClientRect();
  menu.style.display = "block";
  const alt = menu.offsetHeight;
  menu.style.left = Math.min(r.left, window.innerWidth - menu.offsetWidth - 14) + "px";
  menu.style.top = (r.bottom + alt + 10 > window.innerHeight
                    ? Math.max(8, r.top - alt - 6) : r.bottom + 6) + "px";
}
function fecharMenu(){ menu.style.display = "none"; }
document.addEventListener("click", fecharMenu);

function trocar(i, nome){
  guardar();
  const velho = SEG[i].f;
  if (modoTroca === "diante"){
    let j = i;
    while (j < SEG.length && SEG[j].f === velho){ SEG[j].f = nome; atualizarLinha(j); j++; }
    recado("Trocado em " + (j - i) + " fala(s), até mudar de falante.");
  } else {
    // Modo normal: vale para a SELEÇÃO (que, no clique simples, é uma fala só).
    const quais = marcadas.size ? [...marcadas].sort((a, b) => a - b) : [i];
    quais.forEach(j => { SEG[j].f = nome; atualizarLinha(j); });
    if (quais.length > 1) recado("Trocado em " + quais.length + " falas.");
  }
  // Trabalho feito, seleção desfeita: a próxima correção começa limpa.
  limparMarcas();
  refazerFalantes();
  contar();
  marcarSujo();
}

/* ------------------------------------------- o menu de cor de cada pessoa */
function menuDoFalante(evento, nome){
  evento.stopPropagation();
  menu.innerHTML = "";
  menu.classList.remove("largo");

  const titulo = document.createElement("div");
  titulo.className = "tituloMenu";
  titulo.textContent = nome;
  menu.appendChild(titulo);

  const grade = document.createElement("div");
  grade.className = "cores";
  PALETA.forEach(p => {
    const b = document.createElement("span");
    b.className = "amostra" + (cor(nome) === p.cor ? " atual" : "");
    b.style.background = p.cor;
    b.title = p.nome;
    b.onclick = (e) => {
      e.stopPropagation();
      CORMAP[nome] = p.cor;
      guardarCores();
      pintarDeNovo();
      fecharMenu();
      recado(nome + ": " + p.nome.toLowerCase() + ".");
    };
    grade.appendChild(b);
  });
  menu.appendChild(grade);

  const renomeia = document.createElement("button");
  renomeia.className = "novo";
  renomeia.textContent = "Renomear em toda a legenda…";
  renomeia.onclick = (e) => { e.stopPropagation(); fecharMenu(); renomear(nome); };
  menu.appendChild(renomeia);

  const r = evento.currentTarget.getBoundingClientRect();
  menu.style.display = "block";
  const alt = menu.offsetHeight;
  menu.style.left = Math.min(r.left, window.innerWidth - menu.offsetWidth - 14) + "px";
  menu.style.top = (r.bottom + alt + 10 > window.innerHeight
                    ? Math.max(8, r.top - alt - 6) : r.bottom + 6) + "px";
}

function renomear(velho){
  const nome = (prompt("Novo nome para “" + velho + "” em toda a legenda:", velho) || "").trim();
  if (!nome || nome === velho) return;
  guardar();
  let quantos = 0;
  SEG.forEach((s, i) => { if (s.f === velho){ s.f = nome; quantos++; } });
  // A cor é da PESSOA, não do nome: renomear não pode trocar a cor dela.
  if (CORMAP[velho] && !CORMAP[nome]) CORMAP[nome] = CORMAP[velho];
  guardarCores();
  const pos = FALANTES.indexOf(velho);
  if (FALANTES.includes(nome)) FALANTES.splice(pos, 1); else FALANTES[pos] = nome;
  guardarOrdem();      // o lugar dele na lista é o mesmo, com o nome novo
  desenhar(); refazerFalantes(); contar(); marcarSujo();
  recado("Renomeado em " + quantos + " fala(s).");
}

/* -------------------------------------------------------------- repetição */
/* Ouvir o mesmo trecho cinco, dez vezes é o jeito de entender uma fala
   atravessada. O laço repete UMA fala (a escolhida) ou o TRECHO INTEIRO das
   falas marcadas, do começo da primeira ao fim da última. */
let laco = null;          // {ini, fim, a, b} em tempo de legenda, sem o ajuste

function fimDe(i){
  if (i + 1 < SEG.length) return SEG[i + 1].t;
  const dur = video.duration;
  return (dur && isFinite(dur)) ? dur - DESLOC : SEG[i].t + 12;
}

function pintarLaco(){
  lista.querySelectorAll(".fala").forEach(el => {
    const i = Number(el.dataset.i);
    el.classList.toggle("emlaco", !!laco && i >= laco.a && i <= laco.b);
  });
  const ligado = !!laco;
  $("#btLaco").classList.toggle("ligado", ligado);
  $("#btLaco").textContent = ligado ? "↻ Repetindo" : "↻ Repetir";
}

function ligarLaco(soMarcadas){
  // Com falas marcadas, repete o trecho delas — mas só quando a fala em que
  // você está É uma das marcadas. Se você clicou em outra, o que você quer
  // repetir é essa outra, e não o bloco marcado lá atrás.
  const i = escolhida >= 0 ? escolhida : atual;
  let quais;
  if (marcadas.size > 1 && (soMarcadas === true || marcadas.has(i))){
    quais = [...marcadas].sort((a, b) => a - b);
  } else {
    if (i < 0){ recado("Clique numa fala antes, para eu saber o que repetir."); return; }
    quais = [i];
  }
  const a = quais[0], b = quais[quais.length - 1];
  laco = {ini: SEG[a].t, fim: fimDe(b), a: a, b: b};
  pintarLaco();
  video.currentTime = Math.max(0, laco.ini + DESLOC);
  video.play().catch(() => {});
  recado(b > a ? "Repetindo " + (b - a + 1) + " falas, sem parar."
               : "Repetindo esta fala, sem parar.");
}

function desligarLaco(){
  laco = null;
  pintarLaco();
}

function alternarLaco(){ laco ? desligarLaco() : ligarLaco(); }
$("#btLaco").onclick = alternarLaco;
// Este botão é explícito: repete o bloco marcado, esteja você onde estiver.
$("#btLacoMarcadas").onclick = () => ligarLaco(true);

/* --------------------------------------------------------------- desfazer */
/* Toda mudança de ESTRUTURA (dividir, juntar, trocar falante, renomear) guarda
   antes uma cópia da legenda inteira. São poucos milhares de linhas de texto:
   custa quase nada e devolve a tranquilidade de experimentar. A edição de
   texto não entra aqui porque, dentro do campo, o ⌘Z do próprio navegador já
   faz o serviço. */
const historico = [];
const LIMITE_HISTORICO = 40;

function guardar(){
  historico.push(JSON.stringify(SEG));
  if (historico.length > LIMITE_HISTORICO) historico.shift();
  $("#btDesfazer").disabled = false;
}

function desfazer(){
  if (!historico.length){ recado("Não há nada para desfazer."); return; }
  const antes = lista.scrollTop;
  rolagemManual = Date.now();
  SEG = JSON.parse(historico.pop());
  $("#btDesfazer").disabled = historico.length === 0;
  desligarLaco();
  marcadas.clear();
  ultimaMarcada = -1;
  atual = -1;
  desenhar();
  lista.scrollTop = antes;
  refazerFalantes();
  contar();
  marcarSujo();
  recado("Desfeito.");
}

$("#btDesfazer").onclick = desfazer;

/* ----------------------------------------------------------------- juntar */
/* O contrário de dividir: duas (ou mais) falas seguidas viram uma só. Serve
   para desfazer uma divisão antiga e para consertar transcrição que picotou
   demais a mesma pessoa. */
function juntar(){
  const quais = [...marcadas].sort((a, b) => a - b);
  if (quais.length < 2){
    recado("Selecione duas falas seguidas (⌘+clique) para juntar.");
    return;
  }
  for (let k = 1; k < quais.length; k++){
    if (quais[k] !== quais[k - 1] + 1){
      recado("Só dá para juntar falas que estão uma atrás da outra.");
      return;
    }
  }
  guardar();
  const primeira = quais[0];
  const texto = quais.map(j => SEG[j].x).join(" ").replace(/\s+/g, " ").trim();
  const antes = lista.scrollTop;
  rolagemManual = Date.now();
  SEG[primeira].x = texto;
  SEG.splice(primeira + 1, quais.length - 1);

  desligarLaco();
  marcadas.clear();
  ultimaMarcada = -1;
  atual = -1;
  desenhar();
  lista.scrollTop = antes;
  refazerFalantes();
  contar();
  marcarSujo();
  selecionarSo(primeira);
  recado(quais.length + " falas viraram uma só.");
}

$("#btJuntar").onclick = juntar;

/* ---------------------------------------------------------------- dividir */
/* Quando a transcrição junta duas pessoas numa fala só, é preciso partir a
   fala em duas: o texto no ponto certo, e o horário no momento em que a
   segunda pessoa começa a falar. Daí é só dizer quem fala em cada parte. */

function posicaoDoCursor(txt){
  // Quantos caracteres existem antes do cursor, dentro deste texto.
  const s = window.getSelection();
  if (!s || !s.rangeCount || !txt.contains(s.anchorNode)) return -1;
  const r = s.getRangeAt(0).cloneRange();
  const todo = document.createRange();
  todo.selectNodeContents(txt);
  todo.setEnd(r.startContainer, r.startOffset);
  return todo.toString().length;
}

function cortePorEspaco(texto){
  // Sem cursor, corta no espaço mais perto do meio: partir palavra no meio
  // nunca é o que a pessoa queria.
  const meio = Math.floor(texto.length / 2);
  let melhor = -1;
  for (let i = 0; i < texto.length; i++){
    if (texto[i] !== " ") continue;
    if (melhor < 0 || Math.abs(i - meio) < Math.abs(melhor - meio)) melhor = i;
  }
  return melhor;
}

function dividir(){
  const i = marcadas.size === 1 ? [...marcadas][0]
                                : (escolhida >= 0 ? escolhida : atual);
  if (i < 0 || !SEG[i]){ recado("Clique na fala que você quer dividir."); return; }

  const el = lista.querySelector('.fala[data-i="' + i + '"]');
  const txt = el ? el.querySelector(".txt") : null;
  const texto = SEG[i].x;

  // Onde cortar: o cursor de agora, se ele ainda estiver no texto; senão o
  // último lugar em que ele esteve NESTA fala; e só em último caso o meio.
  let pos = txt ? posicaoDoCursor(txt) : -1;
  if (pos < 0 && corteLembrado.i === i) pos = corteLembrado.pos;
  if (pos <= 0 || pos >= texto.length) pos = cortePorEspaco(texto);
  const parte1 = texto.slice(0, pos).trim();
  const parte2 = texto.slice(pos).trim();
  if (!parte1 || !parte2){
    recado("Não dá para dividir aqui: um dos lados ficaria vazio.");
    return;
  }

  // O horário da segunda parte: o ponto em que o vídeo está, quando ele está
  // DENTRO desta fala (que é o caso de quem pausou na hora da troca de voz).
  // Fora disso, cai no meio do intervalo.
  const fim = fimDe(i);
  const agora = video.currentTime - DESLOC;
  let t2;
  if (agora > SEG[i].t + 0.4 && agora < fim - 0.4){
    t2 = agora;                       // onde o vídeo está: o mais confiável
  } else {
    // Sem isso, estima pelo tamanho do texto: metade das palavras, metade do
    // tempo. É um palpite, mas muito melhor que cortar no meio do intervalo.
    t2 = SEG[i].t + (fim - SEG[i].t) * (pos / texto.length);
  }
  t2 = Math.round(t2);
  if (t2 <= SEG[i].t) t2 = SEG[i].t + 1;
  if (t2 >= fim && fim - 1 > SEG[i].t) t2 = Math.round(fim) - 1;

  guardar();
  SEG[i].x = parte1;
  SEG.splice(i + 1, 0, {t: t2, f: SEG[i].f, x: parte2});

  // Os índices mudaram daqui para baixo, então a lista é redesenhada - mas a
  // rolagem é devolvida EXATAMENTE onde estava. Antes, o redesenho jogava a
  // lista para o topo e a tela "pulava" no meio da correção.
  const rolagem = lista.scrollTop;
  // Segura o "Acompanhar" por alguns segundos: com o vídeo rodando, ele
  // arrastaria a lista para a fala que está tocando bem na hora em que você
  // está olhando para o corte que acabou de fazer.
  rolagemManual = Date.now();
  desligarLaco();
  marcadas.clear();
  ultimaMarcada = -1;
  atual = -1;
  corteLembrado = {i: -1, pos: -1};
  desenhar();
  lista.scrollTop = rolagem;
  contar();
  marcarSujo();
  selecionarSo(i + 1);
  recado("Fala dividida em " + formatarCurto(SEG[i].t) + " e " +
         formatarCurto(t2) + ". Agora diga quem fala em cada parte.");
}

function formatarCurto(t){ return hhmmss(t); }

// O botão não rouba o foco do texto: sem isto, o clique apagaria a seleção
// antes de o programa conseguir ler onde estava o cursor.
$("#btDividir").onmousedown = (e) => e.preventDefault();
$("#btDividir").onclick = dividir;

/* ------------------------------------------------------------ video e foco */
function escolher(i){
  escolhida = i;
  const el = lista.querySelector('.fala[data-i="' + i + '"]');
  if (el) el.scrollIntoView({block:"center", behavior:"smooth"});
}
function irPara(i, tocar){
  escolhida = i;
  // Clicou fora do trecho que está repetindo: sem falas marcadas, o laço
  // simplesmente muda para a fala nova (é o que a pessoa quer ao pular de uma
  // fala difícil para outra); com falas marcadas, ele desliga, porque senão o
  // vídeo seria puxado de volta sem explicação.
  // Clicou numa fala fora do trecho que está repetindo: a repetição vai junto,
  // porque clicar numa fala agora é dizer "é esta aqui que eu quero ouvir".
  if (laco && (i < laco.a || i > laco.b)){
    laco = {ini: SEG[i].t, fim: fimDe(i), a: i, b: i};
    pintarLaco();
  }
  video.currentTime = Math.max(0, SEG[i].t + DESLOC);
  // Clicar no horário ou no corpo da fala já começa a tocar; clicar no texto
  // não, porque ali a pessoa quer escrever, e vídeo tocando atrapalha.
  if (tocar !== false && video.paused) video.play().catch(() => {});
}

video.addEventListener("timeupdate", () => {
  const agora = video.currentTime - DESLOC;
  if (laco && agora >= laco.fim){
    video.currentTime = Math.max(0, laco.ini + DESLOC);
    if (video.paused) video.play().catch(() => {});
    return;
  }
  let lo = 0, hi = SEG.length - 1, achado = -1;
  while (lo <= hi){
    const meio = (lo + hi) >> 1;
    if (SEG[meio].t <= agora + 0.01){ achado = meio; lo = meio + 1; } else hi = meio - 1;
  }
  if (achado === atual) return;
  const antes = lista.querySelector(".fala.agora");
  if (antes) antes.classList.remove("agora");
  atual = achado;
  if (atual < 0) return;
  const el = lista.querySelector('.fala[data-i="' + atual + '"]');
  if (!el) return;
  el.classList.add("agora");
  if ($("#btSeguir").classList.contains("ligado") &&
      Date.now() - rolagemManual > 5000 &&
      Date.now() - ultimaDigitacao > 4000){
    el.scrollIntoView({block:"center", behavior:"smooth"});
  }
});
lista.addEventListener("wheel", () => { rolagemManual = Date.now(); }, {passive:true});

video.addEventListener("play", () => { $("#btTocar").textContent = "Pausar"; });
video.addEventListener("pause", () => { $("#btTocar").textContent = "Tocar"; });
video.addEventListener("error", () => {
  recado("O navegador não conseguiu tocar este vídeo. Converta para MP4 e tente de novo.");
});

$("#btTocar").onclick = () => video.paused ? video.play() : video.pause();
$("#btVoltar").onclick = () => { video.currentTime = Math.max(0, video.currentTime - 5); };
$("#btAvancar").onclick = () => { video.currentTime += 5; };
$("#btSeguir").onclick = () => $("#btSeguir").classList.toggle("ligado");
document.querySelectorAll(".vel").forEach(b => b.onclick = () => {
  video.playbackRate = Number(b.dataset.v);
  document.querySelectorAll(".vel").forEach(o => o.classList.remove("ligado"));
  b.classList.add("ligado");
});

/* --------------------------------------------------------------- sincronia */
function porDeslocamento(valor){
  DESLOC = Math.round(valor * 10) / 10;
  $("#desloc").value = DESLOC.toFixed(1);
  lista.querySelectorAll(".fala").forEach(el => {
    el.querySelector(".hora").textContent = hhmmss(SEG[Number(el.dataset.i)].t);
  });
  atual = -1;
  marcarSujo();
}
$("#btMenos").onclick = () => porDeslocamento(DESLOC - 0.5);
$("#btMais").onclick = () => porDeslocamento(DESLOC + 0.5);
$("#desloc").onchange = () => porDeslocamento(Number($("#desloc").value) || 0);
$("#btAlinhar").onclick = () => {
  if (escolhida < 0){ recado("Clique primeiro na fala que começa neste ponto."); return; }
  porDeslocamento(video.currentTime - SEG[escolhida].t);
  recado("Legenda deslocada em " + DESLOC.toFixed(1) + "s.");
};

/* ------------------------------------------------------------------ busca */
let ultimaBusca = -1;
$("#busca").addEventListener("keydown", (e) => {
  if (e.key !== "Enter") return;
  const alvo = $("#busca").value.trim().toLowerCase();
  if (!alvo) return;
  const achados = [];
  SEG.forEach((s, i) => { if (s.x.toLowerCase().includes(alvo)) achados.push(i); });
  if (!achados.length){ $("#achados").textContent = "nada encontrado"; return; }
  const proximo = achados.find(i => i > ultimaBusca);
  const i = proximo === undefined ? achados[0] : proximo;
  ultimaBusca = i;
  $("#achados").textContent = (achados.indexOf(i) + 1) + " de " + achados.length;
  lista.querySelectorAll(".achado").forEach(el => el.classList.remove("achado"));
  const el = lista.querySelector('.fala[data-i="' + i + '"]');
  if (el){ el.classList.add("achado"); el.scrollIntoView({block:"center", behavior:"smooth"}); }
  escolhida = i;
});

/* ----------------------------------------------------------------- atalhos */
function atalho(e){
  const digitando = document.activeElement &&
    (document.activeElement.isContentEditable || document.activeElement.tagName === "INPUT");
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s"){ e.preventDefault(); salvar(); return; }
  // ⌘Z fora do texto desfaz a última mudança de estrutura. DENTRO do texto,
  // quem trata é o navegador, desfazendo o que você digitou.
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z" && !digitando){
    e.preventDefault(); desfazer(); return;
  }
  if (e.key === "Escape" && marcadas.size){ limparMarcas(); return; }
  if (digitando) return;
  if (e.key === " "){ e.preventDefault(); video.paused ? video.play() : video.pause(); }
  else if (e.key.toLowerCase() === "j"){ video.currentTime = Math.max(0, video.currentTime - 5); }
  else if (e.key.toLowerCase() === "l"){ video.currentTime += 5; }
  else if (e.key.toLowerCase() === "r"){ alternarLaco(); }
  else if (e.key === "ArrowDown"){ e.preventDefault(); escolher(Math.min(SEG.length - 1, (escolhida < 0 ? atual : escolhida) + 1)); }
  else if (e.key === "ArrowUp"){ e.preventDefault(); escolher(Math.max(0, (escolhida < 0 ? atual : escolhida) - 1)); }
  else if (e.key === "Enter" && escolhida >= 0){ e.preventDefault(); irPara(escolhida); }
}
document.addEventListener("keydown", atalho);

/* -------------------------------------------------- as dicas dos botões */
/* Cada botão diz o que faz e qual é o atalho. A lista fica num lugar só para
   não haver texto de ajuda espalhado e desencontrado pela tela. */
const DICAS = {
  btSalvar:        ["Grava o .docx e o .txt agora", "⌘S"],
  btPainel:        ["Esconde a coluna do vídeo e usa a tela toda", ""],
  btVoltarTopo:    ["Traz o vídeo de volta para esta janela", ""],
  btSeguir:        ["A lista acompanha o vídeo sozinha", ""],
  btLaco:          ["Repete sem parar a fala (ou o trecho) selecionada", "R"],
  btDividir:       ["Parte a fala em duas no ponto do cursor", "⌘↵"],
  btVideoGrande:   ["O vídeo ocupa toda a direita, sem os controles", ""],
  btDesfazer:      ["Desfaz a última divisão, junção ou troca de falante", "⌘Z"],
  busca:           ["Procura no texto das falas", "Enter pula para a próxima"],
  btTrocarMarcadas:["Troca quem fala em todas as selecionadas", ""],
  btJuntar:        ["Junta as falas selecionadas numa só", ""],
  btLacoMarcadas:  ["Repete o trecho das falas selecionadas", "R"],
  btLimparMarcas:  ["Limpa a seleção", "Esc"],
  btTocar:         ["Toca e pausa o vídeo", "espaço"],
  btVoltar:        ["Volta 5 segundos", "J"],
  btAvancar:       ["Avança 5 segundos", "L"],
  btMenos:         ["Atrasa a legenda meio segundo", ""],
  btMais:          ["Adianta a legenda meio segundo", ""],
  btAlinhar:       ["Faz a fala selecionada começar no ponto atual do vídeo", ""],
  btOutraJanela:   ["Manda o vídeo para uma janela à parte, para o outro monitor", ""],
  btVoltarVideo:   ["Traz o vídeo de volta para esta janela", ""],
  btMostrar:       ["Abre a pasta no Finder, com o arquivo selecionado", ""],
  btFecharSalvo:   ["Esconde este aviso", ""],
};

function porDica(el, texto, tecla){
  if (!el) return;
  el.dataset.dica = texto + (tecla ? "   ·   " + tecla : "");
  el.removeAttribute("title");     // senão apareceriam duas dicas sobrepostas
}

Object.keys(DICAS).forEach((id) => porDica($("#" + id), DICAS[id][0], DICAS[id][1]));
porDica($("#divisor"), "Arraste para mudar a largura", "dois cliques voltam ao normal");
document.querySelectorAll(".vel").forEach(b =>
  porDica(b, "Velocidade do vídeo: " + b.textContent));

/* ------------------------------------------------- largura das duas colunas */
/* A divisória é arrastável e a largura escolhida fica guardada neste
   navegador, para não ter que ajustar tudo de novo na próxima entrevista. */
const palco = $("#palco"), divisor = $("#divisor");
function porLargura(px){
  const limite = Math.max(300, Math.min(px, window.innerWidth - 360));
  palco.style.flex = "0 0 " + limite + "px";
  try{ localStorage.setItem("larguraPalco", limite); }catch(e){}
}
try{
  const guardada = Number(localStorage.getItem("larguraPalco"));
  if (guardada > 0) porLargura(guardada);
}catch(e){}

divisor.addEventListener("mousedown", (e) => {
  e.preventDefault();
  divisor.classList.add("arrastando");
  document.body.classList.add("arrastando");
  const mover = (ev) => porLargura(window.innerWidth - ev.clientX);
  const soltar = () => {
    divisor.classList.remove("arrastando");
    document.body.classList.remove("arrastando");
    document.removeEventListener("mousemove", mover);
    document.removeEventListener("mouseup", soltar);
  };
  document.addEventListener("mousemove", mover);
  document.addEventListener("mouseup", soltar);
});
/* Esconder a coluna da direita. Serve para dois momentos: quando o vídeo foi
   para a outra tela (e a coluna aqui fica sobrando) e quando a pessoa só quer
   ler a legenda com a janela inteira. */
let painelAberto = true;
function painel(mostrar){
  painelAberto = mostrar;
  palco.style.display = mostrar ? "" : "none";
  divisor.style.display = mostrar ? "" : "none";
  const b = $("#btPainel");
  b.textContent = mostrar ? "Ocultar painel ⟩" : "⟨ Mostrar painel";
  b.classList.toggle("ligado", !mostrar);
  b.title = mostrar
    ? "Esconder a coluna da direita e usar a tela toda para a legenda"
    : "Trazer de volta a coluna do vídeo, da sincronia e dos falantes";
}
$("#btPainel").onclick = () => painel(!painelAberto);

/* Vídeo grande: o painel da direita passa a ser só o vídeo, esticado. Quem
   trabalha numa tela só resolve aqui, sem precisar da janela separada. */
$("#btVideoGrande").onclick = () => {
  if (janelaVideo && !janelaVideo.closed){
    recado("O vídeo está na outra janela. Traga ele de volta primeiro.");
    return;
  }
  if (!painelAberto) painel(true);
  const grande = palco.classList.toggle("sovideo");
  $("#btVideoGrande").classList.toggle("ligado", grande);
  $("#btVideoGrande").textContent = grande ? "⤢ Vídeo normal" : "⤢ Vídeo grande";
};

divisor.addEventListener("dblclick", () => {
  // Duplo clique volta ao tamanho de fábrica.
  try{ localStorage.removeItem("larguraPalco"); }catch(e){}
  palco.style.flex = "";
});

/* --------------------------------------------- o vídeo em uma janela à parte */
/* Para quem usa dois monitores: o vídeo SAI desta página e vai para uma janela
   nova, que você arrasta para a outra tela. Não é uma segunda cópia do vídeo:
   é o mesmo elemento, mudado de lugar, e por isso ele continua tocando do
   ponto em que estava, e tudo (fala acesa, clique na fala, ajuste) continua
   valendo. */
let janelaVideo = null;
const ondeMora = video.parentNode;

function abrirEmOutraJanela(){
  if (janelaVideo && !janelaVideo.closed){ janelaVideo.focus(); return; }
  janelaVideo = window.open("", "videoTranscriptStudio",
                            "width=980,height=620,menubar=no,toolbar=no");
  if (!janelaVideo){
    recado("O navegador bloqueou a janela nova. Libere as janelas pop-up para 127.0.0.1.");
    return;
  }
  const d = janelaVideo.document;
  // O pedacinho de código lá dentro é a rede de segurança que não depende
  // desta página: a janela do vídeo confere sozinha, de segundo em segundo,
  // se quem a abriu
  // ainda existe. Se a aba da legenda for fechada, ela se fecha junto. Sem
  // isso, o navegador deixa um vídeo tocando sozinho numa janela órfã.
  d.write('<!DOCTYPE html><html lang="pt-br"><head><meta charset="utf-8">' +
          '<title>Vídeo — ' + (DADOS.titulo || "") + '</title><style>' +
          'html,body{margin:0;height:100%;background:#000;overflow:hidden}' +
          'video{width:100%;height:100%;object-fit:contain;background:#000}' +
          '</style></head><body><scr' + 'ipt>' +
          'setInterval(function(){try{if(!window.opener||window.opener.closed)' +
          'window.close();}catch(e){window.close();}},1000);' +
          '</scr' + 'ipt></body></html>');
  d.close();

  // Alguns navegadores param o vídeo ao mudá-lo de documento. Guardamos o
  // ponto e o estado antes, e devolvemos depois, para a pessoa não perder o
  // lugar em que estava ouvindo.
  const onde = video.currentTime, tocando = !video.paused;
  try{
    d.body.appendChild(d.adoptNode(video));
  }catch(err){
    recado("Este navegador não deixou mover o vídeo de janela.");
    janelaVideo.close(); janelaVideo = null; return;
  }
  retomar(onde, tocando);
  d.addEventListener("keydown", atalho);
  janelaVideo.addEventListener("beforeunload", trazerDeVolta);

  $("#fora").style.display = "block";
  $("#btOutraJanela").textContent = "O vídeo está em outra janela";
  $("#btOutraJanela").disabled = true;
  // Com o vídeo na outra tela, a coluna da direita só ocupa espaço: ela sai
  // sozinha, e a legenda fica com a janela inteira. O botão lá em cima a
  // traz de volta quando você precisar da sincronia ou dos falantes.
  painel(false);
  // Com o painel escondido, o botão de trazer o vídeo de volta ficaria
  // inalcançável: por isso ele aparece também na barra de cima.
  $("#btVoltarTopo").style.display = "";
  recado("Arraste a janela do vídeo para o outro monitor.");
}

function retomar(onde, tocando){
  try{
    if (Math.abs(video.currentTime - onde) > 0.3) video.currentTime = onde;
    if (tocando && video.paused) video.play().catch(() => {});
  }catch(e){}
}

function trazerDeVolta(){
  if (!janelaVideo) return;
  const onde = video.currentTime, tocando = !video.paused;
  try{ ondeMora.insertBefore(document.adoptNode(video), ondeMora.firstChild); }catch(e){}
  retomar(onde, tocando);
  try{ if (!janelaVideo.closed) janelaVideo.close(); }catch(e){}
  janelaVideo = null;
  $("#fora").style.display = "none";
  $("#btOutraJanela").textContent = "Abrir o vídeo em outra janela";
  $("#btOutraJanela").disabled = false;
  $("#btVoltarTopo").style.display = "none";
  painel(true);      // o vídeo voltou: a coluna dele volta junto
}

$("#btOutraJanela").onclick = abrirEmOutraJanela;
$("#btVoltarVideo").onclick = trazerDeVolta;
$("#btVoltarTopo").onclick = trazerDeVolta;
// Se esta página for fechada, a janela do vídeo não pode ficar órfã na tela.
// São três eventos porque nenhum é garantido sozinho: o "unload" foi ficando
// menos confiável, e no Safari quem costuma chegar é o "pagehide".
function fecharVideo(){
  try{ if (janelaVideo && !janelaVideo.closed) janelaVideo.close(); }catch(e){}
}
window.addEventListener("pagehide", fecharVideo);
window.addEventListener("unload", fecharVideo);
// De propósito NÃO usamos "beforeunload" aqui: ele dispara quando o navegador
// só PERGUNTA se pode sair. Se a pessoa desistir de fechar, o vídeo já teria
// sumido da outra tela sem motivo.

/* ------------------------------------------- o programa ainda está aberto? */
/* Quem serve o vídeo é o Transcript Studio / Media Studio. Se ele for
   fechado, esta tela deixa de salvar e o vídeo na outra janela viraria um
   fantasma. Então batemos na porta do programa de cinco em cinco segundos. */
let falhas = 0, sessaoMorta = false;
setInterval(async () => {
  if (sessaoMorta) return;
  try{
    const r = await fetch(U("/vivo"), {cache: "no-store"});
    if (!r.ok) throw new Error("sem resposta");
    falhas = 0;
  }catch(e){
    // Duas falhas seguidas, para um soluço de rede não derrubar a sessão.
    if (++falhas < 2) return;
    sessaoMorta = true;
    fecharVideo();
    $("#btSalvar").disabled = true;
    $("#estado").textContent = "o programa foi fechado — esta tela não salva mais";
    $("#estado").style.color = "var(--erro)";
    recado("O programa foi fechado. Reabra a aba Sincronizar para continuar.");
  }
}, 5000);

/* ------------------------------------------------------------- gravar tudo */
async function salvar(){
  $("#btSalvar").disabled = true;
  $("#estado").textContent = "gravando…";
  $("#estado").style.color = "var(--suave)";
  try{
    const r = await fetch(U("/salvar"), {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({segmentos:SEG, deslocamento:DESLOC, titulo:TITULO,
                            arquivo:ARQUIVO, gravar_ajuste:true,
                            docx:true, txt:true})
    }).then(x => x.json());
    if (!r.ok) throw new Error(r.erro || "não deu certo");
    sujo = false;
    $("#estado").textContent = "salvo";
    $("#estado").style.color = "var(--ok)";

    // Mostra, e deixa na tela, O QUE foi gravado e ONDE.
    const caminhos = r.caminhos || [];
    const nomes = caminhos.map(c => c.replace(/^.*[\\/]/, ""));
    const pasta = caminhos.length
      ? caminhos[0].slice(0, caminhos[0].length - nomes[0].length - 1)
      : DADOS.saida;
    $("#salvoNomes").textContent = nomes.join("   •   ") || "(nada a gravar)";
    $("#salvoPasta").textContent = "na pasta " + pasta;
    $("#salvo").classList.add("mostra");
    recado("Gravado: " + (nomes[0] || ""));
  }catch(err){
    $("#estado").textContent = "erro ao salvar";
    $("#estado").style.color = "var(--erro)";
    recado("Não consegui salvar: " + err.message);
  }
  $("#btSalvar").disabled = false;
}
$("#btSalvar").onclick = salvar;
$("#btFecharSalvo").onclick = () => $("#salvo").classList.remove("mostra");
// Quem abre a pasta é o programa, não a página: o navegador não mexe no Finder.
$("#btMostrar").onclick = async () => {
  try{
    const r = await fetch(U("/mostrar"), {method: "POST",
      headers: {"Content-Type": "application/json"}, body: "{}"}).then(x => x.json());
    if (!r.ok) throw new Error(r.erro || "");
  }catch(e){ recado("Não consegui abrir a pasta daqui."); }
};

/* ------------------------------------------------- salvamento automático */
/* A cada 20 segundos, se houver mudança, o trabalho vai para os ARQUIVOS de
   verdade (.docx e .txt), e não só para o rascunho. Assim, um tombo do
   navegador, um fechar sem querer ou um dia inteiro de correção sem clicar em
   salvar não custam nada. O rascunho continua sendo gravado junto, porque é
   ele que guarda a seleção e o ajuste fino para a tela voltar como estava. */
async function salvarSozinho(){
  if (!sujo || sessaoMorta) return;
  try{
    fetch(U("/rascunho"), {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({segmentos:SEG, deslocamento:DESLOC})
    }).catch(() => {});

    const r = await fetch(U("/salvar"), {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({segmentos:SEG, deslocamento:DESLOC, titulo:TITULO,
                            arquivo:ARQUIVO, gravar_ajuste:true,
                            docx:true, txt:true, auto:true})
    }).then(x => x.json());
    if (!r.ok) throw new Error(r.erro || "");
    sujo = false;
    const agora = new Date();
    const dois = (x) => String(x).padStart(2, "0");
    $("#estado").textContent = "salvo sozinho às " + dois(agora.getHours()) +
                               ":" + dois(agora.getMinutes());
    $("#estado").style.color = "var(--ok)";
  }catch(e){
    // Deu errado: o aviso de "não salvo" volta, e o relógio tenta de novo.
    marcarSujo();
  }
}
setInterval(salvarSozinho, 20000);

window.addEventListener("beforeunload", (e) => {
  if (!sujo) return;
  e.preventDefault();
  e.returnValue = "";
});

comecar();
</script>
</body>
</html>
"""


def pagina(token):
    """Devolve a pagina com o token da sessao ja embutido."""
    return _PAGINA.replace("__TOKEN__", token)
