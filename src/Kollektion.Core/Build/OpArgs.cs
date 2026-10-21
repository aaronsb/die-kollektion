using System;
using System.Collections.Generic;
using System.Globalization;
using System.Numerics;
using System.Text;
using System.Text.Json;

namespace Kollektion.Core.Build
{
    /// <summary>One operation's parameters from vehicle.json, or one item of a list of them (a tube, a plate), read
    /// as build_vehicle.py reads them. Errors name the parameter (and the item); VehicleBuild adds the mesh, the
    /// operation's index and its name. Shapes meshlib accepts (a selection or a list of them, a box or a list of
    /// boxes, null bounds) are accepted here too; JSON's types are not bent (true is a boolean, 8 an integer).</summary>
    public sealed class OpArgs
    {
        public readonly string Op;
        readonly JsonElement e;
        readonly string prefix;

        public OpArgs(JsonElement element)
        {
            e = element;
            prefix = "";
            if (e.ValueKind != JsonValueKind.Object) throw new FormatException("an operation must be an object");
            Op = Has("op") && e.GetProperty("op").ValueKind == JsonValueKind.String
                ? e.GetProperty("op").GetString()
                : throw new FormatException("an operation needs \"op\", its name");
        }

        OpArgs(JsonElement item, string op, string prefix)
        {
            e = item;
            Op = op;
            this.prefix = prefix;
        }

        /// <summary>The items of a list parameter, each an object read like an operation's parameters, its errors
        /// prefixed with its place ("tubes[2]: ").</summary>
        public List<OpArgs> Items(string name)
        {
            var v = Get(name);
            if (v.ValueKind != JsonValueKind.Array) throw Error($"\"{name}\" must be a list of objects");
            var items = new List<OpArgs>();
            foreach (var item in v.EnumerateArray())
            {
                var where = $"{prefix}{name}[{items.Count.ToString(CultureInfo.InvariantCulture)}]: ";
                if (item.ValueKind != JsonValueKind.Object) throw new FormatException(where + "must be an object");
                items.Add(new OpArgs(item, Op, where));
            }
            return items;
        }

        public bool Has(string name) => e.TryGetProperty(name, out var v) && v.ValueKind != JsonValueKind.Null;

        public JsonElement Get(string name) =>
            e.TryGetProperty(name, out var v) ? v : throw Error($"needs \"{name}\"");

        /// <summary>The parameter's names, but "op" and "notes".</summary>
        public IEnumerable<string> Names()
        {
            foreach (var p in e.EnumerateObject())
                if (p.Name != "op" && p.Name != "notes") yield return p.Name;
        }

        public FormatException Error(string what) => new FormatException(prefix + what);

        public double Num(string name) => Num(Get(name), name);

        public double Num(string name, double fallback) => Has(name) ? Num(name) : fallback;

        public double? OptNum(string name) => Has(name) ? Num(name) : (double?)null;

        public int Int(string name, int fallback)
        {
            if (!Has(name)) return fallback;
            var v = Get(name);
            return v.ValueKind == JsonValueKind.Number && v.TryGetInt32(out var i) ? i : throw Error($"\"{name}\" must be an integer");
        }

        public bool Bool(string name, bool fallback)
        {
            if (!Has(name)) return fallback;
            switch (Get(name).ValueKind)
            {
                case JsonValueKind.True: return true;
                case JsonValueKind.False: return false;
                default: throw Error($"\"{name}\" must be true or false");
            }
        }

        public string Str(string name) =>
            Has(name) ? (Get(name).ValueKind == JsonValueKind.String ? Get(name).GetString() : throw Error($"\"{name}\" must be a string")) : null;

        public double[] Vector(string name, int length) => Vector(Get(name), name, length);

        public double[][] Points(string name, int length) => Points(Get(name), name, length);

        public IReadOnlyList<Selection> Selections(string name) => Selections(Get(name), name);

        public IReadOnlyList<Selection> OptSelections(string name) => Has(name) ? Selections(name) : null;

        public Box OptBox(string name) => Has(name) ? Box(Get(name), name) : null;

        public double Num(JsonElement v, string name) =>
            v.ValueKind == JsonValueKind.Number && v.TryGetDouble(out var x) && double.IsFinite(x)
                ? x
                : throw Error($"\"{name}\" must be a number" + (v.ValueKind == JsonValueKind.Number ? $" a double can hold, not {v.GetRawText()}" : ""));

        public double[] Vector(JsonElement v, string name, int length)
        {
            if (v.ValueKind != JsonValueKind.Array || (length > 0 && v.GetArrayLength() != length))
                throw Error($"\"{name}\" must be a list of {(length > 0 ? length.ToString(CultureInfo.InvariantCulture) + " " : "")}numbers");
            var r = new double[v.GetArrayLength()];
            var i = 0;
            foreach (var x in v.EnumerateArray()) r[i++] = Num(x, name);
            return r;
        }

