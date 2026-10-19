"""Build a derived vehicle's meshes from its definition.

Usage: python3 tools/build_vehicle.py vehicles/<name>.json

Reads the donor meshes exported by export_car_mesh.py from meshes/<donor>/ and writes the
results to plugins/VehicleMods/vehicles/<codename>/ for the plugin build to deploy. A mesh edited
by hand in Blender can be dropped in meshes/<donor>/ under the same name.

A definition with "patch": true modifies the donor itself (no clone), so it has no body cut and
its wheelbase equals the donor's.

Each "meshes" entry maps a node path to either a file name or {"file", "stretch", "ops"}:
- stretch (default true): lengthen behind the definition's body cut by (wheelbase - donor
  wheelbase). The body cut steps with height: [[y0, z0], [y1, z1], ...] means a vertex at height
  y uses the z of the highest y_i <= y.
- ops: further edits in order, e.g. {"op": "coilSprings", "sides": 8, "segmentsPerTurn": 10}.
  removeRegion drops the faces in a box, removePieces the pieces matching a selection; insertPart adds the faces of meshes/<file> inside a box,
  keeping whole pieces that match an "include" selection (if given) and no "exclude" selection.
  Boxes are {"x": [lo, hi], ...} with omitted axes and null bounds open, or a list of such boxes
  (their union). A face counts by its centroid, a piece under unitSize (0.5 m) as a whole.
  stretchPieces moves the vertices of the matching pieces lying past cutZ (ahead of it for a
  positive shift, behind it for a negative one, or the side "move" names) by shift, e.g. to
  lengthen a load bed or pull a collider's end in. movePieces moves the matching pieces rigidly
  by "offset" [x, y, z], e.g. to lower a load bed; scalePieces scales them about "origin" by
  "scale" [x, y, z] (only vertices inside "box", if given), e.g. to make bed sides taller.
  addBoxes appends closed boxes, and paint recolours faces (chosen by piece "select", "box" with
  "whole": true for every vertex inside, "uvRect" [[u0, u1], [v0, v1]] less any "uvExclude" rects,
  and "facing" [x, y, z]),
  from one atlas point "uv" (e.g. a painted panel or glass). addTubes sweeps one continuous capped
  tube along each polyline ({"points", "radius", "sides", "square", "bendRadius"}: mitred joints,
  corners over 30 degrees rounded), for pipes, brackets and sloped rails;
  addPlates appends slabs on any quad ({"corners": [4 points], "thickness"}), e.g. slanted guards;
  addDecals appends single-sided polygons with per-corner UVs ({"corners", "uvs", "facing"}), e.g. a
  lamp lens showing the atlas's lens graphic. addProfileBands sweeps a plan-view band between an
  inner and an outer polyline straight up ({"inner", "outer", "y"}), e.g. a lens wrapping a corner.
  removeNearAxle drops faces touching the space within "radius" of an axle line ("centre" [y, z], optional "box"),
  clearing bodywork a larger tyre would hit.
  Piece selections may be a list (any match).
All coordinates are car-root space in metres (OBJ: x negated, y up, z forward).
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import meshlib  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def cut_at(profile, y):
    steps = sorted(profile)
    return next((z for y0, z in reversed(steps) if y >= y0), steps[0][1])


def stretch(obj, profile, shift):
    moved = 0
    for p in obj.v:
        if p[2] < cut_at(profile, p[1]):
            p[2] += shift
            moved += 1
    obj.header.append(f"# lengthened {shift:+.3f} m behind cut {profile}")
    return f"moved {moved} of {len(obj.v)} vertices"


def snake(op):
    """JSON op parameters (camelCase) as meshlib keyword arguments (snake_case)."""
    return {"".join("_" + c.lower() if c.isupper() else c for c in k): v for k, v in op.items() if k != "op"}


def coil_springs(obj, op):
    removed, coils = meshlib.coil_springs(obj, **snake(op))
    return f"removed {removed} leaf-spring vertices, added {coils} coils"


def portal_axle(obj, op):
    lifted, housings = meshlib.portal_axle(obj, **snake(op))
    return f"lifted {lifted} axle vertices, added {housings} portal housings"


def relocate_piece(obj, op):
    lo, hi = meshlib.relocate_piece(obj, op["select"], op.get("rotateY", 0.0), op.get("anchorTo"))
    return "piece now at " + " ".join(f"{a} {l:+.2f}..{h:+.2f}" for a, l, h in zip("xyz", lo, hi))


def stretch_pieces(obj, op):
    count, moved = meshlib.stretch_pieces(obj, op["select"], op["cutZ"], op["shift"], op.get("move"))
    return f"moved {moved} vertices of {count} pieces {op['shift']:+.3f} m past z {op['cutZ']}"


def scale_pieces(obj, op):
    moved = meshlib.scale_pieces(obj, op["select"], op["origin"], op["scale"], op.get("box"))
    return f"scaled {moved} vertices by {op['scale']} about {op['origin']}"


def move_pieces(obj, op):
    count, moved = meshlib.move_pieces(obj, op["select"], op["offset"])
    return f"moved {moved} vertices of {count} pieces by {op['offset']}"


def widen_pieces(obj, op):
    moved = meshlib.widen_pieces(obj, op["select"], op["cutX"], op["shift"], op.get("box"))
    return f"moved {moved} vertices {op['shift']:+.3f} m outward past |x| {op['cutX']}"


def remove_region(obj, op):
    return f"removed {meshlib.remove_region(obj, op['box'], op.get('unitSize', 0.5))} faces in {op['box']}"


def remove_pieces(obj, op):
    return f"removed {meshlib.remove_pieces(obj, op['select'])} pieces matching {op['select']}"


def paint(obj, op):
    painted = meshlib.paint(obj, op["uv"], op.get("select"), op.get("box"), op.get("uvRect"), op.get("whole", False),
                            op.get("facing"), op.get("uvExclude", ()))
    return f"painted {painted} faces from uv {op['uv']}"


def add_boxes(obj, op):
    return f"added {meshlib.add_boxes(obj, op['boxes'], op['uv'])} boxes"


def add_profile_bands(obj, op):
    return f"added {meshlib.add_profile_bands(obj, op['bands'], op['uv'])} profile bands"


def add_decals(obj, op):
    return f"added {meshlib.add_decals(obj, op['decals'])} decals"


def add_plates(obj, op):
    return f"added {meshlib.add_plates(obj, op['plates'], op['uv'])} plates"


def remove_near_axle(obj, op):
    return f"removed {meshlib.remove_near_axle(obj, op['centre'], op['radius'], op.get('box'))} faces near the axle"


def add_tubes(obj, op):
    tubes, rings = meshlib.add_tubes(obj, op["tubes"], op["uv"])
    return f"added {tubes} tubes ({rings} rings)"


def insert_part(obj, op):
    part = meshlib.Obj.read(os.path.join(ROOT, "meshes", op["file"]))
    added = meshlib.insert_part(obj, part, op.get("box"), op.get("include"), op.get("exclude", []),
                                op.get("unitSize", 0.5))
    return f"inserted {added} faces from {op['file']}"


OPS = {"coilSprings": coil_springs, "portalAxle": portal_axle, "relocatePiece": relocate_piece,
       "stretchPieces": stretch_pieces, "movePieces": move_pieces, "scalePieces": scale_pieces, "widenPieces": widen_pieces, "removeRegion": remove_region,
       "removePieces": remove_pieces, "insertPart": insert_part,
       "paint": paint, "addBoxes": add_boxes, "addTubes": add_tubes, "addPlates": add_plates, "addDecals": add_decals, "addProfileBands": add_profile_bands,
       "removeNearAxle": remove_near_axle}


def missing_game_meshes(definition, src_dir):
    """The donor and part OBJs this definition reads that aren't on disk. They come from the player's own
    game install (tools/export_car_mesh.py, tools/export_named_mesh.py) and are never in the repository."""
    paths = [os.path.join(src_dir, node_path.replace("/", "__") + ".obj") for node_path in definition["meshes"]]
    paths += [os.path.join(ROOT, "meshes", op["file"]) for entry in definition["meshes"].values() if isinstance(entry, dict)
              for op in entry.get("ops", []) if op["op"] == "insertPart"]
    return sorted({p for p in paths if not os.path.exists(p)})


def main():
    definition = json.load(open(sys.argv[1]))
    donor_wheelbase = definition["donorAxleZ"]["front"] - definition["donorAxleZ"]["rear"]
    shift = -(definition["wheelbase"] - donor_wheelbase)
    src_dir = os.path.join(ROOT, "meshes", definition["donor"].lower())
    missing = missing_game_meshes(definition, src_dir)
    if missing:
        sys.exit("missing game meshes; export them from your own install first (README, \"Building from source\"):\n  "
                 + "\n  ".join(os.path.relpath(p, ROOT) for p in missing))
    out_dir = os.path.join(ROOT, "plugins", "VehicleMods", "vehicles", definition["codename"].lower())
    os.makedirs(out_dir, exist_ok=True)
    print(f"{definition['codename']}: wheelbase {donor_wheelbase:.2f} -> {definition['wheelbase']:.2f} m, rear shift {shift:+.3f} m")
    for node_path, entry in definition["meshes"].items():
        entry = {"file": entry} if isinstance(entry, str) else entry
        obj = meshlib.Obj.read(os.path.join(src_dir, node_path.replace("/", "__") + ".obj"))
        notes = []
        if entry.get("stretch", True) and definition["bodyCut"]:
            notes.append(stretch(obj, definition["bodyCut"], shift))
        for op in entry.get("ops", []):
            notes.append(OPS[op["op"]](obj, op))
        obj.write(os.path.join(out_dir, entry["file"]))
        print(f"  {entry['file']}: {'; '.join(notes) or 'copied'}")


if __name__ == "__main__":
    main()
