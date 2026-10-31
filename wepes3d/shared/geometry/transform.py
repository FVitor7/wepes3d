"""
Geometria ASSET-AGNOSTICA: bounding box, auto-fit e calculo de normais.

As conversoes int16<->float (especificas de cada asset) NAO ficam aqui — estao
em `faces/profile.py` e `trophy/profile.py`, expostas via CoordSpace. As funcoes
abaixo recebem o conversor `int16_to_obj` quando precisam reverter os int16 do
template para o espaco OBJ.
"""

import math
from typing import Callable, List, Tuple


# ============================================================================
# Bounding box e auto-fit
# ============================================================================

def compute_obj_bbox(vertices: List[Tuple[float, float, float]]
                     ) -> Tuple[Tuple[float, float, float],
                                Tuple[float, float, float]]:
    """Retorna (min_xyz, max_xyz) das coordenadas de um array de vertices."""
    return (
        (min(v[0] for v in vertices),
         min(v[1] for v in vertices),
         min(v[2] for v in vertices)),
        (max(v[0] for v in vertices),
         max(v[1] for v in vertices),
         max(v[2] for v in vertices)),
    )


def compute_template_obj_bbox(template, int16_to_obj: Callable
                              ) -> Tuple[Tuple[float, float, float],
                                         Tuple[float, float, float]]:
    """Bbox de um template (Model) no espaco OBJ — reverte os int16 dos
    vertices de todas as parts para float e tira min/max.

    `int16_to_obj`: conversor stored->obj do asset (`profile.coord.int16_to_obj_vertex`)."""
    all_x: List[float] = []
    all_y: List[float] = []
    all_z: List[float] = []
    for part in template.parts:
        for (s0, s1, s2) in part.vertices:
            x, y, z = int16_to_obj(s0, s1, s2)
            all_x.append(x)
            all_y.append(y)
            all_z.append(z)
    return (
        (min(all_x), min(all_y), min(all_z)),
        (max(all_x), max(all_y), max(all_z)),
    )


def auto_fit_vertices(vertices: List[Tuple[float, float, float]],
                      template, int16_to_obj: Callable
                      ) -> List[Tuple[float, float, float]]:
    """
    Re-escala e re-posiciona vertices do OBJ para caber dentro do bbox do
    template.

    Usa escala UNIFORME (preserva proporcoes do rosto importado):
      - Calcula bbox do OBJ e do template (ambos em espaco float OBJ).
      - Escala uniformemente usando MIN ratio (rosto cabe inteiro no bbox).
      - Translada para alinhar centros.

    Sem isso, um .obj com posicao/escala arbitraria (vindo de fontes externas)
    fica fora do frustum do PES PS2 -> face invisivel no editor + jogo.
    """
    omin, omax = compute_obj_bbox(vertices)
    tmin, tmax = compute_template_obj_bbox(template, int16_to_obj)

    o_span = (omax[0] - omin[0], omax[1] - omin[1], omax[2] - omin[2])
    t_span = (tmax[0] - tmin[0], tmax[1] - tmin[1], tmax[2] - tmin[2])

    sx = t_span[0] / o_span[0] if o_span[0] > 0 else 1.0
    sy = t_span[1] / o_span[1] if o_span[1] > 0 else 1.0
    sz = t_span[2] / o_span[2] if o_span[2] > 0 else 1.0
    scale = min(sx, sy, sz)

    o_ctr = ((omin[0] + omax[0]) / 2,
             (omin[1] + omax[1]) / 2,
             (omin[2] + omax[2]) / 2)
    t_ctr = ((tmin[0] + tmax[0]) / 2,
             (tmin[1] + tmax[1]) / 2,
             (tmin[2] + tmax[2]) / 2)

    print(f"      OBJ bbox:      X[{omin[0]:.3f}..{omax[0]:.3f}] "
          f"Y[{omin[1]:.3f}..{omax[1]:.3f}] Z[{omin[2]:.3f}..{omax[2]:.3f}]")
    print(f"      Template bbox: X[{tmin[0]:.3f}..{tmax[0]:.3f}] "
          f"Y[{tmin[1]:.3f}..{tmax[1]:.3f}] Z[{tmin[2]:.3f}..{tmax[2]:.3f}]")
    print(f"      Escala uniforme: {scale:.4f} "
          f"(sx={sx:.4f}, sy={sy:.4f}, sz={sz:.4f})")

    return [
        ((x - o_ctr[0]) * scale + t_ctr[0],
         (y - o_ctr[1]) * scale + t_ctr[1],
         (z - o_ctr[2]) * scale + t_ctr[2])
        for (x, y, z) in vertices
    ]


# ============================================================================
# Calculo de normais
# ============================================================================

def compute_vertex_normals(
    vertices: List[Tuple[float, float, float]],
    faces: List[Tuple[int, int, int]],
) -> List[Tuple[float, float, float]]:
    """
    Calcula normais SUAVES por vertice como media ponderada por area dos
    triangulos vizinhos.

    Para cada face, normal_face = cross(b-a, c-a). A magnitude do cross
    eh proporcional a 2x a area do triangulo, entao somar essa normal
    pondera implicitamente por area. Normalizamos no final.

    Resultado: cada vertice recebe a media das normais das faces que o
    contem, ponderada por area. Bom default para faces sem informacao
    explicita de smoothing.
    """
    n = len(vertices)
    sx = [0.0] * n
    sy = [0.0] * n
    sz = [0.0] * n

    for (a, b, c) in faces:
        ax, ay, az = vertices[a]
        bx, by, bz = vertices[b]
        cx, cy, cz = vertices[c]

        e1x, e1y, e1z = bx - ax, by - ay, bz - az
        e2x, e2y, e2z = cx - ax, cy - ay, cz - az

        fnx = e1y * e2z - e1z * e2y
        fny = e1z * e2x - e1x * e2z
        fnz = e1x * e2y - e1y * e2x

        for vi in (a, b, c):
            sx[vi] += fnx
            sy[vi] += fny
            sz[vi] += fnz

    result: List[Tuple[float, float, float]] = []
    for i in range(n):
        length = math.sqrt(sx[i] ** 2 + sy[i] ** 2 + sz[i] ** 2)
        if length > 1e-10:
            result.append((sx[i] / length, sy[i] / length, sz[i] / length))
        else:
            result.append((0.0, 1.0, 0.0))   # fallback para vertices isolados
    return result
