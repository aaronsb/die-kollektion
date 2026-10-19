"""Export a car prefab's upgrade nodes, their parts and their meshes, for placements and the Blender add-on.

Usage: python3 -I export_upgrades.py <out dir> <prefab root name> <bundle> [<bundle> ...]
       (the cars bundle, the scriptableobjects bundle, which holds the parts, and the monoscripts bundle)

Writes <out dir>/upgrades.json and one OBJ per upgrade option in <out dir>/upgrades/. Every node under the car's
Parts/*_CosmeticParts node is listed with its local TRS and its car-root position, rotation and scale (Unity
convention: x right, y up, z forward; rotation as a quaternion x, y, z, w). A node carrying a
VehicleUpgradeObject is an option: the part that shows it (name, ItemId, CosmeticType or UpgradeType, linked
parts) and its OBJ, in which each mesh node of the option (LOD0 only) is an "o <path>" object in car-root
metres with x negated (right-handed, as tools/export_car_mesh.py writes). Read from the player's own install
into extracted/, which is never committed. A car without such a node gets an upgrades.json with no nodes.
"""
import json, math, os, re, sys

# The enums as the interop declares them (VehicleCosmetic.CosmeticType, VehicleUpgrade.UpgradeType).
COSMETIC_TYPES = ["Hidden", "FrontSection", "RearSection", "SideSection", "FrontBumper", "RearBumper", "Hood", "Roof",
                  "Bed", "RoofLights", "Fenders", "SideStep", "Antenna", "BushCables", "Horns"]
UPGRADE_TYPES = ["Default", "Drone", "Engine", "Health", "Headlight", "Horn", "Inventory", "Suspension", "WaterResistance",
                 "Tire", "Winch", "Protection"]
HIGHER_LOD = re.compile(r"_LOD[1-9]$")


CONVENTION = "Unity car-root space: x right, y up, z forward; rotations are quaternions (x, y, z, w)"


def find_cosmetic_root(root):
    """The path of the car's Parts/<name>_CosmeticParts node, or None. The name isn't always the car's own
    (The Ding's is DingDing_SUV_CosmeticParts, the Trailrat's TrailRat_CosmeticParts)."""
    for child in root.m_Children:
        parts = child.read()
        if parts.m_GameObject.read().m_Name != "Parts":
            continue
        for grandchild in parts.m_Children:
            name = grandchild.read().m_GameObject.read().m_Name
            if name.lower().endswith("_cosmeticparts"):
                return f"Parts/{name}"
    return None


def write_json(path, data):
    with open(path + ".tmp", "w") as f:
        json.dump(data, f, indent=1)
    os.replace(path + ".tmp", path)


def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def trs(p, q, s):
    x, y, z, w = q
    r = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    return [[r[i][0] * s[0], r[i][1] * s[1], r[i][2] * s[2], p[i]] for i in range(3)] + [[0.0, 0.0, 0.0, 1.0]]


def quat_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def rounded(values, digits=6):
    return [round(v, digits) + 0.0 for v in values]


