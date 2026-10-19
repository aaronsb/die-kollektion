"""Write a cab master's game LOD OBJs, headless in Blender; with --derive, first rebuild its far LODs from LOD0.

Usage: blender -b meshes/glyptodon/cab_glyptodon_master.blend --python tools/export_master.py -- [--derive]
(tools/build_cab_part.sh runs this.) A master <dir>/<name>_master.blend writes <dir>/<name>_LOD<n>.obj.

A master holds collections LOD0..LOD3, one object per part in each, named <Part>.LOD<n> (Shell.LOD0,
RearDoor_L.LOD2...). Every face takes its material's name as its class: the flat-colour classes
(Paint, Hood, Glass, Black, Lamp, Amber) carry their atlas point as the material's "atlas_uv" and every
corner is written with it, so a face added by hand needs no UVs; HeadlampLens keeps its own UVs (the
lens graphic). A face with the integer face attribute "two_sided" set is written twice, back to back,
for thin open parts the game would otherwise cull from behind. Modifiers are applied; faces are
triangulated; normals are smooth within 35 degrees per material (flat for the "flat" materials, the
lenses), as the game had them. Coordinates are Blender's (Z up, the truck's front toward -Y, +X its
left); the OBJ is car-root metres (x negated, y up, z forward).

--derive: for every LOD0 part whose geometry changed since its far LODs were made (each far LOD
object keeps "src_hash", the hash of the LOD0 part it came from), rebuild <Part>.LOD1..3 by collapse
decimation of the LOD0 part to that object's "ratio" of its faces (symmetric across X for a part
that straddles the centreline), drop far LOD parts whose LOD0 part is gone, and save the master.
A new LOD0 part gets far LODs at DEFAULT_RATIO; a part a far LOD leaves out (too small to keep) stays
out until its LOD0 part changes ("far_hash" on the LOD0 object). Parts edited in a far LOD itself are
left alone until their LOD0 part changes.
"""
import hashlib, math, os, sys
import bpy, bmesh

SMOOTH_DEGREES = 35.0
DEFAULT_RATIO = {1: 0.7, 2: 0.55, 3: 0.5}


def part_hash(mesh):
    """Hash of a part's own geometry, materials and two-sided flags (not its name or position in the file)."""
    h = hashlib.md5()
    for v in mesh.vertices:
        h.update(("%.6f %.6f %.6f;" % tuple(v.co)).encode())
    two = mesh.attributes.get("two_sided")
    for p in mesh.polygons:
        flag = two.data[p.index].value if two else 0
        h.update(("%s/%d/%d;" % (",".join(map(str, p.vertices)), p.material_index, flag)).encode())
    for m in mesh.materials:
        h.update((m.name if m else "-").encode())
    return h.hexdigest()


def lod_objects(n):
    coll = bpy.data.collections.get(f"LOD{n}")
    return sorted((o for o in coll.all_objects if o.type == "MESH"), key=lambda o: o.name) if coll else []


def part_name(ob):
    return ob.name.rsplit(".LOD", 1)[0]


def derive():
    """Rebuilds far LOD parts from changed LOD0 parts; returns the number rebuilt."""
    rebuilt = 0
    lod0 = {part_name(o): o for o in lod_objects(0)}
    for n in (1, 2, 3):
        coll = bpy.data.collections[f"LOD{n}"]
        far = {part_name(o): o for o in lod_objects(n)}
        for name, ob in far.items():
            if name not in lod0 and "src_hash" in ob:
                bpy.data.objects.remove(ob)
                rebuilt += 1
        for name, src in lod0.items():
            h = part_hash(src.data)
            ob = far.get(name)
            if ob is not None and ob.get("src_hash") == h:
                continue
            if ob is None and src.get("far_hash") == h:
                continue                      # left out of this LOD on purpose (too small to keep)
            ratio = ob["ratio"] if ob is not None and "ratio" in ob else DEFAULT_RATIO[n]
            mesh = src.data.copy()
            mesh.name = f"{name}.LOD{n}"
            tmp = bpy.data.objects.new("derive_tmp", mesh)
            coll.objects.link(tmp)
            if ratio < 1.0:
                xs = [v.co.x for v in mesh.vertices]
                mod = tmp.modifiers.new("decimate", "DECIMATE")
                mod.ratio = ratio
                mod.use_collapse_triangulate = True
                if min(xs) < -0.05 and max(xs) > 0.05:
                    mod.use_symmetry, mod.symmetry_axis = True, "X"
                bpy.context.view_layer.objects.active = tmp
                with bpy.context.temp_override(object=tmp, active_object=tmp):
                    bpy.ops.object.modifier_apply(modifier=mod.name)
            if ob is not None:
                old = ob.data
                ob.data = tmp.data
                bpy.data.objects.remove(tmp)
                bpy.data.meshes.remove(old)
            else:
                ob = tmp
                ob.name = f"{name}.LOD{n}"
                ob["ratio"] = ratio
            ob.matrix_world = src.matrix_world
            ob["src_hash"] = h
            rebuilt += 1
    for src in lod0.values():
        src["far_hash"] = part_hash(src.data)
    return rebuilt


