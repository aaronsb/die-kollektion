using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using System.Threading;

namespace DieKollektion.Loader;

/// <summary>What the loader does at plugin Load, kept free of BepInEx and game types so tools/loader-plan can run it offline.</summary>
/// <remarks>
/// The real plugin (BepInEx/VehicleMods/VehicleMods.dll, outside plugins/, so BepInEx never scans it) is compiled
/// against BepInEx's interop, which BepInEx regenerates from the game before any plugin loads. Its deployed.json
/// records the interop hash it was built for. When that matches BepInEx/interop/assembly-hash.txt the loader
/// starts it; when not (the game updated), it installs a DLL built for the new interop first: the release's
/// prebuilt one when it was built for it, else one compiled from the Werkstatt folder recorded at deploy, if that
/// folder's plugin sources are still the deployed ones. The game waits meanwhile (Load runs on Unity's main thread,
/// before the swap chain is set up), with a progress window. Whenever the plugin can't be started (CantStart), a
/// save holding our trucks would hang the game at load, so the loader says why and the game quits; with no such
/// save it runs stock.
/// </remarks>
public static class LoaderCore
{
    public const string PluginDll = "VehicleMods.dll";
    public const string Record = "deployed.json";
    /// <summary>Under BepInEx/: where the loader compiles, so the checkout's bin/ is left alone; removed once used.</summary>
    public const string BuildDir = "VehicleMods.build";
    static readonly string[] TruckIds = { "3000000001", "3000000002", "3000000003", "3000000004" };
    static readonly string[] BuildInputs = { "Directory.Build.props", "Directory.Build.targets", "global.json" };

    public enum Outcome { Load, Stock, Quit }

    public sealed class Result
    {
        public Outcome Outcome;
        public string Dll;
        /// <summary>The Steam build the plugin was rebuilt for this launch, or null when no rebuild was needed.</summary>
        public string RebuiltFor;
        public string Message;
    }

    public interface IUi
    {
        void Begin(string text);
        void End();
        void Error(string title, string text);
        void Notify(string title, string text);
    }

    public sealed class Setup
    {
        public string GameDir;
        public string BepInExDir;
        /// <summary>BepInEx/plugins/: the loader's own folder, where no other copy of the plugin may be.</summary>
        public string PluginsDir;
        public string PluginDir;
        /// <summary>The game's Saves/ folder; every profile in it is checked for our trucks.</summary>
        public string SavesDir;
        public Action<string> Log = _ => { };
        public IUi Ui;
        /// <summary>A dotnet to use instead of searching for one (WERKSTATT_DOTNET; tests).</summary>
        public string Dotnet;
        public TimeSpan BuildTimeout = TimeSpan.FromMinutes(5);
        public TimeSpan LockWait = TimeSpan.FromSeconds(10);
        /// <summary>Reads one save file (tests: a save that changes between reads).</summary>
        public Func<string, string> ReadSave = File.ReadAllText;
    }

    public static Result Prepare(Setup s)
    {
        try
        {
            using var held = Lock(s);
            if (held == null)
                return CantStart(s, "another Werkstatt step (a deploy?) holds BepInEx/werkstatt.lock");
            return PrepareLocked(s);
        }
        catch (Exception e)
        {
            return CantStart(s, $"the loader failed ({e.GetType().Name}: {e.Message})");
        }
    }

