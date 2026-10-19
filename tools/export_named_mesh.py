"""Export Mesh assets by name (e.g. scene props) to OBJ in another car's root space.

Usage: python -I export_named_mesh.py <bundle> <out dir> <scale> <dx> <dy> <dz> <mesh name> [<mesh name> ...]
Each vertex becomes mesh * scale + (dx, dy, dz), then x is negated as in export_car_mesh.py, so the
offset is given in OBJ space. Find the scale and offset by overlaying the result on the target car
with render_parts.py; the merchant truck fits Mammoth at scale 100, offset (0, -0.071, 0.086).
"""
import os, sys
import UnityPy
from UnityPy.helpers.MeshHelper import MeshHandler

UnityPy.config.FALLBACK_UNITY_VERSION = "6000.0.75f1"


def export(mesh, scale, offset, out_path):
    h = MeshHandler(mesh)
    h.process()
    with open(out_path, "w") as f:
        f.write(f"# {mesh.m_Name}; scale {scale}, offset {offset}; car-root space, metres, x negated (right-handed)\n")
        for x, y, z in h.m_Vertices:
            f.write(f"v {-x * scale + offset[0]:.6f} {y * scale + offset[1]:.6f} {z * scale + offset[2]:.6f}\n")
        for u, v in (h.m_UV0 or []):
            f.write(f"vt {u:.6f} {v:.6f}\n")
        for n in (h.m_Normals or []):
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
    bundle, out_dir, scale, dx, dy, dz, *names = sys.argv[1:]
    env = UnityPy.load(bundle)
    meshes = {}
    for obj in env.objects:
        if obj.type.name == "Mesh":
            mesh = obj.read()
            meshes.setdefault(mesh.m_Name, mesh)
    os.makedirs(out_dir, exist_ok=True)
    for name in names:
        if name not in meshes:
            raise SystemExit(f"no Mesh named {name}")
        export(meshes[name], float(scale), (float(dx), float(dy), float(dz)), os.path.join(out_dir, name + ".obj"))


if __name__ == "__main__":
    main()
