# 03 — Pipeline de importação

Como o pacote transforma um `.obj` em um `.bin` do PES PS2, fase por fase.

```mermaid
flowchart TB
    OBJ[".obj"] --> F1
    TPL["template.bin"] --> F1
    F1["1 · parse template + .obj"] --> F2["2 · auto-fit"]
    F2 --> F3["3 · partição (≤ N parts)"]
    F3 --> F4["4 · atribui triângulos às parts"]
    F4 --> F5["5 · normais (recalcula ou preserva)"]
    F5 --> F6["6 · rebuild de cada part<br/>(int16 + strip + ~15 campos)"]
    F6 --> F7["7 · patch global + write"]
    F7 --> BIN[".bin"]
```

A função orquestradora é `shared/pipeline/importer._import`, parametrizada por um
**AssetProfile** (face ou troféu) — ver [11 — Arquitetura](11-arquitetura.md).

---

## Fase 1 — Parsing do template e do OBJ

### Template (`bin_io.decompress_bin` + `model.parse_model`)

```python
payload, outer_header, trailing = decompress_bin(template_path)
template = parse_model(payload, model_offset)   # model_offset vem do profile.locate
```

O template é a **fonte da verdade** para:

- Estrutura do header e do VIF prologue (clonamos com pequenas atualizações).
- Bytes de textura no `post_parts` (preservados intactos).
- Bytes de bones em templates "ricos" (preservados, não tocamos).
- Bounding box / clipping matrix nos floats do header.

### OBJ (`obj_io.parse_obj`)

```python
obj = parse_obj(obj_path)
# obj.vertices: List[(x, y, z) float]
# obj.uvs:      List[(u, v) float]
# obj.faces:    List[(a, b, c) 0-based]
# obj.face_groups + obj.group_names: para --use-groups
```

Parser minimalista que aceita `v`, `vt`, `vn` (ignoradas — recalculamos),
`g`/`o` (grupos) e `f`.

**Pré-condições críticas:**

- `len(vertices) == len(uvs)`. Se diferir, abortamos com mensagem clara sobre
  `Merge UVs by Distance` no Blender.
- **Faces com >3 vértices são trianguladas por leque** automaticamente (quad
  `f a b c d` → `(a,b,c)` + `(a,c,d)`). Funciona para polígonos convexos; côncavos
  devem ser triangulados no Blender antes.

---

## Fase 2 — Auto-fit (`geometry.transform.auto_fit_vertices`)

`.obj` de fontes diversas vem em **escala/posição arbitrária**. Sem ajuste, os
vértices caem fora do frustum → face invisível ou gigante/microscópica.

```mermaid
flowchart LR
    O["bbox do .obj"] --> S["scale = min(t_span / o_span)<br/>(uniforme nos 3 eixos)"]
    T["bbox do template"] --> S
    S --> V["v' = (v − obj_center)·scale + tmpl_center"]
```

**Escala uniforme (`min`)** preserva as proporções faciais — escala por-eixo
distorceria o rosto. Para a maioria dos casos, **use sempre `--auto-fit`**.

---

## Fase 3 — Partição (`pipeline.partition.*`)

O `.obj` pode ter qualquer número de vértices; cada part precisa de ≤ 255. Como
distribuir? Quatro estratégias, em ordem de prioridade:

```mermaid
flowchart TD
    Q{"contagem == template?"}
    Q -->|sim| ORIG["usa distribuição original<br/>(roundtrip)"]
    Q -->|não| Q2{"flag dada?"}
    Q2 -->|"--part-sizes"| PS["tamanhos manuais"]
    Q2 -->|"--use-groups"| UG["1 grupo do .obj = 1 part"]
    Q2 -->|"--match-template"| MT["nearest-neighbor do template"]
    Q2 -->|"(nenhuma)"| BFS["BFS por adjacência (default)"]
```

### Por que duplicar vértices nos *seams*

Triângulos **não podem cruzar** a fronteira de duas parts (todos os 3 vértices têm
de estar na mesma part). Quando um triângulo ficaria a cavalo, o vértice
compartilhado é **duplicado** na part vizinha — mesma posição int16 e UV, só o
índice muda. Sem buracos, custo pequeno de memória.

### Expansão de parts (`--max-verts-per-part`)