def gather(n):
    """Faces of LOD n per material: {material: (co, uv per corner, faces as vertex index lists, two_sided
    flags, material)}, vertices shared as in the source objects (every part is whole islands, so no
    vertex is shared across objects)."""
    groups = {}
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for ob in lod_objects(n):
        ev = ob.evaluated_get(depsgraph)
        mesh = ev.to_mesh()
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.transform(ob.matrix_world)
        two = bm.faces.layers.int.get("two_sided")
        uvl = bm.loops.layers.uv.active
        bmesh.ops.triangulate(bm, faces=bm.faces, quad_method="BEAUTY", ngon_method="BEAUTY")
        slots = [s.material for s in ob.material_slots]
        local = {}
        for f in bm.faces:
            mat = slots[f.material_index] if f.material_index < len(slots) else None
            name = mat.name if mat else "Paint"
            co, uvs, faces, flags, _ = groups.setdefault(name, ([], [], [], [], mat))
            idx = []
            for v in f.verts:
                key = (name, v.index)
                if key not in local:
                    local[key] = len(co)
                    co.append(tuple(v.co))
                idx.append(local[key])
            fixed = mat.get("atlas_uv") if mat else None
            uvs.append([tuple(fixed) if fixed else (tuple(l[uvl].uv) if uvl else (0.0, 0.0)) for l in f.loops])
            faces.append(idx)
            flags.append(f[two] if two else 0)
        bm.free()
        ev.to_mesh_clear()
    return groups


def material_mesh(name, co, faces, flags, flat):
    """A temporary mesh of one material's faces, with each two-sided face's back-to-back twin (the twins
    share their own copies of the vertices, so a twinned panel shades smoothly on both sides), and
    Blender's smooth-by-angle corner normals. Returns the mesh and, per loop, its (face, corner) source."""
    verts = list(co)
    polys = [list(f) for f in faces]
    src = [(fi, k) for fi, f in enumerate(faces) for k in range(len(f))]
    twin = {}
    for fi, (f, flag) in enumerate(zip(faces, flags)):
        if flag:
            for i in f:
                if i not in twin:
                    twin[i] = len(verts)
                    verts.append(co[i])
            polys.append([twin[i] for i in reversed(f)])
            src.extend((fi, k) for k in reversed(range(len(f))))
    mesh = bpy.data.meshes.new(f"export_{name}")
    mesh.from_pydata(verts, [], polys)
    if flat:
        mesh.shade_flat()
    else:
        mesh.shade_smooth()
        mesh.set_sharp_from_angle(angle=math.radians(SMOOTH_DEGREES))
    return mesh, src


def write_lod(n, path):
    groups = gather(n)
    out = [f"# {os.path.basename(bpy.data.filepath)} LOD{n}, written by tools/export_master.py"]
    vlines, vtlines, vnlines, flines = [], [], [], []
    vt_index, vn_index = {}, {}
    v_base = 0
    for name in sorted(groups):
        co, uvs, faces, flags, mat = groups[name]
        mesh, corner_src = material_mesh(name, co, faces, flags, bool(mat and mat.get("flat")))
        normals = mesh.corner_normals
        for v in mesh.vertices:
            x, y, z = v.co
            vlines.append(f"v {x:.6f} {z:.6f} {-y:.6f}")
        flines.append(f"o {name}")
        for p in mesh.polygons:
            corners = []
            for li in p.loop_indices:
                fi, k = corner_src[li]
                u, w = uvs[fi][k]
                ti = vt_index.setdefault((round(u, 6), round(w, 6)), len(vt_index))
                nx, ny, nz = normals[li].vector
                ni = vn_index.setdefault((round(nx, 6), round(nz, 6), round(-ny, 6)), len(vn_index))
                corners.append(f"{v_base + mesh.loops[li].vertex_index + 1}/{ti + 1}/{ni + 1}")
            flines.append("f " + " ".join(corners))
        v_base += len(mesh.vertices)
        bpy.data.meshes.remove(mesh)
    vtlines = [f"vt {u:.6f} {w:.6f}" for u, w in vt_index]
    vnlines = [f"vn {x:.6f} {y:.6f} {z:.6f}" for x, y, z in vn_index]
    with open(path, "w") as f:
        f.write("\n".join(out + vlines + vtlines + vnlines + flines) + "\n")
    print(f"LOD{n}: {sum(len(g[2]) + sum(g[3]) for g in groups.values())} faces -> {path}")


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    master = bpy.data.filepath
    if not master.endswith("_master.blend"):
        sys.exit(f"{master}: a master is <name>_master.blend")
    if "--derive" in args:
        print(f"derived {derive()} far LOD parts")
        bpy.ops.wm.save_mainfile()
    prefix = master[: -len("_master.blend")]
    for n in range(4):
        if lod_objects(n):
            write_lod(n, f"{prefix}_LOD{n}.obj")


if __name__ == "__main__":
    main()
