"""
Encoding of connected TRIANGLE STRIPS (instead of a triangle list).
This is the DEFAULT mode of the pipeline (strip_mode="connected"), checked in
the game.

Why
---
The `strip.py` encoder (list mode) uses a *triangle list*: 3 indices per
triangle, each one isolated in [neg, neg, pos]. It is robust and does not
depend on the winding, but it uses ~3x more bytes in the strip data than the
connected strips that the game uses.

The ORIGINAL strips of the game are connected (in `face.bin`, 92 of the 130
triangles of a part are "case 3" = a strip that continues) and they decode
with ALTERNATING winding (+-+-+-). Since `face.bin` draws perfectly, we
conclude that the PS2 GS **flips the winding automatically** in strip
primitives — like every GPU does. So connected strips are valid in the game.

CRITICAL precondition (the missing piece)
-----------------------------------------
The meshes that enter the pipeline are usually NOT coherently oriented
(measured: community `.obj` files have only 18-32% of the inner edges with a
consistent winding). A tristrip can only keep going if the mesh is coherently
oriented. That is why this module ORIENTS the mesh (flood-fill) BEFORE making
the strips; without it, the winding-aware encoder falls back to ~1
triangle/strip (= a triangle list).

Measured result (nico_low.obj, 897 triangles in 8 parts):
    triangle list : 2692 indices
    tristrip      : 1736 indices  (-35.5%)  with a correct winding by construction
The gain in the final `.bin` is small (~2-5%) because the strip data is ~13%
of the payload (vertices/normals/UVs/texture take most of the space).

Status
------
DEFAULT mode of the pipeline (strip_mode="connected"), checked IN THE GAME
(PCSX2): the PS2 GS flips the winding as we expected. For the old encoding
(triangle list) use `--strip-mode list`.

Usage
-----
    # measure the gain / check offline (3 checks, incl. the decode_strip oracle):
    python -m wepes3d.shared.model.strip_connected face.bin my.obj

    # create a .bin (connected is the default):
    python -m wepes3d import face.bin my.obj out.bin \
        --allow-recount --recalculate-normals --auto-fit

API:
    orient_coherent(triangles)            -> oriented triangles
    build_connected_strips(triangles)     -> list of strips (winding-aware)
    connected_strips_to_indices(strips)   -> int16 indices (PES format)
    decode_connected_strips(strips)       -> triangles (with the GS flip), to check
"""

from collections import defaultdict, deque
from typing import List, Tuple


# ============================================================================
# Coherent orientation of the mesh (flood-fill)
# ============================================================================

def orient_coherent(triangles: List[Tuple[int, int, int]]
                    ) -> List[Tuple[int, int, int]]:
    """
    Turns all triangles to a coherent winding, per connected component:
    neighbour triangles walk their shared edge in OPPOSITE directions. It runs
    a BFS from a seed and flips the neighbours that do not agree.

    Without this, meshes with mixed winding (common in community `.obj` files)
    cannot be turned into strips.
    """
    edge2tri = defaultdict(list)
    for ti, (a, b, c) in enumerate(triangles):
        for e in ((a, b), (b, c), (c, a)):
            edge2tri[frozenset(e)].append(ti)

    out: List[Tuple[int, int, int]] = [None] * len(triangles)  # type: ignore
    done = [False] * len(triangles)

    for seed in range(len(triangles)):
        if done[seed]:
            continue
        done[seed] = True
        out[seed] = triangles[seed]
        queue = deque([seed])
        while queue:
            t = queue.popleft()
            a, b, c = out[t]
            for (u, v) in ((a, b), (b, c), (c, a)):
                for nt in edge2tri[frozenset((u, v))]:
                    if nt == t or done[nt]:
                        continue
                    x, y, z = triangles[nt]
                    ndir = {(x, y), (y, z), (z, x)}
                    # a coherent neighbour walks (v, u); if it walks (u, v), flip it
                    out[nt] = (x, z, y) if (u, v) in ndir else (x, y, z)
                    done[nt] = True
                    queue.append(nt)
    return out