Se a malha é grande, o BFS pode estourar 255 v/part. Essa flag faz o pipeline
**criar mais parts** (clonando a última do template). **Limite hard: 8 parts em
faces** — acima disso, abortamos ([Bug 12](06-bugs-historicos.md#bug-12--mais-de-8-parts--face-invisível)). Troféus não têm esse limite.

---

## Fase 4 — Atribuição de triângulos (`partition.assign_triangles_to_parts`)

Com os ranges `[start_v, end_v)` por part, cada triângulo é atribuído à part dos
seus vértices e convertido para **índices locais**. Se a contagem bate com o
template mas a **ordem** dos vértices não respeita as fronteiras (caso de `.obj`
de simplifier QEM), aplicamos **BFS automático** como fallback.

---

## Fase 5 — Normais (`geometry.transform.compute_vertex_normals`)

Com `--recalculate-normals` (recomendado para faces novas):

```
para cada face (a,b,c):  n = cross(b−a, c−a)   # magnitude ∝ área
   sum[a]+=n ; sum[b]+=n ; sum[c]+=n            # pondera por área
para cada vértice v:     normalize(sum[v])
```

Sem a flag, as normais do **template** são preservadas para os vértices na mesma
posição; vértices novos usam fallback `(0,0,+1)`.

> ⚠ **[Bug 7](06-bugs-historicos.md#bug-7--normal_scale-30-menor-que-o-correto):** `NORMAL_SCALE = 32767` (int16 max). Valores menores → lighting errado.

---

## Fase 6 — Rebuild de cada part (`model.rebuilder.rebuild_part`)

O trabalho pesado: gravar os **~15 campos derivados** ([mapa completo](02-anatomia-payload.md#5-o-mapa-dos-bytes-que-você-precisa-gravar))
e codificar a geometria nova.

```mermaid
flowchart TB
    R1["converte verts/normais/UVs → int16 (via CoordSpace)"] --> R2["codifica triângulos no strip<br/>(connected, default)"]
    R2 --> R3["alinha strip a múltiplo de 4 (pad −32768)"]
    R3 --> R4["recalcula part_size + alinha a 16 (DMA)"]
    R4 --> R5["grava header: part_size · QWC · strip_total · vbe · ss"]
    R5 --> R6["grava prologue: vbe(×3) · ss · se · vc · tags NUM/IMMED"]
```

### Strip: `connected` (padrão) ou `list`

```python
# rebuild_part(..., strip_mode="connected")   # default desde a validação in-game
```

- **`connected`** (padrão): *triangle strips* conectados, ~35% menores. Exige
  orientar a malha (flood-fill) antes — feito automaticamente. Validado in-game.
- **`list`**: *triangle list* (3 índices/triângulo isolados), robusto e
  independente de winding — formato legado, via `--strip-mode list`.

Detalhes e o porquê em [05 — Strip encoding](05-strip-encoding.md).

### Passthrough zero-diff (parts não editadas)

Antes de recodificar, o pipeline checa se a part **reproduz exatamente** a do
template (`_part_is_faithful`: mesmos vc, verts/UVs/normais int16, e o mesmo
conjunto de triângulos). Se sim, **preserva o strip original** byte-a-byte — essa é
a base do [roundtrip zero-diff](#validação-roundtrip). `--no-preserve-strips`
desliga e recodifica tudo.

---

## Fase 7 — Patch global + write

```mermaid
flowchart TB
    P1["total_parts (offset_file_1 + 0x20), se mudou"] --> P2
    P2["parts_end mudou?"] -->|sim| P3["patch defensivo no pre_parts:<br/>byte == parts_end → +Δ ; byte == parts_end−16 → +Δ"]
    P2 -->|não| P4
    P3 --> P4["zlib(payload, 9) + outer_header (tamanhos) + trailing"]
    P4 --> OUT[".bin"]
```

O patch dos ponteiros é **defensivo** (varre o `pre_parts` procurando qualquer
uint32 que valha `parts_end` ou `parts_end − 16`) — pega ambos os ponteiros
conhecidos e qualquer outro relacionado. Para troféus, há um patch adicional do
diretório de seções (ver [08 §4](08-trofeus.md)).

---

## Validação: roundtrip

```mermaid
flowchart LR
    BIN["template.bin"] -->|export| OBJ["template.obj"]
    OBJ -->|"import (sem editar)"| RT["rt.bin"]
    RT -. "byte-idêntico?" .-> BIN
```

Há **dois níveis** de roundtrip, e a diferença é importante:

| Cenário | Resultado |
|---|---|
| `.obj` reproduz **exatamente** o template (não editado) | **zero-diff** — o passthrough preserva o strip original; `rt.bin` é byte-idêntico a `template.bin`. |
| `.obj` com geometria **editada** (alguns vértices/triângulos mudam) | só as parts alteradas são recodificadas (strip `connected`); a **geometria** é preservada, os **bytes** das parts editadas mudam. |

Teste prático (export → import sem editar → comparar):

```bash
python -m wepes3d export face.bin face.obj --type face
python -m wepes3d import face.bin face.obj rt.bin --type face
cmp face.bin rt.bin && echo "zero-diff ✓"
```

```python
# valida que a GEOMETRIA sobrevive (mesmo quando os bytes mudam):
from wepes3d import export_face
export_face("rt.bin", "rt.obj")
# compare rt.obj com face.obj — vértices/UVs/faces iguais
```

---

## Próximo: VU microcode

Para entender por que campos como `vbe` e `ss` são tão críticos:
[04 — VIF e VU1](04-vu-microcode.md).
