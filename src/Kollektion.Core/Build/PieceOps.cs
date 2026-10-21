using System;
using System.Collections.Generic;

namespace Kollektion.Core.Build
{
    /// <summary>paint's face choice: any combination of pieces, a box, a UV rectangle (less exclusions) and a facing.</summary>
    public sealed class PaintChoice
    {
        public IReadOnlyList<Selection> Select;
        public Box Box;
        /// <summary>With a box: every vertex inside it, not just the centroid.</summary>
        public bool Whole;
        /// <summary>[[u0, u1], [v0, v1]].</summary>
        public double[][] UvRect;
        public IReadOnlyList<double[][]> UvExclude = Array.Empty<double[][]>();
        public double[] Facing;
    }

    /// <summary>The operations that move, cut or recolour existing geometry, and insertPart.</summary>
    public static partial class MeshOps
    {
        /// <summary>Lengthens the mesh behind a stepped body cut: a vertex at height y moves by shift along z when it
        /// lies behind the z of the highest step at or below y (the lowest step's below them all). Returns how many
        /// moved.</summary>
        public static int Stretch(ObjFile obj, double[][] profile, double shift)
        {
            var steps = (double[][])profile.Clone();
            Array.Sort(steps, (p, q) => p[0] != q[0] ? p[0].CompareTo(q[0]) : p[1].CompareTo(q[1]));
            var moved = 0;
            foreach (var p in obj.V)
            {
                var cut = steps[0][1];
                for (var i = steps.Length - 1; i >= 0; i--)
                    if (p[1] >= steps[i][0])
                    {
                        cut = steps[i][1];
                        break;
                    }
                if (p[2] < cut)
                {
                    p[2] += shift;
                    moved++;
                }
            }
            return moved;
        }

        /// <summary>Widens the chosen pieces about the centreline: vertices with |x| > cutX (and inside box, if
        /// given) move outward by shift, so the sides move rigidly and faces spanning the cut stretch. Returns the
        /// number of vertices moved.</summary>
        public static int WidenPieces(ObjFile obj, IReadOnlyList<Selection> select, double cutX, double shift, Box box)
        {
            var moved = 0;
            foreach (var idx in Pieces.Select(obj, select))
                foreach (var i in idx)
                {
                    var p = obj.V[i];
                    if (Math.Abs(p[0]) > cutX && (box == null || box.Contains(p)))
                    {
                        p[0] += p[0] > 0 ? shift : -shift;
                        moved++;
                    }
                }
            return moved;
        }

        /// <summary>Drops the faces FacesInBox chooses; returns how many.</summary>
        public static int RemoveRegion(ObjFile obj, Box box, double unitSize)
        {
            var doomed = new HashSet<int>(Pieces.FacesInBox(obj, box, unitSize));
            RemoveFaces(obj, doomed);
            return doomed.Count;
        }

        static void RemoveFaces(ObjFile obj, HashSet<int> doomed)
        {
            var kept = new List<Corner[]>(obj.Faces.Count - doomed.Count);
            for (var n = 0; n < obj.Faces.Count; n++)
                if (!doomed.Contains(n)) kept.Add(obj.Faces[n]);
            obj.Faces = kept;
        }

        /// <summary>Drops faces with any corner within radius of the lateral (x) line through centre [y, z] (an
        /// axle) and, if given, inside box: clears bodywork a larger tyre would run into. Returns how many.</summary>
        public static int RemoveNearAxle(ObjFile obj, double[] centre, double radius, Box box)
        {
            bool Near(double[] p) => Py.Hypot(p[1] - centre[0], p[2] - centre[1]) < radius && (box == null || box.Contains(p));
            var doomed = new HashSet<int>();
            for (var n = 0; n < obj.Faces.Count; n++)
                if (Array.Exists(obj.Faces[n], c => Near(obj.V[c.V]))) doomed.Add(n);
            RemoveFaces(obj, doomed);
            return doomed.Count;
        }

        /// <summary>Drops every chosen piece; returns how many.</summary>
        public static int RemovePieces(ObjFile obj, IReadOnlyList<Selection> select)
        {
            var chosen = Pieces.Select(obj, select);
            var doomed = new HashSet<int>();
            foreach (var idx in chosen) doomed.UnionWith(idx);
            obj.RemoveVertices(doomed);
            return chosen.Count;
        }

