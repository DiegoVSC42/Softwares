# Cronômetro de Tempo de Resposta — Telefone

Mede quanto tempo a outra pessoa demora para responder em uma conversa por
telefone (ou qualquer diálogo entre duas pessoas).

## Como usar

1. Abra o programa.
2. Quando **atender a chamada**, aperte **Espaço** (ou clique em *Atendi a
   chamada*). Isso só marca o início da chamada como referência — **não** entra
   no cálculo do tempo de resposta.
3. Quando **você terminar de falar**, aperte a tecla **1** (ou clique em
   *Terminei de falar*). O cronômetro começa a contar.
4. Quando **ouvir a voz da outra pessoa**, aperte a tecla **2** (ou clique em
   *Ouvi a outra pessoa*). O tempo de resposta é registrado.

O tempo entre o passo 3 e o passo 4 é o **tempo de resposta** da outra pessoa.

## Atalhos de teclado

| Tecla    | Ação |
|----------|------|
| `Espaço` | Atendi a chamada (marca o início da chamada) |
| `1`      | Terminei de falar (inicia a contagem) |
| `2`      | Ouvi a outra pessoa (registra o tempo) |
| `3`      | Cancela o `1` (descarta a contagem em andamento, útil em misclick) |
| `Esc`    | Cancela a medição em andamento |

As teclas funcionam tanto no teclado normal quanto no numérico.

## Recursos

- Cronômetro ao vivo enquanto você aguarda a resposta.
- Histórico de todas as medições da sessão (número, tempo e hora).
- Estatísticas automáticas: quantidade, média, menor e maior tempo.
- **Exportar CSV** (separado por `;`, compatível com Excel em português) com o
  histórico e o resumo estatístico.

## Executar

Requer apenas Python 3 (o Tkinter já vem incluído):

```
python cronometro_resposta_telefone.py
```

Não há dependências externas para instalar.
