using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
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

        /// <summary>A Transform chain longer than this is a loop in damaged data, not a prefab.</summary>
        public const int MaxDepth = 1000;

        /// <summary>The node's mesh (MeshFilter, MeshCollider or SkinnedMeshRenderer) in car-root space, metres
        /// (export_car_mesh.py): only translate and scale may lie between node and root.</summary>
        public static void CarMesh(Bundles b, Asset root, string rootName, string path, string outDir, Action<string> log)
        {
            var node = b.FindChild(root, path);
            var go = b.Deref(node, node.F["m_GameObject"]) ?? throw new InvalidDataException($"{path} has no GameObject");
            var meshRef = b.Components(go).FirstOrDefault(c => c.Type == AssetClassID.MeshFilter
                                                               || c.Type == AssetClassID.MeshCollider
                                                               || c.Type == AssetClassID.SkinnedMeshRenderer);
            if (meshRef == null) throw new InvalidDataException($"{go.Name} has no MeshFilter, MeshCollider or SkinnedMeshRenderer");
            var meshAsset = b.Deref(meshRef, meshRef.F["m_Mesh"]) ?? throw new InvalidDataException($"{go.Name}: no mesh");
            var mesh = MeshData.Read(b, meshAsset);

            double[] scale = { 1, 1, 1 }, offset = { 0, 0, 0 };
            long rootGo = root.F["m_GameObject"]["m_PathID"].AsLong;
            int depth = 0;
            for (var t = node; t.F["m_GameObject"]["m_PathID"].AsLong != rootGo;
                 t = b.Deref(t, t.F["m_Father"]) ?? throw new InvalidDataException($"{path} doesn't lie under {rootName}"))
            {
                if (++depth > MaxDepth) throw new InvalidDataException($"{path}: its parents form a loop");
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

            var obj = new ObjWriter().Line($"# {mesh.Name} from {rootName}; car-root space, metres, x negated (right-handed)");
            var (weights, bones) = Skin(mesh);
            for (int i = 0; i < mesh.VertexCount; i++)
            {
                var v = mesh.Vertices[i];
                double px = v[0] * scale[0] + offset[0], py = v[1] * scale[1] + offset[1], pz = v[2] * scale[2] + offset[2];
                if (weights == null)
                {
                    obj.Vertex(-px, py, pz);
                    continue;
                }
                int best = 0;
                for (int k = 1; k < 4; k++)
                    if (weights[i][k] > weights[i][best]) best = k;
                long bone = (long)bones[i][best];
                obj.Vertex(-px, py, pz, BoneColours[(int)(((bone % BoneColours.Length) + BoneColours.Length) % BoneColours.Length)]);
                // Extension: per-vertex skinning, parallel to the v lines (ignored by Blender).
                obj.Line("bw " + string.Join(" ", bones[i].Select(x => ((long)x).ToString(CultureInfo.InvariantCulture)))
                         + " " + string.Join(" ", weights[i].Select(x => PyFormat.Fixed(x, 6))));
            }
            // Extension: bind poses in the original mesh space, row-major, one line per bone.
            var bindPose = meshAsset.F["m_BindPose"];
            if (!bindPose.IsDummy)
                foreach (var m in bindPose["Array"].Children)
                    obj.Line("bp " + string.Join(" ", Enumerable.Range(0, 16).Select(k => PyFormat.Fixed(m[$"e{k / 4}{k % 4}"].AsFloat, 8))));
            AppendTail(obj, mesh);
            var outPath = Path.Combine(outDir, path.Replace("/", "__") + ".obj");
            Output.WriteText(outPath, obj.ToString());
            log($"{outPath}: {mesh.VertexCount} vertices, {mesh.Triangles.Count} triangles, uv={PyBool(mesh.UV0)} normals={PyBool(mesh.Normals)}");
        }

        /// <summary>The mesh's skinning as four weights and four bone indices per vertex, or nulls when it has no
        /// weights (export_car_mesh.py writes no skinning then). Unity stores one, two or four influences per vertex;
        /// fewer than four are padded with weight 0 on bone 0, the influences Unity leaves out. (export_car_mesh.py
        /// reads four and fails on fewer.)</summary>
        public static (double[][] Weights, double[][] Bones) Skin(MeshData mesh)
        {
            var w = mesh.BoneWeights;
            if (w == null || w.Length == 0) return (null, null);
            var bi = mesh.BoneIndices ?? throw new InvalidDataException($"{mesh.Name}: bone weights without bone indices");
            if (bi.Length != w.Length) throw new InvalidDataException($"{mesh.Name}: {w.Length} bone weights for {bi.Length} bone indices");
            if (w[0].Length > 4 || bi[0].Length > 4)
                throw new InvalidDataException($"{mesh.Name}: {w[0].Length} bone weights per vertex (at most 4)");
            return (w.Select(Pad4).ToArray(), bi.Select(Pad4).ToArray());
        }

        static double[] Pad4(double[] v) => v.Length == 4 ? v : v.Concat(new double[4 - v.Length]).ToArray();

        /// <summary>Mesh assets by name, each vertex mesh × scale + offset with x negated (export_named_mesh.py); the
        /// first mesh of each name wins.</summary>
        public static void NamedMeshes(Bundles b, Bundle bundle, string outDir, double scale, double[] offset,
                                       IReadOnlyList<string> names, Action<string> log)
        {
            var wanted = new HashSet<string>(names);
            var meshes = new Dictionary<string, MeshData>();
            foreach (var asset in b.OfType(AssetClassID.Mesh, wanted, bundle))
                if (!meshes.ContainsKey(asset.Name)) meshes[asset.Name] = MeshData.Read(b, asset);
            foreach (var name in names)
            {
                if (!meshes.TryGetValue(name, out var mesh)) throw new InvalidDataException($"no Mesh named {name}");
                var obj = new ObjWriter().Line(
                    $"# {mesh.Name}; scale {PyFormat.Repr(scale)}, offset ({PyFormat.Repr(offset[0])}, {PyFormat.Repr(offset[1])}, " +
                    $"{PyFormat.Repr(offset[2])}); car-root space, metres, x negated (right-handed)");
                foreach (var v in mesh.Vertices ?? Array.Empty<double[]>())
                    obj.Vertex(-v[0] * scale + offset[0], v[1] * scale + offset[1], v[2] * scale + offset[2]);
                AppendTail(obj, mesh);
                var outPath = Path.Combine(outDir, name + ".obj");
                Output.WriteText(outPath, obj.ToString());
                log($"{outPath}: {mesh.VertexCount} vertices, {mesh.Triangles.Count} triangles, uv={PyBool(mesh.UV0)} normals={PyBool(mesh.Normals)}");
            }
        }

        static string PyBool(double[][] a) => a != null && a.Length > 0 ? "True" : "False";

        static void AppendTail(ObjWriter obj, MeshData mesh)
        {
            bool hasUv = mesh.UV0 != null && mesh.UV0.Length > 0, hasN = mesh.Normals != null && mesh.Normals.Length > 0;
            if (hasUv)
                foreach (var uv in mesh.UV0) obj.TexCoord(uv[0], uv[1]);
            if (hasN)   // stored as half4 in this game; w is padding
                foreach (var n in mesh.Normals) obj.Normal(-n[0], n[1], n[2]);
            foreach (var (a, b, c) in mesh.Triangles)
                obj.Face(a + 1, c + 1, b + 1, hasUv, hasN);     // reversed winding for the mirrored axis
        }

        public static double[] Vec(AssetsTools.NET.AssetTypeValueField f) => new double[] { f["x"].AsFloat, f["y"].AsFloat, f["z"].AsFloat };

        public static double[] Quat(AssetsTools.NET.AssetTypeValueField f) =>
            new double[] { f["x"].AsFloat, f["y"].AsFloat, f["z"].AsFloat, f["w"].AsFloat };
    }
}