    static Result PrepareLocked(Setup s)
    {
        var stray = StrayCopies(s.PluginsDir);
        if (stray.Count > 0)
        {
            var files = string.Join(", ", stray.Select(f => "BepInEx/plugins/" + f));
            // `make deploy` moves only an install from before the loader, BepInEx/plugins/VehicleMods/, out of plugins/.
            var deployMoves = stray.All(f => f.StartsWith("VehicleMods/", StringComparison.Ordinal));
            var fix = deployMoves
                ? $"Run `make deploy` in the Werkstatt folder, which moves this install from before the loader out of plugins/, or delete {files}. "
                : $"Delete {files}. ";
            return CantStart(s, $"another copy of the plugin is in BepInEx/plugins/ ({files}), which BepInEx loads by itself",
                             fix + "Until then the mod may still load from that copy, which may not fit this game.",
                             "Die Kollektion: remove a stray copy");
        }
        var record = ReadJson(Path.Combine(s.PluginDir, Record));
        var dll = Path.Combine(s.PluginDir, PluginDll);
        if (record == null || !File.Exists(dll))
            return CantStart(s, $"nothing is deployed in {s.PluginDir} (run `make deploy`)");
        var live = InteropHash(s.BepInExDir);
        if (live == null)
            return CantStart(s, "BepInEx's interop hash (BepInEx/interop/assembly-hash.txt) is missing, so the loader can't tell which game the plugin must fit");
        var builtFor = Text(record["game"]?["interopHash"]);
        if (builtFor == live)
            return new Result { Outcome = Outcome.Load, Dll = dll, Message = "the plugin fits this game" };

        var build = SteamBuild(s.GameDir) ?? "?";
        s.Log($"The game's interop changed ({Short(builtFor)} → {Short(live)}, Steam build {build}); getting a plugin built for it");
        s.Ui?.Begin($"Die Kollektion: rebuilding the plugin for the game's new version (Steam build {build})…");
        string candidate, how = null, why;
        try
        {
            var werkstatt = Text(record["werkstatt"]);
            (candidate, why) = Prebuilt(werkstatt, live);
            if (candidate != null)
                how = "prebuilt";
            else
            {
                s.Log($"No prebuilt plugin fits: {why}");
                (candidate, why) = Compile(s, record, werkstatt);
                how = "compiled";
            }
            if (candidate != null)
                Install(s, record, candidate, live, builtFor, build, how);
        }
        finally
        {
            s.Ui?.End();
            RemoveBuildDir(s);
        }
        if (candidate == null)
            return CantStart(s, why);
        s.Log($"Installed a plugin built for Steam build {build} ({how})");
        return new Result { Outcome = Outcome.Load, Dll = dll, RebuiltFor = build, Message = $"rebuilt for Steam build {build} ({how})" };
    }

    public const string UpdateFix = "In the Werkstatt folder, run `make update` (it needs the .NET SDK, or a release built for this game version).";

    /// <summary>Every way the plugin can't be started ends here: a save holding our trucks would hang the game at
    /// load without it, so then the game quits with a dialog naming the fix; otherwise it runs stock, with a
    /// notification titled <paramref name="stockTitle"/>.</summary>
    public static Result CantStart(Setup s, string why, string fix = UpdateFix, string stockTitle = "Die Kollektion is off this session")
    {
        if (TrucksOrUnreadable(s))
        {
            s.Log($"Die Kollektion can't start: {why}. A save holds its trucks, which the game can't load without it; quitting");
            s.Ui?.Error("Die Kollektion can't start",
                $"{why}.\n\nYour save holds Die Kollektion's trucks, and the game can't load it without the plugin, so it will close now. Nothing was changed.\n\n{fix}");
            return new Result { Outcome = Outcome.Quit, Message = why };
        }
        s.Log($"Die Kollektion can't start: {why}. The loader doesn't start the plugin; the game goes on. {fix}");
        s.Ui?.Notify(stockTitle, $"{why}. {fix}");
        return new Result { Outcome = Outcome.Stock, Message = why };
    }

