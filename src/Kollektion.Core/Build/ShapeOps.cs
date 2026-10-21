using System;
using System.Collections.Generic;

namespace Kollektion.Core.Build
{
    /// <summary>A capped tube along a polyline (addTubes).</summary>
    public sealed class Tube
    {
        public double[][] Points;
        public double Radius;
        public int Sides = 8;
        public bool Square;
        /// <summary>The corner rounding radius; null for twice the tube's radius.</summary>
        public double? BendRadius;
    }

    /// <summary>A quad thickened into a slab (addPlates).</summary>
    public sealed class Plate
    {
        public double[][] Corners;
        public double Thickness;
    }

    /// <summary>A plan-view band between two polylines of [x, z] points, swept from Y0 up to Y1 (addProfileBands).</summary>
    public sealed class Band
    {
        public double[][] Inner, Outer;
        public double Y0, Y1;
    }

    /// <summary>A single-sided polygon with its own UVs (addDecals).</summary>
    public sealed class Decal
    {
        public double[][] Corners, Uvs;
        public double[] Facing;
        public bool DoubleSided;
    }

    /// <summary>The operations that add new geometry: boxes, tubes, plates, profile bands and decals.</summary>
    public static partial class MeshOps
    {
        /// <summary>Appends one polygon from (position, normal) corners, ordered so it faces outward. In a skinned
        /// mesh the corners are bound wholly to bone; bone is ignored otherwise.</summary>
        static void AddFace(ObjFile obj, IReadOnlyList<(double[] Position, double[] Normal)> corners, double[] outward,
            int bone, int uvIndex)
        {
            int b = obj.V.Count, nBase = obj.Vn.Count;
            foreach (var (position, normal) in corners)
            {
                obj.V.Add((double[])position.Clone());
                obj.Vn.Add((double[])normal.Clone());
                if (obj.Skinned)
                {
                    obj.Color.Add(new[] { 0.8, 0.8, 0.8 });
                    obj.Bw.Add(BoneWeights.Single(bone));
                }
                else obj.Color.Add(null);
            }
            var g = Vec.Cross(Vec.Sub(obj.V[b + 1], obj.V[b]), Vec.Sub(obj.V[b + 2], obj.V[b]));
            obj.Faces.Add(Ordered(corners.Count, Vec.Dot(g, outward) > 0, m => new Corner(b + m, uvIndex, nBase + m)));
        }

        /// <summary>A face of n corners in order, or reversed.</summary>
        static Corner[] Ordered(int n, bool forward, Func<int, Corner> corner)
        {
            var face = new Corner[n];
            for (var i = 0; i < n; i++) face[i] = corner(forward ? i : n - 1 - i);
            return face;
        }

        static int AddUv(ObjFile obj, double[] uv)
        {
            obj.Vt.Add((double[])uv.Clone());
            return obj.Vt.Count - 1;
        }

        /// <summary>Appends closed axis-aligned boxes, given as lo and hi corners, every corner mapped to one atlas
        /// point uv so the faces take that spot's flat colour. Returns the number of boxes.</summary>
        public static int AddBoxes(ObjFile obj, IReadOnlyList<(double[] Lo, double[] Hi)> boxes, double[] uv)
        {
            var uvIndex = AddUv(obj, uv);
            foreach (var (lo, hi) in boxes)
                for (var k = 0; k < 3; k++)
                {
                    int a = (k + 1) % 3, b = (k + 2) % 3;
                    foreach (var (side, value) in new[] { (-1.0, lo[k]), (1.0, hi[k]) })
                    {
                        var corners = new List<(double[], double[])>();
                        foreach (var (ca, cb) in new[] { (lo[a], lo[b]), (hi[a], lo[b]), (hi[a], hi[b]), (lo[a], hi[b]) })
                        {
                            var p = new double[3];
                            p[k] = value;
                            p[a] = ca;
                            p[b] = cb;
                            var normal = new double[3];
                            normal[k] = side;
                            corners.Add((p, normal));
                        }
                        AddFace(obj, corners, corners[0].Item2, 0, uvIndex);
                    }
                }
            return boxes.Count;
        }

