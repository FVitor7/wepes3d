# Second-pass review — attacking the first audit (November 2026)

This review tries to **break** the conclusions of the
[engineering audit](2026-11-engineering-audit.md), and looks for what it
missed. It does not repeat that report: finding IDs `A-xx` point to it, new
findings are `B-xx`. No source file was changed. Reproductions are in
[`tests/test_audit_second_pass.py`](../../tests/test_audit_second_pass.py).

Same rules as before: **CONFIRMED** (reproduced or proven), **PROBABLE**
(strong evidence), **HYPOTHESIS** (needs reverse engineering or PCSX2).
Nothing was run in PCSX2.

---

## Summary

| Conclusion of the first audit | Attack | Result |
|---|---|---|
| A-06 — the game uses an *absolute* strip parity | 4 parity models against the game's normals; random-mesh property test | **Stands.** New nuance: the visible effect may differ per asset (§1.1) |
| The connected encoder never loses a triangle | 1,800 random meshes, 6 adversarial families | **Stands.** One side effect found (B-04) |
| The export reader is right on real files | independent address-based decoder on every seed part | **Stands.** A-10 is the only failure mode |
| Derived fields are right for the face layout | field-by-field check after recounts; search for more pointers in the model header | **Stands.** Nothing else to move |
| The trophy container update is safe | scan for absolute pointers in other sections; byte compare | **Stands.** Two weak spots (B-05, B-06) |
| The zero-diff oracle equals the hardware on real files | the GS firing rule on synthetic strips | **Narrowed.** True for game files only (B-02) |
| A-19 — parts above ~480 VU qwords may break | the project's own test outputs | **Weakened**, open question for the maintainer (§1.6) |
| A-18 — `face.bin` normals match no axis mapping | all 48 signed permutations | **Stands** |
| A-03 — the stale `payload[0x10]` pointer is critical | what the block is | **Narrowed:** binary fact stands; in-game impact PROBABLE (§1.8) |

**New:** 8 findings. The most important one: **all 9 real face/hair
templates draw their parts with 3–4 different textures**, and the importer
fills those parts without looking at the texture (B-01). Only `face.bin`
uses one texture.

**Updated top five risks (both passes):** A-01 (trophy colour program),
A-03 (face pointer), **B-01** (multi-texture templates), A-02 (unsupported
sections), A-04 (empty parts). A-06 moves down: its effect depends on
back-face culling, which the data suggests may not be the same for every
asset.

---

## 1. Attacks on the first audit

### 1.1 Winding parity (A-06)

**Attack 1 — other parity models.** If the encoders' model were right in a
form I did not test, one of these would fit the game's normals:

| Parity model | Trophy sec0 | Kits | Real faces/hair |
|---|---|---|---|
| absolute index (export reader) | **99.7%** | **100%** | **91.1%** |
| count kicks only | 67.1% | 48.4% | 37.7% |
| reset at each ADC pair (encoders) | 63.2% | 41.9% | 39.0% |
| reset at any ADC | 36.8% | 58.1% | 61.0% |

Only the absolute model fits. **Attack 2 — is it just `face.obj`?** A
property test on 60 random meshes (grids, random winding, fans, soups) shows
that connected strips are reversed whenever a strip starts at an odd index
(`test_a06_connected_strips_keep_the_winding_under_absolute_parity`). The
conclusion stands.

**What changed — the visible effect.** Two facts do not fit a single story:

1. Real faces/hair agree only 91% (trophies 99.7%, kits 100%). The 9% that
   disagree look like double-sided hair cards. If hair is drawn
   double-sided, back-face culling is off for those parts, and winding
   errors there are invisible.
