using System;
using System.Collections.Generic;

namespace Kollektion.Core.Build
{
    /// <summary>coilSprings parameters (meshlib.coil_springs' keyword arguments and defaults).</summary>
    public sealed class CoilSpringsOptions
    {
        public double OuterDiameter = 0.17, WireDiameter = 0.024, Turns = 4.5, Top = 0.80;
        public double? Height;
        public double[] LeafX = { 0.35, 0.49 };
        public int Sides = 12, SegmentsPerTurn = 16, BodyBone = 0;
        public double? X;
    }

    /// <summary>portalAxle parameters (meshlib.portal_axle's keyword arguments and defaults).</summary>
    public sealed class PortalAxleOptions
    {
        public double Lift = 0.20, TubeScale = 2.0, DiffOffset = 0.0, HousingWidth = 0.10, HousingDepth = 0.24;
        public double[] DiffScale = { 1.5, 1.5, 1.5 };
        public int HousingSegments = 20, BodyBone = 0;
    }

    /// <summary>The suspension operations: coil springs in place of leaf springs, and a portal axle.</summary>
    public static partial class MeshOps
    {
        /// <summary>Replaces a leaf-sprung axle's springs with coils standing on the axle's spring seats.
        /// Leaf-spring geometry is every piece whose lateral centre lies within LeafX (absolute), except the spring
        /// seat: the short piece directly over the axle. Each seat gets a coil from its top to Top, or Height above
        /// the seat when given, skinned to the seat's hub bone at the bottom and to BodyBone at the top, with the
        /// shock absorber's UV. X, if given, first moves each seat sideways to that lateral centre (absolute).
        /// Returns the leaf-spring vertices removed and the coils added.</summary>
        public static (int Removed, int Coils) CoilSprings(ObjFile obj, CoilSpringsOptions o)
        {
            var pieces = AxlePieces(obj, 1, "an axle");
            var axle = pieces[0];
            foreach (var p in pieces)
                if (p.Vertices.Count > axle.Vertices.Count) axle = p;     // the differential housing is the largest
            var axleZ = axle.Centre(2);

            var inLeafBand = pieces.FindAll(p => o.LeafX[0] <= Math.Abs(p.Centre(0)) && Math.Abs(p.Centre(0)) <= o.LeafX[1]);
            var seats = inLeafBand.FindAll(p => p.Hi[2] - p.Lo[2] < 0.12 && Math.Abs(p.Centre(2) - axleZ) < 0.05);
            var doomed = new List<int>();
            foreach (var p in inLeafBand)
                if (!seats.Contains(p)) doomed.AddRange(p.Vertices);
            obj.RemoveVertices(doomed);

            var shock = pieces.Find(p => p.Vertices.Exists(i => obj.DominantBone(i) == o.BodyBone))
                ?? throw new InvalidOperationException("no piece is skinned to the body bone (the shock absorber)");
            var uvIndex = CopyUv(obj, shock.Vertices);

            if (o.X.HasValue)
            {
                var moved = new List<Piece>();
                foreach (var seat in seats)
                {
                    var dx = Math.CopySign(o.X.Value, seat.Centre(0)) - seat.Centre(0);
                    foreach (var i in seat.Vertices) obj.V[i][0] += dx;
                    var (lo, hi) = Pieces.Bounds(obj, seat.Vertices);
                    moved.Add(new Piece(seat.Vertices, lo, hi));
                }
                seats = moved;
            }
            foreach (var seat in seats)
            {
                var hubBone = MostCommon(seat.Vertices.ConvertAll(obj.DominantBone));
                var coilTop = o.Height.HasValue ? seat.Hi[1] + o.Height.Value : o.Top;
                AddCoil(obj, seat.Centre(0), seat.Hi[1], seat.Centre(2), coilTop, o, hubBone, o.BodyBone, uvIndex);
            }
            return (doomed.Count, seats.Count);
        }

        /// <summary>The skinned axle mesh's whole components, at least min of them (what they must include).</summary>
        static List<Piece> AxlePieces(ObjFile obj, int min, string needs)
        {
            if (!obj.Skinned) throw new InvalidOperationException("needs a skinned axle mesh (bw lines); this one isn't skinned");
            var pieces = Pieces.WholeComponents(obj);
            if (pieces.Count < min)
                throw new InvalidOperationException($"needs {needs}; the mesh has {pieces.Count} piece{(pieces.Count == 1 ? "" : "s")} with faces");
            return pieces;
        }

