"""Particionamento: atribuição de triângulos e estratégias (unitário)."""

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
    assert out[1] == [(0, 1, 2)]            # índices LOCAIS (relativos à part)


def test_assign_triangles_vertex_out_of_range():
    with pytest.raises(ValueError):
        assign_triangles_to_parts([(0, 1, 9)], [(0, 3), (3, 6)])   # v9 fora de tudo


def test_assign_triangles_crosses_boundary():
    with pytest.raises(ValueError):
        assign_triangles_to_parts([(0, 1, 4)], [(0, 3), (3, 6)])   # cruza fronteira


def test_bfs_more_parts_than_faces():
    verts = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
    uvs = [(0, 0), (1, 0), (0, 1)]
    faces = [(0, 1, 2)]
    # 1 face mas 4 parts pedidas -> sobram parts vazias (cobre o break do BFS)
    nv, nu, nf, sizes = partition_mesh_by_faces(verts, uvs, faces, 4)
    assert sum(sizes) >= 3


def test_partition_by_obj_groups_ignores_out_of_range_gidx():
    verts = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
    uvs = [(0, 0), (1, 0), (0, 1)]
    faces = [(0, 1, 2)]
    # face_groups com índice >= n_groups deve ser ignorada
    nv, nu, nf, sizes = partition_by_obj_groups(verts, uvs, faces, [5], n_groups=2)
    assert len(sizes) == 2
