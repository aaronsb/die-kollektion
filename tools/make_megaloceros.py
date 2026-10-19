"""Write vehicles/megaloceros.json, Das Megaloceros (Glyptodon-styled crew cab), from a few dimensions.

Usage: python3 tools/make_megaloceros.py && tools/preview_vehicle.sh vehicles/megaloceros.json

The Glyptodon's front, nose and running gear with a crew cab (meshes/glyptodon/cab_megaloceros_master.blend,
first spliced from the two-door cab the way crew cabs are built from two-doors: 1.127 m longer, a copy of the front
door behind it) on 3.70 m, the wheelbase of the long crew-cab reference
drawing. The bed starts behind the crew cab's rear wall and ends
1.28 m behind the rear axle, as on the Glyptodon (2.56 m long, inside the drawing's 2.70 maximum).
Under the longer cab the fuel tank drops below the cab floor between the battery box and the rear
step; the frame's rise, crossmembers, air tanks, silencer and tailpipe keep their distance from the
rear axle. The spare stands upright in its carrier at the front of the bed against the cab's rear
wall, on the right, tread outboard.

Storage boxes: the mechanic's truck's rounded black box (meshes/merchant/
Merchant_LOD*.obj, one each side, sharing the Mammoth's UV layout) hangs from the bed in the open bays,
shortened to fit, double-sided (the merchant's are open inboard) and on the unpainted black:
STORAGE_BOXES lists them; empty it to leave them off.
"""
import math

import meshlib
import glyptodon_family

CAB_EXTRA = 1.127
WHEELBASE = 3.70
r = round(glyptodon_family.FRONT_AXLE - WHEELBASE - glyptodon_family.GLYPTODON_REAR_AXLE, 3)   # -0.45: the rear axle's move from the Glyptodon's
BED_F = round(-0.03 - CAB_EXTRA, 3)
# Rail top under a bed mount: the frame rises 0.245 m from the dropped middle (top 0.725) to the rear
# rail (top 0.97) between 0.75 and 1.45 m behind the cab's rear wall on the two-door, moved with the axle.
RISE = (-0.75 + r, -1.45 + r)


def rail_top(z):
    t = min(1.0, max(0.0, (RISE[0] - z) / (RISE[0] - RISE[1])))
    return round(0.725 + 0.245 * t, 3)


SPARE_R, SPARE_HALF_W = glyptodon_family.SPARE_R, glyptodon_family.SPARE_HALF_W
BED_FLOOR = 1.225                    # the bed floor's top after the drop
HEADBOARD = BED_F - 0.06             # the bed's front panel
CARRIER = 0.05                       # the carrier's depth between the tyre and the headboard

# Storage boxes: (side, front z, rear z), the outer face 0.075 m inside the bed side, the top under the
# bed (the merchant's own height, y 0.62-1.14). Left and right between the cab and the rear wheels,
# clear of the tailpipe (z -1.67) and the forward guards and air tanks; right rear behind the rear
# wheel, clear of the trailing guard (z -3.13), where the reference truck carries its toolbox.
STORAGE_BOXES = [("left", -1.18, -1.58), ("right", -1.18, -1.70), ("right", -3.20, -3.68)]
BOX_SOURCE = {"left": {"x": [0.6, 1.0], "y": [0.55, 1.2], "z": [-1.4, -0.55]},
              "right": {"x": [-1.0, -0.6], "y": [0.55, 1.2], "z": [-1.4, -0.55]}}
BOX_OUTER_X = round(glyptodon_family.BED_HALF - 0.075, 3)
BOX_PARTS = "glyptodon/megaloceros_boxes_LOD{lod}.obj"