        /// <summary>The polyline with every corner turning more than minTurnDeg rounded into an arc of the given
        /// radius (shrunk where the neighbouring segments are short), one point per 15 degrees.</summary>
        static List<double[]> Fillet(double[][] points, double radius, double minTurnDeg = 30.0)
        {
            var output = new List<double[]> { (double[])points[0].Clone() };
            for (var i = 1; i < points.Length - 1; i++)
            {
                double[] p = points[i], prev = output[output.Count - 1], next = points[i + 1];
                var a = Vec.Sub(p, prev);
                var b = Vec.Sub(next, p);
                double la = Vec.Length(a), lb = Vec.Length(b);
                a = new[] { a[0] / la, a[1] / la, a[2] / la };
                b = new[] { b[0] / lb, b[1] / lb, b[2] / lb };
                var turn = Math.Acos(Py.Max(-1.0, Py.Min(1.0, Vec.Dot(a, b))));
                if (radius <= 0 || Py.Degrees(turn) <= minTurnDeg)
                {
                    output.Add((double[])p.Clone());
                    continue;
                }
                var r = Py.Min(radius, 0.45 * Py.Min(la, lb) / Math.Tan(turn / 2));
                var t = r * Math.Tan(turn / 2);
                var start = new double[3];
                var end = new double[3];
                for (var k = 0; k < 3; k++)
                {
                    start[k] = p[k] - a[k] * t;
                    end[k] = p[k] + b[k] * t;
                }
                var inward = Vec.Normalised(Vec.Sub(b, a));
                var centre = new double[3];
                for (var k = 0; k < 3; k++) centre[k] = p[k] + inward[k] * r / Math.Cos(turn / 2);
                var v0 = Vec.Sub(start, centre);
                var v1 = Vec.Sub(end, centre);
                var steps = Math.Max(2, (int)Math.Ceiling(Py.Degrees(turn) / 15.0));
                for (var j = 0; j <= steps; j++)
                {
                    var f = (double)j / steps;     // slerp between the arc's ends about its centre
                    double w0 = Math.Sin((1 - f) * turn) / Math.Sin(turn), w1 = Math.Sin(f * turn) / Math.Sin(turn);
                    output.Add(new[]
                    {
                        centre[0] + w0 * v0[0] + w1 * v1[0], centre[1] + w0 * v0[1] + w1 * v1[1],
                        centre[2] + w0 * v0[2] + w1 * v1[2],
                    });
                }
            }
            output.Add((double[])points[points.Length - 1].Clone());
            return output;
        }

        /// <summary>v rotated by the smallest rotation taking unit vector a to unit vector b.</summary>
        static double[] Turned(double[] v, double[] a, double[] b)
        {
            var axis = Vec.Cross(a, b);
            var c = Vec.Dot(a, b);
            var s = Vec.Length(axis);
            if (s < 1e-9) return (double[])v.Clone();
            axis = new[] { axis[0] / s, axis[1] / s, axis[2] / s };
            var dot = Vec.Dot(axis, v);
            var cross = Vec.Cross(axis, v);
            var result = new double[3];
            for (var k = 0; k < 3; k++) result[k] = v[k] * c + cross[k] * s + axis[k] * dot * (1 - c);
            return result;
        }