2. Bug 8 in [06](../06-bug-history.md#bug-8--reversed-triangle-winding)
   says one global flip of a list strip turned a face from *completely
   invisible* to *fully visible*. Under the absolute parity, a list strip
   always has half of its triangles on each side, before and after the
   flip. No parity model that fits the game data can give "all invisible →
   all visible" with per-triangle culling.

So either culling is not per triangle for faces, or the invisible face of
Bug 8 had another cause (Bug 10 — also "invisible in the game" — was fixed
in the same period). **Outcome:** the inconsistency in A-06 is certain; its
visible effect is a HYPOTHESIS and may be "holes on trophies, nothing on
faces". The PCSX2 test T1 below settles it.

### 1.2 The connected encoder keeps every triangle

1,800 random meshes in 6 families — regular grids, random winding, triangle
soups, non-manifold fans (3+ triangles on an edge), exact duplicates,
double-sided pairs on shared vertices, degenerate triangles — went through
`orient_coherent → build_connected_strips → connected_strips_to_indices`
and back through `decode_strip`. **The triangle multiset was kept in 1,800
of 1,800.** The encoder is also self-consistent under its own model (1,800
of 1,800). What it gets wrong is only the parity model (A-06) and one side
effect of the orientation (B-04).

### 1.3 The export reader

An address-based decoder (it reads the VU address of every submesh from
its UNPACK IMMED and maps each strip index exactly) was compared with
`read_part_geometry` on every part of every seed (face, 9 trophy sections,
kit, stadium, boards) and, in the first pass, on 3,453 real parts. Same
triangle sets everywhere. **Narrowing of A-10:** the `diff` guess never
fails on game files; it fails on files whose strip does not use the last
vertex of a part — files that this importer writes when vertices are left
unused (A-21).

### 1.4 Derived fields and the model header

- **Face layout, decoded as VIF code** (prologue at `0xB0`):
  `STCYCL 1/1 · STMOD 1 · UNPACK V4-16 @0 NUM 2` (qw0 = `(flag,0,4,vbe)`,
  qw1 = `(0,0,ss,se)`) · `STMOD 0 · STMASK · UNPACK S-32 masked @0` ·
  `STMASK · STMOD 1 · UNPACK V4-16 @2 NUM 2` (qw2 = `(0,0,4,vbe)`, qw3 =
  `(vbe,…)`) · `STMOD 0 · UNPACK V2-16 masked @2` (`vc`) · `STCYCL 4/1`. Every
  field that the rebuilder writes is one of these values: the face formulas
  are right.
- **Recounts checked field by field:** a sphere into `face.bin` (all parts
  consistent, `model+0x2C` right) and into trophy **sec1** (consistent; the
  other 8 sections byte-identical; texture container identical).
- **More pointers in the model header?** In all 117 models: `+0x28`,
  `+0x30`, `+0x34` are 0; `+0x38` is a count and `+0x3C` points to a table of
  texture IDs **inside** the model header. A resize does not have to move
  anything else.
- **Outer file header:** bytes `0x0C..0x1F` are zero and there is no data
  after the zlib stream in all 16 face/trophy files, so `compress_bin` keeps
  nothing stale.

### 1.5 Trophy pointer update

No uint32 inside sections 1–8 of the 6 trophies is an absolute offset that
lands on the start of a section or a container after the parts of sec0, so
moving those sections unchanged is safe (and they stay byte-identical after
a real recount, §1.4). The heuristic itself has two weak spots (B-05, B-06), with no hit
in real files.

### 1.6 VU budget per part (A-19)

The project's own test outputs (in the maintainer's work folder) go far
beyond the game: `list.bin` and `nico_strip.bin` (8 parts, up to 191
vertices per part) end their strips at VU addresses 964 and 887; Konami
never goes above 480. **If those files drew every triangle in PCSX2, the
512-qword (double buffer) idea is false** and the real limit is VU1's 1,024
qwords. The hard limit of A-05 does not change.

### 1.7 `face.bin` (A-18)

Attack: maybe its normals use an axis order I did not try. All 48 signed
permutations were tested; the best median |cos| is 0.10 (random level),
against 0.96 for the 9 other faces. Its normals do not belong to its
geometry. Its origin (a community tool) is still a HYPOTHESIS.

### 1.8 `payload[0x10]` in face templates (A-03)

