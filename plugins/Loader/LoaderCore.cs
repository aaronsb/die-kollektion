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

namespace DieKollektion.Loader;

/// <summary>What the loader does at plugin Load, kept free of BepInEx and game types so tools/loader-plan can run it offline.</summary>
/// <remarks>
/// The real plugin (BepInEx/VehicleMods/VehicleMods.dll, outside plugins/, so BepInEx never scans it) is compiled
/// against BepInEx's interop, which BepInEx regenerates from the game before any plugin loads. Its deployed.json
/// records the interop hash it was built for. When that matches BepInEx/interop/assembly-hash.txt the loader
/// starts it; when not (the game updated), it installs a DLL built for the new interop first: the release's
/// prebuilt one when it was built for it, else one compiled from the Werkstatt checkout recorded at deploy, if that
/// checkout's plugin sources are still the deployed ones. The game waits meanwhile (Load runs on Unity's main
/// thread, before the swap chain is set up), with a progress window. Without a fitting DLL the plugin isn't
/// loaded: if the save holds our trucks the game would hang loading it, so the loader says why and the game quits;
/// otherwise it runs stock.
/// </remarks>
public static class LoaderCore
{
    public const string PluginDll = "VehicleMods.dll";
    public const string Record = "deployed.json";
    static readonly string[] TruckIds = { "3000000001", "3000000002", "3000000003", "3000000004" };

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
        public string PluginDir;
        public string SaveFile;
        public Action<string> Log = _ => { };
        public IUi Ui;
        /// <summary>A dotnet to use instead of searching for one (WERKSTATT_DOTNET; tests).</summary>
        public string Dotnet;
        public TimeSpan BuildTimeout = TimeSpan.FromMinutes(5);
    }

    public static Result Prepare(Setup s)
    {
        var record = ReadJson(Path.Combine(s.PluginDir, Record));
        var dll = Path.Combine(s.PluginDir, PluginDll);
        if (record == null || !File.Exists(dll))
            return new Result { Outcome = Outcome.Stock, Message = $"nothing deployed in {s.PluginDir} (run `make deploy`)" };
        var live = InteropHash(s.BepInExDir);
        var builtFor = record["game"]?["interopHash"]?.GetValue<string>();
        if (live != null && builtFor == live)
            return new Result { Outcome = Outcome.Load, Dll = dll, Message = "the plugin fits this game" };

        var build = SteamBuild(s.GameDir) ?? "?";
        s.Log($"The game's interop changed ({Short(builtFor)} → {Short(live)}, Steam build {build}); getting a plugin built for it");
        s.Ui?.Begin($"Die Kollektion: rebuilding the plugin for the game's new version (Steam build {build})…");
        string candidate = null, how = null, why;
        try
        {
            var werkstatt = record["werkstatt"]?.GetValue<string>();
            (candidate, why) = Prebuilt(werkstatt, live);
            if (candidate != null)
                how = "prebuilt";
            else
            {
                s.Log($"No prebuilt plugin fits: {why}");
                (candidate, why) = Compile(s, record, werkstatt);
                if (candidate != null)
                    how = "compiled";
            }
            if (candidate != null)
                Install(s, record, candidate, live, builtFor, build, how);
        }
        catch (Exception e)
        {
            candidate = null;
            why = $"installing the rebuilt plugin failed ({e.Message})";
        }
        finally
        {
            s.Ui?.End();
        }

        if (candidate != null)
        {
            s.Log($"Installed a plugin built for Steam build {build} ({how})");
            return new Result { Outcome = Outcome.Load, Dll = dll, RebuiltFor = build, Message = $"rebuilt for Steam build {build} ({how})" };
        }

        var fix = "In the Werkstatt folder, run `make update` (it needs the .NET SDK, or a release built for this game version).";
        if (SaveHasTrucks(s.SaveFile))
        {
            s.Log($"No plugin fits the game: {why}. The save holds Die Kollektion's trucks, which the game can't load without it; quitting");
            s.Ui?.Error("Die Kollektion needs a rebuild",
                $"The game has updated, and the plugin couldn't be rebuilt for it:\n{why}.\n\n" +
                $"Your save holds Die Kollektion's trucks, and the game can't load it without the plugin, so it will close now. Nothing was changed.\n\n{fix}");
            return new Result { Outcome = Outcome.Quit, Message = why };
        }
        s.Log($"No plugin fits the game: {why}. Starting without Die Kollektion");
        s.Ui?.Notify("Die Kollektion is off this session", $"The game has updated and the plugin couldn't be rebuilt: {why}. {fix}");
        return new Result { Outcome = Outcome.Stock, Message = why };
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
        if (info["builtAgainst"]?["gameAssemblyHash"]?.GetValue<string>() != live)
            return (null, "the release's prebuilt plugin was built for another game version");
        if (Sha256(dll) != info["sha256"]?.GetValue<string>())
            return (null, "the prebuilt plugin doesn't match its recorded checksum");
        return (dll, null);
    }

    static (string, string) Compile(Setup s, JsonNode record, string werkstatt)
    {
        if (string.IsNullOrEmpty(werkstatt) || !Directory.Exists(werkstatt))
            return (null, $"the Werkstatt folder recorded at deploy ({werkstatt ?? "none"}) isn't there");
        var project = Path.Combine(werkstatt, "plugins", "VehicleMods");
        var deployed = record["pluginSources"]?["sha256"]?.GetValue<string>();
        if (deployed == null || !Directory.Exists(project) || SourcesHash(project) != deployed)
            return (null, $"the plugin's sources in {werkstatt} have changed since the deploy, so a rebuild there wouldn't match the installed vehicles");
        var (dotnet, container) = s.Dotnet != null ? (s.Dotnet, false) : FindDotnet();
        if (dotnet == null)
            return (null, "the .NET SDK wasn't found");
        // Removed first, so the file found afterwards is this build's (MSBuild copies it out of obj/ again).
        var output = Path.Combine(project, "bin", "Release", "net6.0", PluginDll);
        if (File.Exists(output))
            File.Delete(output);
        var args = new[] { "build", project, "-c", "Release", "-nologo", "-v", "minimal", "-m:1", "-nodeReuse:false",
                           "-p:UseSharedCompilation=false", "-p:Deploy=false", $"-p:GameDir={s.GameDir}" };
        s.Log($"Compiling with {dotnet}{(container ? " (the host's SDK, from inside Steam's runtime)" : "")}");
        var (code, text) = Run(dotnet, args, BuildEnvironment(container), s.BuildTimeout);
        if (code != 0)
        {
            s.Log("The build failed:\n" + Tail(text, 30));
            return (null, code == -1 ? "the build timed out" : "the build failed (see BepInEx/werkstatt-launch.log)");
        }
        if (!File.Exists(output))
            return (null, $"the build didn't produce {output}");
        return (output, null);
    }

    static void Install(Setup s, JsonNode record, string candidate, string live, string builtFor, string build, string how)
    {
        var dll = Path.Combine(s.PluginDir, PluginDll);
        var temp = dll + ".loader-new";
        File.Copy(candidate, temp, true);
        using (var f = new FileStream(temp, FileMode.Open, FileAccess.Read)) f.Flush(true);
        File.Move(temp, dll, true);
        var hash = Sha256(dll);
        foreach (var entry in record["files"]?.AsArray() ?? new JsonArray())
            if (entry?["path"]?.GetValue<string>() == PluginDll)
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

    // ------------------------------------------------------------------ the SDK, inside or outside Steam's runtime

    /// <summary>Steam starts the game inside its Linux runtime (pressure-vessel), where the host's files are under
    /// /run/host and the SDK needs the host's libraries (OpenSSL, ICU) on the library path.</summary>
    public static bool InSteamRuntime() => Directory.Exists("/run/pressure-vessel") && Directory.Exists("/run/host/usr");

    public static (string, bool) FindDotnet()
    {
        var container = InSteamRuntime();
        var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        var candidates = new List<string> { Environment.GetEnvironmentVariable("WERKSTATT_DOTNET"), Path.Combine(home, ".dotnet", "dotnet") };
        var roots = container ? new[] { "/run/host/usr" } : new[] { "/usr", "/usr/local" };
        foreach (var root in roots)
            foreach (var sub in new[] { "share/dotnet", "lib/dotnet", "lib64/dotnet" })
                candidates.Add(Path.Combine(root, sub, "dotnet"));
        if (!container)
            candidates.AddRange((Environment.GetEnvironmentVariable("PATH") ?? "").Split(':').Where(p => p.Length > 0).Select(p => Path.Combine(p, "dotnet")));
        var found = candidates.FirstOrDefault(c => !string.IsNullOrEmpty(c) && File.Exists(c));
        return (found, container);
    }

    static Dictionary<string, string> BuildEnvironment(bool container)
    {
        var env = new Dictionary<string, string>
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
        return env;
    }

    /// <summary>Runs a child process with the game's environment minus what Steam and BepInEx inject (LD_PRELOAD, the
    /// runtime's library path, BepInEx's own .NET), plus <paramref name="set"/>; null values are removed.</summary>
    public static (int, string) Run(string file, IEnumerable<string> args, Dictionary<string, string> set, TimeSpan timeout)
    {
        var info = new ProcessStartInfo(file) { RedirectStandardOutput = true, RedirectStandardError = true, RedirectStandardInput = true, UseShellExecute = false };
        foreach (var a in args) info.ArgumentList.Add(a);
        CleanEnvironment(info.Environment);
        foreach (var (k, v) in set ?? new Dictionary<string, string>())
            if (v == null) info.Environment.Remove(k); else info.Environment[k] = v;
        var text = new StringBuilder();
        using var p = new Process { StartInfo = info };
        p.OutputDataReceived += (_, e) => { if (e.Data != null) lock (text) text.AppendLine(e.Data); };
        p.ErrorDataReceived += (_, e) => { if (e.Data != null) lock (text) text.AppendLine(e.Data); };
        p.Start();
        p.StandardInput.Close();
        p.BeginOutputReadLine();
        p.BeginErrorReadLine();
        if (!p.WaitForExit((int)timeout.TotalMilliseconds))
        {
            try { p.Kill(true); } catch (Exception) { }
            return (-1, text.ToString());
        }
        p.WaitForExit();
        return (p.ExitCode, text.ToString());
    }

    public static void CleanEnvironment(IDictionary<string, string> env)
    {
        foreach (var key in env.Keys.ToList())
            if (key is "LD_PRELOAD" or "LD_LIBRARY_PATH" or "DOTNET_ROOT" or "DOTNET_STARTUP_HOOKS" || key.StartsWith("DOORSTOP_")
                || key.StartsWith("COREHOST_") || key.StartsWith("DOTNET_gc"))
                env.Remove(key);
    }

    // ------------------------------------------------------------------ facts read from disk

    public static string InteropHash(string bepinex)
    {
        var p = Path.Combine(bepinex, "interop", "assembly-hash.txt");
        return File.Exists(p) ? File.ReadAllText(p).Trim() : null;
    }

    public static string SteamBuild(string game)
    {
        var p = Path.GetFullPath(Path.Combine(game, "..", "..", "appmanifest_2929250.acf"));
        if (!File.Exists(p)) return null;
        var m = Regex.Match(File.ReadAllText(p), "\"buildid\"\\s+\"(\\d+)\"", RegexOptions.IgnoreCase);
        return m.Success ? m.Groups[1].Value : null;
    }

    public static bool SaveHasTrucks(string save)
    {
        if (string.IsNullOrEmpty(save) || !File.Exists(save)) return false;
        var text = File.ReadAllText(save);
        return TruckIds.Any(id => Regex.IsMatch(text, $"(?<!\\d){id}(?!\\d)"));
    }

    /// <summary>The plugin's sources as deployed: SHA-256 over every .cs and .csproj under the project folder
    /// (bin/ and obj/ excluded), each as its relative path, a NUL, its bytes and a NUL, in ordinal path order.
    /// tools/werkstatt.py computes the same at deploy (plugin_sources_hash).</summary>
    public static string SourcesHash(string project)
    {
        var root = Path.GetFullPath(project);
        var files = Directory.EnumerateFiles(root, "*", SearchOption.AllDirectories)
            .Select(f => Path.GetRelativePath(root, f).Replace(Path.DirectorySeparatorChar, '/'))
            .Where(r => (r.EndsWith(".cs") || r.EndsWith(".csproj")) && !r.StartsWith("bin/") && !r.StartsWith("obj/"))
            .OrderBy(r => r, StringComparer.Ordinal);
        using var sha = SHA256.Create();
        var nul = new byte[] { 0 };
        foreach (var rel in files)
        {
            var name = Encoding.UTF8.GetBytes(rel);
            sha.TransformBlock(name, 0, name.Length, null, 0);
            sha.TransformBlock(nul, 0, 1, null, 0);
            var bytes = File.ReadAllBytes(Path.Combine(root, rel));
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

    static JsonNode ReadJson(string path)
    {
        try { return File.Exists(path) ? JsonNode.Parse(File.ReadAllText(path)) : null; }
        catch (Exception) { return null; }
    }

    static void WriteJson(string path, JsonNode node)
    {
        var temp = path + ".loader-new";
        File.WriteAllText(temp, node.ToJsonString(new JsonSerializerOptions { WriteIndented = true }) + "\n");
        File.Move(temp, path, true);
    }

    static string Short(string hash) => string.IsNullOrEmpty(hash) ? "none" : hash.Length > 10 ? hash[..10] : hash;

    static string Tail(string text, int lines) => string.Join("\n", text.Split('\n').TakeLast(lines));
}

/// <summary>A progress window and dialogs from zenity, with notify-send as the fallback. Both exist inside Steam's
/// runtime; they run with the game's environment minus what Steam and BepInEx inject.</summary>
public sealed class DesktopUi : LoaderCore.IUi
{
    Process progress;

    static string Find(string name) =>
        (Environment.GetEnvironmentVariable("PATH") ?? "/usr/bin:/bin").Split(':').Where(p => p.Length > 0)
            .Select(p => Path.Combine(p, name)).FirstOrDefault(File.Exists);

    static Process Start(string file, params string[] args)
    {
        var info = new ProcessStartInfo(file) { UseShellExecute = false, RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true };
        foreach (var a in args) info.ArgumentList.Add(a);
        LoaderCore.CleanEnvironment(info.Environment);
        return Process.Start(info);
    }

    public void Begin(string text)
    {
        try
        {
            var zenity = Find("zenity");
            if (zenity != null)
                progress = Start(zenity, "--progress", "--pulsate", "--no-cancel", "--auto-close", "--width=460",
                                 "--title=Die Kollektion", $"--text={text}");
            else
                Notify("Die Kollektion", text);
        }
        catch (Exception) { }
    }

    public void End()
    {
        try
        {
            if (progress != null && !progress.HasExited)
                progress.Kill();
        }
        catch (Exception) { }
        progress = null;
    }

    public void Error(string title, string text)
    {
        try
        {
            var zenity = Find("zenity");
            if (zenity != null)
            {
                using var p = Start(zenity, "--error", "--width=520", $"--title={title}", $"--text={text}");
                p.StandardInput.Close();
                p.WaitForExit(10 * 60 * 1000);
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
                using (var p = Start(send, "-u", urgency, "-a", "Die Kollektion", title, text))
                    p.WaitForExit(5000);
        }
        catch (Exception) { }
    }
}
