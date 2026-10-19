"""The Glyptodon-family vehicle definition, shared by Das Glyptodon (two-door) and Das Megaloceros (crew cab).

Usage (as a library): glyptodon_family.write(TRUCK) with a dict of the truck's own parameters; see
tools/make_glyptodon.py and tools/make_megaloceros.py.

Mammoth donor, with the Glyptodon cab and front (lenses, indicators and side flashers included) from
vehicles/<name>/meshes/<cab>_LOD*.obj, exported from its Blender master vehicles/<name>/<cab>_master.blend
(tools/build_cab_part.sh), the Mastodon's stakeless ribbed bed widened to the Glyptodon's, portal axles,
coils and the soft suspension. Everything under the bed is the Glyptodon's own, built from boxes and
tubes placed at the reference model's frame, tank, battery, air-tank and exhaust positions: the Mammoth's step box, round
tank, side-exit exhaust and rear fender skirts are removed. Every position that follows the rear axle
derives from the wheelbase; the frame's rise, crossmembers B-F, silencer and tailpipe keep their
distance from the rear axle (shift REAR_SHIFT from the Glyptodon's 3.25 m), and the bed starts just
behind the cab, whose rear wall a crew cab moves back by cabExtra. Proportions follow the dimensioned
drawing (a dimensioned reference drawing): wheelbase 3250, track 1860, bed ending 1280
behind the rear axle, about 2300 overall width.

Ride height: the drawing and the reference photos agree that the bed's lower edge sits 0.71 m above the
hub, the cab roof 2.03 m, the underbody at mid-wheelbase level with the hub, and the diff 0.07 m
under it (440 mm on the drawing's 12.5R20s, whose hub it draws 0.51 m up). At rest the hub sits
0.01 m over the modelled 0.45 (SUSPENSION below; the anchor read as measured up from full extension,
which driving bore out), so the body rides 0.05 m deeper on its wheels than drawn: the
tyres sit tighter in their arches by choice. The cab and frame come from the reference model as drawn; the bed sits directly
on bearers on the rails, with steel drop sides 0.575 m tall as on the reference truck.

The spare wheel is a clone of the donor's own wheel visual (the definition's "spare" block, placed by
the plugin), so it keeps the tyre material; tools/spare_part.py writes the same wheel at the same pose
for the offline renders. On the two-door it lies in a carrier under the bed front on the left, as in
the reference photos; on the crew cab, whose rear cab covers that spot, it stands upright in the same carrier
at the front of the bed against the cab's rear wall. Slanted sheet-steel guards hang from the bed
ahead of and behind each rear tyre.
"""
import json, math, os

import spare_part


def mirrored(box):
    """A box and its mirror across x = 0 (the OBJ's +x is the truck's left)."""
    return [box, dict(box, x=[-box["x"][1], -box["x"][0]])]


def both_sides(tube):
    flip = dict(tube, points=[[-p[0], p[1], p[2]] for p in tube["points"]])
    return [tube, flip]


def both_plates(plate):
    flip = dict(plate, corners=[[-p[0], p[1], p[2]] for p in plate["corners"]])
    return [plate, flip]


def shifted(z, by):
    """z moved by `by`, rounded to the millimetre; z itself when `by` is zero, so the Glyptodon's
    numbers come out exactly as written."""
    return round(z + by, 3) if by else z


TRACK = 1.86
TYRE = {"radius": 0.545, "width": 0.352}   # Continental MPT 80 14.5R20: 1090 mm overall, 352 mm section
FRONT_AXLE, DONOR_WHEELBASE = 1.22, 2.53
GLYPTODON_REAR_AXLE = -2.03          # the 3.25 m truck the undercarriage was placed on
HUB_Y = 0.45                         # the donor's modelled hub height
# Suspension (VPP wheel colliders): the spring and damper the other Kollektion trucks ride on, with
# 0.10 m of preload so the truck droops 0.30 m (was 0.40) and sits 0.05 m deeper in its arches than
# before, while full bump stays where it was (0.11 m over the modelled hub): travel 0.40, anchor
# 0.725. Static compression from full extension is the wheel load over the rate, less the preload;
# the anchor is the modelled pose's height up the travel from full extension.
SUSPENSION = {"travel": 0.40, "anchor": 0.725, "springRate": 18300, "damperRate": 4500, "preloadDistance": 0.10,
              "bumpTravelOffset": 0.03}