        public double[][] Points(JsonElement v, string name, int length)
        {
            if (v.ValueKind != JsonValueKind.Array) throw Error($"\"{name}\" must be a list of points");
            var r = new List<double[]>();
            foreach (var p in v.EnumerateArray()) r.Add(Vector(p, name, length));
            return r.ToArray();
        }

        public IReadOnlyList<Selection> Selections(JsonElement v, string name)
        {
            var r = new List<Selection>();
            if (v.ValueKind == JsonValueKind.Array)
                foreach (var s in v.EnumerateArray()) r.Add(Selection(s, name));
            else r.Add(Selection(v, name));
            return r;
        }

        public Selection Selection(JsonElement v, string name)
        {
            if (v.ValueKind != JsonValueKind.Object) throw Error($"\"{name}\" must be a selection (an object) or a list of them");
            var s = new Selection();
            for (var k = 0; k < 3; k++)
                if (v.TryGetProperty("xyz".Substring(k, 1), out var range)) s.Ranges[k] = Vector(range, name, 2);
            if (v.TryGetProperty("minVertices", out var min)) s.MinVertices = Num(min, name + ".minVertices");
            if (v.TryGetProperty("minSize", out var size))
            {
                if (size.ValueKind != JsonValueKind.Object) throw Error($"\"{name}.minSize\" must be an object");
                for (var k = 0; k < 3; k++)
                    if (size.TryGetProperty("xyz".Substring(k, 1), out var m)) s.MinSize[k] = Num(m, name + ".minSize");
            }
            return s;
        }

        public Box Box(JsonElement v, string name)
        {
            var box = new Box();
            AddBoxParts(box, v, name);
            return box;
        }

        void AddBoxParts(Box box, JsonElement v, string name)
        {
            if (v.ValueKind == JsonValueKind.Array)
            {
                foreach (var b in v.EnumerateArray()) AddBoxParts(box, b, name);
                return;
            }
            if (v.ValueKind != JsonValueKind.Object) throw Error($"\"{name}\" must be a box (an object) or a list of them");
            var part = new double[3][];
            for (var k = 0; k < 3; k++)
            {
                if (!v.TryGetProperty("xyz".Substring(k, 1), out var range)) continue;
                if (range.ValueKind != JsonValueKind.Array || range.GetArrayLength() != 2)
                    throw Error($"\"{name}\" axis ranges must be [lo, hi]");
                var bounds = new double[2];
                var i = 0;
                foreach (var x in range.EnumerateArray())
                    bounds[i++] = x.ValueKind == JsonValueKind.Null ? double.NaN : Num(x, name);
                part[k] = bounds;
            }
            box.Parts.Add(part);
        }

        /// <summary>Python's repr of a JSON value as json.load gives it: dicts, lists, None, True, ints as written,
        /// floats as repr(float), strings quoted; what build_vehicle.py's messages print.</summary>
        public static string Repr(JsonElement v)
        {
            var sb = new StringBuilder();
            Repr(sb, v);
            return sb.ToString();
        }

        static void Repr(StringBuilder sb, JsonElement v)
        {
            switch (v.ValueKind)
            {
                case JsonValueKind.Object:
                    sb.Append('{');
                    var first = true;
                    foreach (var p in v.EnumerateObject())
                    {
                        if (!first) sb.Append(", ");
                        first = false;
                        sb.Append(Quote(p.Name)).Append(": ");
                        Repr(sb, p.Value);
                    }
                    sb.Append('}');
                    break;
                case JsonValueKind.Array:
                    sb.Append('[');
                    var i = 0;
                    foreach (var x in v.EnumerateArray())
                    {
                        if (i++ > 0) sb.Append(", ");
                        Repr(sb, x);
                    }
                    sb.Append(']');
                    break;
                case JsonValueKind.Number:
                    var raw = v.GetRawText();
                    sb.Append(raw.IndexOfAny(new[] { '.', 'e', 'E' }) >= 0
                        ? Py.Repr(v.GetDouble())
                        : BigInteger.Parse(raw, NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture).ToString(CultureInfo.InvariantCulture));
                    break;
                case JsonValueKind.String:
                    sb.Append(Quote(v.GetString()));
                    break;
                case JsonValueKind.True:
                    sb.Append("True");
                    break;
                case JsonValueKind.False:
                    sb.Append("False");
                    break;
                default:
                    sb.Append("None");
                    break;
            }
        }

        static string Quote(string s)
        {
            var q = s.Contains('\'') && !s.Contains('"') ? '"' : '\'';
            var sb = new StringBuilder().Append(q);
            foreach (var c in s)
            {
                if (c == q || c == '\\') sb.Append('\\').Append(c);
                else if (c == '\n') sb.Append("\\n");
                else if (c == '\r') sb.Append("\\r");
                else if (c == '\t') sb.Append("\\t");
                else if (c < ' ' || c == '\x7f') sb.Append("\\x").Append(((int)c).ToString("x2", CultureInfo.InvariantCulture));
                else sb.Append(c);
            }
            return sb.Append(q).ToString();
        }
    }
}
