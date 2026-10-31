"""
Coordenadas do PES6/WE PC (espaco OBJ/Blender).

Diferente do PS2 (int16 + CoordSpace): no PC os vertices ja sao float32 no
.bin; aqui so aplicamos a mesma conversao do plugin pes_face_modifier.py de
Suat CAGDAS / PES Indie Team (a referencia do pes6_bin_to_obj.py):

    X_obj = raw_z * 0.025
    Y_obj = raw_x * -0.025
    Z_obj = raw_y * -0.025
    UV    = (u, 1 - v)               # flip vertical do V

FACE e TROFEU do PC usam o MESMO espaco (validado: troqueu pl.str renderiza taca
em pe; Kroos renderiza rosto em pe).
"""

PC_SCALE = 0.025


def raw_to_obj_vertex(raw_x: float, raw_y: float, raw_z: float):
    """float32 cru (raw_x, raw_y, raw_z) -> OBJ (x, y, z)."""
    return (raw_z * PC_SCALE, raw_x * -PC_SCALE, raw_y * -PC_SCALE)


def raw_to_obj_uv(u: float, v: float):
    """UV cru -> OBJ (u, 1 - v)."""
    return (u, 1.0 - v)
