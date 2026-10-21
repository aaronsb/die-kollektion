using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

namespace Kollektion.Core
{
    /// <summary>Where things are on this OS: the one place per-OS differences live (docs/vehicle_factory.md, Parity).
    /// GAME_DIR, MY_GAMES and KOLLEKTION_STEAM_ROOT point everything at copies, as they do for the Makefile.</summary>
    public static class Platform
    {
        public const string GameFolderName = "over the hill";
        public const string ExeLinux = "over the hill.x86_64";
        public const string ExeWindows = "over the hill.exe";
        public const string AppId = "2929250";

        public static bool IsWindows => OperatingSystem.IsWindows();
        public static string Os => IsWindows ? "windows" : OperatingSystem.IsLinux() ? "linux" : "other";

        static string Home => Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);

        /// <summary>Steam installs on this machine, each once (Linux has several paths to the same one).</summary>
        public static List<string> SteamRoots()
        {
            var cands = new List<string>();
            var env = Environment.GetEnvironmentVariable("KOLLEKTION_STEAM_ROOT");
            if (!string.IsNullOrEmpty(env))
                cands.Add(env);
            else if (IsWindows)
            {
                // The default install first: Steam writes SteamPath lower-cased with forward slashes, and the
                // case-blind dedupe below keeps the first spelling of a folder.
                var x86 = Environment.GetEnvironmentVariable("ProgramFiles(x86)") ?? @"C:\Program Files (x86)";
                cands.Add(Path.Combine(x86, "Steam"));
                cands.Add(WindowsSteamPath());
            }
            else
            {
                foreach (var p in new[] { ".local/share/Steam", ".steam/steam", ".steam/debian-installation",
                                          ".var/app/com.valvesoftware.Steam/.local/share/Steam" })
                    cands.Add(Path.Combine(Home, p));
            }
            var seen = new HashSet<string>(IsWindows ? StringComparer.OrdinalIgnoreCase : StringComparer.Ordinal);
            var roots = new List<string>();
            foreach (var c in cands.Where(c => !string.IsNullOrEmpty(c) && Directory.Exists(c)))
                if (seen.Add(RealPath(c)))
                    roots.Add(c);
            return roots;
        }

        static string WindowsSteamPath()
        {
            if (!OperatingSystem.IsWindows()) return null;
            using var key = Microsoft.Win32.Registry.CurrentUser.OpenSubKey(@"Software\Valve\Steam");
            return (key?.GetValue("SteamPath") as string)?.Replace('/', '\\');
        }

        static string RealPath(string path)
        {
            try
            {
                var target = new DirectoryInfo(path).ResolveLinkTarget(returnFinalTarget: true);
                return Path.GetFullPath(target?.FullName ?? path).TrimEnd(Path.DirectorySeparatorChar);
            }
            catch (Exception e) when (e is IOException || e is UnauthorizedAccessException)
            {
                return Path.GetFullPath(path).TrimEnd(Path.DirectorySeparatorChar);
            }
        }

        /// <summary>Every Steam library: each root, and the paths its libraryfolders.vdf lists.</summary>
        public static List<string> SteamLibraries()
        {
            var libraries = new List<string>();
            foreach (var root in SteamRoots())
            {
                libraries.Add(root);
                var vdf = Path.Combine(root, "steamapps", "libraryfolders.vdf");
                var folders = Vdf.Section(Vdf.Load(vdf), "libraryfolders");
                if (folders == null) continue;
                foreach (var entry in folders.Values.OfType<Dictionary<string, object>>())
                    if (Vdf.Value(entry, "path") is string p && p.Length > 0)
                        libraries.Add(p);
            }
            return libraries;
        }

        /// <summary>The game folder: GAME_DIR, else the first Steam library holding the game, else null.</summary>
        public static string GameDir()
        {
            var env = Environment.GetEnvironmentVariable("GAME_DIR");
            if (!string.IsNullOrEmpty(env)) return env;
            foreach (var lib in SteamLibraries())
            {
                var cand = Path.Combine(lib, "steamapps", "common", GameFolderName);
                if (File.Exists(Path.Combine(cand, ExeLinux)) || File.Exists(Path.Combine(cand, ExeWindows)))
                    return cand;
            }
            return null;
        }

        /// <summary>The game's documents folder, which holds Saves/ and LocalLiveries/: ~/My Games/over the hill
        /// on Linux, Documents\My Games\over the hill on Windows (the official livery guide).</summary>
        public static string MyGames()
        {
            var env = Environment.GetEnvironmentVariable("MY_GAMES");
            if (!string.IsNullOrEmpty(env)) return env;
            var docs = IsWindows ? Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments) : Home;
            if (string.IsNullOrEmpty(docs)) docs = Path.Combine(Home, "Documents");
            return Path.Combine(docs, "My Games", GameFolderName);
        }

        public static string SavesDir() => Path.Combine(MyGames(), "Saves");

        /// <summary>Unity's Player.log for this game.</summary>
        public static string PlayerLog()
        {
            if (IsWindows)
                return Path.Combine(Home, "AppData", "LocalLow", "Funselektor", GameFolderName, "Player.log");
            var config = Environment.GetEnvironmentVariable("XDG_CONFIG_HOME");
            if (string.IsNullOrEmpty(config)) config = Path.Combine(Home, ".config");
            return Path.Combine(config, "unity3d", "Funselektor", GameFolderName, "Player.log");
        }
    }
}