WHEEL_LOAD = 7300.0                  # N per wheel: 3200 kg over four
COMPRESSION = WHEEL_LOAD / SUSPENSION["springRate"] - SUSPENSION["preloadDistance"]
HUB_REST = round(HUB_Y + COMPRESSION - SUSPENSION["anchor"] * SUSPENSION["travel"], 3)        # 0.46
HUB_FULL_BUMP = round(HUB_Y + (1 - SUSPENSION["anchor"]) * SUSPENSION["travel"], 3)           # 0.56
BED_HALF = 1.125                     # 2.25 m outer, inside the drawing's 2330 overall
BED_WIDEN = round(BED_HALF - 0.875, 3)
BED_DROP = 0.10                      # the Mammoth bed's lower edge, 1.243, down to 0.73 m over the hub at rest
BED_BOTTOM = round(1.243 - BED_DROP, 3)
# Drop sides 0.575 m tall: the Mammoth slats above their bottom edge (1.314 before the drop) scale up,
# keeping the two grooves evenly placed; raised ribs fill in at the grooves' pitch.
SIDE_HEIGHT = 0.575
SLAT_BASE = 1.314
SIDE_SCALE = round((1.243 + SIDE_HEIGHT - SLAT_BASE) / (1.715 - SLAT_BASE), 4)


def side_y(y):
    """A height on the Mammoth bed side (before the drop) after the sides are made taller and lowered."""
    return round((SLAT_BASE + (y - SLAT_BASE) * SIDE_SCALE if y > SLAT_BASE else y) - BED_DROP, 3)


# Black parts (bumper, flares, frame, undercarriage, guards) take an unpainted black: the skin's 54-grey
# where Mammoth_masks is zero, so liveries do not tint it as they do the Mammoth bumper's (0.04, 0.504).
BLACK, PAINT = [0.0264, 0.124], [0.635, 0.59]
GROOVE = (side_y(1.461) + side_y(1.492)) / 2
RIB_PITCH = 0.044
RIB_YS = [round(GROOVE + k * RIB_PITCH, 3) for k in range(-3, 7) if k != 0]
SIDE_OUT = BED_HALF - 0.019          # the slats' outer face
LAMP_X, LAMP_Y = 0.885, 1.04         # the rear lamp blocks' lens centre

# Slanted sheet-steel guards hanging from the bed (as on a reference truck on the same 14.5R20s), both 0.448 m
# long and leaning 28 degrees from upright, mirrored about the rear axle: behind each rear tyre, down
# and back from 0.44 m behind the axle, leaving room for the axle's travel; ahead of it, down and
# forward to a foot 0.62 m ahead of the axle, above the tailpipe.
# Each has a rolled lip down its outboard edge like the front flares' (whose outer edge turns 6 cm
# down toward the tyre over 3 cm), here 4 cm over 1.8 cm; the trailing guard carries a 0.10 m rubber
# flap from its lower edge. Profiles are (z, y) in side view.
GUARD_LENGTH = 0.448
GUARD_SLOPE = (0.28, -0.523)                 # (z, y) direction down the trailing guard; the leading one mirrors it
GUARD_X = (0.72, 1.12)
LIP = [(-0.02, 0.0), (0.0, 0.0), (0.012, 0.01), (0.018, 0.025), (0.018, 0.04)]   # (outboard, toward the tyre)
FLAP_LENGTH = 0.10

# The donor's tyre as modelled, and the spare: a clone of its front-left wheel visual, scaled like the
# road wheels (the game's mesh is 0.53 m radius, 0.372 m wide).
WHEEL = {"radius": 0.52, "width": 0.4}
SPARE_SOURCE = "Axles/WheelMeshes/FL/Mammoth_Wheel/Mammoth_wheel"
HEADLIGHTS = {
    "notes": [
        "Halogen headlights. kelvin is the headlight colour temperature to aim for: the halogen lamps of this truck's",
        "period run near 3200 K, against the game's shared headlight at about 4200 K. The headlight and its glow on the",
        "ground (the bounce light) both move by that step from the game's own colours, so the glow stays as much whiter",
        "than the beam as the game made it. intensity is a factor on the game's: 0.8, as halogens give less light. The",
        "plugin applies both to this vehicle's own copies of the configs at spawn; stock cars keep theirs."
    ],
    "kelvin": 3200,
    "intensity": 0.8
}
SPARE_AXLE_SCALE, SPARE_RADIAL_SCALE = TYRE["width"] / WHEEL["width"], TYRE["radius"] / WHEEL["radius"]
SPARE_R, SPARE_HALF_W = 0.53 * SPARE_RADIAL_SCALE, 0.372 / 2 * SPARE_AXLE_SCALE
# The spare's carrier, after a sketch (from above): a
# stamped pan against the tyre's inner face, wide (0.52 m) at its mounting end and tapering to 0.35 m
# at the far end, with pressed lips down its long edges; across its far end a skid bar, the carrier's
# outermost part, longer than the pan is wide but inside the tyre's outline (ends 0.55 m from its
# centre), whose ends sweep up smoothly to the tyre so an empty carrier slides over obstacles. All of
# it follows the spare's pose.
PAN_U, PAN_HALF_V = (-0.14, 0.33), (0.26, 0.175)
SKID_U = PAN_U[1] + 0.02

SEG = {0: (24, 12, 16), 1: (16, 8, 10), 2: (12, 6, 8), 3: (8, 4, 6)}

