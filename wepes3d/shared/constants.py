"""
Constantes do formato face/hair do PES PS2.

Valores aqui foram derivados por engenharia reversa de templates (face.payload,
face_X.payload, h1..h4.payload) e validados via roundtrip BIN -> OBJ -> BIN.
Cada constante tem um comentario explicando POR QUE tem aquele valor.
"""

# ============================================================================
# Magic numbers e marcadores
# ============================================================================

MAGIC_MODEL = bytes([0x03, 0x00, 0xFF, 0xFF])
"""Magic do header do modelo. Marca o inicio do sub-bloco que contem
total_parts + parts_start_rel.

- FACE: aparece DIRETO em `offset_file_1` (payload[8]).
- TROFEU: aparece mais fundo, em `offset_mdl` (apos navegar o container).

Ver `model_parser.locate_model`."""

CONTAINER_MAGIC = bytes([0x00, 0x06, 0x00, 0x00])
"""Magic do container aninhado dos TROFEUS, em `offset_file_1` (payload[8])
quando o asset NAO eh uma face direta. Indica que o modelo real (MDL, com
MAGIC_MODEL) esta mais adiante: a partir de `offset_file_1` pula 32 bytes
(base), le um uint32 em base+8 que aponta (relativo a base) para o MDL.

Em base ha um DIRETORIO DE SECOES: base[0]=qtde de secoes, base[8]=offset da
secao 0 (=MDL, rel a base), base[12..]=offsets das demais secoes (texturas),
todos rel a base. A secao 1 comeca exatamente onde as parts do MDL terminam
(parts_end) — por isso, ao redimensionar o MDL, as entradas a partir de base+12
deslizam +delta. Ver `containers.TrophyContainer`."""

VIF_STRIP_MARKER = bytes([0x01, 0x00, 0x00, 0x05, 0x01, 0x01, 0x00, 0x01])
"""Marker fixo de 8 bytes que precede a tag VIF UNPACK do strip dentro de
cada part. Composto por 2 VIFcodes: STMOD mode=1 (ADD) + STCYCL CL=1 WL=1.
O STCYCL reseta o ciclo de unpack para tight-packed (diferente do CL=4 WL=1
usado para vertices/normais/UVs interleaved)."""


# ============================================================================
# Offsets dentro do model header
# ============================================================================

PARTS_INFO_OFFSET = 32
"""Offset relativo a `offset_file_1` onde fica `total_parts` (uint32).
Em seguida (offset + 4) vem `parts_start_rel`."""

PARTS_END_REL_OFFSET = 0x2C
"""Offset relativo a `offset_file_1` onde fica o FIM das parts, gravado
RELATIVO ao modelo: `parts_end - offset_file_1` (uint32). Muda junto com o
tamanho das parts.

Validado em todos os modelos reais analisados (faces com o modelo em 0x10 e
em 0x20, as 9 secoes dos trofeus, kits e estadios). Em face.bin, com o modelo
em 0x10, ele coincide com `payload[0x3C] = parts_end - 16` — e foi assim que o
Bug 4 o descreveu, o que deixava templates com o modelo em 0x20 (h2, face_1)
e os trofeus com esse campo desatualizado no recount."""

TEXTURE_INDEX_IN_PART = 52
"""Offset relativo ao inicio de uma part onde fica `tex_id` (uint32)."""

VERTEX_IN_PART_OFFSET = 88
"""Offset relativo a `part_info_start_raw` (= rel 0x0B0..0x110, o VIF prologue)
onde fica `vertex_count` (uint16). Bate com o `data: vc, 0` do UNPACK do
prologue."""


# ============================================================================
# Fatores de conversao de coordenadas
# ============================================================================