    /// <summary>The plugin's own can't-start: no safe place for its hooks' jump slots (issue #34; after an interop
    /// regeneration, the first start after a game update), or its entry hook failing. At the plugin's Load
    /// (<paramref name="atLoad"/>) the main thread hasn't read a save yet, so with trucks in a save this is
    /// <see cref="CantStart"/> and the game quits; without, the plugin goes on (Outcome.Load) and tries again before
    /// its hooks. After Load the game reads and writes its save while a dialog waits, so quitting then could cut a
    /// save write short: this never returns Quit then, and reads the saves once, so a save that changes between
    /// reads can't turn into a quit. With trucks the dialog tells the player not to load the save; without, a
    /// notification says the mod is off.</summary>
    public static Result PluginCantStart(Setup s, string why, string fix, bool atLoad)
    {
        var trucks = TrucksOrUnreadable(s);
        if (atLoad)
            return trucks ? CantStart(s, why, fix) : new Result { Outcome = Outcome.Load, Message = why };
        if (trucks)
        {
            s.Log($"Die Kollektion can't start: {why}. A save holds its trucks; too late to quit safely, so the player is told not to load it");
            s.Ui?.Error("Die Kollektion can't start",
                $"{why}.\n\nYour save holds Die Kollektion's trucks, which the game can't load without it. Quit the game from the main menu without loading your save.\n\n{fix}");
        }
        else
        {
            s.Log($"Die Kollektion can't start: {why}. No save holds its trucks; the game goes on without it. {fix}");
            s.Ui?.Notify("Die Kollektion is off this session", $"{why}. {fix}");
        }
        return new Result { Outcome = Outcome.Stock, Message = why };
    }

    static bool TrucksOrUnreadable(Setup s)
    {
        try { return SavesHoldTrucks(s.SavesDir, s.ReadSave); }
        catch (Exception) { return true; }      // can't read the saves: assume the worst rather than hang
    }

    // ------------------------------------------------------------------ the DLL for the new interop

    static (string, string) Prebuilt(string werkstatt, string live)
    {
        if (string.IsNullOrEmpty(werkstatt))
            return (null, "the deploy didn't record its Werkstatt folder");
        var dll = Path.Combine(werkstatt, "prebuilt", PluginDll);
        var info = ReadJson(Path.Combine(werkstatt, "prebuilt", "VehicleMods.json"));
        if (info == null || !File.Exists(dll))
            return (null, "this Werkstatt folder has no prebuilt plugin (a source checkout builds its own)");
        if (Text(info["builtAgainst"]?["gameAssemblyHash"]) != live)
            return (null, "the release's prebuilt plugin was built for another game version");
        if (Sha256(dll) != Text(info["sha256"]))
            return (null, "the prebuilt plugin doesn't match its recorded checksum");
        return (dll, null);
    }

    static (string, string) Compile(Setup s, JsonNode record, string werkstatt)
    {
        var container = InSteamRuntime();
        var where = container ? " inside Steam's runtime container" : "";
        if (string.IsNullOrEmpty(werkstatt))
            return (null, "the deploy didn't record its Werkstatt folder (run `make deploy` once)");
        if (!Directory.Exists(werkstatt))
            return (null, container
                ? $"the Werkstatt folder {werkstatt} isn't visible inside Steam's runtime container (only your home folder is shared with it)"
                : $"the Werkstatt folder recorded at deploy ({werkstatt}) isn't there");
        var project = Path.Combine(werkstatt, "plugins", "VehicleMods");
        var deployed = Text(record["pluginSources"]?["sha256"]);
        if (deployed == null || !Directory.Exists(project) || SourcesHash(project, werkstatt) != deployed)
            return (null, $"the plugin's sources in {werkstatt} have changed since the deploy, so a build there wouldn't match the installed vehicles");
        var dotnet = s.Dotnet ?? FindDotnet(container);
        if (dotnet == null)
            return (null, container
                ? "no .NET SDK is visible inside Steam's runtime container (looked in ~/.dotnet and the host's /usr; a Flatpak Steam can't see the host's)"
                : "the .NET SDK wasn't found");
        var output = Path.Combine(s.BepInExDir, BuildDir);
        RemoveBuildDir(s);
        var args = new[] { "build", project, "-c", "Release", "-nologo", "-v", "minimal", "-m:1", "-nodeReuse:false",
                           "-p:UseSharedCompilation=false", "-p:Deploy=false", $"-p:GameDir={s.GameDir}", "-o", output };
        s.Log($"Compiling with {dotnet}{(container ? " (the host's SDK, from inside Steam's runtime)" : "")}");
        var (code, text) = Run(dotnet, args, BuildEnvironment(container), s.BuildTimeout);
        if (code != 0)
        {
            s.Log("The build failed:\n" + Tail(text, 30));
            return (null, code == -1 ? $"the build timed out{where}" : $"the build failed{where} (see BepInEx/werkstatt-launch.log)");
        }
        var built = Path.Combine(output, PluginDll);
        return File.Exists(built) ? (built, null) : (null, $"the build didn't produce {built}");
    }

