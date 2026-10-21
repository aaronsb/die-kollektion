using System.IO;
using System.Text;
using System.Text.RegularExpressions;

namespace Kollektion.Core
{
    /// <summary>Read-only facts about a game folder: the game's Steam build, BepInEx and our install, as
    /// tools/werkstatt.py's status reads them.</summary>
    public sealed class GameFolder
    {
        public const string LoaderName = "DieKollektion.Loader.dll";

        public string Path { get; }

        public GameFolder(string path) { Path = path; }

        string At(params string[] parts) => System.IO.Path.Combine(Path, System.IO.Path.Combine(parts));

        /// <summary>The game's Steam build id, from steamapps/appmanifest_&lt;id&gt;.acf two levels up, or null.</summary>
        public string SteamBuild()
        {
            var acf = Vdf.Load(At("..", "..", $"appmanifest_{Platform.AppId}.acf"));
            return acf == null ? null : Vdf.Value(Vdf.Section(acf, "appstate"), "buildid");
        }

        /// <summary>BepInEx's version string (6.0.0-be.N+hash) read from BepInEx.Core.dll; "unknown" when the file
        /// holds none or can't be read, null when BepInEx isn't installed.</summary>
        public string BepInExVersion()
        {
            var dll = At("BepInEx", "core", "BepInEx.Core.dll");
            if (!File.Exists(dll)) return null;
            var bytes = Files.ReadBytes(dll);
            var m = bytes == null ? Match.Empty : Regex.Match(Encoding.Latin1.GetString(bytes), @"6\.0\.0-be\.\d+\+[0-9a-f]{7,40}");
            return m.Success ? m.Value : "unknown";
        }

        /// <summary>BepInEx's hash of the game assemblies its interop came from; the plugin is built against it.</summary>
        public string InteropHash()
        {
            return Files.ReadText(At("BepInEx", "interop", "assembly-hash.txt"))?.Trim();
        }

        public bool LoaderInstalled => File.Exists(At("BepInEx", "plugins", LoaderName));
    }
}