The block starts with `94 72 85 29 01 00 00 00 80 xx 00 00 0y 00 00 00` in
all 9 files. The pointer going stale is a fact. **Whether the game reads
this block is not known**, so the in-game impact is PROBABLE, not
CONFIRMED.

---

## 2. New findings

| ID | Sev. | Status | One line |
|---|---|---|---|
| B-01 | HIGH | CONFIRMED (structure) · PROBABLE (in game) | real face/hair templates use 3–4 textures; the import ignores the texture of each part |
| B-02 | MEDIUM | CONFIRMED | `decode_strip` skips `[pos, neg, pos]` windows that the GS draws |
| B-03 | MEDIUM | HYPOTHESIS | rich templates keep per-part words (`0x90/0x94`, …) that probably index the bone data |
| B-04 | LOW | CONFIRMED | `orient_coherent` may flip one copy of an exact duplicate triangle |
| B-05 | LOW | CONFIRMED (code) | face `patch_resize` scans 12 KB of bone data for two magic values |
| B-06 | LOW | CONFIRMED (code) | trophy `patch_resize` uses the *new* payload length as its upper bound |
| B-07 | MEDIUM | CONFIRMED | parts added with `--max-verts-per-part` clone the donor's texture, per-part words and colour program |
| B-08 | LOW | HYPOTHESIS | the "12 × 128.0 bbox" of [04 §7](../04-vif-and-vu1.md#7-frustum-culling-bbox-in-the-part-header) is not a bbox |

### B-01 — Multi-texture templates are filled without looking at the texture

- **Where:** `pipeline/partition.py` (all strategies), `importer._import`
  (part *i* of the partition goes into template part *i*, keeping its
  `tex_id` at `part+0x34`).
- **What:** every real face/hair template draws its parts with different
  textures: `face_1..5`, `h1`: `[1, 3, 2, 0, 0, 0]`; `h2`, `h3`: `[0, 1, 1, 1]`;
  `h4`: `[0, 2, 2, 1, 2]` (the count is in the model header at `+0x38`). The
  `.obj` has one UV layout for one texture, but its pieces land in parts
  that sample other textures. Only `face.bin` (`tex_id` 0 everywhere) and
  the trophy sec0 parts (all 0) are safe.
- **Expected:** route triangles by material (`usemtl` → `tex_id`), or refuse
  a multi-texture template when the `.obj` has one material.
- **Actual:** silent; the import "COMPLETES SUCCESSFULLY".
- **Test:** `test_b01_*` (a copy of `face.bin` with `tex_id` `[1,3,2,0,…]`).
- **Fix:** read `usemtl` in `parse_obj`; group parts by `tex_id`; partition
  each material into the parts of its texture; refuse when it cannot.

### B-02 — The zero-diff oracle skips a window that the GS draws

- **Where:** `strip.decode_strip` (cases `nnp`, `npp`, `ppp` only); the same
  function is the oracle of `strip_connected.verify`.
- **What:** the GS fires a triangle on every vertex without ADC once three
  are queued — also for `[pos, neg, pos]` (one ADC between two kicks). The
  export reader draws it; `decode_strip` does not. Game files never contain
  this window (0 of 78,520), but files from other tools can, and then the
  passthrough sees a "missing" triangle and rebuilds a part that did not
  change (Bug 13 again, with another pattern).
- **Test:** `test_b02_*`. **Fix:** fire on any non-ADC index after two
  entries (like the reader), and keep the distinct-index check.

### B-03 — Rich templates: per-part words that probably point into the bone data

- **Where:** part header, kept by `rebuild_part`, copied by
  `clone_part_structure`.
- **What:** in `face_1.bin` (bones in `pre_parts`), these words change from
  part to part: `0x90` and `0x94` (`0x000C0000`, `0x0090000E`, …; `0, 14, 25,
  67, 72, 46`), `0x20/0x28/0x38` (144/146 vs 150/152), and floats at
  `0x48..0x58`, `0x80..0x88`. They look like references into the skinning
  tables. They are kept when the part gets other vertices, and copied when a
  part is cloned. [01 §4](../01-bin-format.md#4-simple-vs-rich-templates)
  only warns about the bone area itself.
- **Fix:** until they are understood, refuse a recount on templates with a
  bone area (or document it as unsupported).

### B-04 — Duplicates can become double-sided

`orient_coherent([(0,1,2), (0,1,2)])` returns `[(0,1,2), (0,2,1)]`: the copy
is flipped because it "walks" the shared edges in the same direction. Inside
a larger mesh the result depends on the BFS order. A z-fighting duplicate
in the `.obj` becomes a double-sided pair in the game. **Fix:** detect
duplicates before the flood-fill and keep them as they are.

### B-05 — The face pointer scan looks at bone data

`faces/profile.patch_resize` scans all of `pre_parts` — 12 KB of bone data
in rich templates — and rewrites any uint32 equal to `parts_end` or
`parts_end − 16`. With the model at `0x20` the second value has no meaning
(the real relative field is `parts_end − 0x20`, written later). No hit in the
9 real files, but a bone word with one of these values would be corrupted
on resize. **Fix:** patch the known fields only (`payload[0x0C..]` entries
and `model+0x2C`).

### B-06 — The trophy pointer bound uses the new length

`trophies/profile.patch_resize` moves outer-header values in
`[orig_parts_end, len(payload))`, where `payload` is the **new** payload. A
field equal to the old payload length is moved when the payload grows but
not when it shrinks. No such field exists in the 6 trophies. **Fix:** use
the old length, or patch known fields only.

### B-07 — Cloned parts inherit everything from the last part

`parser.clone_part_structure(donor)` copies the donor's header (including
`tex_id`, the per-part words of B-03, and for trophies the colour program
with the **donor's** `vc` and addresses). A fix of A-01 must also rebuild
the program of cloned parts; a fix of B-01 must choose the texture of each
new part. Today every added face part uses the texture of the last
template part.

### B-08 — The part "bbox" is probably not a bbox

[04 §7](../04-vif-and-vu1.md#7-frustum-culling-bbox-in-the-part-header)
says the 12 floats at `0x60..0x8C` (all `128.0` in `face.bin`) form a
bounding box. In trophy sec0 they are `(0, 0, 0, 128)` rows, and in parts
with the prologue at `0xD0` there are other floats at `0x90..0xAF` that look
like real bounds (`-655.3, -78.6, -358.9` and `-340.8, 0, 353.9`). `128.0` is the usual PS2
"1.0" for colours. If a real bbox exists, it is in the layouts that the
rebuilder does not support yet (A-02) — it must be recomputed when they are.

---

## 3. PCSX2 tests that would close the open questions

Each test is one small file; each answer changes the fix plan.

| # | Question | How | If yes | If no |
|---|---|---|---|---|
| T1 | Does the game cull back faces, with an absolute parity? | Same trophy part twice: all triangles at even indices / all at odd indices (one ADC pad) | A-06 is HIGH for that asset | winding is cosmetic there |
| T2 | Is the VU budget 512 qwords? | Did `list.bin` / `nico_strip.bin` draw fully? Then: one part with 120 and one with 190 vertices | budget = ~480–512 | budget = 1,024 |
| T3 | Which sign do normals need? | A trophy with the original normals vs the same with recalculated ones | A-08 fix as written | keep the sign, fix only the length |
| T4 | Is the trophy colour program read? | Import with the A-01 fix, and a copy with a red colour qword | the program matters | only the overwrite of vertices matters |
| T5 | Which texture does each `tex_id` select? | `h2.bin` with one part's `tex_id` changed | B-01 fix needs the table at `model+0x3C` | — |

---

## 4. Tests added

`tests/test_audit_second_pass.py`:

- **Passing (attacks that did not break the first audit):** reader vs
  address-based decoder on every seed part; absolute parity fits the game's
  normals (trophy and kit seeds) and the encoders' model does not; the
  connected encoder keeps the triangle multiset on random meshes; the model
  header has no pointer that a resize must move.
- **Strict xfail:** B-01, B-02, and the property-level proof of A-06.

With both test files: `189 passed, 19 xfailed`, coverage 97.8%.