    static void Install(Setup s, JsonNode record, string candidate, string live, string builtFor, string build, string how)
    {
        var dll = Path.Combine(s.PluginDir, PluginDll);
        using (var from = File.OpenRead(candidate))
            ReplaceSynced(dll, from.CopyTo);
        var hash = Sha256(dll);
        foreach (var entry in record["files"] as JsonArray ?? new JsonArray())
            if (Text(entry?["path"]) == PluginDll)
                entry["sha256"] = hash;
        var game = record["game"] as JsonObject ?? new JsonObject();
        game["interopHash"] = live;
        record["game"] = game;
        record["plugin"] = how;
        record["afterUpdate"] = new JsonObject
        {
            ["by"] = "loader",
            ["how"] = how,
            ["fromInterop"] = builtFor,
            ["steamBuild"] = build,
            ["rebuiltAt"] = DateTimeOffset.Now.ToString("yyyy-MM-ddTHH:mm:sszzz"),
        };
        WriteJson(Path.Combine(s.PluginDir, Record), record);
    }

    /// <summary>A leftover build folder costs nothing but space, so failing to remove it (a killed build's child still
    /// writing into it) is logged and never changes the outcome.</summary>
    static void RemoveBuildDir(Setup s)
    {
        var dir = Path.Combine(s.BepInExDir, BuildDir);
        try
        {
            if (Directory.Exists(dir))
                Directory.Delete(dir, true);
        }
        catch (Exception e)
        {
            s.Log($"Couldn't remove BepInEx/{BuildDir} ({e.GetType().Name}: {e.Message}); leaving it");
        }
    }

    // ------------------------------------------------------------------ the SDK, inside or outside Steam's runtime

    /// <summary>Steam starts the game inside its Linux runtime (pressure-vessel), where the host's files are under
    /// /run/host and the SDK needs the host's libraries (OpenSSL, ICU) on the library path.</summary>
    public static bool InSteamRuntime() => Directory.Exists("/run/pressure-vessel") && Directory.Exists("/run/host/usr");

    public static string FindDotnet(bool container)
    {
        var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        var candidates = new List<string> { Environment.GetEnvironmentVariable("WERKSTATT_DOTNET"), Path.Combine(home, ".dotnet", "dotnet") };
        foreach (var root in container ? new[] { "/run/host/usr" } : new[] { "/usr", "/usr/local" })
            foreach (var sub in new[] { "share/dotnet", "lib/dotnet", "lib64/dotnet" })
                candidates.Add(Path.Combine(root, sub, "dotnet"));
        if (!container)
            candidates.AddRange((Environment.GetEnvironmentVariable("PATH") ?? "").Split(':').Where(p => p.Length > 0).Select(p => Path.Combine(p, "dotnet")));
        return candidates.FirstOrDefault(c => !string.IsNullOrEmpty(c) && File.Exists(c));
    }

    static Dictionary<string, string> BuildEnvironment(bool container) => new()
    {
        ["DOTNET_CLI_TELEMETRY_OPTOUT"] = "1",
        ["DOTNET_NOLOGO"] = "1",
        ["DOTNET_SKIP_FIRST_TIME_EXPERIENCE"] = "1",
        ["MSBUILDDISABLENODEREUSE"] = "1",
        ["DOTNET_CLI_USE_MSBUILD_SERVER"] = "0",
        ["LD_LIBRARY_PATH"] = container
            ? string.Join(":", new[] { "/run/host/usr/lib/x86_64-linux-gnu", "/run/host/usr/lib64", "/run/host/usr/lib" }.Where(Directory.Exists))
            : null,
    };

