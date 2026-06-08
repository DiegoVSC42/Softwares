# Distribuição dos executáveis na rede (D:\Softwares)

Este documento explica como os executáveis chegam à pasta de rede do escritório.

## A ideia em uma frase

Existem **duas coisas diferentes**, e é importante não misturá-las:

1. **O código-fonte** (a pasta do projeto `gerenciador-pastas`) → fica no
   **GitHub** e alimenta o robô (GitHub Actions) que monta os executáveis.
2. **A pasta de distribuição** (`D:\Softwares`) → é só o lugar **compartilhado
   na rede** onde os executáveis prontos ficam, para o pessoal do escritório
   abrir. **Ela não precisa ser um repositório git.**

```
D:\Softwares\              <- pasta compartilhada na rede (NÃO precisa ser git)
├── Windows\
│   └── FolderManagerWIN.exe
└── Mac\
    └── FolderManagerMAC.app
```

## Como cada executável chega lá

| Executável | Como é gerado | Como vai parar na pasta de rede |
|------------|---------------|----------------------------------|
| `FolderManagerWIN.exe` | `build_exe.bat` roda no seu PC Windows | O próprio `build_exe.bat` já salva direto em `D:\Softwares\Windows`. |
| `FolderManagerMAC.app` | GitHub Actions monta na nuvem | Você roda `baixar-mac-da-nuvem.bat`, que baixa o `.app` da nuvem e salva em `D:\Softwares\Mac`. |

### Por que o Mac é diferente

O `.app` do Mac só pode ser montado dentro de um macOS. Como você optou por
gerar na nuvem, o GitHub Actions faz isso numa máquina Mac remota. Só que **a
nuvem não enxerga o seu `D:`** — por isso existe o passo do
`baixar-mac-da-nuvem.bat`, que traz o arquivo pronto para a pasta de rede.

## Passo a passo do dia a dia

**Para atualizar o executável do Windows:**

1. Dois cliques em `build_exe.bat`.
2. Pronto — `D:\Softwares\Windows\FolderManagerWIN.exe` já está atualizado.

**Para atualizar o executável do Mac:**

1. Suba o código novo para o GitHub (ou deixe que ele já esteja lá).
2. Espere o build terminar na aba **Actions** do GitHub (uns 3 minutos).
3. Dois cliques em `baixar-mac-da-nuvem.bat`.
4. Pronto — `D:\Softwares\Mac\FolderManagerMAC.app` já está atualizado.

> Antes do primeiro uso do `baixar-mac-da-nuvem.bat`, faça a configuração única
> descrita dentro do próprio arquivo (instalar o GitHub CLI e rodar
> `gh auth login`), e ajuste a linha `REPO=SEU-USUARIO/gerenciador-pastas` com o
> nome real do seu repositório.

## Vários projetos na mesma pasta de rede

Se você tiver outras ferramentas (ex.: `comprimir-mp4`, `normalizador-numeros`),
a mesma pasta `D:\Softwares\Windows` serve de central para todos os `.exe`. Cada
projeto só precisa do próprio `build_exe.bat` apontando o `DESTINO` para
`D:\Softwares\Windows`. Assim o escritório tem um único lugar com todos os
programas.

## E se eu quiser mudar os caminhos?

Os destinos são variáveis no topo de cada script — é só editar:

- `build_exe.bat` → linha `set "DESTINO=D:\Softwares\Windows"`
- `baixar-mac-da-nuvem.bat` → linha `set "DESTINO=D:\Softwares\Mac"`

Se preferir uma subpasta única (ex.: `D:\Softwares\compartilhada`), basta apontar
as duas variáveis para lá.