        /// <summary>Scales the vertices of the chosen pieces about origin, only those inside box if given. Returns
        /// the number of vertices moved.</summary>
        public static int ScalePieces(ObjFile obj, IReadOnlyList<Selection> select, double[] origin, double[] scale, Box box)
        {
            var moved = 0;
            foreach (var i in ChosenVertices(obj, select))
            {
                var p = obj.V[i];
                if (box != null && !box.Contains(p)) continue;
                for (var k = 0; k < 3; k++) p[k] = origin[k] + (p[k] - origin[k]) * scale[k];
                moved++;
            }
            return moved;
        }

        /// <summary>Moves the chosen pieces rigidly by offset; returns the number of pieces and vertices moved.</summary>
        public static (int Pieces, int Vertices) MovePieces(ObjFile obj, IReadOnlyList<Selection> select, double[] offset)
        {
            var chosen = Pieces.Select(obj, select);
            var moved = new HashSet<int>();
            foreach (var idx in chosen) moved.UnionWith(idx);
            foreach (var i in moved)
                for (var k = 0; k < 3; k++)
                    obj.V[i][k] += offset[k];
            return (chosen.Count, moved.Count);
        }

        static HashSet<int> ChosenVertices(ObjFile obj, IReadOnlyList<Selection> select)
        {
            var set = new HashSet<int>();
            foreach (var idx in Pieces.Select(obj, select)) set.UnionWith(idx);
            return set;
        }

        /// <summary>Lengthens or shortens the chosen pieces across cutZ: their vertices on one side of the cut move
        /// by shift along z. move is "ahead" (z > cutZ) or "behind"; null for the side shift points to. Returns the
        /// number of pieces and vertices moved.</summary>
        public static (int Pieces, int Vertices) StretchPieces(ObjFile obj, IReadOnlyList<Selection> select, double cutZ,
            double shift, string move)
        {
            var ahead = move == null ? shift > 0 : move == "ahead";
            var chosen = Pieces.Select(obj, select);
            var moved = 0;
            foreach (var idx in chosen)
                foreach (var i in idx)
                    if ((obj.V[i][2] > cutZ) == ahead)
                    {
                        obj.V[i][2] += shift;
                        moved++;
                    }
            return (chosen.Count, moved);
        }

        /// <summary>Moves one connected piece: rotates it by rotateY degrees about the vertical through its anchor
        /// (the centre of its +z end), then moves the anchor to anchorTo (a null axis keeps its value). Exactly one
        /// piece must match. Returns the piece's bounds after the move.</summary>
        public static (double[] Lo, double[] Hi) RelocatePiece(ObjFile obj, Selection select, double rotateY, double?[] anchorTo)
        {
            var matches = Pieces.Find(obj).FindAll(p => select.Matches(p.Lo, p.Hi, p.Vertices.Count));
            if (matches.Count != 1)
                throw new InvalidOperationException($"relocatePiece selection matched {matches.Count} pieces");
            var idx = matches[0].Vertices;
            var (_, hi) = Pieces.Bounds(obj, idx);
            var anchor = new double[3];
            for (var k = 0; k < 3; k++)
            {
                var sum = new Py.Sum();
                var count = 0;
                foreach (var i in idx)
                    if (obj.V[i][2] > hi[2] - 0.03)
                    {
                        sum.Add(obj.V[i][k]);
                        count++;
                    }
                anchor[k] = sum.Value / count;
            }
            var a = Py.Radians(rotateY);
            double c = Math.Cos(a), s = Math.Sin(a);
            var target = new double[3];
            for (var k = 0; k < 3; k++) target[k] = anchorTo == null || anchorTo[k] == null ? anchor[k] : anchorTo[k].Value;
            var members = new HashSet<int>(idx);
            var normals = new HashSet<int>();
            foreach (var f in obj.Faces)
                foreach (var cn in f)
                    if (members.Contains(cn.V) && cn.Vn >= 0) normals.Add(cn.Vn);
            foreach (var i in idx)
            {
                double x = obj.V[i][0] - anchor[0], y = obj.V[i][1] - anchor[1], z = obj.V[i][2] - anchor[2];
                obj.V[i] = new[] { x * c + z * s + target[0], y + target[1], -x * s + z * c + target[2] };
            }
            foreach (var n in normals)
            {
                double x = obj.Vn[n][0], y = obj.Vn[n][1], z = obj.Vn[n][2];
                obj.Vn[n] = new[] { x * c + z * s, y, -x * s + z * c };
            }
            return Pieces.Bounds(obj, idx);
        }

