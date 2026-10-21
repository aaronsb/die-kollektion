using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using AssetsTools.NET.Extra;

namespace Kollektion.Core.GameData
{
    /// <summary>A car prefab's upgrade nodes, their parts and option meshes, as tools/export_upgrades.py writes
    /// upgrades.json and upgrades/*.obj: every node under Parts/*_CosmeticParts with its local and car-root TRS; a
    /// node with a VehicleUpgradeObject is an option, with its part and an OBJ of its LOD0 mesh nodes.</summary>
    public static class Upgrades
    {
        // The enums as the interop declares them (VehicleCosmetic.CosmeticType, VehicleUpgrade.UpgradeType).
        static readonly string[] CosmeticTypes =
        {
            "Hidden", "FrontSection", "RearSection", "SideSection", "FrontBumper", "RearBumper", "Hood", "Roof", "Bed",
            "RoofLights", "Fenders", "SideStep", "Antenna", "BushCables", "Horns",
        };
        static readonly string[] UpgradeTypes =
        {
            "Default", "Drone", "Engine", "Health", "Headlight", "Horn", "Inventory", "Suspension", "WaterResistance", "Tire",
            "Winch", "Protection",
        };
        static readonly Regex HigherLod = new Regex("_LOD[1-9]$");
        const string Convention = "Unity car-root space: x right, y up, z forward; rotations are quaternions (x, y, z, w)";

        static List<object> Rounded(double[] v) => v.Select(x => (object)(PyFormat.Round(x, 6) + 0.0)).ToList();

        /// <summary>Python's list indexing of the enum names: a value past the end stays a number, a negative one
        /// counts from the end.</summary>
        static object EnumName(string[] names, int v) => v < names.Length ? names[v >= 0 ? v : names.Length + v] : (object)v;

        public static double[,] MatMul(double[,] a, double[,] m)
        {
            var r = new double[4, 4];
            for (int i = 0; i < 4; i++)
                for (int j = 0; j < 4; j++)
                {
                    double s = 0;
                    for (int k = 0; k < 4; k++) s += a[i, k] * m[k, j];
                    r[i, j] = s;
                }
            return r;
        }

