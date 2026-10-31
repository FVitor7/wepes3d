# examples/ — arquivos de exemplo

Esta pasta traz um **arquivo real do jogo** para você experimentar a ferramenta
sem precisar extrair nada. Tudo aqui é usado pelo passo a passo
[docs/14 — A face byte a byte](../docs/14-exemplo-face-byte-a-byte.md).

| Arquivo | O que é | Tamanho |
|---|---|---|
| `face.bin` | uma **face/cabelo do PES PS2** (template "simples", 8 parts, 696 vértices) | 25.761 B |
| `face.obj` | o **export** de `face.bin` (gerado pela própria ferramenta) | ~60 KB |
| `face.mtl` | o material do `.obj` (aponta para `face.png`, a textura) | — |

> O `face.obj`/`face.mtl` são **gerados** a partir do `face.bin`. Você pode
> recriá-los a qualquer momento com o comando de `export` abaixo.

---

## Experimente (rode da raiz do repositório)

```bash
# 1) LISTAR — diz o tipo do arquivo
python -m wepes3d list examples/face.bin --type face

# 2) EXPORTAR — .bin → .obj (abra no Blender)
python -m wepes3d export examples/face.bin minha_face.obj --type face

# 3) IMPORTAR — .obj → .bin (usa o face.bin como "casca"/template)
python -m wepes3d import examples/face.bin minha_face.obj saida.bin --type face
```

Pela API Python:

```python
from wepes3d import export_face, import_face
export_face("examples/face.bin", "minha_face.obj")
import_face("examples/face.bin", "minha_face.obj", "saida.bin")
```

---

## O que esperar

- `face.bin` é um template **sem bones** (face estática) — o caminho de menor
  resistência para importar geometria nova. Ver [docs/01 §4](../docs/01-formato-bin.md).
- O `export` informa `696 v, 984 faces`.
- Sobre o que significa "roundtrip idêntico" (e o que **não** é byte-idêntico),
  leia a [seção 4 do docs/14](../docs/14-exemplo-face-byte-a-byte.md#4-roundtrip-o-que-idêntico-significa-em-cada-camada).

> **Textura:** o `.mtl` aponta para `face.png`, que **não** acompanha o pacote (a
> textura mora dentro do `post_parts` do `.bin` e é extraída à parte). O `.obj`
> abre normalmente no Blender mesmo sem o `.png` — só ficará sem a imagem.