# Undercarriage pieces under the cab and between the axles, as placed on the 3.25 m Glyptodon (from
# the reference model's Fuel Tank, Battery Box, Brake Air System and Exhaust layers); a truck may replace them.
GLYPTODON_FUEL_TANK = {"x": [-0.98, -0.47], "y": [0.74, 1.12], "z": [-0.92, -0.38]}   # right side, tucked under the bed
GLYPTODON_AIR_TANKS = [{"points": [[-0.565, 0.88, -1.28], [-0.565, 0.88, -1.64]], "radius": 0.13, "sides": 12},   # right
                       {"points": [[-0.565, 0.64, -1.40], [-0.565, 0.64, -1.75]], "radius": 0.13, "sides": 12}]
# Bed mounts on the rails: (x, z, rail top under it), over the dropped and sloped rail.
GLYPTODON_BED_MOUNTS = ((-0.41, -0.40, 0.74), (0.41, -1.05, 0.83), (-0.41, -1.05, 0.83))
# The two-door's spare: tilted 16 degrees with the outer edge down so its tread faces out, the
# tread's outer edge flush with the bed side (x 1.11), behind the cab under the bed front. Placed by
# search for the most room to the cab, bed, step and guards; the left rail and a crossmember pass
# through its hidden underside. "bearer" is where the left bed bearer starts, behind it.
UNDER_BED_SPARE = {"pose": "under", "tilt": 16.0, "outerX": 1.11, "y": 0.86, "z": -0.35, "bearer": -0.95}


