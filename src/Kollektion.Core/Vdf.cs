using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;

namespace Kollektion.Core
{
    /// <summary>Valve's KeyValues text format (libraryfolders.vdf, appmanifest_*.acf), as tools/werkstatt.py's
    /// vdf_load reads it: nested dictionaries, keys lower-cased, values strings.</summary>
    public static class Vdf
    {
        static readonly Regex Token = new Regex("\"((?:[^\"\\\\]|\\\\.)*)\"|([{}])", RegexOptions.Compiled);

        public static Dictionary<string, object> Parse(string text)
        {
            var stack = new Stack<Dictionary<string, object>>();
            var cur = new Dictionary<string, object>();
            string key = null;
            foreach (Match m in Token.Matches(text))
            {
                string brace = m.Groups[2].Success ? m.Groups[2].Value : null;
                if (brace == "{")
                {
                    var child = new Dictionary<string, object>();
                    cur[(key ?? "").ToLowerInvariant()] = child;
                    stack.Push(cur);
                    cur = child;
                    key = null;
                }
                else if (brace == "}")
                {
                    if (stack.Count > 0) cur = stack.Pop();
                }
                else if (key == null)
                {
                    key = m.Groups[1].Value;
                }
                else
                {
                    cur[key.ToLowerInvariant()] = m.Groups[1].Value.Replace("\\\"", "\"").Replace("\\\\", "\\");
                    key = null;
                }
            }
            return cur;
        }

        public static Dictionary<string, object> Load(string path) =>
            Parse(File.ReadAllText(path, Encoding.UTF8));

        /// <summary>The dictionary at a path of keys, or null.</summary>
        public static Dictionary<string, object> Section(Dictionary<string, object> root, params string[] keys)
        {
            var cur = root;
            foreach (var k in keys)
            {
                if (cur == null || !cur.TryGetValue(k, out var next)) return null;
                cur = next as Dictionary<string, object>;
            }
            return cur;
        }

        public static string Value(Dictionary<string, object> section, string key) =>
            section != null && section.TryGetValue(key, out var v) ? v as string : null;
    }
}
