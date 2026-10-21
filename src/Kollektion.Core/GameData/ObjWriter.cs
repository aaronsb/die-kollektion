using System.Globalization;
using System.Text;

namespace Kollektion.Core.GameData
{
    /// <summary>OBJ text as tools/export_*.py write it: coordinates already in OBJ space (the caller negates Unity's
    /// x), six decimals as Python's f"{x:.6f}", "\n" line ends. Shared by <see cref="ObjExport"/> and
    /// <see cref="Upgrades"/>.</summary>
    public sealed class ObjWriter
    {
        readonly StringBuilder sb = new StringBuilder();

        static string F6(double v) => PyFormat.Fixed(v, 6);

        static string N(int i) => i.ToString(CultureInfo.InvariantCulture);

        /// <summary>A whole line as given (comments, "o" lines and the format's extension lines).</summary>
        public ObjWriter Line(string text)
        {
            sb.Append(text).Append('\n');
            return this;
        }

        /// <summary>"v x y z", with an RGB colour (three decimals) when given.</summary>
        public void Vertex(double x, double y, double z, double[] colour = null)
        {
            sb.Append("v ").Append(F6(x)).Append(' ').Append(F6(y)).Append(' ').Append(F6(z));
            if (colour != null)
                foreach (var c in colour) sb.Append(' ').Append(PyFormat.Fixed(c, 3));
            sb.Append('\n');
        }

        public void TexCoord(double u, double v) => sb.Append("vt ").Append(F6(u)).Append(' ').Append(F6(v)).Append('\n');

        public void Normal(double x, double y, double z) =>
            sb.Append("vn ").Append(F6(x)).Append(' ').Append(F6(y)).Append(' ').Append(F6(z)).Append('\n');

        /// <summary>"f a b c" with 1-based vertex numbers.</summary>
        public void Face(int a, int b, int c) =>
            sb.Append("f ").Append(N(a)).Append(' ').Append(N(b)).Append(' ').Append(N(c)).Append('\n');

        /// <summary>"f a/a/a b/b/b c/c/c" with 1-based numbers, the texture and normal references empty when the
        /// mesh has none ("a//").</summary>
        public void Face(int a, int b, int c, bool uv, bool normals)
        {
            sb.Append('f');
            foreach (var i in new[] { a, b, c })
            {
                var s = N(i);
                sb.Append(' ').Append(s).Append('/').Append(uv ? s : "").Append('/').Append(normals ? s : "");
            }
            sb.Append('\n');
        }

        public override string ToString() => sb.ToString();
    }
}