def write(truck):
    """Writes vehicles/<name>/vehicle.json for one Glyptodon-family truck and its spare's preview OBJ."""
    WHEELBASE = truck["wheelbase"]
    CAB, CAB_EXTRA = truck.get("cab", "cab_glyptodon"), truck.get("cabExtra", 0.0)
    d_wb = WHEELBASE - 2.90              # rear shift beyond the Mastodon's, whose numbers these started from
    REAR_AXLE = FRONT_AXLE - WHEELBASE
    REAR_SHIFT = round(REAR_AXLE - GLYPTODON_REAR_AXLE, 3)
    BED_F = round(-0.03 - CAB_EXTRA, 3)   # headboard just behind the cab's rear wall (z ~0.0 on the two-door)
    BED_E = round(REAR_AXLE - 1.275, 3)  # bed end: 1.28 m behind the rear axle
    BED_SHIFT_FWD = round(BED_F - (-0.85), 3)                       # the Mammoth bed front sits at z -0.85 after the stretch
    BED_REAR_EXTRA = round(BED_E - (-2.165 - (WHEELBASE - DONOR_WHEELBASE)), 3)   # its end sits at -2.165 less the stretch
    BED = {"y": [1.2, 1.8], "z": truck.get("bedSelectZ", [-3.5, 0.2]), "minSize": {"x": 1.5}}
    BED_BACKING = [   # painted panels behind the slats, as on the Mastodon
        {"x": [0.81 + BED_WIDEN, 0.845 + BED_WIDEN], "y": [1.305, 1.6], "z": [BED_E + 0.029, BED_F - 0.029]},
        {"x": [-0.845 - BED_WIDEN, -0.81 - BED_WIDEN], "y": [1.305, 1.6], "z": [BED_E + 0.029, BED_F - 0.029]},
        {"x": [-0.845 - BED_WIDEN, 0.845 + BED_WIDEN], "y": [1.305, 1.6], "z": [BED_F - 0.06, BED_F - 0.03]},
        {"x": [-0.845 - BED_WIDEN, 0.845 + BED_WIDEN], "y": [1.305, 1.6], "z": [BED_E + 0.03, BED_E + 0.06]},
    ]
    BED_BACKING = [dict(b, y=[side_y(b["y"][0]), side_y(b["y"][1])]) for b in BED_BACKING]
    # The bed's lower skirt (y 1.143-1.196 after the drop) is a single outward sheet: with the Mammoth's
    # bottom cover gone its inside shows from below and ahead, so it gets a solid filling.
    SKIRT = [{"x": [BED_HALF - 0.032, BED_HALF - 0.002], "y": [BED_BOTTOM + 0.002, BED_BOTTOM + 0.054], "z": [BED_E + 0.002, BED_F - 0.002]},
             {"x": [-BED_HALF + 0.002, -BED_HALF + 0.032], "y": [BED_BOTTOM + 0.002, BED_BOTTOM + 0.054], "z": [BED_E + 0.002, BED_F - 0.002]},
             {"x": [-BED_HALF + 0.002, BED_HALF - 0.002], "y": [BED_BOTTOM + 0.002, BED_BOTTOM + 0.054], "z": [BED_E + 0.002, BED_E + 0.03]},
             {"x": [-BED_HALF + 0.002, BED_HALF - 0.002], "y": [BED_BOTTOM + 0.002, BED_BOTTOM + 0.054], "z": [BED_F - 0.03, BED_F - 0.002]}]
    # Ribs: the upper groove (1.461-1.492 on the Mammoth side) sets the pitch; ten lines in all run from
    # just above the plain lower band to just under the top rail, the lower groove capping the band.
    RIBS = [box for y in RIB_YS for box in (
        *mirrored({"x": [SIDE_OUT - 0.006, SIDE_OUT + 0.008], "y": [y - 0.008, y + 0.008], "z": [BED_E + 0.02, BED_F - 0.03]}),
        {"x": [-SIDE_OUT + 0.01, SIDE_OUT - 0.01], "y": [y - 0.008, y + 0.008], "z": [BED_E + 0.011, BED_E + 0.025]})]

    # Rear lamps: the Mammoth's upper rectangular blocks (red brake lens and orange indicator, y 0.97-1.11,
    # their rear face at z -2.549 less d_wb after the stretch) move to the bed end, tucked under its rear
    # corners on brackets from the crossmember; its lower round lamps and their bar go. The tow hitch
    # moves to the crossmember too.
    LAMP_REAR, HITCH_REAR = round(-2.433 - d_wb, 3), round(-2.645 - d_wb, 3)
    LAMPS = [{"x": [0.79, 0.96], "y": [0.69, 0.85], "z": [LAMP_REAR - 0.01, LAMP_REAR + 0.16]},
             {"x": [-0.96, -0.79], "y": [0.69, 0.85], "z": [LAMP_REAR - 0.01, LAMP_REAR + 0.16]}]
    LAMP_BLOCKS = [{"x": [0.7, 1.05], "y": [0.95, 1.12], "z": [round(-2.6 - d_wb, 3), round(-2.4 - d_wb, 3)]},
                   {"x": [-1.05, -0.7], "y": [0.95, 1.12], "z": [round(-2.6 - d_wb, 3), round(-2.4 - d_wb, 3)]}]
    LAMP_BLOCK_SHIFT = round(BED_E - 0.005 - round(-2.549 - d_wb, 3), 3)
    HITCH = {"x": [-0.2, 0.2], "y": [0.85, 1.02], "z": [HITCH_REAR - 0.01, HITCH_REAR + 0.15]}
    LAMP_Z = BED_E - 0.04                # light nodes just behind the lenses

    spare = truck.get("spare", UNDER_BED_SPARE)
    left_bearer = spare.get("bearer", BED_F)
    r = REAR_SHIFT
    # Undercarriage, positions from the reference model (frame layers, Fuel Tank, Battery Box, Brake Air System,
    # Transmission, Exhaust Pipe and Muffler). Rails: high over the front axle, dropped under the cab,
    # rising again ahead of the rear axle, out to a rear crossmember at the bed end.
    UNDER_BOXES = (
        mirrored({"x": [0.37, 0.43], "y": [0.75, 0.91], "z": [0.55, 2.30]})            # rail, front
        + mirrored({"x": [0.37, 0.43], "y": [0.57, 0.74], "z": [shifted(-0.75, r), 0.15]})   # rail, dropped middle
        + mirrored({"x": [0.37, 0.43], "y": [0.82, 0.98], "z": [BED_E, shifted(-1.45, r)]})  # rail, rear
        # Bed bearers on the rails (the two-door's left one starting behind the spare), with mounts
        # over the dropped and sloped rail.
        + [{"x": [0.37, 0.45], "y": [0.98, BED_BOTTOM], "z": [BED_E, left_bearer]},
           {"x": [-0.45, -0.37], "y": [0.98, BED_BOTTOM], "z": [BED_E, BED_F]}]
        + [box for x, z, y in truck.get("bedMounts", GLYPTODON_BED_MOUNTS)
           for box in [{"x": [x - 0.035, x + 0.035], "y": [y, 0.98], "z": [z - 0.05, z + 0.05]}]]
        + [
            {"x": [-0.44, 0.44], "y": [0.75, 0.91], "z": [2.15, 2.30]},     # front crossmember
            {"x": [-0.44, 0.44], "y": [0.67, 0.81], "z": [0.47, 0.57]},     # crossmembers A-F
            {"x": [-0.40, 0.40], "y": [0.64, 0.83], "z": [shifted(-0.93, r), shifted(-0.85, r)]},
            {"x": [-0.44, 0.44], "y": [0.72, 0.82], "z": [shifted(-1.09, r), shifted(-0.99, r)]},
            {"x": [-0.44, 0.44], "y": [0.83, 0.93], "z": [shifted(-1.36, r), shifted(-1.22, r)]},
            {"x": [-0.72, 0.72], "y": [0.85, 0.95], "z": [shifted(-1.82, r), shifted(-1.72, r)]},
            {"x": [-0.40, 0.40], "y": [0.82, 0.98], "z": [shifted(-2.74, r), shifted(-2.66, r)]},
            {"x": [-0.45, 0.45], "y": [0.75, 1.00], "z": [BED_E, BED_E + 0.22]},   # rear crossmember with the lamps
            truck.get("fuelTank", GLYPTODON_FUEL_TANK),
            {"x": [-0.81, -0.46], "y": [0.67, 0.97], "z": [-0.19, 0.28]},   # battery box, right side
            {"x": [-0.30, 0.30], "y": [0.42, 0.70], "z": [-0.45, 0.37]},    # divorced transmission, level with the hub
            {"x": [-0.36, 0.36], "y": [0.92, 1.30], "z": [0.62, 1.85]},     # engine, behind grille and bumper, over the diff at full bump
        ]
        + mirrored({"x": [0.43, 0.76], "y": [0.98, 1.02], "z": [BED_E + 0.01, BED_E + 0.06]})   # lamp brackets
        # Upper coil seats, as the reference model's spring perches: a cup plate over each coil on a plate off the rail.
        # The front plates stop at x 0.615, clear of the tyre at full lock and full bump.
        + [box for z, x0, x1, y0 in ((FRONT_AXLE, 0.455, 0.615, 0.75), (REAR_AXLE, 0.48, 0.69, 0.82)) for box in (
            *mirrored({"x": [x0, x1], "y": [1.02, 1.045], "z": [z - 0.10, z + 0.10]}),
            *mirrored({"x": [0.43, x0], "y": [y0, 1.045], "z": [z - 0.10, z + 0.10]}))]
    )

    def guard(top, direction, sx):
        """A guard plate from top (z, y) along direction (z, y), its lip on the outboard edge, on side sx."""
        dz, dy = direction
        n = math.hypot(dz, dy)
        dz, dy = dz / n, dy / n
        bottom = (top[0] + dz * GUARD_LENGTH, top[1] + dy * GUARD_LENGTH)
        # The side of the plate facing the rear wheel's centre at full bump.
        nz, ny = -dy, dz
        if (REAR_AXLE - top[0]) * nz + (HUB_FULL_BUMP - top[1]) * ny < 0:
            nz, ny = -nz, -ny
        at = lambda end, x, t: [round(sx * x, 4), round(end[1] + ny * t, 4), round(end[0] + nz * t, 4)]
        plates = [{"corners": [at(top, GUARD_X[0], 0), at(top, GUARD_X[1], 0), at(bottom, GUARD_X[1], 0), at(bottom, GUARD_X[0], 0)],
                   "thickness": 0.006}]
        for (o0, t0), (o1, t1) in zip(LIP, LIP[1:]):
            x0, x1 = GUARD_X[1] + o0, GUARD_X[1] + o1
            plates.append({"corners": [at(top, x0, t0), at(top, x1, t1), at(bottom, x1, t1), at(bottom, x0, t0)], "thickness": 0.004})
        return plates, bottom

    GUARDS, FLAPS = [], []
    for sx in (1, -1):
        rear, rear_bottom = guard((REAR_AXLE - 0.44, BED_BOTTOM), (-GUARD_SLOPE[0], GUARD_SLOPE[1]), sx)
        lead_top = REAR_AXLE + 0.62 - GUARD_LENGTH * GUARD_SLOPE[0] / math.hypot(*GUARD_SLOPE)
        front, _ = guard((lead_top, BED_BOTTOM), GUARD_SLOPE, sx)
        GUARDS += rear + front
        FLAPS.append({"x": sorted([sx * GUARD_X[0], sx * GUARD_X[1]]), "y": [round(rear_bottom[1] - FLAP_LENGTH, 4), round(rear_bottom[1], 4)],
                      "z": [round(rear_bottom[0] - 0.006, 4), round(rear_bottom[0], 4)]})

    # The spare's pose: its centre, and a frame for its carrier: `out` along its lower face (the face
    # the carrier holds) toward the carrier's far end, `along` across the carrier, and its axis (from
    # the lower face into the tyre). Lying under the bed, the axis tilts SPARE_TILT up and out; standing
    # behind the cab, it points back from the cab, and `out` points up.
    if spare["pose"] == "under":
        tilt = spare["tilt"]
        t = math.radians(tilt)
        centre = [round(spare["outerX"] - (SPARE_R * math.cos(t) + SPARE_HALF_W * math.sin(t)), 3), spare["y"], spare["z"]]
        out_dir, along_dir, axis_dir = (math.cos(t), -math.sin(t), 0.0), (0.0, 0.0, 1.0), (math.sin(t), math.cos(t), 0.0)
        yaw, rotation = 0.0, [0.0, 0.0, tilt - 90.0]
    else:
        tilt = 90.0
        centre = [spare["x"], spare["y"], spare["z"]]
        out_dir, along_dir, axis_dir = (0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, -1.0)
        yaw, rotation = 90.0, [0.0, -90.0, 0.0]

    def on_spare(u, v, off):
        """A point in the spare's own frame: u along `out` and v along `along` in the plane of its
        lower face, off along its axis from that face (negative: outside it)."""
        h = off - SPARE_HALF_W
        return [round(centre[k] + u * out_dir[k] + v * along_dir[k] + h * axis_dir[k], 4) for k in range(3)]

    CARRIER_PLATES = [{"corners": [on_spare(PAN_U[0], -PAN_HALF_V[0], -0.011), on_spare(PAN_U[1], -PAN_HALF_V[1], -0.011),
                                   on_spare(PAN_U[1], PAN_HALF_V[1], -0.011), on_spare(PAN_U[0], PAN_HALF_V[0], -0.011)],
                       "thickness": 0.006}]
    CARRIER_PLATES += [{"corners": [on_spare(PAN_U[0], side * PAN_HALF_V[0], -0.008), on_spare(PAN_U[1], side * PAN_HALF_V[1], -0.008),
                                    on_spare(PAN_U[1], side * PAN_HALF_V[1], -0.04), on_spare(PAN_U[0], side * PAN_HALF_V[0], -0.04)],
                        "thickness": 0.005} for side in (-1, 1)]
    SKID = [{"points": [on_spare(SKID_U, v, -0.032 + rise) for v, rise in
                        ((-0.42, 0.030), (-0.39, 0.016), (-0.35, 0.005), (-0.30, 0.0), (0.30, 0.0), (0.35, 0.005), (0.39, 0.016), (0.42, 0.030))],
             "radius": 0.02, "sides": 8}]

    TAILPIPE_Z = shifted(-1.32, r)       # the drawing's exit, under the forward guard
    UNDER_TUBES = (
        both_sides({"points": [[0.40, 0.83, 0.55], [0.40, 0.655, 0.15]], "radius": 0.07, "sides": 4, "square": True})
        + both_sides({"points": [[0.40, 0.655, shifted(-0.75, r)], [0.40, 0.90, shifted(-1.45, r)]], "radius": 0.07, "sides": 4, "square": True})
        + truck.get("airTanks", GLYPTODON_AIR_TANKS)
        + [
            # Exhaust: down from the manifold, under the left rail, into the frame-rail silencer; the
            # tailpipe leaves it sideways to the left, ending at the bed edge ahead of the rear tyre.
            {"points": truck.get("downpipe", [[0.28, 0.92, 1.40], [0.32, 0.80, 1.00], [0.42, 0.62, 0.60], [0.52, 0.49, 0.20],
                        [0.55, 0.50, shifted(-0.66, r)], [0.55, 0.55, shifted(-0.88, r)], [0.55, 0.73, shifted(-0.98, r)]]),
             "radius": 0.04, "sides": 8},
            {"points": [[0.55, 0.73, shifted(-0.98, r)], [0.55, 0.73, shifted(-1.52, r)]], "radius": 0.09, "sides": 12},
            {"points": [[0.62, 0.725, shifted(-1.22, r)], [1.06, 0.725, shifted(-1.27, r)], [1.16, 0.69, TAILPIPE_Z]], "radius": 0.045, "sides": 8},
        ]
        + SKID
    )
    EXHAUST_OUTLET = [-1.17, 0.69, TAILPIPE_Z]   # Unity space (x right): the tailpipe end, on the truck's left

    # The bed: the Mammoth's, its front pulled to BED_F and its end out to BED_E. A front moving forward
    # stretches the bed across a cut at z -1.5; one moving back (behind a crew cab) moves the bed rigidly
    # and stretches only its end.
    if BED_SHIFT_FWD >= 0:
        bed_ops = [{"op": "stretchPieces", "select": BED, "cutZ": -1.5, "shift": BED_SHIFT_FWD},
                   {"op": "stretchPieces", "select": BED, "cutZ": -2.2, "shift": BED_REAR_EXTRA}]
    else:
        bed_ops = [{"op": "movePieces", "select": BED, "offset": [0.0, 0.0, BED_SHIFT_FWD]},
                   {"op": "stretchPieces", "select": BED, "cutZ": round(-2.2 + BED_SHIFT_FWD, 3),
                    "shift": round(BED_REAR_EXTRA - BED_SHIFT_FWD, 3)}]

    def body_ops(lod):
        return [
            {"op": "movePieces", "select": LAMP_BLOCKS, "offset": [0.0, 0.0, LAMP_BLOCK_SHIFT]},
            {"op": "removePieces", "select": LAMPS},
            {"op": "stretchPieces", "select": HITCH, "cutZ": 0.0, "shift": round(BED_E - 0.02 - HITCH_REAR, 3)},
            # The Mammoth's cab and front, then everything of its own under the bed: frame, step box,
            # round tank, exhaust and rear fender skirts (the moved lamps and hitch lie behind the box).
            {"op": "removeRegion", "box": [{"y": [1.05, None], "z": [-0.86, None]}, {"z": [0.62, None]}]},
            {"op": "removeRegion", "box": {"y": [None, 1.2], "z": [round(BED_E + 0.1, 3), 0.62]}},
            {"op": "removePieces", "select": {"y": [1.1, 1.25], "z": [-3.5, 0.0]}},   # its fender tops and bed-end step
            {"op": "insertPart", "file": f"meshes/{CAB}_LOD{lod}.obj"},
            # The reference model's front flare was drawn round a 12.5R20; trim its inner rear lip where the 14.5R20
            # would come within 0.045 m at full bump (the arch itself clears it).
            {"op": "removeNearAxle", "centre": [HUB_Y, FRONT_AXLE], "radius": 0.70,
             "box": [{"x": [0.70, 0.90], "y": [0.80, 1.20], "z": [0.80, 1.25]},
                     {"x": [-0.90, -0.70], "y": [0.80, 1.20], "z": [0.80, 1.25]}]},
            {"op": "removePieces", "select": [   # bed stakes
                {"x": [0.3, 0.9], "y": [1.25, 1.8], "z": [-3.5, 0.2], "minSize": {"y": 0.3}},
                {"x": [-0.9, -0.3], "y": [1.25, 1.8], "z": [-3.5, 0.2], "minSize": {"y": 0.3}}]},
            *bed_ops,
            {"op": "widenPieces", "select": BED, "cutX": 0.7, "shift": BED_WIDEN},
            {"op": "paint", "select": BED, "uv": PAINT},
            # The Mammoth bed's flat bottom cover, 0.057 m under the floor's own underside: dropped, so the
            # floor is the underside, with room for the spare's raised inner edge.
            {"op": "removeRegion", "box": {"x": [-0.6, 0.6], "y": [1.235, 1.25], "z": [round(BED_E + 0.105, 3), round(BED_F - 0.17, 3)]}},
            {"op": "scalePieces", "select": BED, "origin": [0.0, SLAT_BASE, 0.0], "scale": [1.0, SIDE_SCALE, 1.0],
             "box": {"y": [SLAT_BASE, None]}},
            {"op": "movePieces", "select": dict(BED, y=[1.2, 1.9]), "offset": [0.0, -BED_DROP, 0.0]},
            {"op": "addBoxes", "boxes": BED_BACKING + RIBS + SKIRT, "uv": PAINT},
            {"op": "addPlates", "plates": GUARDS + CARRIER_PLATES, "uv": BLACK},
            # The Mammoth's own black parts kept here sit on livery-painted dark texels: the hitch, and the
            # housings round the rear lamp blocks' lenses. Repaint them unpainted black too.
            {"op": "paint", "uv": BLACK, "box": {"z": [None, -3.0]}, "uvRect": [[0.07, 0.22], [0.17, 0.26]]},
            {"op": "paint", "uv": BLACK, "box": {"z": [None, -3.0]}, "uvRect": [[0.69, 0.78], [0.095, 0.145]],
             "uvExclude": [[[0.7065, 0.7315], [0.1060, 0.1200]], [[0.7450, 0.7700], [0.1060, 0.1200]]]},
            {"op": "addBoxes", "boxes": UNDER_BOXES + FLAPS, "uv": BLACK},
            {"op": "addTubes", "tubes": UNDER_TUBES, "uv": BLACK},
            # A truck's own parts already placed in car-root space (e.g. the crew cab's storage boxes).
            *[{"op": "insertPart", "file": part.format(lod=lod)} for part in truck.get("extraParts", [])],
        ]

    meshes = {}
    for lod in range(4):
        meshes[f"Parts/Mammoth/Mammoth_body_LOD{lod}"] = {"file": f"body_LOD{lod}.obj", "ops": body_ops(lod)}
    # Top collider (cab greenhouse): pull its rear from the Mammoth crew cab's -0.85 to the Glyptodon cab's rear wall.
    meshes["Collider/Top"] = {"file": "collider_top.obj", "ops": [
        {"op": "stretchPieces", "select": {}, "cutZ": -0.5, "shift": round(0.85 - CAB_EXTRA, 3), "move": "behind"}]}
    # Base collider: out to the bed end, forward to the Glyptodon bumper (+2.55), and as wide as the bed behind the cab.
    meshes["Collider/Base"] = {"file": "collider_base.obj", "ops": [
        {"op": "stretchPieces", "select": {}, "cutZ": -2.0,
         "shift": round(BED_E - (-2.157 - (WHEELBASE - DONOR_WHEELBASE)), 3)},
        {"op": "stretchPieces", "select": {}, "cutZ": 1.5, "shift": 0.47},
        {"op": "widenPieces", "select": {}, "cutX": 0.7, "shift": round(BED_HALF - 1.011, 3), "box": {"z": [None, round(BED_F - 0.07, 3)]}}]}
    # Portals: the tube 0.13 m over the wheel centre, under a taller diff whose underside sits 0.075 m
    # under it (the drawing's 440 mm on 12.5R20s); the diff stays clear of the coils.
    for axle, off in (("Front", 0.04), ("Rear", -0.04)):
        for lod in range(4):
            hs, sides, spt = SEG[lod]
            meshes[f"Axles/SuspensionRigid{axle}/SuspensionRigidMesh_LOD{lod}"] = {
                "file": f"suspension_{axle.lower()}_LOD{lod}.obj", "stretch": False,
                "ops": [{"op": "portalAxle", "lift": 0.10, "tubeScale": 2.0, "diffScale": [1.5, 2.2, 2.0], "diffOffset": off, "housingSegments": hs},
                        # Coils outboard of the rails on the axle tubes, up to perches off the rails, as in the reference model.
                        {"op": "coilSprings", "x": 0.56 if axle == "Front" else 0.585, "top": 1.02,
                         "outerDiameter": 0.20, "wireDiameter": 0.028, "sides": sides, "segmentsPerTurn": spt}]}

    lamps = {f"Lights/{side}{kind}": {"position": [x, LAMP_Y, round(LAMP_Z, 3)]}
             for side, x in (("Left", -LAMP_X), ("Right", LAMP_X)) for kind in ("PositionBrakelight", "BrakingBrakelight")}
    lamps.update({f"Lights/{side}Reverselight": {"position": [x, LAMP_Y, round(LAMP_Z, 3)]}
                  for side, x in (("Left", -0.80), ("Right", 0.80))})
    preview = truck.get("sparePreview", "generated/spare_preview.obj")
    d = {
        "codename": truck["codename"],
        "displayName": truck["displayName"],
        "description": truck["description"],
        # Die Kollektion's catalogue (README, CLI, pack listing); the plugin ignores it and it never reaches the game.
        "listing": truck["listing"],
        "itemId": truck["itemId"],
        "donor": "Mammoth",
        # "based": built from the player's extracted Mammoth plus the differences below; the truck's script
        # says which kind it is (Die Kollektion's tools read this; the plugin reads "donor").
        "kind": truck["kind"],
        "base": {"car": "Mammoth"},
        "gates": {
            "notes": ["Long thin faces the cab has by design: its roof ribs and the trim strips running across the cab's",
                      "width at the window line and the roof edge. check_slivers allows slivers wholly inside this box;",
                      "any other sliver still fails."],
            "sliverAllow": [[-0.9, 0.9, 1.83, 2.42, round(-0.1 - CAB_EXTRA, 3), 1.25]],
        },
        "donorAxleZ": {"front": FRONT_AXLE, "rear": FRONT_AXLE - DONOR_WHEELBASE},
        "wheelbase": WHEELBASE,
        "track": TRACK,
        "maxSteerAngle": 37.8,
        # Full bump 0.11 m over the modelled hub: the 14.5R20 then reaches 0.655 m from it, inside the
        # reference model's 0.72 m front arch and under the bed.
        "suspension": SUSPENSION,
        "bodyCut": [[0.0, -0.62], [1.05, -0.865], [1.21, -1.45]],
        "wheel": dict(WHEEL, y=HUB_Y),
        "tyre": TYRE,
        "headlights": HEADLIGHTS,
        "transforms": {
            "Effects/VehicleParticles/ExhaustParticlesManager": {"position": EXHAUST_OUTLET, "yaw": 90},
            **lamps,
            # The Glyptodon cab carries its headlamps in the bumper (lens centres x +-0.70, y 0.83, front face z 2.28);
            # it has no cab-corner spotlights, so their flares sit on the headlamps too.
            "Lights/LeftHeadlight": {"position": [-0.70, 0.83, 2.30]},
            "Lights/RightHeadlight": {"position": [0.70, 0.83, 2.30]},
            "Lights/LeftSpotlightFlare": {"position": [-0.70, 0.83, 2.30]},
            "Lights/RightSpotlightFlare": {"position": [0.70, 0.83, 2.30]},
            # Winch points on the Glyptodon bumper and the rear crossmember.
            "Winch/WinchAttachPoints/Front": {"position": [0.0, 0.85, 2.30]},
            "Winch/WinchAttachPoints/Rear": {"position": [0.0, 0.88, round(BED_E - 0.03, 3)]},
            # The rear-section upgrades (the tailgate spare and its accessories, the bike rack) hang on the
            # Mammoth's tailgate. The plugin moves them back only by the added wheelbase, but the bed's end
            # moves BED_REAR_EXTRA further, so without this they sit inside the bed. Same height, moved with it.
            "Parts/Mammoth_CosmeticParts/Visual/Rear": {
                "position": [0.0, 0.903, round(-2.077 - (WHEELBASE - DONOR_WHEELBASE) + BED_REAR_EXTRA, 3)]},
        },
        "meshes": meshes,
        # Unity root space (x right): the OBJ pose with x negated; the clone's outer face (its local -x)
        # turns by the Euler angles. "preview" is for tools/render_vehicle.py; the plugin ignores it.
        "spare": {"source": SPARE_SOURCE, "position": [-centre[0], centre[1], centre[2]],
                  "rotation": rotation, "preview": preview},
    }
    vehicle_dir = f"vehicles/{truck['codename'].lower()}"
    os.makedirs(os.path.join(vehicle_dir, "generated"), exist_ok=True)
    spare_part.write(os.path.join(vehicle_dir, preview), SPARE_AXLE_SCALE, SPARE_RADIAL_SCALE, centre, tilt, yaw)
    out = os.path.join(vehicle_dir, "vehicle.json")
    json.dump(d, open(out, "w"), indent=2)
    print(f"{out}: wheelbase {WHEELBASE}, bed {BED_F}..{BED_E}, {2 * BED_HALF:.2f} m wide, tyre r {TYRE['radius']}")
    return d
