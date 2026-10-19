"""Write a car prefab's node facts (every transform in car-root space, with its components) to JSON.

Usage: python -I tools/export_node_facts.py <cars bundle> Car_<Donor> <out.json>

Reads the player's own install. For each node under the prefab root it records the path, the
root-space position (Unity convention: x right, y up, z forward), the local rotation as a
quaternion, the component types (MonoBehaviours by script name) and, for box and sphere colliders,
their centre and size. tools/contact_sheet.py places attach points from this file; it is extracted
data and lives in the gitignored extracted/ folder.
"""
import glob, json, os, sys

import UnityPy

UnityPy.config.FALLBACK_UNITY_VERSION = "6000.0.75f1"


def quat_rotate(q, v):
    x, y, z, w = q
    vx, vy, vz = v
    # v' = q v q*, expanded
    ix = w * vx + y * vz - z * vy
    iy = w * vy + z * vx - x * vz
    iz = w * vz + x * vy - y * vx
    iw = -x * vx - y * vy - z * vz
    return (ix * w + iw * -x + iy * -z - iz * -y,
            iy * w + iw * -y + iz * -x - ix * -z,
            iz * w + iw * -z + ix * -y - iy * -x)


def quat_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def main():
    bundle, root_name, out = sys.argv[1:4]
    scripts = {}
    for obj in UnityPy.load(glob.glob(os.path.join(os.path.dirname(bundle), "*monoscripts*.bundle"))[0]).objects:
        if obj.type.name == "MonoScript":
            scripts[obj.path_id] = obj.read().m_ClassName
    env = UnityPy.load(bundle)
    root = None
    for obj in env.objects:
        if obj.type.name == "GameObject" and obj.read().m_Name == root_name:
            go = obj.read()
            for c in go.m_Component:
                co = c.component.deref()
                if co.type.name == "Transform":
                    t = co.read()
                    if not t.m_Father or t.m_Father.path_id == 0:
                        root = t
    if root is None:
        raise SystemExit(f"no root transform named {root_name}")

    nodes = []

    def components(go):
        found = []
        for c in go.m_Component:
            co = c.component.deref()
            kind = co.type.name
            if kind == "Transform":
                continue
            entry = {"type": kind}
            if kind == "MonoBehaviour":
                try:
                    entry["type"] = "MB:" + scripts.get(co.read_typetree()["m_Script"]["m_PathID"], "?")
                except Exception:
                    entry["type"] = "MB:?"
            elif kind in ("BoxCollider", "SphereCollider", "CapsuleCollider"):
                d = co.read_typetree()
                entry["center"] = [d["m_Center"][k] for k in "xyz"]
                if "m_Size" in d:
                    entry["size"] = [d["m_Size"][k] for k in "xyz"]
                if "m_Radius" in d:
                    entry["radius"] = d["m_Radius"]
            found.append(entry)
        return found

    def walk(t, path, pos, rot, scale):
        go = t.m_GameObject.read()
        lp, lr, ls = t.m_LocalPosition, t.m_LocalRotation, t.m_LocalScale
        local = (lp.x * scale[0], lp.y * scale[1], lp.z * scale[2])
        here = pos if path is None else tuple(p + d for p, d in zip(pos, quat_rotate(rot, local)))
        here_rot = rot if path is None else quat_mul(rot, (lr.x, lr.y, lr.z, lr.w))
        here_scale = scale if path is None else (scale[0] * ls.x, scale[1] * ls.y, scale[2] * ls.z)
        if path is not None:
            nodes.append({"path": path, "position": [round(v, 5) for v in here],
                          "rotation": [round(v, 5) for v in here_rot],
                          "scale": [round(v, 5) for v in here_scale],
                          "active": bool(go.m_IsActive), "components": components(go)})
        for ch in t.m_Children:
            c = ch.read()
            name = c.m_GameObject.read().m_Name
            walk(c, name if path is None else f"{path}/{name}", here, here_rot, here_scale)

    walk(root, None, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), (1.0, 1.0, 1.0))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w") as f:
        json.dump({"root": root_name, "convention": "Unity car-root space: x right, y up, z forward",
                   "nodes": nodes}, f, indent=1)
    print(f"{len(nodes)} nodes -> {out}")


if __name__ == "__main__":
    main()
