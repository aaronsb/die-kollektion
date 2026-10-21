using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using AssetsTools.NET.Extra;

namespace Kollektion.Core.GameData
{
    /// <summary>Meshes to OBJ as tools/export_car_mesh.py and export_named_mesh.py write them: x negated and the
    /// winding reversed (Unity is left-handed), numbers as Python formats them.</summary>
    public static class ObjExport
    {
        static readonly double[][] BoneColours =
        {
            new[] { 0.8, 0.8, 0.8 }, new[] { 0.9, 0.2, 0.2 }, new[] { 0.2, 0.4, 0.9 }, new[] { 0.2, 0.8, 0.2 }, new[] { 0.9, 0.8, 0.1 },
        };

        static string F6(double v) => PyFormat.Fixed(v, 6);

        /// <summary>The node's mesh (MeshFilter, MeshCollider or SkinnedMeshRenderer) in car-root space, metres
        /// (export_car_mesh.py): only translate and scale may lie between node and root.</summary>
        public static string CarMesh(Bundles b, Asset root, string rootName, string path, string outDir, Action<string> log)
        {
            var node = b.FindChild(root, path);
            var go = b.Deref(node, node.F["m_GameObject"]);
            var meshRef = b.Components(go).FirstOrDefault(c => c.Type == AssetClassID.MeshFilter
                                                               || c.Type == AssetClassID.MeshCollider
                                                               || c.Type == AssetClassID.SkinnedMeshRenderer);
            if (meshRef == null) throw new InvalidDataException($"{go.Name} has no MeshFilter, MeshCollider or SkinnedMeshRenderer");
            var meshAsset = b.Deref(meshRef, meshRef.F["m_Mesh"]) ?? throw new InvalidDataException($"{go.Name}: no mesh");
            var mesh = MeshData.Read(b, meshAsset);

            double[] scale = { 1, 1, 1 }, offset = { 0, 0, 0 };
            long rootGo = root.F["m_GameObject"]["m_PathID"].AsLong;
            for (var t = node; t.F["m_GameObject"]["m_PathID"].AsLong != rootGo; t = b.Deref(t, t.F["m_Father"]))
            {
                if (Math.Abs(t.F["m_LocalRotation"]["w"].AsFloat) < 0.9999)
                    throw new InvalidDataException($"{b.NodeName(t)} is rotated; only translate/scale chains are supported");
                var s = Vec(t.F["m_LocalScale"]);
                var p = Vec(t.F["m_LocalPosition"]);
                for (int i = 0; i < 3; i++)
                {
                    offset[i] = offset[i] * s[i] + p[i];
                    scale[i] = scale[i] * s[i];
                }
            }

            var sb = new StringBuilder();
            sb.Append($"# {mesh.Name} from {rootName}; car-root space, metres, x negated (right-handed)\n");
            var w = mesh.BoneWeights;
            var bi = mesh.BoneIndices;
            bool skinned = w != null && w.Length > 0;
            for (int i = 0; i < mesh.VertexCount; i++)
            {
                var v = mesh.Vertices[i];
                double px = v[0] * scale[0] + offset[0], py = v[1] * scale[1] + offset[1], pz = v[2] * scale[2] + offset[2];
                sb.Append("v ").Append(F6(-px)).Append(' ').Append(F6(py)).Append(' ').Append(F6(pz));
                if (skinned)
                {
                    int best = 0;
                    for (int k = 1; k < 4; k++)
                        if (w[i][k] > w[i][best]) best = k;
                    var c = BoneColours[(int)((long)bi[i][best] % BoneColours.Length)];
                    foreach (var x in c) sb.Append(' ').Append(PyFormat.Fixed(x, 3));
                }
                sb.Append('\n');
                if (skinned)
                {
                    // Extension: per-vertex skinning, parallel to the v lines (ignored by Blender).
                    sb.Append("bw ").Append(string.Join(" ", bi[i].Select(x => ((long)x).ToString())))
                      .Append(' ').Append(string.Join(" ", w[i].Select(F6))).Append('\n');
                }
            }
            // Extension: bind poses in the original mesh space, row-major, one line per bone.
            var bindPose = meshAsset.F["m_BindPose"];
            if (!bindPose.IsDummy)
                foreach (var m in bindPose["Array"].Children)
                {
                    sb.Append("bp");
                    for (int r = 0; r < 4; r++)
                        for (int c = 0; c < 4; c++)
                            sb.Append(' ').Append(PyFormat.Fixed(m[$"e{r}{c}"].AsFloat, 8));
                    sb.Append('\n');
                }
            AppendTail(sb, mesh);
            var outPath = Path.Combine(outDir, path.Replace("/", "__") + ".obj");
            Output.WriteText(outPath, sb.ToString());
            log($"{outPath}: {mesh.VertexCount} vertices, {mesh.Triangles.Count} triangles, uv={PyBool(mesh.UV0)} normals={PyBool(mesh.Normals)}");
            return outPath;
        }