    /// <summary>Runs a child process with the game's environment minus what Steam and BepInEx inject (LD_PRELOAD, the
    /// runtime's library path, BepInEx's own .NET), plus <paramref name="set"/>; null values are removed. One deadline
    /// covers the run and the end of its output: a grandchild left holding the pipes can't hold the game.</summary>
    public static (int, string) Run(string file, IEnumerable<string> args, Dictionary<string, string> set, TimeSpan timeout)
    {
        var info = new ProcessStartInfo(file) { RedirectStandardOutput = true, RedirectStandardError = true, RedirectStandardInput = true, UseShellExecute = false };
        foreach (var a in args) info.ArgumentList.Add(a);
        CleanEnvironment(info.Environment);
        foreach (var (k, v) in set ?? new Dictionary<string, string>())
            if (v == null) info.Environment.Remove(k); else info.Environment[k] = v;
        var text = new StringBuilder();
        var deadline = DateTime.UtcNow + timeout;
        using var p = new Process { StartInfo = info };
        p.OutputDataReceived += (_, e) => { if (e.Data != null) lock (text) text.AppendLine(e.Data); };
        p.ErrorDataReceived += (_, e) => { if (e.Data != null) lock (text) text.AppendLine(e.Data); };
        p.Start();
        p.StandardInput.Close();
        p.BeginOutputReadLine();
        p.BeginErrorReadLine();
        if (!p.WaitForExit(Remaining(deadline)))
        {
            try { p.Kill(true); } catch (Exception) { }
            p.WaitForExit(5000);
            lock (text) return (-1, text.ToString());
        }
        // The process has exited; its output ends when every holder of the pipes has closed them, so that wait is
        // bounded too (5 s at most, within the deadline).
        using (var cts = new CancellationTokenSource(Math.Min(5000, Math.Max(1, Remaining(deadline)))))
        {
            try { p.WaitForExitAsync(cts.Token).Wait(); }
            catch (Exception) { }
        }
        lock (text) return (p.ExitCode, text.ToString());
    }

    static int Remaining(DateTime deadline) => (int)Math.Max(0, (deadline - DateTime.UtcNow).TotalMilliseconds);

    public static void CleanEnvironment(IDictionary<string, string> env)
    {
        foreach (var key in env.Keys.ToList())
            if (key is "LD_PRELOAD" or "LD_LIBRARY_PATH" or "DOTNET_ROOT" or "DOTNET_STARTUP_HOOKS"
                || key.StartsWith("DOORSTOP_", StringComparison.Ordinal) || key.StartsWith("COREHOST_", StringComparison.Ordinal))
                env.Remove(key);
    }

    // ------------------------------------------------------------------ facts read from disk

    /// <summary>BepInEx/werkstatt.lock, the lock Werkstatt's deploy takes (Python's fcntl.flock; .NET's FileShare.None
    /// is flock on Unix), waited for at most <see cref="Setup.LockWait"/>. Null when another step holds it.</summary>
    static IDisposable Lock(Setup s)
    {
        var path = Path.Combine(s.BepInExDir, "werkstatt.lock");
        var until = DateTime.UtcNow + s.LockWait;
        while (true)
        {
            try { return new FileStream(path, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None); }
            catch (IOException) when (DateTime.UtcNow < until) { Thread.Sleep(250); }
            catch (IOException) { return null; }
        }
    }

    /// <summary>Copies of the plugin under BepInEx/plugins/: BepInEx would load them as well as the loader's.</summary>
    public static List<string> StrayCopies(string pluginsDir) =>
        string.IsNullOrEmpty(pluginsDir) || !Directory.Exists(pluginsDir)
            ? new List<string>()
            : Directory.EnumerateFiles(pluginsDir, PluginDll, SearchOption.AllDirectories)
                .Select(f => Path.GetRelativePath(pluginsDir, f).Replace(Path.DirectorySeparatorChar, '/')).ToList();

    public static string InteropHash(string bepinex)
    {
        var p = Path.Combine(bepinex, "interop", "assembly-hash.txt");
        var text = File.Exists(p) ? File.ReadAllText(p).Trim() : "";
        return text.Length > 0 ? text : null;
    }