        /// <summary>Appends capped tubes swept along polylines, every corner mapped to one atlas point uv. Each
        /// polyline is one continuous tube: one ring of vertices per point, each ring in the plane that bisects its
        /// corner, frames carried along the path so it never twists; corners over 30 degrees are rounded first.
        /// Normals are smooth round the tube (flat with Square) and flat on the end caps. Returns the number of
        /// tubes and of rings.</summary>
        public static (int Tubes, int Rings) AddTubes(ObjFile obj, IReadOnlyList<Tube> tubes, double[] uv)
        {
            var uvIndex = AddUv(obj, uv);
            var ringsAdded = 0;

            int Vertex(double[] position)
            {
                obj.V.Add(position);
                if (obj.Skinned)
                {
                    obj.Color.Add(new[] { 0.8, 0.8, 0.8 });
                    obj.Bw.Add(BoneWeights.Single(0));
                }
                else obj.Color.Add(null);
                return obj.V.Count - 1;
            }

            int Normal(double[] n)
            {
                obj.Vn.Add((double[])n.Clone());
                return obj.Vn.Count - 1;
            }

            foreach (var tube in tubes)
            {
                double r = tube.Radius;
                var n = tube.Sides;
                var start = tube.Square ? Math.PI / n : 0.0;
                var path = Fillet(tube.Points, tube.BendRadius ?? 2.0 * r);
                var dirs = new List<double[]>();
                for (var i = 0; i + 1 < path.Count; i++)
                {
                    var d = Vec.Sub(path[i + 1], path[i]);
                    var length = Vec.Length(d);
                    dirs.Add(new[] { d[0] / length, d[1] / length, d[2] / length });
                }
                // The first segment's frame, then carried along: (u, w) span the plane square to the path.
                var d0 = dirs[0];
                var reference = Math.Abs(d0[1]) < 0.9 ? new[] { 0.0, 1.0, 0.0 } : new[] { 1.0, 0.0, 0.0 };
                var frames = new List<double[]> { Vec.Normalised(Vec.Cross(reference, d0)) };
                for (var i = 0; i + 1 < dirs.Count; i++)
                    frames.Add(Vec.Normalised(Turned(frames[frames.Count - 1], dirs[i], dirs[i + 1])));
                var rings = new List<int[]>();
                var radial = new List<double[][]>();
                for (var i = 0; i < path.Count; i++)
                {
                    var p = path[i];
                    var seg = Math.Min(i, dirs.Count - 1);      // the segment arriving here (the first one at the start)
                    double[] d = dirs[seg], u = frames[seg];
                    var w = Vec.Cross(d, u);
                    var t = 0 < i && i < path.Count - 1
                        ? Vec.Normalised(new[] { dirs[i - 1][0] + dirs[i][0], dirs[i - 1][1] + dirs[i][1], dirs[i - 1][2] + dirs[i][2] })
                        : d;
                    var ring = new int[n];
                    var outs = new double[n][];
                    for (var j = 0; j < n; j++)
                    {
                        var ang = start + 2 * Math.PI * j / n;
                        var c = new double[3];
                        for (var k = 0; k < 3; k++) c[k] = Math.Cos(ang) * u[k] + Math.Sin(ang) * w[k];
                        // The section square to the arriving segment, slid along it onto the bisecting plane.
                        var slide = -r * Vec.Dot(c, t) / Vec.Dot(d, t);
                        var position = new double[3];
                        for (var k = 0; k < 3; k++) position[k] = p[k] + r * c[k] + slide * d[k];
                        ring[j] = Vertex(position);
                        outs[j] = c;
                    }
                    rings.Add(ring);
                    radial.Add(outs);
                    ringsAdded++;
                }
                for (var i = 0; i + 1 < path.Count; i++)
                    for (var j = 0; j < n; j++)
                    {
                        var jj = (j + 1) % n;
                        var between = new double[3];
                        for (var k = 0; k < 3; k++) between[k] = radial[i][j][k] + radial[i][jj][k];
                        int[] nn;
                        if (tube.Square)    // flat sides: one normal per face, square to the segment
                        {
                            var side = Normal(Vec.Normalised(between));
                            nn = new[] { side, side, side, side };
                        }
                        else
                            nn = new[]
                            {
                                Normal(radial[i][j]), Normal(radial[i][jj]), Normal(radial[i + 1][jj]), Normal(radial[i + 1][j]),
                            };
                        var quad = new[] { rings[i][j], rings[i][jj], rings[i + 1][jj], rings[i + 1][j] };
                        var outward = Vec.Normalised(between);
                        var e1 = Vec.Sub(obj.V[quad[1]], obj.V[quad[0]]);
                        var e2 = Vec.Sub(obj.V[quad[2]], obj.V[quad[0]]);
                        var forward = Vec.Dot(Vec.Cross(e1, e2), outward) > 0;
                        obj.Faces.Add(Ordered(4, forward, m => new Corner(quad[m], uvIndex, nn[m])));
                    }
                foreach (var (ring, d, sign) in new[] { (rings[0], dirs[0], -1.0), (rings[rings.Count - 1], dirs[dirs.Count - 1], 1.0) })
                {
                    var cap = Normal(new[] { sign * d[0], sign * d[1], sign * d[2] });
                    var e1 = Vec.Sub(obj.V[ring[1]], obj.V[ring[0]]);
                    var e2 = Vec.Sub(obj.V[ring[2]], obj.V[ring[0]]);
                    var g = Vec.Cross(e1, e2);
                    var forward = Py.Sum3(g[0] * sign * d[0], g[1] * sign * d[1], g[2] * sign * d[2]) > 0;
                    obj.Faces.Add(Ordered(n, forward, m => new Corner(ring[m], uvIndex, cap)));
                }
            }
            return (tubes.Count, ringsAdded);
        }