VERTEX_FACTOR = -0.001553
"""Multiplicador para converter int16 do .bin para float OBJ.

Sinal negativo: invertido — vertices no .bin usam um sistema de coordenadas
onde o eixo Y eh "para baixo" e o multiplicador negativo + inversao do X
deixa tudo consistente com o sistema OBJ (Y para cima, X para direita).

Magnitude (~1/644): escolhida para que faces tipicas caibam em ~1.5 unidades
no espaco OBJ (compativel com Blender default).

Inversao do X: aplicada SEPARADAMENTE como `ix = round(x / VERTEX_FACTOR * -1)`,
ou seja, X tem MAIS um flip alem do sinal negativo do VERTEX_FACTOR. Resultado
liquido: X invertido relativo a Y/Z.
"""

UV_FACTOR = 0.000244
"""Multiplicador para int16 -> float em UVs. Aproximadamente 1/4096, que eh a
resolucao tipica de texturas PS2 (4096 = 12 bits). UV no .bin armazena
coordenadas em "texels" multiplicado por 4096 (saturated int16)."""

NORMAL_SCALE = 32767
"""Magnitude do vetor normal int16. Cada componente de normal eh `int16` com
range [-32767, 32767], representando float unitario [-1.0, 1.0].

Bug historico: versoes antigas usavam 1108. Causa: alguem mediu APENAS um
componente individual em uma face especifica e nao a MAGNITUDE do vetor
(sqrt(nx^2 + ny^2 + nz^2)). Validacao correta em todas as 8 parts de
face.payload: magnitude = 32767 +- 1."""


# ============================================================================
# Limites do formato
# ============================================================================

MAX_PARTS_HARD = 8
"""Numero maximo de parts que o jogo suporta.

`payload[0x04] = 8` em TODOS os exemplos analisados (face.payload com 8 parts,
face_X com 6, h1 com 6, h2/h3 com 4, h4 com 5). Provavelmente capacidade fixa
do buffer de parts no engine.

Tentativa de subir esse byte para `new_total > 8` NAO funciona — face fica
invisivel no jogo (mas aparece em editores externos da comunidade que ignoram
esse campo)."""

MAX_VERTEX_COUNT_PER_PART = 255
"""Numero maximo de vertices em uma part. O campo `NUM` do VIF UNPACK eh uint8
(byte 2 do VIFcode), entao max representavel = 255. Com 8 parts × 255 = 2040
vertices total no .obj suportado."""

MAX_STRIP_NUM = 255
"""Numero maximo de elementos V4-16 no strip data. Mesmo limite do `NUM` do
VIF UNPACK (uint8).

Cada elemento V4-16 = 4 indices int16. No modo triangle list o encoder gera
3 indices por triangulo e empacota TODOS os triangulos de forma contigua; o
strip inteiro eh entao paddeado UMA vez ate o proximo multiplo de 4 indices.
Logo:

    num_v4 = ceil(3 * num_triangulos / 4)

O teto num_v4 <= 255 da 1020 indices, ou seja ~340 triangulos por part
(NAO 255: nao ha 1 pad por triangulo, so 1 pad no fim do strip)."""


# ============================================================================
# DMA / alinhamento
# ============================================================================

DMA_ALIGN = 16
"""Cada DMA chain do PS2 transfere multiplos de 16 bytes (qwords). Toda part
do .bin deve ter `size % 16 == 0`. O script aplica padding com zeros no
final do `post_strip_bytes` para garantir esse alinhamento."""


# ============================================================================
# Bone weights / area opcional no pre_parts
# ============================================================================

BONE_REGION_RELATIVE_START = 0xE0
"""Offset relativo a `offset_file_1` onde COMECA a area de bones em arquivos
"ricos" (face_X.bin, h1.bin). Em arquivos "simples" (face.bin) essa area NAO
existe — pre_parts inteiro ocupa so 272 bytes."""

# Notas sobre a area de bones:
#   - Cada entry parece ter 8 bytes: 3 int16 vertex_pos + 1 int16 bone_idx.
#   - Em ~90% das entries byte[7] == 0 (bone_idx < 256).
#   - Estrutura completa tem sub-tabelas com formatos mistos (6/8 bytes).
#   - face.bin (template simples) NAO tem essa area, e o jogo renderiza
#     sem aplicar bone transformation. Por isso o script funciona com
#     face.bin como template sem precisar tocar em bone weights.
