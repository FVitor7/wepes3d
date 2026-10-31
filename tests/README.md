# tests/ — suíte automatizada

Testes da ferramenta com **pytest** + **cobertura** (`pytest-cov`). Eles usam
arquivos **reais do jogo** (em [`seed/`](seed/)) para cobrir os 5 tipos de asset.

> O pacote em si (runtime) **não** tem dependências externas — só a stdlib do
> Python. O `pytest`/`pytest-cov` são dependências **só de teste**
> (ver [`../requirements-dev.txt`](../requirements-dev.txt)).

---

## Como rodar

Instale as dependências de teste e rode da raiz do repositório:

```bash
pip install -r requirements-dev.txt

# roda tudo + relatório de cobertura (já configurado no pyproject.toml):
python -m pytest
```

A configuração (em [`../pyproject.toml`](../pyproject.toml)) já liga
`--cov=wepes3d --cov-report=term-missing`. Para um relatório HTML:

```bash
python -m pytest --cov-report=html
# abra htmlcov/index.html
```

---

## O que cada arquivo testa

| Arquivo | Foco |
|---|---|
| `test_io.py` | compressão/descompressão `.bin`; leitura de `.obj` (triangulação, grupos); conversão 1 UV por vértice. |
| `test_coords.py` | `CoordSpace`: a conversão `int16 ↔ float` é **lossless** (face/troféu/estádio/PC). |
| `test_geometry.py` | bounding box, auto-fit, cálculo de normais. |
| `test_parser.py` | detecção (face/troféu), navegação e serialização (`write_model` lossless). |
| `test_reader_strip.py` | leitor universal de geometria + codificação/decodificação do strip. |
| `test_strip_connected.py` | tristrips conectados (orientação, encode, demo `_measure`). |
| `test_partition.py` | distribuição de vértices em parts (BFS, grupos, erros de fronteira). |
| `test_export.py` | export dos 5 tipos: face, troféu, estádio, kit, PES6 PC. |
| `test_import.py` | import face/troféu: roundtrip + cada estratégia de partição + erros. |
| `test_cli.py` | os 3 subcomandos (`export`/`import`/`list`), flags e tratamento de erro. |
| `test_public_api.py` | API de alto nível (`import_auto`/`export_auto` + compat). |
| `test_edge_cases.py` | caminhos de erro/defensivos (magics inválidos, seções inexistentes…). |

---

## Os arquivos-semente (`seed/`)

São arquivos reais, pequenos, um por caminho de código:

| Semente | Tipo | Notas |
|---|---|---|
| `face.bin` | face PS2 | 8 parts, 696 v (o mesmo de `examples/`). |
| `face.obj` | export da face | usado nos testes de import/roundtrip. |
| `trophy.bin` | troféu PS2 | container com **9 seções** (sub-modelos). |
| `stadium.str` | estádio (torcida) | bloco comprimido único, 1 modelo. |
| `stadium_data.bin` | estádio (container) | container com **0 modelos** (só dados/textura). |
| `adboard.bin` | estádio (placas) | container **com modelos** (caminho de scan). |
| `kit.bin` | kit (mãos) | 4 modelos (LODs). |
| `pc_face.bin` | face PES6 PC | formato `20050420`, 1 modelo. |
| `pc_trophy.str` | troféu PES6 PC | container com 9 partes. |

`.obj` sintéticos (grade, ilhas, fita) são **gerados em memória** pelos fixtures
do [`conftest.py`](conftest.py) — não precisam ficar no disco.

---

## Cobertura

A meta é **cobrir todo o código** do pacote. O que sobra sem cobertura são poucas
linhas **defensivas** (saídas de erro para arquivos corrompidos raros, expansão de
parts de troféu, e leitura de geometria multi-submesh que os arquivos-semente não
exercem). Rode com `--cov-report=term-missing` para ver exatamente quais.
