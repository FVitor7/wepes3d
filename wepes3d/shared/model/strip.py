"""
Encoding of the PES PS2 strip data.

The strip data is a list of int16 values that the PS2 VU1 decodes into
triangles. Each index has:

  - bit 15 = ADC flag (Address Don't Connect): 1 = does not fire a triangle,
    it only enters the queue.
  - bits 0..14 = (vertex_local_idx + 1) × 4.

The VU1 keeps a sliding window of 3 indices [a, b, c] and fires the triangle
(decode(a), decode(b), decode(c)) when `c` has ADC=0. Three cases:

  Case 1: [neg, neg, pos]  - 2 restarts + 1 fire (isolated triangle).
  Case 2: [neg, pos, pos]  - 1 restart at the start + 2 fires (continues the
                              previous segment).
  Case 3: [pos, pos, pos]  - normal extension: each `c` fires a new triangle
                              made with the 2 previous indices.

This module is the legacy "list" mode: it only uses Case 1, so each triangle
is an isolated segment [neg, neg, pos], which costs 3 indices/triangle. The
default "connected" mode (real tristrips) is in strip_connected.py.

Historical note: an old version of this text said that connected strips cannot
keep a consistent winding because the PS2 does not flip it automatically. That
was proven WRONG in the game — the GS does flip the winding in strips. See
docs/05-strip-encoding.md.
"""

import struct
from typing import List, Tuple


# ============================================================================
# Encoding of one triangle (case 1: [neg, neg, pos])
# ============================================================================

def _encode_vertex_with_adc(v: int) -> int:
    """Encodes a local vertex with ADC=1 (no kick). Negative int16."""
    raw = (v + 1) * 4
    # bit 15 set -> read as a negative int16
    return (raw | 0x8000) - 0x10000


def _encode_vertex_kick(v: int) -> int:
    """Encodes a local vertex with ADC=0 (kick = fires a triangle).
    Positive int16 in the range [4, 0x7FFC]."""
    raw = (v + 1) * 4
    if raw > 0x7FFF:
        raise ValueError(
            f"Vertex index {v} is above 0x7FFF after multiplying by 4. "
            f"Max per part: 8190 vertices."
        )
    return raw


# ============================================================================
# Encoding of the whole strip (triangle list mode)
# ============================================================================

def triangles_to_pes_strip(
    triangles: List[Tuple[int, int, int]],
) -> List[int]:
    """
    Converts a list of triangles (a, b, c) into int16 indices for the PS2
    strip data.

    It applies:
      1. A winding flip (a, c, b) on each triangle — it compensates for the X
         flip applied to the vertices (the face CoordSpace,
         `obj_to_int16_vertex`). Without it, all triangles would face
         backwards after the implicit X flip.
      2. Triangle list encoding: each triangle becomes [neg(v0), neg(v1),
         pos(v2)] (case 1 of the decoder). Costs 3 indices/triangle.

    It does NOT extend strips: each triangle is independent, so the winding
    is correct by construction, whatever the orientation of the mesh. That is
    why this mode is robust (and bigger). The default mode is "connected"
    (strip_connected.py).
    """
    indices: List[int] = []
    for (a, b, c) in triangles:
        # Winding flip: (a, b, c) -> (a, c, b)
        v0, v1, v2 = a, c, b
        indices.append(_encode_vertex_with_adc(v0))
        indices.append(_encode_vertex_with_adc(v1))
        indices.append(_encode_vertex_kick(v2))
    return indices


def pack_strip_indices(indices: List[int]) -> bytes:
    """Packs the list of int16 indices into bytes (little endian)."""
    return struct.pack(f"<{len(indices)}h", *indices)


# ============================================================================
# Padding and alignment
# ============================================================================

STRIP_PADDING_VALUE = -32768
"""Value used for padding: int16 -32768 = 0x8000. Only the ADC bit is set, so
the decoder NEVER fires a triangle; it stands for vertex 0 with ADC on, a safe
no-op."""


def align_strip_to_v4(indices: List[int]) -> List[int]:
    """
    Pads the list so the total number of indices is a multiple of 4 (each
    V4-16 element = 4 int16 = 8 bytes). Without this, the VIF UNPACK V4-16
    tag does not match the size of the strip data.
    """
    rem = len(indices) % 4
    if rem == 0:
        return indices
    pad_count = 4 - rem
    return indices + [STRIP_PADDING_VALUE] * pad_count


def pad_to_length(indices: List[int], target_length: int) -> List[int]:
    """
    Pads up to `target_length` (used when we want to keep the part size
    exactly the same as in the template).
    """
    if len(indices) >= target_length:
        return indices
    return indices + [STRIP_PADDING_VALUE] * (target_length - len(indices))


# ============================================================================
# Diagnostics (useful for debugging)
# ============================================================================

def decode_strip(indices: List[int], vc: int) -> List[Tuple[int, int, int]]:
    """
    Copies the official PS2 decoder (port of the pes_ps2_imp Blender plugin).
    Useful to check that the encoding produced the right triangles.

    Returns a list of triangles (a, b, c) with the LOCAL indices of the part.
    """
    divided = [int(i / 4) for i in indices]
    triangles: List[Tuple[int, int, int]] = []

    def safe(value: int, is_restart: bool) -> int:
        return (8192 + value - 1) if is_restart else (value - 1)

    def valid(tri: Tuple[int, int, int]) -> bool:
        # The DECODED indices must be different: neg(v) and pos(v) only differ
        # in their sign, so they pass the `a != b` test below and would make a
        # degenerate triangle — one that the export reader
        # (reader.read_part_geometry) drops.
        return all(0 <= i < vc for i in tri) and len(set(tri)) == 3

    for f in range(len(divided) - 2):
        a, b, c = divided[f], divided[f + 1], divided[f + 2]
        if a < 0 and b < 0 and c >= 0:
            # Case 1: [neg, neg, pos]
            if a != b and b != c and c != a:
                tri = (safe(a, True), safe(b, True), safe(c, False))
                if valid(tri):
                    triangles.append(tri)
        elif a <= 0 and b >= 0 and c >= 0:
            # Case 2: [neg, pos, pos]
            if a != b and b != c and c != a:
                tri = (safe(a, True), safe(b, False), safe(c, False))
                if valid(tri):
                    triangles.append(tri)
        elif a > 0 and b >= 0 and c >= 0:
            # Case 3: [pos, pos, pos]
            if a != b and b != c and c != a:
                tri = (safe(a, False), safe(b, False), safe(c, False))
                if valid(tri):
                    triangles.append(tri)
    return triangles