        /// <summary>Appends a copy of the first UV a face gives one of these vertices, returning its index.</summary>
        static int CopyUv(ObjFile obj, List<int> vertices)
        {
            var set = new HashSet<int>(vertices);
            foreach (var f in obj.Faces)
                foreach (var c in f)
                    if (set.Contains(c.V) && c.Vt >= 0)
                    {
                        obj.Vt.Add((double[])obj.Vt[c.Vt].Clone());
                        return obj.Vt.Count - 1;
                    }
            throw new InvalidOperationException("no face gives these vertices a UV");
        }

        /// <summary>Counter(values).most_common(1): the most frequent value, the first seen on a tie.</summary>
        static int MostCommon(List<int> values)
        {
            var counts = new Dictionary<int, int>();
            var order = new List<int>();
            foreach (var v in values)
            {
                if (!counts.ContainsKey(v))
                {
                    counts[v] = 0;
                    order.Add(v);
                }
                counts[v]++;
            }
            var best = order[0];
            foreach (var v in order)
                if (counts[v] > counts[best]) best = v;
            return best;
        }

        /// <summary>Appends a helical tube (vertical axis) skinned bottomBone to topBone by height.</summary>
        static void AddCoil(ObjFile obj, double cx, double y0, double cz, double y1, CoilSpringsOptions o, int bottomBone,
            int topBone, int uvIndex)
        {
            var radius = (o.OuterDiameter - o.WireDiameter) / 2;
            var tube = o.WireDiameter / 2;
            var sides = o.Sides;
            var steps = (int)(o.Turns * o.SegmentsPerTurn);
            var b = obj.V.Count;
            for (var s = 0; s <= steps; s++)
            {
                var t = (double)s / steps;
                var angle = 2 * Math.PI * o.Turns * t;
                var centre = new[]
                {
                    cx + radius * Math.Cos(angle), y0 + tube + (y1 - y0 - 2 * tube) * t, cz + radius * Math.Sin(angle),
                };
                var tangent = new[] { -Math.Sin(angle), (y1 - y0) / (2 * Math.PI * o.Turns * radius), Math.Cos(angle) };
                var tl = Math.Sqrt(Py.Sum3(tangent[0] * tangent[0], tangent[1] * tangent[1], tangent[2] * tangent[2]));
                for (var k = 0; k < 3; k++) tangent[k] /= tl;
                var outward = new[] { Math.Cos(angle), 0.0, Math.Sin(angle) };
                var binormal = new[]
                {
                    tangent[1] * outward[2] - tangent[2] * outward[1],
                    tangent[2] * outward[0] - tangent[0] * outward[2],
                    tangent[0] * outward[1] - tangent[1] * outward[0],
                };
                for (var k = 0; k < sides; k++)
                {
                    var a = 2 * Math.PI * k / sides;
                    var normal = new double[3];
                    for (var i = 0; i < 3; i++) normal[i] = outward[i] * Math.Cos(a) + binormal[i] * Math.Sin(a);
                    obj.V.Add(new[] { centre[0] + tube * normal[0], centre[1] + tube * normal[1], centre[2] + tube * normal[2] });
                    obj.Color.Add(new[] { 0.8, 0.8, 0.8 });
                    obj.Vn.Add(normal);
                    obj.Bw.Add(new BoneWeights(new[] { bottomBone, topBone, 0, 0 }, new[] { 1 - t, t, 0.0, 0.0 }));
                }
            }
            var normalsBase = obj.Vn.Count - (steps + 1) * sides;

            int[] Quad(int s, int k) =>
                new[] { s * sides + k, s * sides + (k + 1) % sides, (s + 1) * sides + (k + 1) % sides, (s + 1) * sides + k };

            // Front faces are counter-clockwise in this right-handed file; pick the order that makes the first
            // quad's geometric normal agree with its outward vertex normal.
            var q0 = Quad(0, 0);
            var geometric = Vec.Cross(Vec.Sub(obj.V[b + q0[1]], obj.V[b + q0[0]]), Vec.Sub(obj.V[b + q0[2]], obj.V[b + q0[0]]));
            var forward = Vec.Dot(geometric, obj.Vn[normalsBase + q0[0]]) > 0;
            for (var s = 0; s < steps; s++)
                for (var k = 0; k < sides; k++)
                {
                    var corners = Quad(s, k);
                    if (!forward) Array.Reverse(corners);
                    obj.Faces.Add(Array.ConvertAll(corners, i => new Corner(b + i, uvIndex, normalsBase + i)));
                }
        }

