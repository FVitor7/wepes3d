"""Partitioning: triangle assignment and strategies (unit tests)."""

from collections import Counter

import pytest

from wepes3d.shared.pipeline.partition import (
    assign_triangles_to_parts, compute_new_ranges_from_sizes,
    partition_mesh_by_faces, partition_by_obj_groups,
)


def test_compute_ranges():
    assert compute_new_ranges_from_sizes([2, 3]) == [(0, 2), (2, 5)]


def test_assign_triangles_ok():
    ranges = [(0, 3), (3, 6)]
    out = assign_triangles_to_parts([(0, 1, 2), (3, 4, 5)], ranges)
    assert out[0] == [(0, 1, 2)]
    assert out[1] == [(0, 1, 2)]            # LOCAL indices (relative to the part)


def test_assign_triangles_vertex_out_of_range():
    with pytest.raises(ValueError):
        assign_triangles_to_parts([(0, 1, 9)], [(0, 3), (3, 6)])   # v9 is outside every range


def test_assign_triangles_crosses_boundary():
    with pytest.raises(ValueError):
        assign_triangles_to_parts([(0, 1, 4)], [(0, 3), (3, 6)])   # cruza fronteira


def test_bfs_more_parts_than_faces():
    verts = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
    uvs = [(0, 0), (1, 0), (0, 1)]
    faces = [(0, 1, 2)]
    # 1 face but 4 parts asked -> some parts stay empty (covers the BFS break)
    nv, nu, nf, sizes = partition_mesh_by_faces(verts, uvs, faces, 4)
    assert sum(sizes) >= 3


def _grid(n):
    """n×n grid on the Z=0 plane: (verts, uvs, faces), 0-based."""
    verts = [(float(i), float(j), 0.0) for j in range(n) for i in range(n)]
    uvs = [(i / (n - 1), j / (n - 1)) for j in range(n) for i in range(n)]
    faces = []
    for j in range(n - 1):
        for i in range(n - 1):
            a, b = j * n + i, j * n + i + 1
            c, d = (j + 1) * n + i + 1, (j + 1) * n + i
            faces += [(a, b, c), (a, c, d)]
    return verts, uvs, faces


def test_bfs_max_verts_is_a_hard_limit():
    # Bug 16: the limit used to be only an average (parts went over it)
    verts, uvs, faces = _grid(12)                       # 144 v, 242 faces
    nv, nu, nf, sizes = partition_mesh_by_faces(verts, uvs, faces, 4, max_verts=20)
    assert max(sizes) <= 20
    assert len(sizes) > 4                               # extra parts were created
    # every face is kept exactly once (positions are unique in a grid)
    assert Counter(frozenset(nv[x] for x in t) for t in nf) == \
        Counter(frozenset(verts[x] for x in t) for t in faces)
    # and every triangle stays inside one part
    assign_triangles_to_parts(nf, compute_new_ranges_from_sizes(sizes))


def test_bfs_limit_not_reached_gives_the_same_result():
    verts, uvs, faces = _grid(12)
    free = partition_mesh_by_faces(verts, uvs, faces, 4)
    capped = partition_mesh_by_faces(verts, uvs, faces, 4, max_verts=255)
    assert capped == free
    assert len(free[3]) == 4


def test_partition_by_obj_groups_ignores_out_of_range_gidx():
    verts = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
    uvs = [(0, 0), (1, 0), (0, 1)]
    faces = [(0, 1, 2)]
    # a face_groups entry with index >= n_groups must be ignored
    nv, nu, nf, sizes = partition_by_obj_groups(verts, uvs, faces, [5], n_groups=2)
    assert len(sizes) == 2
