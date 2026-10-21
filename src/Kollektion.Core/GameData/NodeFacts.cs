using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using AssetsTools.NET.Extra;

namespace Kollektion.Core.GameData
{
    /// <summary>A car prefab's node facts, as tools/export_node_facts.py writes nodes.json: every transform below the
    /// root in car-root space (Unity convention), its components (MonoBehaviours by script class name) and its box,
    /// sphere and capsule colliders' centre, size and radius.</summary>
    public static class NodeFacts
    {
        public static double[] QuatRotate(double[] q, double[] v)
        {
            double x = q[0], y = q[1], z = q[2], w = q[3], vx = v[0], vy = v[1], vz = v[2];
            double ix = w * vx + y * vz - z * vy, iy = w * vy + z * vx - x * vz, iz = w * vz + x * vy - y * vx;
            double iw = -x * vx - y * vy - z * vz;
            return new[] { ix * w + iw * -x + iy * -z - iz * -y, iy * w + iw * -y + iz * -x - ix * -z, iz * w + iw * -z + ix * -y - iy * -x };
        }

        public static double[] QuatMul(double[] a, double[] b)
        {
            double ax = a[0], ay = a[1], az = a[2], aw = a[3], bx = b[0], by = b[1], bz = b[2], bw = b[3];
            return new[] { aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
                           aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz };
        }

        static List<object> Round5(double[] v) => v.Select(x => (object)PyFormat.Round(x, 5)).ToList();

        static List<object> Floats(double[] v) => v.Select(x => (object)x).ToList();

        /// <summary>Script class names by MonoScript path id, from the monoscripts bundle. The node facts look a
        /// MonoBehaviour's script up by path id alone, as the Python does.</summary>
        public static Dictionary<long, string> ScriptsByPathId(Bundles b, Bundle monoscripts)
        {
            var scripts = new Dictionary<long, string>();
            foreach (var s in b.OfType(AssetClassID.MonoScript, null, monoscripts))
                scripts[s.PathId] = s.F["m_ClassName"].AsString;
            return scripts;
        }

        public static void Export(Bundles b, Bundle cars, Dictionary<long, string> scripts, string rootName, string outPath,
                                  Action<string> log)
        {
            // The last root of that name, as the Python's loop keeps it.
            var root = b.FindRoots(rootName, cars).LastOrDefault()
                       ?? throw new InvalidDataException($"no root transform named {rootName}");
            var nodes = new List<object>();

            List<object> Components(Asset go)
            {
                var found = new List<object>();
                foreach (var co in b.Components(go))
                {
                    var kind = co.Type;
                    if (kind == AssetClassID.Transform) continue;
                    var entry = new PyDict { ["type"] = kind.ToString() };
                    if (kind == AssetClassID.MonoBehaviour)
                    {
                        var script = co.F["m_Script"];
                        entry["type"] = "MB:" + (script.IsDummy ? "?" : scripts.TryGetValue(script["m_PathID"].AsLong, out var n) ? n : "?");
                    }
                    else if (kind == AssetClassID.BoxCollider || kind == AssetClassID.SphereCollider || kind == AssetClassID.CapsuleCollider)
                    {
                        entry["center"] = Floats(ObjExport.Vec(co.F["m_Center"]));
                        if (!co.F["m_Size"].IsDummy) entry["size"] = Floats(ObjExport.Vec(co.F["m_Size"]));
                        if (!co.F["m_Radius"].IsDummy) entry["radius"] = (double)co.F["m_Radius"].AsFloat;
                    }
                    found.Add(entry);
                }
                return found;
            }

            void Walk(Asset t, string path, double[] pos, double[] rot, double[] scale)
            {
                var go = b.Deref(t, t.F["m_GameObject"]);
                var lp = ObjExport.Vec(t.F["m_LocalPosition"]);
                var lr = ObjExport.Quat(t.F["m_LocalRotation"]);
                var ls = ObjExport.Vec(t.F["m_LocalScale"]);
                var here = pos;
                var hereRot = rot;
                var hereScale = scale;
                if (path != null)
                {
                    var d = QuatRotate(rot, new[] { lp[0] * scale[0], lp[1] * scale[1], lp[2] * scale[2] });
                    here = new[] { pos[0] + d[0], pos[1] + d[1], pos[2] + d[2] };
                    hereRot = QuatMul(rot, lr);
                    hereScale = new[] { scale[0] * ls[0], scale[1] * ls[1], scale[2] * ls[2] };
                    nodes.Add(new PyDict
                    {
                        ["path"] = path, ["position"] = Round5(here), ["rotation"] = Round5(hereRot), ["scale"] = Round5(hereScale),
                        ["active"] = go.F["m_IsActive"].AsBool, ["components"] = Components(go),
                    });
                }
                foreach (var c in b.Children(t))
                {
                    var name = b.NodeName(c);
                    Walk(c, path == null ? name : $"{path}/{name}", here, hereRot, hereScale);
                }
            }

            Walk(root, null, new double[] { 0, 0, 0 }, new double[] { 0, 0, 0, 1 }, new double[] { 1, 1, 1 });
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(outPath)));
            Output.WriteText(outPath, PyJson.Dump(new PyDict
            {
                ["root"] = rootName, ["convention"] = "Unity car-root space: x right, y up, z forward", ["nodes"] = nodes,
            }));
            log($"{nodes.Count} nodes -> {outPath}");
        }
    }
}