        public static double[,] Trs(double[] p, double[] q, double[] s)
        {
            double x = q[0], y = q[1], z = q[2], w = q[3];
            var r = new double[,]
            {
                { 1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w) },
                { 2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w) },
                { 2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y) },
            };
            var m = new double[4, 4];
            for (int i = 0; i < 3; i++)
            {
                m[i, 0] = r[i, 0] * s[0]; m[i, 1] = r[i, 1] * s[1]; m[i, 2] = r[i, 2] * s[2]; m[i, 3] = p[i];
            }
            m[3, 3] = 1;
            return m;
        }

        /// <summary>The path of the car's Parts/&lt;name&gt;_CosmeticParts node, or null. The name isn't always the
        /// car's own (The Ding's is DingDing_SUV_CosmeticParts, the Trailrat's TrailRat_CosmeticParts).</summary>
        static string FindCosmeticRoot(Bundles b, Asset root)
        {
            foreach (var parts in b.Children(root))
            {
                if (b.NodeName(parts) != "Parts") continue;
                foreach (var g in b.Children(parts))
                {
                    var name = b.NodeName(g);
                    if (name.ToLowerInvariant().EndsWith("_cosmeticparts", StringComparison.Ordinal)) return "Parts/" + name;
                }
            }
            return null;
        }

        static PyDict PartOf(Bundles b, Asset go)
        {
            foreach (var c in b.Components(go))
            {
                if (c.Type != AssetClassID.MonoBehaviour) continue;
                try
                {
                    if (b.ScriptName(c) != "VehicleUpgradeObject") continue;
                }
                catch (InvalidDataException)
                {
                    continue;                   // a script that can't be resolved: not ours
                }
                Asset reference;
                var pointer = c.F["vehiclePartReference"];
                try
                {
                    reference = pointer.IsDummy ? null : b.Deref(c, pointer);
                }
                catch (InvalidDataException)
                {
                    reference = null;
                }
                if (reference == null) return new PyDict { ["name"] = null };   // Rollcage and Winch_01: no part reference
                var part = new PyDict
                {
                    ["name"] = reference.F["m_Name"].IsDummy ? null : reference.F["m_Name"].AsString,
                    ["itemId"] = reference.F["ItemId"].IsDummy ? null : (object)reference.F["ItemId"].AsLong,
                    ["kind"] = b.ScriptName(reference),
                };
                if (!reference.F["CosmeticType"].IsDummy) part["cosmeticType"] = EnumName(CosmeticTypes, reference.F["CosmeticType"].AsInt);
                if (!reference.F["UpgradeType"].IsDummy) part["upgradeType"] = EnumName(UpgradeTypes, reference.F["UpgradeType"].AsInt);
                var linked = new List<object>();
                if (!reference.F["LinkedParts"].IsDummy)
                    foreach (var l in reference.F["LinkedParts"]["Array"].Children)
                    {
                        try
                        {
                            var la = b.Deref(reference, l);
                            if (la != null) linked.Add(la.F["m_Name"].AsString);
                        }
                        catch (InvalidDataException)
                        {
                        }
                    }
                if (linked.Count > 0) part["linked"] = linked;
                return part;
            }
            return null;
        }

        static Asset MeshOf(Bundles b, Asset go)
        {
            foreach (var c in b.Components(go))
                if (c.Type == AssetClassID.MeshFilter && c.F["m_Mesh"]["m_PathID"].AsLong != 0)
                    return b.Deref(c, c.F["m_Mesh"]);
            return null;
        }

        public static void Export(Bundles b, Bundle cars, string outDir, string rootName, Action<string> log)
        {
            // The last root of that name, as the Python's loop keeps it.
            var root = b.FindRoots(rootName, cars).LastOrDefault() ?? throw new InvalidDataException($"no prefab root named {rootName}");
            var cosmeticRoot = FindCosmeticRoot(b, root);
            var nodes = new List<PyDict>();
            var meshes = new List<(string Option, string Path, Asset Mesh, double[,] M)>();

            void Walk(Asset t, string path, string parentPath, double[,] matrix, double[] rot, double[] scale, string option)
            {
                var go = b.Deref(t, t.F["m_GameObject"]);
                var lp = ObjExport.Vec(t.F["m_LocalPosition"]);
                var lr = ObjExport.Quat(t.F["m_LocalRotation"]);
                var ls = ObjExport.Vec(t.F["m_LocalScale"]);
                var here = path == null ? matrix : MatMul(matrix, Trs(lp, lr, ls));
                var hereRot = path == null ? rot : NodeFacts.QuatMul(rot, lr);
                var hereScale = path == null ? scale : new[] { scale[0] * ls[0], scale[1] * ls[1], scale[2] * ls[2] };
                bool inside = path != null && (path == cosmeticRoot || path.StartsWith(cosmeticRoot + "/", StringComparison.Ordinal));
                var hereOption = option;
                if (inside)
                {
                    var part = PartOf(b, go);
                    var entry = new PyDict
                    {
                        ["path"] = path, ["parent"] = parentPath,
                        ["local"] = new PyDict { ["position"] = Rounded(lp), ["rotation"] = Rounded(lr), ["scale"] = Rounded(ls) },
                        ["position"] = Rounded(new[] { here[0, 3], here[1, 3], here[2, 3] }), ["rotation"] = Rounded(hereRot),
                        ["scale"] = Rounded(hereScale), ["active"] = go.F["m_IsActive"].AsBool,
                    };
                    if (part != null)
                    {
                        entry["part"] = part;
                        hereOption = path;
                    }
                    if (b.Components(go).Any(c => c.Type == AssetClassID.LODGroup)) entry["lodGroup"] = true;
                    var mesh = MeshOf(b, go);
                    if (mesh != null && hereOption != null && !HigherLod.IsMatch(go.Name))
                    {
                        entry["mesh"] = mesh.Name;
                        meshes.Add((hereOption, path, mesh, here));
                    }
                    nodes.Add(entry);
                }
                foreach (var c in b.Children(t))
                {
                    var name = b.NodeName(c);
                    Walk(c, path == null ? name : $"{path}/{name}", path, here, hereRot, hereScale, hereOption);
                }
            }

            var identity = new double[4, 4];
            for (int i = 0; i < 4; i++) identity[i, i] = 1;
            if (cosmeticRoot != null)
                Walk(root, null, null, identity, new double[] { 0, 0, 0, 1 }, new double[] { 1, 1, 1 }, null);
            var outJson = Path.Combine(outDir, "upgrades.json");
            Directory.CreateDirectory(outDir);
            if (nodes.Count == 0)
            {
                // Not every car has upgrade nodes; the add-on then shows the vehicle without any, and extraction goes on.
                PyJson.WriteFile(outJson, new PyDict
                {
                    ["root"] = rootName, ["cosmeticRoot"] = cosmeticRoot, ["convention"] = Convention, ["nodes"] = new List<object>(),
                    ["notes"] = $"{rootName} has no Parts/*_CosmeticParts node, so no upgrade nodes",
                });
                log($"{outJson}: {rootName} has no Parts/*_CosmeticParts node; written with no upgrade nodes");
                return;
            }

            Directory.CreateDirectory(Path.Combine(outDir, "upgrades"));
            var files = new Dictionary<string, string>();
            foreach (var group in meshes.GroupBy(m => m.Option))
            {
                var name = group.Key.Substring(cosmeticRoot.Length + 1).Replace("/", "__") + ".obj";
                files[group.Key] = "upgrades/" + name;
                var sb = new StringBuilder($"# upgrade option {group.Key} from {rootName}; car-root space, metres, x negated (right-handed)\n");
                int first = 0;
                foreach (var (_, path, meshAsset, m) in group)
                {
                    var md = MeshData.Read(b, meshAsset);
                    sb.Append("o ").Append(path).Append('\n');
                    foreach (var v in md.Vertices ?? Array.Empty<double[]>())
                    {
                        double x = v[0], y = v[1], z = v[2];
                        double px = m[0, 0] * x + m[0, 1] * y + m[0, 2] * z + m[0, 3];
                        double py = m[1, 0] * x + m[1, 1] * y + m[1, 2] * z + m[1, 3];
                        double pz = m[2, 0] * x + m[2, 1] * y + m[2, 2] * z + m[2, 3];
                        sb.Append("v ").Append(PyFormat.Fixed(-px, 6)).Append(' ').Append(PyFormat.Fixed(py, 6))
                          .Append(' ').Append(PyFormat.Fixed(pz, 6)).Append('\n');
                    }
                    // A mirrored node (negative scale determinant) keeps its winding; the x flip reverses it.
                    double det = m[0, 0] * (m[1, 1] * m[2, 2] - m[1, 2] * m[2, 1]) - m[0, 1] * (m[1, 0] * m[2, 2] - m[1, 2] * m[2, 0])
                                 + m[0, 2] * (m[1, 0] * m[2, 1] - m[1, 1] * m[2, 0]);
                    foreach (var (a, bb, c) in md.Triangles)
                    {
                        var tri = det > 0 ? new[] { a, c, bb } : new[] { a, bb, c };
                        sb.Append('f');
                        foreach (var i in tri) sb.Append(' ').Append((first + i + 1).ToString());
                        sb.Append('\n');
                    }
                    first += md.VertexCount;
                }
                Output.WriteAtomic(Path.Combine(outDir, "upgrades", name), sb.ToString());
            }
            foreach (var entry in nodes)
                if (files.TryGetValue((string)entry["path"], out var f)) entry["file"] = f;
            PyJson.WriteFile(outJson, new PyDict
            {
                ["root"] = rootName, ["cosmeticRoot"] = cosmeticRoot, ["convention"] = Convention, ["nodes"] = nodes.Cast<object>().ToList(),
            });
            log($"{outJson}: {nodes.Count} nodes, {nodes.Count(n => n.ContainsKey("part"))} options, {files.Count} option meshes");
        }
    }
}
