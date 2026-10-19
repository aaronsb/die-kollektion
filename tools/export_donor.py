"""Extract what a vehicle built on a stock car needs from the player's own install.

Usage: .venv/bin/python -I tools/export_donor.py <cars bundle> <Donor> <out dir>

<Donor> is the car's internal name (the CarInfo name a manifest's "donor" holds, e.g. DingDing).
Writes, into <out dir> (extracted/<donor>/, never committed):
- the body LODs, found as Parts/<group>/<group>_body_LOD0..3 under Car_<Donor> (the group's spelling
  varies: Car_Trailrat keeps its body under Parts/TrailRat), and Collider/Top and Collider/Base;
- the solid-axle meshes at LOD0, when the car has them (contact sheets draw them);
- nodes.json, the prefab's node facts (tools/export_node_facts.py);
- the car's atlas maps <Donor>_skin00 and <Donor>_masks into extracted/textures/ (contact sheets and
  tools/composite_atlas.py read them).
The Mammoth, which the trucks are built from, has its own fixed list in tools/export_game_data.sh.
"""
import os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import UnityPy  # noqa: E402
import export_car_mesh as ecm  # noqa: E402

UnityPy.config.FALLBACK_UNITY_VERSION = "6000.0.75f1"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def children(t):
    return {c.read().m_GameObject.read().m_Name: c.read() for c in t.m_Children}


def body_group(root):
    """The Parts child whose children are <name>_body_LOD0..3."""
    for name, t in children(ecm.find_child(root, "Parts")).items():
        if f"{name}_body_LOD0" in children(t):
            return name
    raise SystemExit("no Parts/<group>/<group>_body_LOD0 under the prefab")


def main():
    bundle, donor, out_dir = sys.argv[1:4]
    env = UnityPy.load(bundle)
    root = ecm.find_root(env, f"Car_{donor}")
    group = body_group(root)
    paths = [f"Parts/{group}/{group}_body_LOD{n}" for n in range(4)] + ["Collider/Top", "Collider/Base"]
    for side in ("Front", "Rear"):
        path = f"Axles/SuspensionRigid{side}/SuspensionRigidMesh_LOD0"
        try:
            ecm.find_child(root, path)
            paths.append(path)
        except SystemExit:
            print(f"{donor}: no {path}; skipped")
    os.makedirs(out_dir, exist_ok=True)
    for path in paths:
        ecm.export(ecm.find_child(root, path), root, os.path.join(out_dir, path.replace("/", "__") + ".obj"))

    textures = os.path.join(ROOT, "extracted", "textures")
    os.makedirs(textures, exist_ok=True)
    wanted = {f"{group}_{m}".lower(): f"{donor}_{m}" for m in ("skin00", "masks")}
    wanted.update({f"{donor}_{m}".lower(): f"{donor}_{m}" for m in ("skin00", "masks")})
    found = set()
    for obj in env.objects:
        if obj.type.name != "Texture2D":
            continue
        data = obj.read()
        name = wanted.get(data.m_Name.lower())
        if name and name not in found:
            data.image.save(os.path.join(textures, f"{name}.png"))
            found.add(name)
            print(f"Texture2D {data.m_Name} -> extracted/textures/{name}.png")
    missing = set(wanted.values()) - found
    if missing:
        print(f"{donor}: atlas maps not found: {', '.join(sorted(missing))}")

    subprocess.run([sys.executable, "-I", os.path.join(ROOT, "tools", "export_node_facts.py"), bundle, f"Car_{donor}",
                    os.path.join(out_dir, "nodes.json")], check=True)


if __name__ == "__main__":
    main()
