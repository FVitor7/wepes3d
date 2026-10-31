"""
Shared fixtures of the test suite.

- Exposes the real seed files (in `seed/`) as fixtures.
- Offers generators of synthetic `.obj` files (`write_obj`, `islands_obj`,
  `grid_obj`) to test the import paths without depending on an outside file.
"""

import pathlib

import pytest

HERE = pathlib.Path(__file__).resolve().parent
SEED = HERE / "seed"


def _seed(name: str) -> str:
    p = SEED / name
    assert p.exists(), f"missing seed: {p}"
    return str(p)


# ---------------------------------------------------------------------------
# Real seeds (game files)
# ---------------------------------------------------------------------------

@pytest.fixture
def face_bin():
    return _seed("face.bin")


@pytest.fixture
def face_obj():
    return _seed("face.obj")


@pytest.fixture
def trophy_bin():
    return _seed("trophy.bin")


@pytest.fixture
def stadium_str():
    return _seed("stadium.str")


@pytest.fixture
def stadium_data_bin():
    """Stadium container WITHOUT 3D models (only data/texture)."""
    return _seed("stadium_data.bin")


@pytest.fixture
def adboard_bin():
    """Stadium container WITH models (advertising boards)."""
    return _seed("adboard.bin")


@pytest.fixture
def kit_bin():
    return _seed("kit.bin")


@pytest.fixture
def pc_face_bin():
    return _seed("pc_face.bin")


@pytest.fixture
def pc_trophy_str():
    return _seed("pc_trophy.str")


# ---------------------------------------------------------------------------
# Synthetic .obj generators
# ---------------------------------------------------------------------------

@pytest.fixture
def write_obj(tmp_path):
    """Writes an .obj from lists of verts/uvs/faces (0-based).

    `groups`: a list parallel to `faces` with the group name of each face — it
    writes `o NAME` lines (used to test --use-groups).
    """
    def _w(verts, uvs, faces, groups=None, name="mesh.obj"):
        path = tmp_path / name
        lines = []
        for (x, y, z) in verts:
            lines.append(f"v {x:.6f} {y:.6f} {z:.6f}")
        for (u, v) in uvs:
            lines.append(f"vt {u:.6f} {v:.6f}")
        cur = None
        for i, (a, b, c) in enumerate(faces):
            if groups is not None and groups[i] != cur:
                cur = groups[i]
                lines.append(f"o {cur}")
            lines.append(f"f {a+1}/{a+1} {b+1}/{b+1} {c+1}/{c+1}")
        path.write_text("\n".join(lines) + "\n")
        return str(path)
    return _w


@pytest.fixture
def islands_obj(write_obj):
    """N independent "islands" (quads), with the vertices in sequential order.

    Each quad is 4 vertices + 2 triangles that stay INSIDE the block of 4 —
    so the vertices already come in sequential "islands". This lets us test
    --part-sizes [4,4,...] and --use-groups (1 group per island) without any
    triangle crossing a border.
    """
    def _make(n_islands=8, with_groups=False):
        verts, uvs, faces, groups = [], [], [], []
        for k in range(n_islands):
            base = len(verts)
            ox = float(k) * 2.0           # moves the islands apart on the X axis
            verts += [(ox, 0.0, 0.0), (ox + 1, 0.0, 0.0),
                      (ox + 1, 1.0, 0.0), (ox, 1.0, 0.0)]
            uvs += [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
            faces += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
            # The 1st island uses the "default" group (the parser already has it
            # at index 0), so N islands create EXACTLY N groups — no extra
            # "default" group is left over.
            name = "default" if k == 0 else f"part_{k}"
            groups += [name, name]
        return write_obj(verts, uvs, faces,
                         groups=groups if with_groups else None,
                         name=f"islands_{n_islands}.obj")
    return _make


@pytest.fixture
def ribbon_obj(write_obj):
    """A continuous ribbon with EXACTLY `n_verts` vertices (n_verts even).

    It has `n_verts/2` columns of 2 vertices, joined into quads. The triangles
    join vertices of neighbour columns, so they CROSS the sequential 87-vertex
    borders of the template — this forces the BFS fallback when the count
    matches the template (696).
    """
    def _make(n_verts=696):
        cols = n_verts // 2
        verts, uvs, faces = [], [], []
        for i in range(cols):
            verts.append((float(i), 0.0, 0.0))
            verts.append((float(i), 1.0, 0.0))
            uvs.append((i / cols, 0.0))
            uvs.append((i / cols, 1.0))
        for i in range(cols - 1):
            a, b = 2 * i, 2 * i + 1
            c, d = 2 * (i + 1), 2 * (i + 1) + 1
            faces.append((a, b, d))
            faces.append((a, d, c))
        return write_obj(verts, uvs, faces, name=f"ribbon_{n_verts}.obj")
    return _make


@pytest.fixture
def grid_obj(write_obj):
    """A continuous mesh (n×n grid on the Z=0 plane), good for testing the BFS."""
    def _make(n=8):
        verts, uvs, faces = [], [], []
        for j in range(n):
            for i in range(n):
                verts.append((float(i), float(j), 0.0))
                uvs.append((i / (n - 1), j / (n - 1)))
        def vid(i, j):
            return j * n + i
        for j in range(n - 1):
            for i in range(n - 1):
                a, b, c, d = vid(i, j), vid(i + 1, j), vid(i + 1, j + 1), vid(i, j + 1)
                faces.append((a, b, c))
                faces.append((a, c, d))
        return write_obj(verts, uvs, faces, name=f"grid_{n}.obj")
    return _make
