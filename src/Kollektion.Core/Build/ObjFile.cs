using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;

namespace Kollektion.Core.Build
{
    /// <summary>One face corner: 0-based vertex, UV and normal indices, -1 where the file had none.</summary>
    public readonly struct Corner
    {
        public readonly int V, Vt, Vn;

        public Corner(int v, int vt, int vn)
        {
            V = v;
            Vt = vt;
            Vn = vn;
        }
    }

    /// <summary>A vertex's skinning: four bone indices and their weights (a "bw" line).</summary>
    public sealed class BoneWeights
    {
        public readonly int[] Bones;
        public readonly double[] Weights;

        public BoneWeights(int[] bones, double[] weights)
        {
            Bones = bones;
            Weights = weights;
        }

        /// <summary>A vertex bound wholly to one bone.</summary>
        public static BoneWeights Single(int bone) => new BoneWeights(new[] { bone, 0, 0, 0 }, new[] { 1.0, 0.0, 0.0, 0.0 });
    }

    /// <summary>
    /// The car-root-space OBJ files of the vehicle pipeline (tools/meshlib.py's Obj), read and written as it does:
    /// x negated (right-handed), y up, z forward, metres. Beyond plain OBJ: optional vertex colours on v lines,
    /// "bw i0 i1 i2 i3 w0 w1 w2 w3" skinning lines parallel to the v lines, and "bp" bind-pose lines kept verbatim.
    /// Other statements (o, g, s, usemtl) are dropped, as meshlib drops them.
    /// </summary>
    public sealed class ObjFile
    {
        public readonly List<string> Header = new List<string>();
        public readonly List<double[]> V = new List<double[]>();
        /// <summary>Per vertex: [r, g, b], or null when the v line had none.</summary>
        public readonly List<double[]> Color = new List<double[]>();
        /// <summary>Per vertex when skinned, else empty.</summary>
        public readonly List<BoneWeights> Bw = new List<BoneWeights>();
        public readonly List<double[]> Vt = new List<double[]>();
        public readonly List<double[]> Vn = new List<double[]>();
        public readonly List<string> Bp = new List<string>();
        public List<Corner[]> Faces = new List<Corner[]>();

        public bool Skinned => Bw.Count > 0;

        static readonly CultureInfo Inv = CultureInfo.InvariantCulture;

        /// <summary>Reads an OBJ, refusing (FormatException, naming the line) a statement short of numbers, a face
        /// corner indexing past what the file has, or bw lines that don't pair with the v lines.</summary>
        public static ObjFile Read(string path)
        {
            var o = new ObjFile();
            using (var reader = new StreamReader(path, new UTF8Encoding(false), false))
            {
                string line;
                var number = 0;
                while ((line = reader.ReadLine()) != null)
                {
                    number++;
                    try
                    {
                        ReadLine(o, line);
                    }
                    catch (Exception e) when (e is FormatException || e is IndexOutOfRangeException || e is ArgumentOutOfRangeException || e is OverflowException)
                    {
                        throw new FormatException($"{path} line {number}: can't read \"{line}\"", e);
                    }
                }
            }
            if (o.Bw.Count != 0 && o.Bw.Count != o.V.Count)
                throw new FormatException($"{path}: {o.Bw.Count} bw lines for {o.V.Count} vertices; a skinned OBJ has one per v line");
            for (var n = 0; n < o.Faces.Count; n++)
                foreach (var c in o.Faces[n])
                    if (c.V < 0 || c.V >= o.V.Count || c.Vt < -1 || c.Vt >= o.Vt.Count || c.Vn < -1 || c.Vn >= o.Vn.Count)
                        throw new FormatException($"{path}: face {n + 1} names a vertex, UV or normal the file doesn't have");
            return o;
        }

        static void ReadLine(ObjFile o, string line)
        {
            var p = Split(line);
            if (p.Count == 0) return;
            switch (p[0])
            {
                case "#":
                    o.Header.Add(line);
                    break;
                case "v":
                    o.V.Add(new[] { F(p[1]), F(p[2]), F(p[3]) });
                    o.Color.Add(p.Count >= 7 ? new[] { F(p[4]), F(p[5]), F(p[6]) } : null);
                    break;
                case "bw":
                    o.Bw.Add(new BoneWeights(new[] { I(p[1]), I(p[2]), I(p[3]), I(p[4]) },
                        new[] { F(p[5]), F(p[6]), F(p[7]), F(p[8]) }));
                    break;
                case "vt":
                    o.Vt.Add(new[] { F(p[1]), F(p[2]) });
                    break;
                case "vn":
                    o.Vn.Add(new[] { F(p[1]), F(p[2]), F(p[3]) });
                    break;
                case "bp":
                    o.Bp.Add(line);
                    break;
                case "f":
                    var face = new Corner[p.Count - 1];
                    for (var i = 1; i < p.Count; i++) face[i - 1] = ParseCorner(p[i]);
                    o.Faces.Add(face);
                    break;
            }
        }

