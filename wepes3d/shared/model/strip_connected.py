"""
Codificacao de TRIANGLE STRIPS conectados (em vez de triangle list).
E' o modo PADRAO do pipeline (strip_mode="connected"), validado in-game.

Motivacao
---------
O `strip_encoder.py` de producao usa *triangle list*: 3 indices por triangulo,
cada um isolado em [neg, neg, pos]. Robusto e independente de winding, mas
gasta ~3x mais bytes no strip data que os strips conectados que o jogo usa.

Os strips ORIGINAIS do jogo sao conectados (no `face.bin`, 92 de 130 triangulos
por part sao "caso 3" = continuacao de strip) e decodificam com winding
ALTERNADO (+-+-+-). Como o `face.bin` renderiza perfeitamente, conclui-se que
o GS do PS2 **alterna o winding automaticamente** em primitivas de strip — como
toda GPU faz. Logo, strips conectados sao validos no jogo.

Pre-requisito CRITICO (a peca que faltava)
------------------------------------------
As malhas que entram no pipeline geralmente NAO sao coerentemente orientadas
(medido: `.obj` da comunidade tem so 18-32% das arestas internas com winding
consistente). Tristrip so encadeia se a malha for coerentemente orientada.
Por isso este modulo ORIENTA a malha (flood-fill) ANTES de stripificar; sem
isso, o encoder winding-aware degenera para ~1 triangulo/strip (= triangle list).

Resultado medido (nico_low.obj, 897 triangulos em 8 parts):
    triangle list : 2692 indices
    tristrip      : 1736 indices  (-35.5%)  com winding correto por construcao
O ganho no `.bin` final e' pequeno (~2-5%) porque o strip data e' ~13% do
payload (vertices/normais/UVs/textura dominam).

Status
------
Modo PADRAO do pipeline (strip_mode="connected"), validado IN-GAME (PCSX2): o GS
do PS2 alterna o winding como inferido. Para a codificacao antiga (triangle list)
use `--strip-mode list`.

Uso
---
    # medir ganho / validar offline (3 checks, incl. oracle decode_strip):
    python -m wepes3d.shared.model.strip_connected face.bin meu.obj

    # gerar um .bin (connected e' o default):
    python -m wepes3d import face.bin meu.obj saida.bin \
        --allow-recount --recalculate-normals --auto-fit

API:
    orient_coherent(triangles)            -> triangles orientados
    build_connected_strips(triangles)     -> lista de strips (winding-aware)
    connected_strips_to_indices(strips)   -> indices int16 (formato PES)
    decode_connected_strips(strips)       -> triangulos (com flip do GS) p/ verificar
"""

from collections import defaultdict, deque
from typing import List, Tuple


# ============================================================================
# Orientacao coerente da malha (flood-fill)
# ============================================================================

def orient_coherent(triangles: List[Tuple[int, int, int]]
                    ) -> List[Tuple[int, int, int]]:
    """
    Reorienta todos os triangulos para um winding coerente por componente
    conectado: triangulos vizinhos percorrem a aresta compartilhada em sentidos
    OPOSTOS. Faz BFS a partir de uma semente, flipando vizinhos inconsistentes.

    Sem isso, malhas com winding misto (caso comum em `.obj` da comunidade)
    nao stripificam.
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
                    # vizinho coerente percorre (v, u); se percorre (u, v), flipa
                    out[nt] = (x, z, y) if (u, v) in ndir else (x, y, z)
                    done[nt] = True
                    queue.append(nt)
    return out


def orient_for_front(triangles: List[Tuple[int, int, int]],
                     verts: List[Tuple[float, float, float]],
                     normals: List[Tuple[float, float, float]]
                     ) -> List[Tuple[int, int, int]]:
    """
    Orienta coerentemente (flood-fill) E alinha cada componente conectado para
    ficar FRONT-FACING segundo as `normals` (x,y,z float por vertice LOCAL).

    `orient_coherent` sozinho deixa a orientacao GLOBAL de cada componente
    arbitraria (~moeda) — metade dos componentes pode sair "para dentro". Aqui,
    apos orientar, decidimos o sinal de cada componente por votacao do produto
    escalar (normal geometrica . normal media dos vertices): se a maioria estiver
    "para tras", invertemos o componente inteiro (preservando a coerencia).

    Pre-condicao para strips corretos sob a hipotese de flip do GS.
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
        # vota a orientacao global do componente pelas normais
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
# Stripificacao greedy winding-aware
# ============================================================================

