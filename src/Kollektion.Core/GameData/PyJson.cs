using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;

namespace Kollektion.Core.GameData
{
    /// <summary>A JSON object that keeps its keys in insertion order, as a Python dict does.</summary>
    public sealed class PyDict : IEnumerable<KeyValuePair<string, object>>
    {
        readonly List<string> keys = new List<string>();
        readonly Dictionary<string, object> values = new Dictionary<string, object>();

        public object this[string key]
        {
            get => values[key];
            set
            {
                if (!values.ContainsKey(key)) keys.Add(key);
                values[key] = value;
            }
        }

        public void Add(string key, object value) => this[key] = value;
        public bool ContainsKey(string key) => values.ContainsKey(key);
        public int Count => keys.Count;

        public IEnumerator<KeyValuePair<string, object>> GetEnumerator()
        {
            foreach (var k in keys)
                yield return new KeyValuePair<string, object>(k, values[k]);
        }

        IEnumerator IEnumerable.GetEnumerator() => GetEnumerator();
    }

    /// <summary>Python's <c>json.dump(value, f, indent=1)</c>, byte for byte: one space per level, "," at line ends,
    /// ": " after keys, non-ASCII escaped as \uXXXX, floats as repr, no newline at the end. Values: PyDict, IList,
    /// string, double/float, integers, bool, null.</summary>
    public static class PyJson
    {
        public static string Dump(object value)
        {
            var sb = new StringBuilder();
            Write(sb, value, 0);
            return sb.ToString();
        }

        /// <summary>Writes under a temporary name and renames it into place, so an interrupted run leaves the old file
        /// or none, never a truncated one (as tools/export_upgrades.py and export_parts.py do).</summary>
        public static void WriteFile(string path, object value) => Output.WriteAtomic(path, Dump(value));

        static void Write(StringBuilder sb, object value, int level)
        {
            switch (value)
            {
                case null: sb.Append("null"); break;
                case bool b: sb.Append(b ? "true" : "false"); break;
                case string s: WriteString(sb, s); break;
                case double d: sb.Append(Float(d)); break;
                case float f: sb.Append(Float(f)); break;
                case int _:
                case long _:
                case uint _:
                case ulong _:
                case short _:
                case ushort _:
                case byte _:
                case sbyte _:
                    sb.Append(Convert.ToString(value, CultureInfo.InvariantCulture));
                    break;
                case PyDict dict:
                    if (dict.Count == 0) { sb.Append("{}"); break; }
                    sb.Append('{');
                    bool first = true;
                    foreach (var kv in dict)
                    {
                        if (!first) sb.Append(',');
                        first = false;
                        Indent(sb, level + 1);
                        WriteString(sb, kv.Key);
                        sb.Append(": ");
                        Write(sb, kv.Value, level + 1);
                    }
                    Indent(sb, level);
                    sb.Append('}');
                    break;
                case IList list:
                    if (list.Count == 0) { sb.Append("[]"); break; }
                    sb.Append('[');
                    for (int i = 0; i < list.Count; i++)
                    {
                        if (i > 0) sb.Append(',');
                        Indent(sb, level + 1);
                        Write(sb, list[i], level + 1);
                    }
                    Indent(sb, level);
                    sb.Append(']');
                    break;
                default:
                    throw new ArgumentException($"no JSON form for {value.GetType().Name}");
            }
        }

        static string Float(double d)
        {
            if (double.IsNaN(d)) return "NaN";
            if (double.IsInfinity(d)) return d > 0 ? "Infinity" : "-Infinity";
            return PyFormat.Repr(d);
        }

        static void Indent(StringBuilder sb, int level) => sb.Append('\n').Append(' ', level);

        static void WriteString(StringBuilder sb, string s)
        {
            sb.Append('"');
            foreach (char c in s)
            {
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    case '\b': sb.Append("\\b"); break;
                    case '\f': sb.Append("\\f"); break;
                    default:
                        if (c < ' ' || c > '~') sb.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                        else sb.Append(c);
                        break;
                }
            }
            sb.Append('"');
        }
    }

    /// <summary>File output shared by the exporters: UTF-8 without a BOM, "\n" line ends on every OS.</summary>
    public static class Output
    {
        static readonly UTF8Encoding Utf8 = new UTF8Encoding(false);

        public static void WriteText(string path, string text) => File.WriteAllText(path, text, Utf8);

        public static void WriteAtomic(string path, string text)
        {
            var tmp = path + ".tmp";
            File.WriteAllText(tmp, text, Utf8);
            File.Move(tmp, path, true);
        }
    }
}