        /// <summary>Appends the faces of another mesh (same file conventions and space) that lie in box (null for
        /// everywhere). Whole pieces are kept only if they match a selection in include (when given) and none in
        /// exclude. Returns the number of faces added.</summary>
        public static int InsertPart(ObjFile obj, ObjFile part, Box box, IReadOnlyList<Selection> include,
            IReadOnlyList<Selection> exclude, double unitSize)
        {
            if (obj.Skinned)
                throw new InvalidOperationException("insertPart does not skin inserted geometry; the base mesh is skinned");
            var excluded = new HashSet<int>();
            foreach (var p in Pieces.Find(part))
            {
                var wanted = include == null || AnyMatch(include, p);
                if (!wanted || AnyMatch(exclude, p)) excluded.UnionWith(p.Vertices);
            }
            var chosen = Pieces.FacesInBox(part, box ?? Box.Everything(), unitSize);
            var vMap = new Dictionary<int, int>();
            var vtMap = new Dictionary<int, int>();
            var vnMap = new Dictionary<int, int>();

            int Remap(Dictionary<int, int> table, int index, List<double[]> source, List<double[]> target)
            {
                if (index < 0) return -1;
                if (!table.TryGetValue(index, out var mapped))
                {
                    mapped = target.Count;
                    table[index] = mapped;
                    target.Add((double[])source[index].Clone());
                }
                return mapped;
            }

            var added = 0;
            foreach (var n in chosen)
            {
                var face = part.Faces[n];
                if (Array.Exists(face, c => excluded.Contains(c.V))) continue;
                var newFace = new Corner[face.Length];
                for (var i = 0; i < face.Length; i++)
                {
                    var c = face[i];
                    if (!vMap.ContainsKey(c.V)) obj.Color.Add(part.Color[c.V]);
                    newFace[i] = new Corner(Remap(vMap, c.V, part.V, obj.V), Remap(vtMap, c.Vt, part.Vt, obj.Vt),
                        Remap(vnMap, c.Vn, part.Vn, obj.Vn));
                }
                obj.Faces.Add(newFace);
                added++;
            }
            return added;
        }

        static bool AnyMatch(IReadOnlyList<Selection> selects, Piece p)
        {
            foreach (var s in selects)
                if (s.Matches(p.Lo, p.Hi, p.Vertices.Count)) return true;
            return false;
        }

        /// <summary>Maps every corner of the chosen faces to one atlas point uv (e.g. a painted panel or glass), so
        /// they take that spot's flat colour. A facing keeps faces whose mean vertex normal lies within about 25
        /// degrees of it. Returns the number of faces repainted.</summary>
        public static int Paint(ObjFile obj, double[] uv, PaintChoice choice)
        {
            var vertices = choice.Select == null ? null : ChosenVertices(obj, choice.Select);
            var uvIndex = AddUv(obj, uv);
            var painted = 0;
            for (var n = 0; n < obj.Faces.Count; n++)
            {
                var face = obj.Faces[n];
                if (vertices != null && !vertices.Contains(face[0].V)) continue;
                if (choice.Box != null)
                {
                    var inside = choice.Whole
                        ? Array.TrueForAll(face, c => choice.Box.Contains(obj.V[c.V]))
                        : choice.Box.Contains(Pieces.Centroid(obj, face));
                    if (!inside) continue;
                }
                if (choice.Facing != null)
                {
                    if (Array.Exists(face, c => c.Vn < 0)) continue;
                    var normal = new double[3];
                    for (var k = 0; k < 3; k++)
                    {
                        var sum = new Py.Sum();
                        foreach (var c in face) sum.Add(obj.Vn[c.Vn][k]);
                        normal[k] = sum.Value;
                    }
                    var length = Vec.Length(normal);
                    if (length == 0.0) length = 1.0;
                    if (Vec.Dot(normal, choice.Facing) / length < 0.9) continue;
                }
                if (choice.UvRect != null)
                {
                    if (Array.Exists(face, c => c.Vt < 0)) continue;
                    var centre = new double[2];
                    for (var k = 0; k < 2; k++)
                    {
                        var sum = new Py.Sum();
                        foreach (var c in face) sum.Add(obj.Vt[c.Vt][k]);
                        centre[k] = sum.Value / face.Length;
                    }
                    if (!InRect(choice.UvRect, centre)) continue;
                    var excludedRect = false;
                    foreach (var r in choice.UvExclude)
                        if (InRect(r, centre)) excludedRect = true;
                    if (excludedRect) continue;
                }
                var repainted = new Corner[face.Length];
                for (var i = 0; i < face.Length; i++) repainted[i] = new Corner(face[i].V, uvIndex, face[i].Vn);
                obj.Faces[n] = repainted;
                painted++;
            }
            return painted;
        }

        static bool InRect(double[][] rect, double[] centre) =>
            rect[0][0] <= centre[0] && centre[0] <= rect[0][1] && rect[1][0] <= centre[1] && centre[1] <= rect[1][1];
    }
}
