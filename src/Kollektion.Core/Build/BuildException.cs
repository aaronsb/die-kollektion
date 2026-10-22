using System;
using System.Globalization;
using System.Text;

namespace Kollektion.Core.Build
{
    /// <summary>
    /// Why a vehicle build stopped: the one exception <see cref="VehicleBuild.Run"/> throws, whatever went wrong
    /// (a definition that isn't strict JSON, a missing or mistyped field, a path leaving its folder, an operation
    /// refusing its parameters or making something that isn't a finite number, a file that can't be read or written).
    /// The message says where: <c>meshes["Body/paint"].ops[2] (addTubes): ...</c>. Nothing is written when it's thrown
    /// before the outputs are (every case but a failing write).
    /// </summary>
    public sealed class BuildException : Exception
    {
        /// <summary>The node path of the mesh being built; null for the definition as a whole.</summary>
        public string Mesh { get; }

        /// <summary>The operation's index in the mesh's "ops"; -1 outside an operation.</summary>
        public int OpIndex { get; }

        /// <summary>The operation's name, or the step ("read", "stretch") outside one; null when unknown.</summary>
        public string Step { get; }

        public BuildException(string message, Exception inner = null) : base(message, inner) => OpIndex = -1;

        public BuildException(string mesh, int opIndex, string step, string message, Exception inner = null)
            : base(Where(mesh, opIndex, step) + ": " + message, inner)
        {
            Mesh = mesh;
            OpIndex = opIndex;
            Step = step;
        }

        public BuildException(string mesh, int opIndex, string step, Exception inner) : this(mesh, opIndex, step, inner.Message, inner)
        {
        }

        static string Where(string mesh, int opIndex, string step)
        {
            var sb = new StringBuilder("meshes[").Append(Quote(mesh)).Append(']');
            if (opIndex >= 0) sb.Append(".ops[").Append(opIndex.ToString(CultureInfo.InvariantCulture)).Append(']');
            if (step != null) sb.Append(" (").Append(step).Append(')');
            return sb.ToString();
        }

        /// <summary>A string as a JSON literal, for messages naming manifest values.</summary>
        public static string Quote(string s)
        {
            var sb = new StringBuilder("\"");
            foreach (var c in s)
            {
                if (c == '"' || c == '\\') sb.Append('\\').Append(c);
                else if (c < ' ' || c == '\x7f') sb.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                else sb.Append(c);
            }
            return sb.Append('"').ToString();
        }
    }
}