        /// <summary>Mesh assets by name, each vertex mesh × scale + offset with x negated (export_named_mesh.py); the
        /// first mesh of each name wins.</summary>
        public static void NamedMeshes(Bundles b, Bundle bundle, string outDir, double scale, double[] offset,
                                       IReadOnlyList<string> names, Action<string> log)
        {
            var found = new Dictionary<string, Asset>();
            foreach (var asset in b.OfType(AssetClassID.Mesh, new HashSet<string>(names), bundle))
                if (!found.ContainsKey(asset.Name)) found[asset.Name] = asset;
            Directory.CreateDirectory(outDir);
            foreach (var name in names)
            {
                if (!found.TryGetValue(name, out var asset)) throw new InvalidDataException($"no Mesh named {name}");
                var mesh = MeshData.Read(b, asset);
                var sb = new StringBuilder();
                sb.Append($"# {mesh.Name}; scale {PyFormat.Repr(scale)}, offset ({PyFormat.Repr(offset[0])}, {PyFormat.Repr(offset[1])}, " +
                          $"{PyFormat.Repr(offset[2])}); car-root space, metres, x negated (right-handed)\n");
                foreach (var v in mesh.Vertices ?? Array.Empty<double[]>())
                    sb.Append("v ").Append(F6(-v[0] * scale + offset[0])).Append(' ').Append(F6(v[1] * scale + offset[1]))
                      .Append(' ').Append(F6(v[2] * scale + offset[2])).Append('\n');
                AppendTail(sb, mesh);
                var outPath = Path.Combine(outDir, name + ".obj");
                Output.WriteText(outPath, sb.ToString());
                log($"{outPath}: {mesh.VertexCount} vertices, {mesh.Triangles.Count} triangles, uv={PyBool(mesh.UV0)} normals={PyBool(mesh.Normals)}");
            }
        }

        static string PyBool(double[][] a) => a != null && a.Length > 0 ? "True" : "False";

        static void AppendTail(StringBuilder sb, MeshData mesh)
        {
            bool hasUv = mesh.UV0 != null && mesh.UV0.Length > 0, hasN = mesh.Normals != null && mesh.Normals.Length > 0;
            if (hasUv)
                foreach (var uv in mesh.UV0) sb.Append("vt ").Append(F6(uv[0])).Append(' ').Append(F6(uv[1])).Append('\n');
            if (hasN)   // stored as half4 in this game; w is padding
                foreach (var n in mesh.Normals)
                    sb.Append("vn ").Append(F6(-n[0])).Append(' ').Append(F6(n[1])).Append(' ').Append(F6(n[2])).Append('\n');
            foreach (var (a, b, c) in mesh.Triangles)
            {
                sb.Append('f');
                foreach (var i in new[] { a + 1, c + 1, b + 1 })     // reversed winding for the mirrored axis
                {
                    var s = i.ToString();
                    sb.Append(' ').Append(s).Append('/').Append(hasUv ? s : "").Append('/').Append(hasN ? s : "");
                }
                sb.Append('\n');
            }
        }

        public static double[] Vec(AssetsTools.NET.AssetTypeValueField f) => new double[] { f["x"].AsFloat, f["y"].AsFloat, f["z"].AsFloat };

        public static double[] Quat(AssetsTools.NET.AssetTypeValueField f) =>
            new double[] { f["x"].AsFloat, f["y"].AsFloat, f["z"].AsFloat, f["w"].AsFloat };
    }
}