def build_connected_strips(triangles: List[Tuple[int, int, int]]
                           ) -> List[List[int]]:
    """
    Constroi tristrips conectados. Cada strip e' uma sequencia de indices de
    vertice [v0, v1, v2, v3, ...] onde T_i = (v_i, v_{i+1}, v_{i+2}).

    Greedy: seed pelo triangulo de MENOR grau (menos vizinhos livres, evita
    deixar triangulos orfaos), estende pela ultima aresta. Winding-aware:
    so estende se o triangulo, apos o flip alternado do GS, mantiver o winding
    da fonte; caso contrario encerra o strip (= insere restart de paridade).

    Pre-condicao: `triangles` deve estar coerentemente orientado
    (use orient_coherent primeiro).
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
        pos = 1  # proxima posicao no strip (T1 = impar -> GS flipa)
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
                break  # winding sairia errado -> encerra strip (restart)
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
    """Serializa strips em indices int16 PES: 2 ADC (neg) + N kicks (pos)."""
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
    Decodifica strips em triangulos aplicando o flip alternado do GS
    (T_i flipado quando i impar). Usado para VERIFICAR que o strip reproduz
    os triangulos da fonte.
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
    Retorna (geometria_preservada, winding_correto, oracle_ok).

    - geometria_preservada / winding_correto: contra o nosso proprio
      decode_connected_strips (semantica GS assumida).
    - oracle_ok: cross-check INDEPENDENTE — passa os indices pelo decoder de
      PRODUCAO `strip_encoder.decode_strip` (portado do plugin oficial do jogo)
      e confere que o CONJUNTO de triangulos bate. Garante que os indices sao
      bem-formados e decodificam nos triangulos certos pelo decoder real,
      sem depender da nossa hipotese de flip.
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
# Demo / medicao
# ============================================================================

def _measure(template_path: str, obj_path: str) -> None:
    """Mede o ganho vs triangle list num caso real, replicando o pipeline."""
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
    # auto-fit nao eh necessario aqui (a particao por adjacencia independe da
    # escala) e evita dependencia de coord neste demo asset-agnostico.
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
              f"strip={len(strip_idx):4d} em {len(strips):3d} strips "
              f"(avg {len(tris)/max(1,len(strips)):.1f}) "
              f"set={set_ok} wind={wind_ok} oracle={oracle_ok}")

    print(f"\nTOTAL {tot_tris} triangulos | avg {tot_tris/max(1,tot_strips):.1f} tris/strip")
    print(f"  triangle list : {tot_list} indices")
    print(f"  tristrip      : {tot_strip} indices")
    print(f"  reducao strip data: {100*(1-tot_strip/max(1,tot_list)):.1f}% "
          f"({(tot_list-tot_strip)*2} bytes no payload)")
    print(f"  [offline] geometria preservada : {all_set}")
    print(f"  [offline] winding consistente  : {all_wind}")
    print(f"  [offline] oracle decode_strip  : {all_oracle}  "
          f"(decoder de PRODUCAO reconstroi os mesmos triangulos)")
    print("\n[nota] As checagens acima sao OFFLINE; o winding alternado do GS foi")
    print("confirmado IN-GAME (PCSX2) — connected e' o modo padrao. Ver doc 05.")


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("uso: python -m wepes3d.shared.model.strip_connected TEMPLATE.bin MESH.obj")
        sys.exit(1)
    _measure(sys.argv[1], sys.argv[2])