def orient_for_front(triangles: List[Tuple[int, int, int]],
                     verts: List[Tuple[float, float, float]],
                     normals: List[Tuple[float, float, float]]
                     ) -> List[Tuple[int, int, int]]:
    """
    Orients the mesh coherently (flood-fill) AND turns each connected
    component so it faces FORWARD according to `normals` (float x,y,z per
    LOCAL vertex).

    `orient_coherent` alone leaves the GLOBAL orientation of each component
    random (~a coin flip) — half of the components may end up facing
    "inwards". Here, after orienting, we choose the sign of each component by
    a vote of the dot product (geometric normal . average vertex normal): if
    most of it faces "backwards", we flip the whole component (keeping it
    coherent).

    Precondition for correct strips under the GS flip hypothesis.
    """
    def cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
    def sub(a, b): return (a[0]-b[0], a[1]-b[1], a[2]-b[2])
    def dot(a, b): return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]

    edge2tri = defaultdict(list)
    for ti, (a, b, c) in enumerate(triangles):
        for e in ((a, b), (b, c), (c, a)):
            edge2tri[frozenset(e)].append(ti)

    out: List[Tuple[int, int, int]] = [None] * len(triangles)  # type: ignore
    comp = [-1] * len(triangles)

    for seed in range(len(triangles)):
        if comp[seed] >= 0:
            continue
        comp[seed] = seed
        out[seed] = triangles[seed]
        members = [seed]
        queue = deque([seed])
        while queue:
            t = queue.popleft()
            a, b, c = out[t]
            for (u, v) in ((a, b), (b, c), (c, a)):
                for nt in edge2tri[frozenset((u, v))]:
                    if nt == t or comp[nt] >= 0:
                        continue
                    x, y, z = triangles[nt]
                    ndir = {(x, y), (y, z), (z, x)}
                    out[nt] = (x, z, y) if (u, v) in ndir else (x, y, z)
                    comp[nt] = seed
                    members.append(nt)
                    queue.append(nt)
        # votes the global orientation of the component using the normals
        score = 0.0
        for t in members:
            a, b, c = out[t]
            gn = cross(sub(verts[b], verts[a]), sub(verts[c], verts[a]))
            mn = ((normals[a][0]+normals[b][0]+normals[c][0])/3,
                  (normals[a][1]+normals[b][1]+normals[c][1])/3,
                  (normals[a][2]+normals[b][2]+normals[c][2])/3)
            score += dot(gn, mn)
        if score < 0:
            for t in members:
                a, b, c = out[t]
                out[t] = (a, c, b)
    return out


# ============================================================================
# Greedy, winding-aware strip building
# ============================================================================

def build_connected_strips(triangles: List[Tuple[int, int, int]]
                           ) -> List[List[int]]:
    """
    Builds connected tristrips. Each strip is a sequence of vertex indices
    [v0, v1, v2, v3, ...] where T_i = (v_i, v_{i+1}, v_{i+2}).

    Greedy: it starts from the triangle with the LOWEST degree (fewest free
    neighbours, so no triangle is left alone) and extends over the last edge.
    Winding-aware: it only extends when the triangle, after the alternating GS
    flip, keeps the winding of the source; otherwise it ends the strip (= adds
    a parity restart).

    Precondition: `triangles` must be coherently oriented (use
    orient_coherent first).
    """
    edge2tri = defaultdict(list)
    for ti, (a, b, c) in enumerate(triangles):
        for e in ((a, b), (b, c), (c, a)):
            edge2tri[frozenset(e)].append(ti)

    used = [False] * len(triangles)
    orient = [{(t[0], t[1], t[2]), (t[1], t[2], t[0]), (t[2], t[0], t[1])}
              for t in triangles]

    def opposite(t, e0, e1):
        s = set(triangles[t]); s.discard(e0); s.discard(e1)
        return next(iter(s)) if len(s) == 1 else None

    def free_degree(t):
        a, b, c = triangles[t]
        return sum(1 for e in ((a, b), (b, c), (c, a))
                   for nt in edge2tri[frozenset(e)] if nt != t and not used[nt])

    def neighbor(t, e0, e1):
        for nt in edge2tri[frozenset((e0, e1))]:
            if nt != t and not used[nt]:
                return nt
        return None

    strips: List[List[int]] = []
    for seed in sorted(range(len(triangles)), key=free_degree):
        if used[seed]:
            continue
        a, b, c = triangles[seed]
        used[seed] = True
        strip = [a, b, c]
        cur = seed
        pos = 1  # next position in the strip (T1 = odd -> the GS flips it)
        while True:
            q1, q2 = strip[-2], strip[-1]
            nt = neighbor(cur, q1, q2)
            if nt is None:
                break
            d = opposite(nt, q1, q2)
            if d is None:
                break
            rendered = (q1, q2, d) if pos % 2 == 0 else (q1, d, q2)
            if rendered not in orient[nt]:
                break  # the winding would be wrong -> end the strip (restart)
            used[nt] = True
            strip.append(d)
            cur = nt
            pos += 1
        strips.append(strip)
    return strips


# ============================================================================
# Encoding / decoding
# ============================================================================

def connected_strips_to_indices(strips: List[List[int]]) -> List[int]:
    """Serializes strips into PES int16 indices: 2 ADC (neg) + N kicks (pos)."""
    def neg(v): return (((v + 1) * 4) | 0x8000) - 0x10000
    def pos(v): return (v + 1) * 4
    out: List[int] = []
    for s in strips:
        if len(s) < 3:
            continue
        out.append(neg(s[0]))
        out.append(neg(s[1]))
        for v in s[2:]:
            out.append(pos(v))
    return out


