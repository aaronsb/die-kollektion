"""Export meshes from a car prefab to OBJ in car-root space, metres, right-handed.

Usage: python -I export_car_mesh.py <cars bundle> <prefab root name> <out dir> <node path> [<node path> ...]
Node paths are relative to the prefab root, e.g. Parts/Mammoth/Mammoth_body_LOD0 or Collider/Top.

Unity is left-handed; the OBJ negates x and reverses triangle winding so Blender and other
right-handed tools show the car correctly. The VehicleMods plugin applies the inverse on load.
"""
import os, sys
import UnityPy
from UnityPy.helpers.MeshHelper import MeshHandler

UnityPy.config.FALLBACK_UNITY_VERSION = "6000.0.75f1"


BONE_COLOURS = [(0.8, 0.8, 0.8), (0.9, 0.2, 0.2), (0.2, 0.4, 0.9), (0.2, 0.8, 0.2), (0.9, 0.8, 0.1)]


def transform_of(go):
    return next(c.component.deref().read() for c in go.m_Component if c.component.deref().type.name == "Transform")


def find_root(env, name):
    for obj in env.objects:
        if obj.type.name == "GameObject" and obj.read().m_Name == name:
            t = transform_of(obj.read())
            if not t.m_Father or t.m_Father.path_id == 0:
                return t
    raise SystemExit(f"no root GameObject named {name}")


def find_child(t, path):
    for part in path.split("/"):
        t = next((c.read() for c in t.m_Children if c.read().m_GameObject.read().m_Name == part), None)
        if t is None:
            raise SystemExit(f"{path}: no child {part}")
    return t


def root_space(t, root):
    """Scale and offset taking node-local points to root space. Rotations must be identity."""
    scale, offset = [1.0, 1.0, 1.0], [0.0, 0.0, 0.0]
    while t.m_GameObject.path_id != root.m_GameObject.path_id:
        r, s, p = t.m_LocalRotation, t.m_LocalScale, t.m_LocalPosition
        if abs(r.w) < 0.9999:
            raise SystemExit(f"{t.m_GameObject.read().m_Name} is rotated; only translate/scale chains are supported")
        offset = [offset[i] * (s.x, s.y, s.z)[i] + (p.x, p.y, p.z)[i] for i in range(3)]
        scale = [scale[i] * (s.x, s.y, s.z)[i] for i in range(3)]
        t = t.m_Father.read()
    return scale, offset


def export(node, root, out_path):
    go = node.m_GameObject.read()
    mesh_ref = next((c.component.deref().read().m_Mesh for c in go.m_Component
                     if c.component.deref().type.name in ("MeshFilter", "MeshCollider", "SkinnedMeshRenderer")), None)
    if mesh_ref is None:
        raise SystemExit(f"{go.m_Name} has no MeshFilter, MeshCollider or SkinnedMeshRenderer")
    mesh = mesh_ref.read()
    h = MeshHandler(mesh)
    h.process()
    scale, offset = root_space(node, root)
    with open(out_path, "w") as f:
        f.write(f"# {mesh.m_Name} from {root.m_GameObject.read().m_Name}; car-root space, metres, x negated (right-handed)\n")
        # Skinned meshes: colour each vertex by its strongest bone (OBJ vertex-colour extension).
        weights = getattr(h, "m_BoneWeights", None) or []
        indices = getattr(h, "m_BoneIndices", None) or []
        for i, (x, y, z) in enumerate(h.m_Vertices):
            px, py, pz = (x * scale[0] + offset[0], y * scale[1] + offset[1], z * scale[2] + offset[2])
            colour = ""
            if weights:
                bone = indices[i][max(range(4), key=lambda k: weights[i][k])]
                colour = " " + " ".join(f"{c:.3f}" for c in BONE_COLOURS[bone % len(BONE_COLOURS)])
            f.write(f"v {-px:.6f} {py:.6f} {pz:.6f}{colour}\n")
            if weights:
                # Extension: per-vertex skinning, parallel to the v lines (ignored by Blender).
                f.write("bw " + " ".join(str(b) for b in indices[i]) + " " + " ".join(f"{w:.6f}" for w in weights[i]) + "\n")
        # Extension: bind poses in the original mesh space, row-major, one line per bone.
        for m in getattr(mesh, "m_BindPose", None) or []:
            f.write("bp " + " ".join(f"{getattr(m, f'e{r}{c}'):.8f}" for r in range(4) for c in range(4)) + "\n")
        for u, v in (h.m_UV0 or []):
            f.write(f"vt {u:.6f} {v:.6f}\n")
        for n in (h.m_Normals or []):  # stored as half4 in this game; w is padding
            f.write(f"vn {-n[0]:.6f} {n[1]:.6f} {n[2]:.6f}\n")
        has_uv, has_n = bool(h.m_UV0), bool(h.m_Normals)
        tris = 0
        for submesh in h.get_triangles():
            for a, b, c in submesh:
                corners = [i + 1 for i in (a, c, b)]  # reversed winding for the mirrored axis
                f.write("f " + " ".join(f"{i}/{i if has_uv else ''}/{i if has_n else ''}" for i in corners) + "\n")
                tris += 1
    print(f"{out_path}: {len(h.m_Vertices)} vertices, {tris} triangles, uv={has_uv} normals={has_n}")


def main():
    bundle, root_name, out_dir, *paths = sys.argv[1:]
    env = UnityPy.load(bundle)
    root = find_root(env, root_name)
    os.makedirs(out_dir, exist_ok=True)
    for path in paths:
        node = find_child(root, path)
        export(node, root, os.path.join(out_dir, path.replace("/", "__") + ".obj"))


if __name__ == "__main__":
    main()