        /// <summary>Turns a beam axle into a portal axle: the beam rides above the wheel centres. The hub caps (the
        /// short pieces at the axle ends) stay at the wheel centre; every other vertex skinned mainly to a hub bone
        /// rises by Lift. The tube's cross-section grows by TubeScale about its axis, the differential by DiffScale
        /// about its centre and moves sideways by DiffOffset (file x). An oval housing at each end, upright in side
        /// profile, joins the hub cap to the raised tube. Returns the vertices lifted and the housings added.</summary>
        public static (int Lifted, int Housings) PortalAxle(ObjFile obj, PortalAxleOptions o)
        {
            var pieces = AxlePieces(obj, 2, "the differential and the axle tube");
            var diff = pieces[0];
            foreach (var p in pieces)
                if (p.Vertices.Count > diff.Vertices.Count) diff = p;
            Piece tube = null;
            foreach (var p in pieces)
                if (p != diff && (tube == null || p.Hi[0] - p.Lo[0] > tube.Hi[0] - tube.Lo[0])) tube = p;
            var hubCaps = pieces.FindAll(p => Math.Abs(p.Centre(0)) > 0.6 && p.Hi[0] - p.Lo[0] < 0.2);
            var hubBones = new HashSet<int>();
            var capVertices = new HashSet<int>();
            foreach (var p in hubCaps)
            {
                hubBones.Add(obj.DominantBone(p.Vertices[0]));
                capVertices.UnionWith(p.Vertices);
            }

            var lifted = 0;
            for (var i = 0; i < obj.V.Count; i++)
                if (!capVertices.Contains(i) && hubBones.Contains(obj.DominantBone(i)))
                {
                    obj.V[i][1] += o.Lift;
                    lifted++;
                }

            double axisY = tube.Centre(1) + o.Lift, axisZ = tube.Centre(2);
            foreach (var i in tube.Vertices)
            {
                var p = obj.V[i];
                p[1] = axisY + (p[1] - axisY) * o.TubeScale;
                p[2] = axisZ + (p[2] - axisZ) * o.TubeScale;
            }
            var dc = new[] { diff.Centre(0), diff.Centre(1) + o.Lift, diff.Centre(2) };
            foreach (var i in diff.Vertices)
            {
                var p = obj.V[i];
                for (var k = 0; k < 3; k++) p[k] = dc[k] + (p[k] - dc[k]) * o.DiffScale[k];
                p[0] += o.DiffOffset;
            }

            var tubeHalf = (tube.Hi[1] - tube.Lo[1]) / 2 * o.TubeScale;
            foreach (var cap in hubCaps)
            {
                var bone = obj.DominantBone(cap.Vertices[0]);
                var uv = CopyUv(obj, cap.Vertices);
                var left = cap.Centre(0) > 0;
                var inner = left ? cap.Lo[0] : cap.Hi[0];
                var other = left ? inner - o.HousingWidth : inner + o.HousingWidth;
                var (x0, x1) = other < inner ? (other, inner) : (inner, other);
                double bottom = cap.Centre(1) - 0.10, top = axisY + tubeHalf + 0.04;
                AddOvalHousing(obj, x0, x1, (bottom + top) / 2, axisZ, (top - bottom) / 2, o.HousingDepth / 2, bone, uv,
                    o.HousingSegments);
            }
            return (lifted, hubCaps.Count);
        }

        /// <summary>Appends an elliptical prism (oval in side profile, extruded along x) skinned to one bone.</summary>
        static void AddOvalHousing(ObjFile obj, double x0, double x1, double cy, double cz, double halfHeight,
            double halfDepth, int bone, int uvIndex, int segments)
        {
            var ring = new (double Y, double Z, double[] N)[segments];
            for (var k = 0; k < segments; k++)
            {
                var t = 2 * Math.PI * k / segments;
                double y = cy + halfHeight * Math.Cos(t), z = cz + halfDepth * Math.Sin(t);
                double ny = Math.Cos(t) / halfHeight, nz = Math.Sin(t) / halfDepth;
                var length = Py.Hypot(ny, nz);
                ring[k] = (y, z, new[] { 0.0, ny / length, nz / length });
            }
            for (var k = 0; k < segments; k++)
            {
                var a = ring[k];
                var b = ring[(k + 1) % segments];
                var corners = new[]
                {
                    (new[] { x0, a.Y, a.Z }, a.N), (new[] { x0, b.Y, b.Z }, b.N),
                    (new[] { x1, b.Y, b.Z }, b.N), (new[] { x1, a.Y, a.Z }, a.N),
                };
                var outward = new double[3];
                for (var i = 0; i < 3; i++) outward[i] = (a.N[i] + b.N[i]) / 2;
                AddFace(obj, corners, outward, bone, uvIndex);
            }
            foreach (var (x, nx) in new[] { (x0, -1.0), (x1, 1.0) })
            {
                var corners = Array.ConvertAll(ring, r => (new[] { x, r.Y, r.Z }, new[] { nx, 0.0, 0.0 }));
                AddFace(obj, corners, new[] { nx, 0.0, 0.0 }, bone, uvIndex);
            }
        }
    }
}