def decode_connected_strips(strips: List[List[int]]
                            ) -> List[Tuple[int, int, int]]:
    """
    Decodes strips into triangles with the alternating GS flip (T_i is flipped
    when i is odd). Used to CHECK that the strip gives back the source
    triangles.
    """
    tris: List[Tuple[int, int, int]] = []
    for s in strips:
        for i in range(len(s) - 2):
            a, b, c = s[i], s[i + 1], s[i + 2]
            tris.append((a, b, c) if i % 2 == 0 else (a, c, b))
    return tris


def verify(triangles: List[Tuple[int, int, int]],
           strips: List[List[int]]) -> Tuple[bool, bool, bool]:
    """
    Returns (geometry_kept, winding_correct, oracle_ok).

    - geometry_kept / winding_correct: against our own decode_connected_strips
      (assumed GS behaviour).
    - oracle_ok: INDEPENDENT cross-check — runs the indices through the
      `strip.decode_strip` decoder (ported from the official plugin of the
      game) and checks that the SET of triangles matches. It makes sure the
      indices are well formed and decode into the right triangles with the
      real decoder, without depending on our flip hypothesis.
    """
    from .strip import decode_strip
    def cyc(t):
        a, b, c = t
        return min((a, b, c), (b, c, a), (c, a, b))
    dec = decode_connected_strips(strips)
    set_ok = ({frozenset(t) for t in triangles} == {frozenset(t) for t in dec}
              and len(dec) == len(triangles))
    wind_ok = {cyc(t) for t in triangles} == {cyc(t) for t in dec}

    vc = (max((v for s in strips for v in s), default=-1) + 1)
    indices = connected_strips_to_indices(strips)
    oracle_tris = decode_strip(indices, vc)
    oracle_ok = ({frozenset(t) for t in triangles}
                 == {frozenset(t) for t in oracle_tris}
                 and len(oracle_tris) == len(triangles))
    return set_ok, wind_ok, oracle_ok


# ============================================================================
# Demo / measurement
# ============================================================================

def _measure(template_path: str, obj_path: str) -> None:
    """Measures the gain against a triangle list on a real case, repeating the
    pipeline steps."""
    from ..io.bin_io import decompress_bin
    from .parser import parse_model
    from ..io.obj_io import parse_obj
    from ..pipeline.partition import (
        partition_mesh_by_faces, compute_new_ranges_from_sizes,
        assign_triangles_to_parts,
    )
    from .strip import triangles_to_pes_strip, align_strip_to_v4

    pl, _, _ = decompress_bin(template_path)
    tmpl = parse_model(pl)
    obj = parse_obj(obj_path)
    # auto-fit is not needed here (the partition by adjacency does not depend
    # on the scale), and skipping it keeps this asset-agnostic demo free of
    # any coord dependency.
    n_parts = len(tmpl.parts)
    wv, wu, wf, sizes = partition_mesh_by_faces(obj.vertices, obj.uvs, obj.faces, n_parts)
    ranges = compute_new_ranges_from_sizes(sizes)
    tpp = assign_triangles_to_parts(wf, ranges)

    tot_list = tot_strip = tot_tris = tot_strips = 0
    all_set = all_wind = all_oracle = True
    for i, tris in enumerate(tpp):
        oriented = orient_coherent(tris)
        strips = build_connected_strips(oriented)
        list_idx = align_strip_to_v4(triangles_to_pes_strip(oriented))
        strip_idx = align_strip_to_v4(connected_strips_to_indices(strips))
        set_ok, wind_ok, oracle_ok = verify(oriented, strips)
        all_set &= set_ok; all_wind &= wind_ok; all_oracle &= oracle_ok
        tot_list += len(list_idx); tot_strip += len(strip_idx)
        tot_tris += len(tris); tot_strips += len(strips)
        print(f"Part {i}: {len(tris):3d} tris | list={len(list_idx):4d} "
              f"strip={len(strip_idx):4d} in {len(strips):3d} strips "
              f"(avg {len(tris)/max(1,len(strips)):.1f}) "
              f"set={set_ok} wind={wind_ok} oracle={oracle_ok}")

    print(f"\nTOTAL {tot_tris} triangles | avg {tot_tris/max(1,tot_strips):.1f} tris/strip")
    print(f"  triangle list : {tot_list} indices")
    print(f"  tristrip      : {tot_strip} indices")
    print(f"  strip data reduction: {100*(1-tot_strip/max(1,tot_list)):.1f}% "
          f"({(tot_list-tot_strip)*2} bytes in the payload)")
    print(f"  [offline] geometry kept       : {all_set}")
    print(f"  [offline] consistent winding  : {all_wind}")
    print(f"  [offline] decode_strip oracle : {all_oracle}  "
          f"(the decoder gives back the same triangles)")
    print("\n[note] The checks above are OFFLINE; the alternating GS winding was")
    print("confirmed IN THE GAME (PCSX2) — connected is the default mode. See docs/05.")


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("usage: python -m wepes3d.shared.model.strip_connected TEMPLATE.bin MESH.obj")
        sys.exit(1)
    _measure(sys.argv[1], sys.argv[2])