        /// <summary>Appends flat plates of any orientation: the quad (in order round its edge) thickened by the
        /// plate's thickness about its own plane into a closed slab, every corner mapped to one atlas point uv.</summary>
        public static int AddPlates(ObjFile obj, IReadOnlyList<Plate> plates, double[] uv)
        {
            var uvIndex = AddUv(obj, uv);
            foreach (var plate in plates)
            {
                var quad = plate.Corners;
                var half = plate.Thickness / 2;
                var n = Vec.Normalised(Vec.Cross(Vec.Sub(quad[1], quad[0]), Vec.Sub(quad[3], quad[0])));
                var faces = new double[2][][];
                var signs = new[] { 1.0, -1.0 };
                for (var s = 0; s < 2; s++)
                {
                    faces[s] = new double[4][];
                    for (var i = 0; i < 4; i++)
                    {
                        faces[s][i] = new double[3];
                        for (var k = 0; k < 3; k++) faces[s][i][k] = quad[i][k] + signs[s] * half * n[k];
                    }
                }
                for (var s = 0; s < 2; s++)
                {
                    var normal = new[] { signs[s] * n[0], signs[s] * n[1], signs[s] * n[2] };
                    AddFace(obj, Array.ConvertAll(faces[s], p => (p, normal)), normal, 0, uvIndex);
                }
                var centre = new double[3];
                for (var k = 0; k < 3; k++)
                {
                    var sum = new Py.Sum();
                    foreach (var p in quad) sum.Add(p[k]);
                    centre[k] = sum.Value / 4;
                }
                for (var i = 0; i < 4; i++)
                {
                    var j = (i + 1) % 4;
                    var mid = new double[3];
                    for (var k = 0; k < 3; k++) mid[k] = (quad[i][k] + quad[j][k]) / 2;
                    var normal = Vec.Normalised(Vec.Sub(mid, centre));
                    var corners = new[] { (faces[0][i], normal), (faces[0][j], normal), (faces[1][j], normal), (faces[1][i], normal) };
                    AddFace(obj, corners, normal, 0, uvIndex);
                }
            }
            return plates.Count;
        }

