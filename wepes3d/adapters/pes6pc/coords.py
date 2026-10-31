"""
PES6/WE PC coordinates (OBJ/Blender space).

Different from PS2 (int16 + CoordSpace): on PC the vertices are already
float32 in the .bin; here we only apply the same conversion as the
pes_face_modifier.py plugin by Suat CAGDAS / PES Indie Team (the reference
used by pes6_bin_to_obj.py):

    X_obj = raw_z * 0.025
    Y_obj = raw_x * -0.025
    Z_obj = raw_y * -0.025
    UV    = (u, 1 - v)               # vertical flip of V

PC FACES and TROPHIES use the SAME space (checked: the pl.str trophy renders
the cup standing up; Kroos renders the face standing up).
"""

PC_SCALE = 0.025


def raw_to_obj_vertex(raw_x: float, raw_y: float, raw_z: float):
    """Raw float32 (raw_x, raw_y, raw_z) -> OBJ (x, y, z)."""
    return (raw_z * PC_SCALE, raw_x * -PC_SCALE, raw_y * -PC_SCALE)


def raw_to_obj_uv(u: float, v: float):
    """Raw UV -> OBJ (u, 1 - v)."""
    return (u, 1.0 - v)
