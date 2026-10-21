using System;
using System.IO;
using System.Reflection;
using System.Text.Encodings.Web;
using System.Text.Json;
using Kollektion.Core;

namespace Kollektion
{
    static class Program
    {
        static string Version =>
            typeof(Program).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion
                ?.Split('+')[0] ?? "?";

        const string Usage =
            "Die Kollektion {0} ({1})\n\n" +
            "Usage: kollektion <command>\n\n" +
            "  status [--json]   where the game, BepInEx and Die Kollektion are on this machine (reads only)\n" +
            "  extract --out <dir>  the parts the build reads, from your own game (never shared; extract --help)\n" +
            "  version           this program's version\n";

        static int Main(string[] args)
        {
            var cmd = args.Length > 0 ? args[0] : "help";
            switch (cmd)
            {
                case "status":
                    return Status(Array.IndexOf(args, "--json") > 0);
                case "extract": return ExtractCommand.Run(args);
                case "version":
                case "--version":
                    Console.WriteLine(Version);
                    return 0;
                case "help":
                case "--help":
                case "-h":
                    Console.Write(Usage, Version, Platform.Os);
                    return 0;
                default:
                    Console.Error.Write($"Unknown command: {cmd}\n\n" + string.Format(Usage, Version, Platform.Os));
                    return 2;
            }
        }

        static int Status(bool json)
        {
            var dir = Platform.GameDir();
            var game = dir != null ? new GameFolder(dir) : null;
            var facts = new (string Key, string Label, string Value)[]
            {
                ("version", "Die Kollektion", Version),
                ("os", "System", Platform.Os),
                ("gameDir", "Game folder", dir),
                ("steamBuild", "Steam build", game?.SteamBuild()),
                ("bepinex", "BepInEx", game?.BepInExVersion()),
                ("interopHash", "Interop", game?.InteropHash()),
                ("loader", "Loader", game == null ? null : game.LoaderInstalled ? "installed" : "not installed"),
                ("saves", "Saves", Platform.SavesDir()),
                ("playerLog", "Player.log", Platform.PlayerLog()),
            };
            if (json)
            {
                using var stream = Console.OpenStandardOutput();
                using var w = new Utf8JsonWriter(stream, new JsonWriterOptions
                {
                    Indented = true,
                    // Paths and version strings stay readable (a '+' instead of \u002B); this is never HTML.
                    Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
                });
                w.WriteStartObject();
                foreach (var f in facts)
                {
                    if (f.Value == null) w.WriteNull(f.Key);
                    else w.WriteString(f.Key, f.Value);
                }
                w.WriteEndObject();
                w.Flush();
                stream.WriteByte((byte)'\n');
                return 0;
            }
            foreach (var f in facts)
                Console.WriteLine($"{f.Label + ":",-16}{f.Value ?? "not found"}");
            return 0;
        }
    }
}