def main():
    import UnityPy        # here, so tests can import this module's helpers without UnityPy
    from UnityPy.helpers.MeshHelper import MeshHandler
    UnityPy.config.FALLBACK_UNITY_VERSION = "6000.0.75f1"
    out_dir, root_name, *bundles = sys.argv[1:]
    env = UnityPy.load(*bundles)
    root = None
    for obj in env.objects:
        if obj.type.name == "GameObject" and obj.read().m_Name == root_name:
            for c in obj.read().m_Component:
                co = c.component.deref()
                if co.type.name == "Transform":
                    t = co.read()
                    if not t.m_Father or t.m_Father.path_id == 0:
                        root = t
    if root is None:
        sys.exit(f"no prefab root named {root_name}")
    cosmetic_root = find_cosmetic_root(root)

    nodes, meshes = [], []      # meshes: (option path, node path, Mesh, root matrix)

    def part_of(go):
        for c in go.m_Component:
            co = c.component.deref()
            if co.type.name != "MonoBehaviour":
                continue
            try:
                mb = co.read()
                if mb.m_Script.read().m_ClassName != "VehicleUpgradeObject":
                    continue
            except Exception:
                continue
            try:
                ref = mb.vehiclePartReference.deref()
                tree = ref.read_typetree()
                kind = ref.read().m_Script.read().m_ClassName
            except Exception:
                return {"name": None}      # Rollcage and Winch_01: the node has no part reference
            part = {"name": tree.get("m_Name"), "itemId": tree.get("ItemId"), "kind": kind}
            if "CosmeticType" in tree:
                part["cosmeticType"] = COSMETIC_TYPES[tree["CosmeticType"]] if tree["CosmeticType"] < len(COSMETIC_TYPES) else tree["CosmeticType"]
            if "UpgradeType" in tree:
                part["upgradeType"] = UPGRADE_TYPES[tree["UpgradeType"]] if tree["UpgradeType"] < len(UPGRADE_TYPES) else tree["UpgradeType"]
            linked = []
            for link in getattr(ref.read(), "LinkedParts", None) or []:
                try:
                    linked.append(link.deref().read_typetree()["m_Name"])
                except Exception:
                    pass
            if linked:
                part["linked"] = linked
            return part
        return None

    def mesh_of(go):
        for c in go.m_Component:
            co = c.component.deref()
            if co.type.name == "MeshFilter":
                m = co.read().m_Mesh
                if m and m.path_id:
                    return m.read()
        return None

    def walk(t, path, parent_path, matrix, rot, scale, option):
        go = t.m_GameObject.read()
        lp, lr, ls = t.m_LocalPosition, t.m_LocalRotation, t.m_LocalScale
        local_m = trs((lp.x, lp.y, lp.z), (lr.x, lr.y, lr.z, lr.w), (ls.x, ls.y, ls.z))
        here = matrix if path is None else mat_mul(matrix, local_m)
        here_rot = rot if path is None else quat_mul(rot, (lr.x, lr.y, lr.z, lr.w))
        here_scale = scale if path is None else (scale[0] * ls.x, scale[1] * ls.y, scale[2] * ls.z)
        inside = path is not None and (path == cosmetic_root or path.startswith(cosmetic_root + "/"))
        here_option = option
        if inside:
            part = part_of(go)
            entry = {"path": path, "parent": parent_path,
                     "local": {"position": rounded((lp.x, lp.y, lp.z)), "rotation": rounded((lr.x, lr.y, lr.z, lr.w)),
                               "scale": rounded((ls.x, ls.y, ls.z))},
                     "position": rounded([here[i][3] for i in range(3)]), "rotation": rounded(here_rot),
                     "scale": rounded(here_scale), "active": bool(go.m_IsActive)}
            if part is not None:
                entry["part"] = part
                here_option = path
            if any(c.component.deref().type.name == "LODGroup" for c in go.m_Component):
                entry["lodGroup"] = True
            mesh = mesh_of(go)
            if mesh is not None and here_option and not HIGHER_LOD.search(go.m_Name):
                entry["mesh"] = mesh.m_Name
                meshes.append((here_option, path, mesh, here))
            nodes.append(entry)
        for ch in t.m_Children:
            c = ch.read()
            name = c.m_GameObject.read().m_Name
            walk(c, name if path is None else f"{path}/{name}", path, here, here_rot, here_scale, here_option)

    identity = [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]
    if cosmetic_root is not None:
        walk(root, None, None, identity, (0.0, 0.0, 0.0, 1.0), (1.0, 1.0, 1.0), None)
    out = os.path.join(out_dir, "upgrades.json")
    os.makedirs(out_dir, exist_ok=True)
    if not nodes:
        # Not every car has upgrade nodes; the add-on then shows the vehicle without any, and extraction goes on.
        write_json(out, {"root": root_name, "cosmeticRoot": cosmetic_root, "convention": CONVENTION, "nodes": [],
                         "notes": f"{root_name} has no Parts/*_CosmeticParts node, so no upgrade nodes"})
        print(f"{out}: {root_name} has no Parts/*_CosmeticParts node; written with no upgrade nodes")
        return

    os.makedirs(os.path.join(out_dir, "upgrades"), exist_ok=True)
    by_option = {}
    for option, path, mesh, m in meshes:
        by_option.setdefault(option, []).append((path, mesh, m))
    files = {}
    for option, items in by_option.items():
        name = option[len(cosmetic_root) + 1:].replace("/", "__") + ".obj"
        files[option] = f"upgrades/{name}"
        base = 0
        with open(os.path.join(out_dir, "upgrades", name + ".tmp"), "w") as f:
            f.write(f"# upgrade option {option} from {root_name}; car-root space, metres, x negated (right-handed)\n")
            for path, mesh, m in items:
                h = MeshHandler(mesh)
                h.process()
                f.write(f"o {path}\n")
                for x, y, z in h.m_Vertices:
                    px = m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3]
                    py = m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3]
                    pz = m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3]
                    f.write(f"v {-px:.6f} {py:.6f} {pz:.6f}\n")
                # A mirrored node (negative scale determinant) keeps its winding; the x flip reverses it.
                det = (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                       + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
                for submesh in h.get_triangles():
                    for a, b, c in submesh:
                        tri = (a, c, b) if det > 0 else (a, b, c)
                        f.write("f " + " ".join(str(base + i + 1) for i in tri) + "\n")
                base += len(h.m_Vertices)
        os.replace(os.path.join(out_dir, "upgrades", name + ".tmp"), os.path.join(out_dir, "upgrades", name))
    for entry in nodes:
        if entry["path"] in files:
            entry["file"] = files[entry["path"]]
    write_json(out, {"root": root_name, "cosmeticRoot": cosmetic_root, "convention": CONVENTION, "nodes": nodes})
    options = sum(1 for n in nodes if "part" in n)
    print(f"{out}: {len(nodes)} nodes, {options} options, {len(files)} option meshes")


if __name__ == "__main__":
    main()