    public static string SteamBuild(string game)
    {
        var p = Path.GetFullPath(Path.Combine(game, "..", "..", "appmanifest_2929250.acf"));
        if (!File.Exists(p)) return null;
        var m = Regex.Match(File.ReadAllText(p), "\"buildid\"\\s+\"(\\d+)\"", RegexOptions.IgnoreCase);
        return m.Success ? m.Groups[1].Value : null;
    }

    /// <summary>Any profile in Saves/ owning one of our trucks (by ItemId).</summary>
    public static bool SavesHoldTrucks(string savesDir, Func<string, string> read = null)
    {
        if (string.IsNullOrEmpty(savesDir) || !Directory.Exists(savesDir)) return false;
        foreach (var save in Directory.EnumerateFiles(savesDir, "*.json"))
        {
            var text = (read ?? File.ReadAllText)(save);
            if (TruckIds.Any(id => Regex.IsMatch(text, $"(?<!\\d){id}(?!\\d)")))
                return true;
        }
        return false;
    }

    /// <summary>The plugin's sources as deployed: SHA-256 over every .cs and .csproj under the project folder
    /// (bin/ and obj/ excluded) and the MSBuild inputs (Directory.Build.*, global.json) in it and its parents up to
    /// <paramref name="root"/>, each as its path relative to the project, a NUL, its bytes and a NUL, in ordinal path
    /// order. tools/werkstatt.py computes the same at deploy (plugin_sources_hash).</summary>
    public static string SourcesHash(string project, string root = null)
    {
        var dir = Path.GetFullPath(project);
        string Rel(string f) => Path.GetRelativePath(dir, f).Replace(Path.DirectorySeparatorChar, '/');
        var files = Directory.EnumerateFiles(dir, "*", SearchOption.AllDirectories).Select(Rel)
            .Where(r => (r.EndsWith(".cs", StringComparison.Ordinal) || r.EndsWith(".csproj", StringComparison.Ordinal))
                        && !r.StartsWith("bin/", StringComparison.Ordinal) && !r.StartsWith("obj/", StringComparison.Ordinal))
            .ToList();
        var top = Path.GetFullPath(root ?? project);
        for (var d = new DirectoryInfo(dir); d != null; d = d.Parent)
        {
            foreach (var name in BuildInputs)
                if (File.Exists(Path.Combine(d.FullName, name)))
                    files.Add(Rel(Path.Combine(d.FullName, name)));
            if (string.Equals(d.FullName.TrimEnd('/'), top.TrimEnd('/'), StringComparison.Ordinal))
                break;
        }
        using var sha = SHA256.Create();
        var nul = new byte[] { 0 };
        foreach (var rel in files.Distinct().OrderBy(r => r, StringComparer.Ordinal))
        {
            var name = Encoding.UTF8.GetBytes(rel);
            sha.TransformBlock(name, 0, name.Length, null, 0);
            sha.TransformBlock(nul, 0, 1, null, 0);
            var bytes = File.ReadAllBytes(Path.GetFullPath(Path.Combine(dir, rel)));
            sha.TransformBlock(bytes, 0, bytes.Length, null, 0);
            sha.TransformBlock(nul, 0, 1, null, 0);
        }
        sha.TransformFinalBlock(Array.Empty<byte>(), 0, 0);
        return Convert.ToHexString(sha.Hash).ToLowerInvariant();
    }

    public static string Sha256(string path)
    {
        using var f = File.OpenRead(path);
        using var sha = SHA256.Create();
        return Convert.ToHexString(sha.ComputeHash(f)).ToLowerInvariant();
    }

    /// <summary>A JSON value as a string, or null when it is missing or not a string.</summary>
    static string Text(JsonNode node) => node is JsonValue v && v.TryGetValue<string>(out var s) ? s : null;

    static JsonNode ReadJson(string path)
    {
        try { return File.Exists(path) ? JsonNode.Parse(File.ReadAllText(path)) : null; }
        catch (Exception) { return null; }
    }

    static void WriteJson(string path, JsonNode node)
    {
        var bytes = Encoding.UTF8.GetBytes(node.ToJsonString(new JsonSerializerOptions { WriteIndented = true }) + "\n");
        ReplaceSynced(path, to => to.Write(bytes));
    }

