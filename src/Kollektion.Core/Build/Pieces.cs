using System;
using System.Collections.Generic;

namespace Kollektion.Core.Build
{
    /// <summary>A connected piece of a mesh: its vertex indices (ascending) and their bounds.</summary>
    public sealed class Piece
    {
        public readonly List<int> Vertices;
        public readonly double[] Lo, Hi;

        public Piece(List<int> vertices, double[] lo, double[] hi)
        {
            Vertices = vertices;
            Lo = lo;
            Hi = hi;
        }

        public double Centre(int k) => (Lo[k] + Hi[k]) / 2;
    }

    /// <summary>How meshlib finds pieces and chooses them: connected components, selections and boxes.</summary>
    public static class Pieces
    {
        /// <summary>Connected pieces as lists of vertex indices, coincident positions (to 4 decimals) counting as
        /// connected; ordered by their first vertex, as meshlib's components() returns them.</summary>
        public static List<List<int>> Components(ObjFile obj)
        {
            var n = obj.V.Count;
            var parent = new int[n];
            for (var i = 0; i < n; i++) parent[i] = i;

            int Root(int a)
            {
                while (parent[a] != a)
                {
                    parent[a] = parent[parent[a]];
                    a = parent[a];
                }
                return a;
            }

            foreach (var face in obj.Faces)
                for (var c = 1; c < face.Length; c++)
                    parent[Root(face[c].V)] = Root(face[0].V);
            var seen = new Dictionary<(long, long, long), int>();
            for (var i = 0; i < n; i++)
            {
                var p = obj.V[i];
                var key = (Py.RoundKey4(p[0]), Py.RoundKey4(p[1]), Py.RoundKey4(p[2]));
                if (seen.TryGetValue(key, out var first)) parent[Root(i)] = Root(first);
                else seen[key] = i;
            }
            var groups = new List<List<int>>();
            var groupOf = new Dictionary<int, List<int>>();
            for (var i = 0; i < n; i++)
            {
                var r = Root(i);
                if (!groupOf.TryGetValue(r, out var g))
                {
                    g = new List<int>();
                    groupOf[r] = g;
                    groups.Add(g);
                }
                g.Add(i);
            }
            return groups;
        }

        /// <summary>The bounds of some vertices, min and max as Python's builtins keep the first of equal values.</summary>
        public static (double[] Lo, double[] Hi) Bounds(ObjFile obj, IReadOnlyList<int> idx)
        {
            var lo = new double[3];
            var hi = new double[3];
            for (var k = 0; k < 3; k++)
            {
                lo[k] = hi[k] = obj.V[idx[0]][k];
                for (var j = 1; j < idx.Count; j++)
                {
                    var x = obj.V[idx[j]][k];
                    if (x < lo[k]) lo[k] = x;
                    if (x > hi[k]) hi[k] = x;
                }
            }
            return (lo, hi);
        }

        public static HashSet<int> Referenced(ObjFile obj)
        {
            var referenced = new HashSet<int>();
            foreach (var f in obj.Faces)
                foreach (var c in f)
                    referenced.Add(c.V);
            return referenced;
        }

        /// <summary>Whole components (unreferenced vertices included in their bounds) whose first vertex a face still
        /// uses: how coilSprings and portalAxle see the suspension.</summary>
        public static List<Piece> WholeComponents(ObjFile obj)
        {
            var referenced = Referenced(obj);
            var found = new List<Piece>();
            foreach (var idx in Components(obj))
            {
                if (!referenced.Contains(idx[0])) continue;
                var (lo, hi) = Bounds(obj, idx);
                found.Add(new Piece(idx, lo, hi));
            }
            return found;
        }

        /// <summary>Connected pieces still referenced by a face, as their referenced vertices (meshlib's pieces()).</summary>
        public static List<Piece> Find(ObjFile obj)
        {
            var referenced = Referenced(obj);
            var found = new List<Piece>();
            foreach (var all in Components(obj))
            {
                var idx = all.FindAll(referenced.Contains);
                if (idx.Count == 0) continue;
                var (lo, hi) = Bounds(obj, idx);
                found.Add(new Piece(idx, lo, hi));
            }
            return found;
        }

