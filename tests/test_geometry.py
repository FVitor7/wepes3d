"""Asset-agnostic geometry: bbox, auto-fit and normals."""

import math

from wepes3d import decompress_bin, parse_model
from wepes3d.adapters.pesweps2.faces.profile import COORD as FACE
from wepes3d.shared.geometry.transform import (
    compute_obj_bbox, compute_template_obj_bbox, auto_fit_vertices,
    compute_vertex_normals,
)


def test_compute_obj_bbox():
    verts = [(0, 0, 0), (2, -1, 5), (-3, 4, 1)]
    mn, mx = compute_obj_bbox(verts)
    assert mn == (-3, -1, 0)
    assert mx == (2, 4, 5)


def test_template_bbox_and_autofit(face_bin):
    payload, _, _ = decompress_bin(face_bin)
    template = parse_model(payload)
    tmin, tmax = compute_template_obj_bbox(template, FACE.int16_to_obj_vertex)
    assert tmin[0] < tmax[0]

    # a tiny, shifted .obj must be fitted inside the template bbox
    verts = [(100, 100, 100), (101, 100, 100), (100, 101, 100), (100, 100, 101)]
    fitted = auto_fit_vertices(verts, template, FACE.int16_to_obj_vertex)
    fmin, fmax = compute_obj_bbox(fitted)
    # small tolerance: the center was aligned and the scale is uniform (min)
    assert fmin[0] >= tmin[0] - 1e-6 and fmax[0] <= tmax[0] + 1e-6


def test_autofit_degenerate_axis(face_bin):
    payload, _, _ = decompress_bin(face_bin)
    template = parse_model(payload)
    # all vertices at the SAME point -> span 0 on every axis (scale=1.0)
    verts = [(5, 5, 5)] * 4
    fitted = auto_fit_vertices(verts, template, FACE.int16_to_obj_vertex)
    assert len(fitted) == 4


def test_vertex_normals_unit_length():
    verts = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
    faces = [(0, 1, 2)]
    normals = compute_vertex_normals(verts, faces)
    for nx, ny, nz in normals:
        assert math.isclose(math.sqrt(nx*nx + ny*ny + nz*nz), 1.0, abs_tol=1e-6)
    # triangle on the Z plane -> the normal points to +Z (or -Z)
    assert abs(normals[0][2]) == 1.0


def test_vertex_normals_isolated_fallback():
    # vertex 3 is not used by any face -> fallback (0,1,0)
    verts = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (9, 9, 9)]
    faces = [(0, 1, 2)]
    normals = compute_vertex_normals(verts, faces)
    assert normals[3] == (0.0, 1.0, 0.0)
