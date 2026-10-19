"""Writes a preview OBJ of a spare wheel cloned from the game's Mammoth wheel visual.

Usage (as a library): spare_part.write(out_path, axle_scale, radial_scale, centre, tilt, yaw=0)

In game the plugin clones the donor's wheel visual (Axles/WheelMeshes/FL/Mammoth_Wheel/Mammoth_wheel)
onto the car root with the definition's "spare" pose; this OBJ is the same wheel at the same pose,
for the offline renders and clearance checks only. The raw meshes (meshes/glyptodon/spare_raw/
Mammoth_{tyre,wheel}_LOD0.obj) are the game's Mesh assets exported by tools/export_named_mesh.py at
scale 1; the prefab draws them at x100 (tyre radius 0.53, width 0.372), axle along x, outer face
toward -x in Unity (+x in the OBJ). They are scaled like the road wheels (axle_scale, radial_scale),
the axle turned from lateral to upright and tilted outward by tilt degrees (outer edge down, outer
face up and out), then turned yaw degrees about the vertical (90 with tilt 90: the wheel stands with
its axle fore-aft and its outer face to the rear), and moved to centre (OBJ space, +x is the truck's
left). Vertices are coloured
dark for the tyre and grey for the rim.
"""
import math, os

import meshlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "meshes/glyptodon/spare_raw")
PREFAB_SCALE = 100.0
COLOURS = {"tyre": [0.12, 0.12, 0.12], "wheel": [0.45, 0.45, 0.45]}


def _transformed(path, sx, sr, phi, yaw, centre, colour):
    o = meshlib.Obj.read(path)
    c, s = math.cos(phi), math.sin(phi)
    cy, sy = math.cos(yaw), math.sin(yaw)

    def turn(x, y, z):
        x, y = x * c - y * s, x * s + y * c
        return [x * cy + z * sy, y, -x * sy + z * cy] if yaw else [x, y, z]

    o.v = [[a + b for a, b in zip(turn(p[0] * sx, p[1] * sr, p[2] * sr), centre)] for p in o.v]
    normals = []
    for n in o.vn:      # normals take the inverse scale before turning
        m = turn(n[0] / sx, n[1] / sr, n[2] / sr)
        length = math.sqrt(sum(q * q for q in m)) or 1.0
        normals.append([q / length for q in m])
    o.vn = normals
    o.color = [list(colour)] * len(o.v)
    return o


def write(out_path, axle_scale, radial_scale, centre, tilt, yaw=0.0):
    """Writes the tyre and rim (game LOD0) as one OBJ; returns its face count."""
    sx, sr = axle_scale * PREFAB_SCALE, radial_scale * PREFAB_SCALE
    phi = math.radians(90.0 - tilt)      # the OBJ +x (outer face) turns to (sin tilt, cos tilt, 0)
    merged = meshlib.Obj()
    for kind in ("tyre", "wheel"):
        part = _transformed(os.path.join(RAW, f"Mammoth_{kind}_LOD0.obj"), sx, sr, phi, math.radians(yaw), centre, COLOURS[kind])
        base_v, base_vt, base_vn = len(merged.v), len(merged.vt), len(merged.vn)
        merged.v += part.v
        merged.color += part.color
        merged.vt += part.vt
        merged.vn += part.vn
        merged.faces += [[(v + base_v, t + base_vt if t >= 0 else -1, n + base_vn if n >= 0 else -1) for v, t, n in f]
                         for f in part.faces]
    merged.header = [f"# spare wheel preview: game tyre and wheel LOD0 x{axle_scale:.3f} axle, x{radial_scale:.3f} radial, "
                     f"tilt {tilt}, centre {centre}" + (f", yaw {yaw}" if yaw else "")]
    merged.write(out_path)
    return len(merged.faces)
