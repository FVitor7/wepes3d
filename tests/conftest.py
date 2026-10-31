"""
Fixtures compartilhadas da suíte.

- Expõe os arquivos-semente reais (em `seed/`) como fixtures.
- Oferece geradores de `.obj` sintéticos (`write_obj`, `islands_obj`, `grid_obj`)
  para exercitar os caminhos de import sem depender de um arquivo externo.
"""

import pathlib

import pytest

HERE = pathlib.Path(__file__).resolve().parent
SEED = HERE / "seed"


def _seed(name: str) -> str:
    p = SEED / name
    assert p.exists(), f"seed faltando: {p}"
    return str(p)


# ---------------------------------------------------------------------------
# Seeds reais (arquivos do jogo)
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
    """Container de estádio SEM modelos 3D (só dados/textura)."""
    return _seed("stadium_data.bin")


@pytest.fixture
def adboard_bin():
    """Container de estádio COM modelos (placas de publicidade)."""
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
# Geradores de .obj sintéticos
# ---------------------------------------------------------------------------

@pytest.fixture
def write_obj(tmp_path):
    """Escreve um .obj a partir de listas de verts/uvs/faces (0-based).

    `groups`: lista paralela a `faces` com o nome do grupo de cada face — gera
    linhas `o NOME` (usado para testar --use-groups).
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
    """N "ilhas" independentes (quads), em ordem sequencial de vértices.

    Cada quad são 4 vértices + 2 triângulos que ficam DENTRO do bloco de 4 —
    então os vértices já vêm em "ilhas" sequenciais. Isso permite testar
    --part-sizes [4,4,...] e --use-groups (1 grupo por ilha) sem que nenhum
    triângulo cruze a fronteira.
    """
    def _make(n_islands=8, with_groups=False):
        verts, uvs, faces, groups = [], [], [], []
        for k in range(n_islands):
            base = len(verts)
            ox = float(k) * 2.0           # afasta as ilhas no eixo X
            verts += [(ox, 0.0, 0.0), (ox + 1, 0.0, 0.0),
                      (ox + 1, 1.0, 0.0), (ox, 1.0, 0.0)]
            uvs += [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
            faces += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
            # A 1ª ilha usa o grupo "default" (o parser já o registra no índice 0),
            # então N ilhas geram EXATAMENTE N grupos — sem o "default" sobrando.
            name = "default" if k == 0 else f"part_{k}"
            groups += [name, name]
        return write_obj(verts, uvs, faces,
                         groups=groups if with_groups else None,
                         name=f"islands_{n_islands}.obj")
    return _make


@pytest.fixture
def ribbon_obj(write_obj):
    """Uma fita contígua com EXATAMENTE `n_verts` vértices (n_verts par).

    São `n_verts/2` colunas de 2 vértices, ligadas em quads. Os triângulos
    conectam vértices de colunas vizinhas, então eles CRUZAM as fronteiras
    sequenciais de 87 vértices do template — forçando o fallback BFS quando a
    contagem bate com a do template (696).
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
    """Uma malha contígua (grade n×n no plano Z=0), boa para testar o BFS."""
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
