"""
Constants of the PES PS2 face/hair format.

These values come from reverse engineering of real templates (face.payload,
face_X.payload, h1..h4.payload) and were checked with BIN -> OBJ -> BIN
roundtrips. Each constant has a comment that explains WHY it has that value.
"""

# ============================================================================
# Magic numbers and markers
# ============================================================================

MAGIC_MODEL = bytes([0x03, 0x00, 0xFF, 0xFF])
"""Magic of the model header. It marks the start of the block that holds
total_parts + parts_start_rel.

- FACE: found DIRECTLY at `offset_file_1` (payload[8]).
- TROPHY: found deeper, at `offset_mdl` (after going through the container).

See `shared.model.parser.locate_model`."""

CONTAINER_MAGIC = bytes([0x00, 0x06, 0x00, 0x00])
"""Magic of the nested container used by TROPHIES, at `offset_file_1`
(payload[8]) when the asset is NOT a plain face. It means the real model (MDL,
with MAGIC_MODEL) is further ahead: from `offset_file_1` skip 32 bytes (base),
then read a uint32 at base+8 that points (relative to base) to the MDL.

At base there is a SECTION DIRECTORY: base[0] = number of sections, base[8] =
offset of section 0 (= MDL, relative to base), base[12..] = offsets of the
other sections (textures), all relative to base. Section 1 starts exactly where
the MDL parts end (parts_end) — so when the MDL changes size, the entries from
base+12 on move by +delta. See `adapters.pesweps2.trophies.profile`."""

VIF_STRIP_MARKER = bytes([0x01, 0x00, 0x00, 0x05, 0x01, 0x01, 0x00, 0x01])
"""Fixed 8-byte marker before the VIF UNPACK tag of the strip, inside each
part. It is made of 2 VIFcodes: STMOD mode=1 (ADD) + STCYCL CL=1 WL=1.
The STCYCL resets the unpack cycle to tight-packed (different from the
CL=4 WL=1 used for the interleaved vertices/normals/UVs)."""


# ============================================================================
# Offsets inside the model header
# ============================================================================

PARTS_INFO_OFFSET = 32
"""Offset, relative to `offset_file_1`, of `total_parts` (uint32).
Right after it (offset + 4) comes `parts_start_rel`."""

PARTS_END_REL_OFFSET = 0x2C
"""Offset, relative to `offset_file_1`, of the END of the parts, stored
RELATIVE to the model: `parts_end - offset_file_1` (uint32). It changes when
the parts change size.

Checked on every real model we analysed (faces with the model at 0x10 and at
0x20, the 9 sections of the trophies, kits and stadiums). In face.bin, with the
model at 0x10, it is the same as `payload[0x3C] = parts_end - 16` — that is how
Bug 4 described it, which left this field out of date after a recount in
templates with the model at 0x20 (h2, face_1) and in trophies."""

TEXTURE_INDEX_IN_PART = 52
"""Offset, relative to the start of a part, of `tex_id` (uint32)."""

VERTEX_IN_PART_OFFSET = 88
"""Offset, relative to `part_info_start_raw` (= rel 0x0B0..0x110, the VIF
prologue), of `vertex_count` (uint16). It matches the `data: vc, 0` of the
prologue UNPACK."""


# ============================================================================
# Coordinate conversion factors
# ============================================================================

VERTEX_FACTOR = -0.001553
"""Multiplier that converts the .bin int16 values into OBJ floats.

Negative sign: the .bin uses a coordinate system where the Y axis points
"down"; the negative multiplier plus the X flip make it match the OBJ system
(Y up, X to the right).

Size (~1/644): chosen so that a typical face fits in ~1.5 units in OBJ space
(works with the Blender defaults).

X flip: applied SEPARATELY as `ix = round(x / VERTEX_FACTOR * -1)`, so X gets
ONE MORE flip on top of the negative sign of VERTEX_FACTOR. Net result: X is
flipped relative to Y/Z.
"""

UV_FACTOR = 0.000244
"""Multiplier for int16 -> float on UVs. About 1/4096, the usual resolution of
PS2 textures (4096 = 12 bits). The .bin stores UVs in "texels" times 4096
(saturated int16)."""

NORMAL_SCALE = 32767
"""Length of the int16 normal vector. Each normal component is an `int16` in
the range [-32767, 32767], which stands for a unit float in [-1.0, 1.0].

Historical bug: old versions used 1108. Cause: someone measured ONLY one
component of one specific face, not the vector LENGTH
(sqrt(nx^2 + ny^2 + nz^2)). The correct check on all 8 parts of face.payload
gives length = 32767 +- 1."""


# ============================================================================
# Format limits
# ============================================================================

MAX_PARTS_HARD = 8
"""Maximum number of parts that the game supports.

`payload[0x04] = 8` in ALL the analysed examples (face.payload with 8 parts,
face_X with 6, h1 with 6, h2/h3 with 4, h4 with 5). Probably the fixed size of
the parts buffer in the engine.

Raising this byte to `new_total > 8` does NOT work — the face becomes invisible
in the game (but it shows up in community editors, which ignore this field)."""

MAX_VERTEX_COUNT_PER_PART = 255
"""Maximum number of vertices in one part. The `NUM` field of the VIF UNPACK is
a uint8 (byte 2 of the VIFcode), so the largest value is 255. With 8 parts ×
255 = 2040 vertices in total in the .obj."""

MAX_STRIP_NUM = 255
"""Maximum number of V4-16 elements in the strip data. Same limit as the `NUM`
of the VIF UNPACK (uint8).

Each V4-16 element = 4 int16 indices. In triangle list mode the encoder writes
3 indices per triangle and packs ALL triangles one after the other; then the
whole strip is padded ONCE up to the next multiple of 4 indices. So:

    num_v4 = ceil(3 * num_triangles / 4)

The limit num_v4 <= 255 gives 1020 indices, that is ~340 triangles per part
(NOT 255: there is no pad per triangle, only 1 pad at the end of the strip)."""


# ============================================================================
# DMA / alignment
# ============================================================================

DMA_ALIGN = 16
"""Each PS2 DMA chain moves multiples of 16 bytes (qwords). Every part of the
.bin must have `size % 16 == 0`. The code pads the end of `post_strip_bytes`
with zeros to keep this alignment."""


# ============================================================================
# Bone weights / optional area in pre_parts
# ============================================================================

BONE_REGION_RELATIVE_START = 0xE0
"""Offset, relative to `offset_file_1`, where the bones area STARTS in "rich"
files (face_X.bin, h1.bin). In "simple" files (face.bin) this area does NOT
exist — the whole pre_parts is only 272 bytes."""

# Notes about the bones area:
#   - Each entry seems to have 8 bytes: 3 int16 vertex_pos + 1 int16 bone_idx.
#   - In ~90% of the entries byte[7] == 0 (bone_idx < 256).
#   - The full structure has sub-tables with mixed formats (6/8 bytes).
#   - face.bin (simple template) does NOT have this area, and the game draws
#     it without bone transformation. That is why the code works with face.bin
#     as template without touching bone weights.