def write_boxes():
    """Writes the storage boxes, placed, one OBJ per LOD (each LOD of the merchant has one box a side)."""
    for lod in range(4):
        src = meshlib.Obj.read(f"meshes/merchant/Merchant_LOD{lod}.obj")
        out = meshlib.Obj()
        out.header = [f"# Das Megaloceros storage boxes: the merchant's box (Merchant_LOD{lod}), placed by tools/make_megaloceros.py"]
        out.vt.append(list(glyptodon_family.BLACK))
        for side, front, rear in STORAGE_BOXES:
            (idx, lo, hi), = [pc for pc in meshlib.pieces(src) if meshlib.matches_select(pc[1], pc[2], len(pc[0]), BOX_SOURCE[side])]
            keep = set(idx)
            sx = 1.0 if side == "left" else -1.0
            outer = hi[0] if side == "left" else lo[0]
            k = (front - rear) / (hi[2] - lo[2])
            remap, nmap = {}, {}
            for f in src.faces:
                if f[0][0] not in keep:
                    continue
                face = []
                for v, vt, vn in f:
                    if v not in remap:
                        p = src.v[v]
                        remap[v] = len(out.v)
                        out.v.append([p[0] - outer + sx * BOX_OUTER_X, p[1], rear + (p[2] - lo[2]) * k])
                        out.color.append(None)
                    if vn >= 0 and vn not in nmap:
                        n = src.vn[vn]
                        m = [n[0], n[1], n[2] / k]          # normals take the inverse scale
                        length = math.sqrt(sum(c * c for c in m)) or 1.0
                        nmap[vn] = len(out.vn)
                        out.vn.append([c / length for c in m])
                    face.append((remap[v], 0, nmap.get(vn, -1)))
                # Both windings: the merchant's boxes are open on their inboard side, and its right
                # one is wound inside out, so each face goes in twice, back to back.
                out.faces += [face, face[::-1]]
        out.write(f"meshes/{BOX_PARTS.format(lod=lod)}")


write_boxes()
glyptodon_family.write({
    "codename": "Megaloceros",
    "displayName": "Das Megaloceros",
    "description": "Das Megaloceros took one look at the square-jawed two-door and asked where everyone else was supposed to sit. A second row of doors, a roof that keeps going, and still a bed behind it long enough for the gear nobody admits to packing. Built for crews who measure a trip in days and a road in theory.",
    "listing": {
        "family": "Glyptodon", "variant": "crew cab",
        "real": {"make": "Mercedes-Benz", "model": "Unimog U 1300 L (styled)", "series": "435", "variant": "crew cab",
                 "years": "",
                 "description": "No crew-cab U 1300 L was built. The nearest real reference is the U 1550 L/37 crew cab: 3.70 m wheelbase, 5.56 m overall, 1.01 m front overhang, a 2.70 m body starting 70 mm behind the cab, and a 15.8 m turning circle on 12.5R20 tyres.",
                 "basis": "Fictional: this model never came as a crew cab. The two-door's front and running gear with a crew cab, on the 3.70 m wheelbase of the U 1550 L/37 crew-cab drawing."},
    },
    "itemId": 3000000004,
    "wheelbase": WHEELBASE,
    "cab": "cab_megaloceros",
    "cabExtra": CAB_EXTRA,
    "bedSelectZ": [-4.0, 0.2],
    "bedMounts": tuple((x, z, rail_top(z)) for z in (round(BED_F - 0.07, 3), round(BED_F - 0.42, 3)) for x in (-0.41, 0.41)),
    "fuelTank": {"x": [-0.98, -0.47], "y": [0.60, 0.95], "z": [-0.645, -0.205]},
    # The downpipe's long run under the crew cab's rear section, 2 cm lower than the two-door's, so it passes
    # well under the dropped rail rather than leaving a slot along it.
    "downpipe": [[0.28, 0.92, 1.40], [0.32, 0.80, 1.00], [0.42, 0.62, 0.60], [0.52, 0.47, 0.20],
                 [0.55, 0.47, round(-0.66 + r, 3)], [0.55, 0.55, round(-0.88 + r, 3)], [0.55, 0.73, round(-0.98 + r, 3)]],
    "airTanks": [dict(t, points=[[-0.575, p[1], round(p[2] + r, 3)] for p in t["points"]]) for t in glyptodon_family.GLYPTODON_AIR_TANKS],
    "spare": {"pose": "upright", "x": round(-(glyptodon_family.BED_HALF - 0.04 - SPARE_R - 0.01), 3),
              "y": round(BED_FLOOR + 0.005 + SPARE_R, 3), "z": round(HEADBOARD - CARRIER - SPARE_HALF_W, 3)},
    "sparePreview": "glyptodon/spare_preview_megaloceros.obj",
    "extraParts": [BOX_PARTS] if STORAGE_BOXES else [],
})
