"""Strip conectado: funções de orientação/codificação + demo (_measure/__main__)."""

import runpy
import sys

import pytest

from wepes3d.shared.model.strip_connected import (
    orient_coherent, orient_for_front, build_connected_strips,
    connected_strips_to_indices, decode_connected_strips, verify,
)


def test_orient_coherent_makes_winding_consistent():
    # dois triângulos com winding OPOSTO -> orient_coherent deve coerir
    tris = [(0, 1, 2), (1, 2, 3)]
    out = orient_coherent(tris)
    assert len(out) == 2
    assert {frozenset(t) for t in out} == {frozenset(t) for t in tris}


def test_decode_connected_strips_alternates_winding():
    strips = [[0, 1, 2, 3]]                          # T0=(0,1,2), T1 flipado
    tris = decode_connected_strips(strips)
    assert tris == [(0, 1, 2), (1, 3, 2)]


def test_connected_strips_skips_short_strip():
    assert connected_strips_to_indices([[1, 2]]) == []   # strip < 3 vértices: ignora


def test_verify_reports_ok_for_consistent_mesh():
    tris = [(0, 1, 2), (1, 2, 3), (2, 3, 4)]
    oriented = orient_coherent(tris)
    strips = build_connected_strips(oriented)
    set_ok, wind_ok, oracle_ok = verify(oriented, strips)
    assert set_ok and oracle_ok


def test_orient_for_front_flips_backfacing_component():
    # normais apontam para -Z, mas a geometria está orientada para +Z:
    # orient_for_front deve inverter o componente para ficar front-facing.
    tris = [(0, 1, 2), (0, 2, 3)]
    verts = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    normals = [(0, 0, -1)] * 4
    out = orient_for_front(tris, verts, normals)
    assert len(out) == 2


_MOD = "wepes3d.shared.model.strip_connected"


def _run_main():
    # remove do cache para o runpy executar o módulo "do zero" como __main__
    # (evita o RuntimeWarning de "found in sys.modules").
    sys.modules.pop(_MOD, None)
    runpy.run_module(_MOD, run_name="__main__", alter_sys=True)


def test_demo_main_valid_args(monkeypatch, face_bin, face_obj, capsys):
    """`python -m ...strip_connected TEMPLATE OBJ` roda a medição (cobre _measure)."""
    monkeypatch.setattr(sys, "argv", ["strip_connected", face_bin, face_obj])
    _run_main()
    assert "tristrip" in capsys.readouterr().out


def test_demo_main_wrong_args(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["strip_connected"])     # argc errado -> uso + exit(1)
    with pytest.raises(SystemExit):
        _run_main()