        /// <summary>Vertex lists of the pieces matching any of the selections.</summary>
        public static List<List<int>> Select(ObjFile obj, IReadOnlyList<Selection> selects)
        {
            var chosen = new List<List<int>>();
            foreach (var p in Find(obj))
                foreach (var s in selects)
                    if (s.Matches(p.Lo, p.Hi, p.Vertices.Count))
                    {
                        chosen.Add(p.Vertices);
                        break;
                    }
            return chosen;
        }

        /// <summary>Indices of the faces whose centroid lies in box. A piece no longer than unitSize on any axis
        /// goes as a whole, by the centre of its bounds, so small details are never split.</summary>
        public static List<int> FacesInBox(ObjFile obj, Box box, double unitSize)
        {
            var unitCentre = new Dictionary<int, double[]>();
            foreach (var p in Find(obj))
            {
                var extent = p.Hi[0] - p.Lo[0];
                for (var k = 1; k < 3; k++) extent = Py.Max(extent, p.Hi[k] - p.Lo[k]);
                if (extent > unitSize) continue;
                var centre = new[] { p.Centre(0), p.Centre(1), p.Centre(2) };
                foreach (var i in p.Vertices) unitCentre[i] = centre;
            }
            var chosen = new List<int>();
            for (var n = 0; n < obj.Faces.Count; n++)
            {
                var face = obj.Faces[n];
                if (!unitCentre.TryGetValue(face[0].V, out var centre)) centre = Centroid(obj, face);
                if (box.Contains(centre)) chosen.Add(n);
            }
            return chosen;
        }

        /// <summary>The mean of a face's corner positions (Python's compensated sum, then the division).</summary>
        public static double[] Centroid(ObjFile obj, Corner[] face)
        {
            var c = new double[3];
            for (var k = 0; k < 3; k++)
            {
                var s = new Py.Sum();
                foreach (var corner in face) s.Add(obj.V[corner.V][k]);
                c[k] = s.Value / face.Length;
            }
            return c;
        }
    }

    /// <summary>A piece selection: {"x": [lo, hi], "y": [...], "z": [...], "minVertices": n, "minSize": {"y": metres}};
    /// the piece must fall inside every given axis range and be at least minSize long on each given axis.</summary>
    public sealed class Selection
    {
        public readonly double[][] Ranges = new double[3][];
        public readonly double[] MinSize = new double[3];
        public double MinVertices = 1;

        public bool Matches(double[] lo, double[] hi, int n)
        {
            for (var k = 0; k < 3; k++)
            {
                var r = Ranges[k];
                if (r != null && !(r[0] <= lo[k] && hi[k] <= r[1])) return false;
                if (hi[k] - lo[k] < MinSize[k]) return false;
            }
            return n >= MinVertices;
        }
    }

    /// <summary>A box, {"x": [lo, hi], ...} with omitted axes and null bounds open, or the union of a list of
    /// boxes (an empty list holds nothing).</summary>
    public sealed class Box
    {
        /// <summary>Per part of the union, per axis: [lo, hi], NaN for an open bound.</summary>
        public readonly List<double[][]> Parts = new List<double[][]>();

        /// <summary>A box holding everything, as meshlib's <c>{}</c>.</summary>
        public static Box Everything()
        {
            var b = new Box();
            b.Parts.Add(new double[3][]);
            return b;
        }

        public bool Contains(double[] point)
        {
            foreach (var part in Parts)
                if (PartContains(part, point)) return true;
            return false;
        }

        static bool PartContains(double[][] part, double[] point)
        {
            for (var k = 0; k < 3; k++)
            {
                var r = part[k];
                if (r == null) continue;
                if ((!double.IsNaN(r[0]) && point[k] < r[0]) || (!double.IsNaN(r[1]) && point[k] > r[1])) return false;
            }
            return true;
        }
    }
}