        public void Write(string path)
        {
            using var w = new StreamWriter(path, false, new UTF8Encoding(false), 1 << 16) { NewLine = "\n" };
            foreach (var line in Header) w.Write(line + "\n");
            var sb = new StringBuilder();
            for (var i = 0; i < V.Count; i++)
            {
                sb.Clear();
                var v = V[i];
                sb.Append("v ").Append(Py.Fixed(v[0], 6)).Append(' ').Append(Py.Fixed(v[1], 6)).Append(' ').Append(Py.Fixed(v[2], 6));
                var c = Color[i];
                if (c != null && c.Length > 0)
                    foreach (var x in c) sb.Append(' ').Append(Py.Fixed(x, 3));
                sb.Append('\n');
                if (Bw.Count > 0)
                {
                    var b = Bw[i];
                    sb.Append("bw");
                    foreach (var bone in b.Bones) sb.Append(' ').Append(bone.ToString(Inv));
                    foreach (var weight in b.Weights) sb.Append(' ').Append(Py.Fixed(weight, 6));
                    sb.Append('\n');
                }
                w.Write(sb);
            }
            foreach (var t in Vt) w.Write("vt " + Py.Fixed(t[0], 6) + " " + Py.Fixed(t[1], 6) + "\n");
            foreach (var n in Vn) w.Write("vn " + Py.Fixed(n[0], 6) + " " + Py.Fixed(n[1], 6) + " " + Py.Fixed(n[2], 6) + "\n");
            foreach (var line in Bp) w.Write(line + "\n");
            foreach (var face in Faces)
            {
                sb.Clear();
                sb.Append('f');
                foreach (var corner in face)
                {
                    sb.Append(' ');
                    Index(sb, corner.V).Append('/');
                    Index(sb, corner.Vt).Append('/');
                    Index(sb, corner.Vn);
                }
                sb.Append('\n');
                w.Write(sb);
            }
        }

        /// <summary>The bone with the largest weight; the first on a tie.</summary>
        public int DominantBone(int i)
        {
            var b = Bw[i];
            var best = 0;
            for (var k = 1; k < 4; k++)
                if (b.Weights[k] > b.Weights[best]) best = k;
            return b.Bones[best];
        }

        /// <summary>Drops faces touching any doomed vertex; orphaned vertices stay, unreferenced.</summary>
        public void RemoveVertices(ICollection<int> doomed)
        {
            var set = doomed as HashSet<int> ?? new HashSet<int>(doomed);
            Faces = Faces.FindAll(f => !Array.Exists(f, c => set.Contains(c.V)));
        }

        static StringBuilder Index(StringBuilder sb, int i) => i < 0 ? sb : sb.Append((i + 1).ToString(Inv));

        static Corner ParseCorner(string token)
        {
            var ids = token.Split('/');
            return new Corner(Slot(ids, 0), Slot(ids, 1), Slot(ids, 2));
        }

        static int Slot(string[] ids, int k) => k < ids.Length && ids[k].Length > 0 ? I(ids[k]) - 1 : -1;

        static double F(string s) => double.Parse(s, NumberStyles.Float, Inv);

        static int I(string s) => int.Parse(s, NumberStyles.AllowLeadingSign, Inv);

        /// <summary>str.split(): runs of Python whitespace.</summary>
        static List<string> Split(string line)
        {
            var parts = new List<string>();
            var start = -1;
            for (var i = 0; i <= line.Length; i++)
            {
                var space = i == line.Length || IsSpace(line[i]);
                if (space && start >= 0)
                {
                    parts.Add(line.Substring(start, i - start));
                    start = -1;
                }
                else if (!space && start < 0) start = i;
            }
            return parts;
        }

        static bool IsSpace(char c) => char.IsWhiteSpace(c) || (c >= '\x1c' && c <= '\x1f');
    }
}