    /// <summary>Writes a temp file beside <paramref name="path"/>, fsyncs it and renames it over the path, so after a
    /// crash or power loss the path holds the old file or the whole new one, never an empty one.</summary>
    static void ReplaceSynced(string path, Action<Stream> write)
    {
        var temp = path + ".loader-new";
        using (var to = new FileStream(temp, FileMode.Create, FileAccess.Write))
        {
            write(to);
            to.Flush(true);
        }
        File.Move(temp, path, true);
    }

    static string Short(string hash) => string.IsNullOrEmpty(hash) ? "none" : hash.Length > 10 ? hash[..10] : hash;

    static string Tail(string text, int lines) => string.Join("\n", text.Split('\n').TakeLast(lines));
}

/// <summary>A progress window and dialogs from zenity, with notify-send as the fallback. Both exist inside Steam's
/// runtime; they run with the game's environment minus what Steam and BepInEx inject, and are reaped before Load
/// returns.</summary>
public sealed class DesktopUi : LoaderCore.IUi
{
    /// <summary>A rebuild can take about a second; the window stays up at least this long, so it gets drawn and read
    /// (the PR #30 rehearsal's 1 s rebuild showed none: it was closed and reaped before zenity mapped it).</summary>
    static readonly TimeSpan ProgressAtLeast = TimeSpan.FromSeconds(1.5);

    Process progress;
    readonly Stopwatch shown = new();

    static string Find(string name) =>
        (Environment.GetEnvironmentVariable("PATH") ?? "/usr/bin:/bin").Split(':').Where(p => p.Length > 0)
            .Select(p => Path.Combine(p, name)).FirstOrDefault(File.Exists);

    // Only stdin is redirected (zenity's progress mode reads it); output goes where the game's goes, so no pipe fills.
    static Process Start(string file, params string[] args)
    {
        var info = new ProcessStartInfo(file) { UseShellExecute = false, RedirectStandardInput = true };
        foreach (var a in args) info.ArgumentList.Add(a);
        LoaderCore.CleanEnvironment(info.Environment);
        return Process.Start(info);
    }

    static void Reap(Process p, int waitMs)
    {
        if (p == null) return;
        try
        {
            if (!p.WaitForExit(waitMs))
            {
                p.Kill(true);
                p.WaitForExit(2000);
            }
        }
        catch (Exception) { }
        p.Dispose();
    }

    public void Begin(string text)
    {
        try
        {
            var zenity = Find("zenity");
            // --no-markup is a dialog option, not a --progress one (an older zenity may refuse it), so the text holds no markup.
            if (zenity != null)
            {
                shown.Restart();
                progress = Start(zenity, "--progress", "--pulsate", "--no-cancel", "--auto-close", "--width=460",
                                 "--title=Die Kollektion", $"--text={text}");
            }
            else
                Notify("Die Kollektion", text);
        }
        catch (Exception) { }
    }

    public void End()
    {
        if (progress == null) return;
        var left = ProgressAtLeast - shown.Elapsed;
        if (left > TimeSpan.Zero)
            Thread.Sleep(left);
        try { progress.StandardInput.Close(); }
        catch (Exception) { }
        Reap(progress, 1000);    // --auto-close: zenity exits once its input ends
        progress = null;
    }

    /// <summary>Shown for a minute at most; the game exits afterwards either way.</summary>
    public void Error(string title, string text)
    {
        try
        {
            var zenity = Find("zenity");
            if (zenity != null)
            {
                var p = Start(zenity, "--error", "--no-markup", "--width=520", $"--title={title}", $"--text={text}");
                p.StandardInput.Close();
                Reap(p, 60_000);
                return;
            }
            Notify(title, text, "critical");
        }
        catch (Exception) { }
    }

    public void Notify(string title, string text) => Notify(title, text, "normal");

    static void Notify(string title, string text, string urgency)
    {
        try
        {
            var send = Find("notify-send");
            if (send != null)
                Reap(Start(send, "-u", urgency, "-a", "Die Kollektion", title, text), 5000);
        }
        catch (Exception) { }
    }
}