        /// <summary>Appends closed solids swept straight up: each band pairs an inner and an outer plan polyline of
        /// equal length and fills between them from Y0 to Y1 with outer, inner, top, bottom and end faces, every
        /// corner mapped to one atlas point uv. Returns the number of bands.</summary>
        public static int AddProfileBands(ObjFile obj, IReadOnlyList<Band> bands, double[] uv)
        {
            var uvIndex = AddUv(obj, uv);

            double[] P3(double[] q, double y) => new[] { q[0], y, q[1] };

            void Wall(double[] q0, double[] q1, double y0, double y1, double[] facing)
            {
                var corners = new[] { P3(q0, y0), P3(q1, y0), P3(q1, y1), P3(q0, y1) };
                AddFace(obj, Array.ConvertAll(corners, p => (p, Vec.Normalised(facing))), facing, 0, uvIndex);
            }

            foreach (var band in bands)
            {
                double[][] inner = band.Inner, outer = band.Outer;
                for (var i = 0; i + 1 < inner.Length; i++)
                {
                    double[] a = inner[i], b = inner[i + 1], c = outer[i + 1], d = outer[i];
                    var outward = new[] { (c[0] + d[0] - a[0] - b[0]) / 2, 0.0, (c[1] + d[1] - a[1] - b[1]) / 2 };
                    var back = new[] { -outward[0], -outward[1], -outward[2] };
                    Wall(d, c, band.Y0, band.Y1, outward);
                    Wall(a, b, band.Y0, band.Y1, back);
                    foreach (var (y, facing) in new[] { (band.Y0, new[] { 0.0, -1.0, 0.0 }), (band.Y1, new[] { 0.0, 1.0, 0.0 }) })
                        AddFace(obj, Array.ConvertAll(new[] { a, b, c, d }, q => (P3(q, y), facing)), facing, 0, uvIndex);
                }
                foreach (var (i, j) in new[] { (0, 1), (inner.Length - 1, inner.Length - 2) })
                {
                    var facing = new[] { inner[i][0] - inner[j][0], 0.0, inner[i][1] - inner[j][1] };
                    var corners = new[] { P3(inner[i], band.Y0), P3(outer[i], band.Y0), P3(outer[i], band.Y1), P3(inner[i], band.Y1) };
                    AddFace(obj, Array.ConvertAll(corners, p => (p, Vec.Normalised(facing))), facing, 0, uvIndex);
                }
            }
            return bands.Count;
        }

        /// <summary>Appends single-sided convex polygons with their own UVs, wound to face their facing, with a back
        /// face too when double-sided. Returns the number added.</summary>
        public static int AddDecals(ObjFile obj, IReadOnlyList<Decal> decals)
        {
            foreach (var decal in decals)
            {
                var baseVt = obj.Vt.Count;
                foreach (var uv in decal.Uvs) obj.Vt.Add((double[])uv.Clone());
                var facing = Vec.Normalised(decal.Facing);
                int b = obj.V.Count, nBase = obj.Vn.Count;
                foreach (var p in decal.Corners)
                {
                    obj.V.Add((double[])p.Clone());
                    obj.Vn.Add((double[])facing.Clone());
                    obj.Color.Add(null);
                    if (obj.Skinned) obj.Bw.Add(BoneWeights.Single(0));
                }
                double[] pa = decal.Corners[0], pb = decal.Corners[1], pc = decal.Corners[2];
                var g = Vec.Cross(Vec.Sub(pb, pa), Vec.Sub(pc, pa));
                var n = decal.Corners.Length;
                var face = Ordered(n, Vec.Dot(g, facing) > 0, i => new Corner(b + i, baseVt + i, nBase + i));
                obj.Faces.Add(face);
                if (decal.DoubleSided)
                {
                    var backN = obj.Vn.Count;
                    for (var i = 0; i < n; i++) obj.Vn.Add(new[] { -facing[0], -facing[1], -facing[2] });
                    var back = new Corner[n];
                    for (var i = 0; i < n; i++)
                    {
                        var c = face[n - 1 - i];
                        back[i] = new Corner(c.V, c.Vt, backN + (c.Vn - nBase));
                    }
                    obj.Faces.Add(back);
                }
            }
            return decals.Count;
        }
    }
}
