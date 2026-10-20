using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
using System.Runtime.InteropServices;
using System.Text.Json.Nodes;
using DieKollektion.Loader;

// tools/loader-plan: `scenarios` runs LoaderCore.Prepare over fake game folders; `sources <dir> [root]` prints the
// plugin sources hash; `references <dll>` fails when the loader references anything but BepInEx's own assemblies;
// `prepare <game>` runs Prepare on a real (copied) game folder, for rehearsals.
static class Program
{
    static readonly HashSet<string> Allowed = new() { "BepInEx.Core", "BepInEx.Unity.IL2CPP" };

    static int Main(string[] args)
    {
        switch (args.FirstOrDefault())
        {
            case "sources":
                Console.WriteLine(LoaderCore.SourcesHash(args[1], args.Length > 2 ? args[2] : null));
                return 0;
            case "references":
                return References(args[1]);
            case "scenarios":
                return Scenarios();
            case "prepare":
                return PrepareFolder(args[1], args.Contains("--ui"));
            default:
                Console.Error.WriteLine("usage: loader-plan scenarios | sources <project> [root] | references <loader dll> | prepare <game> [--ui]");
                return 2;
        }
    }

    static int PrepareFolder(string game, bool ui)
    {
        var bepinex = Path.Combine(game, "BepInEx");
        var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        var r = LoaderCore.Prepare(new LoaderCore.Setup
        {
            GameDir = game, BepInExDir = bepinex, PluginsDir = Path.Combine(bepinex, "plugins"), PluginDir = Path.Combine(bepinex, "VehicleMods"),
            SavesDir = Environment.GetEnvironmentVariable("SAVES_DIR") ?? Path.Combine(home, "My Games", "over the hill", "Saves"),
            Log = m => Console.WriteLine($"log: {m}"), Ui = ui ? new DesktopUi() : null,
        });
        Console.WriteLine($"outcome: {r.Outcome}; rebuilt for: {r.RebuiltFor ?? "-"}; {r.Message}");
        return 0;
    }

    static int References(string dll)
    {
        using var pe = new PEReader(File.OpenRead(dll));
        var md = pe.GetMetadataReader();
        var bad = new List<string>();
        foreach (var h in md.AssemblyReferences)
        {
            var name = md.GetString(md.GetAssemblyReference(h).Name);
            if (!Allowed.Contains(name) && !name.StartsWith("System", StringComparison.Ordinal) && name != "mscorlib" && name != "netstandard")
                bad.Add(name);
        }
        Console.WriteLine(bad.Count == 0 ? "ok: BepInEx and framework assemblies only" : "references outside BepInEx: " + string.Join(", ", bad));
        return bad.Count == 0 ? 0 : 1;
    }

    sealed class Recorder : LoaderCore.IUi
    {
        public readonly List<string> Calls = new();
        /// <summary>The title and text of each error and notification.</summary>
        public readonly List<string> Shown = new();
        public void Begin(string text) => Calls.Add("begin");
        public void End() => Calls.Add("end");
        public void Error(string title, string text) { Calls.Add("error"); Shown.Add($"{title}: {text}"); }
        public void Notify(string title, string text) { Calls.Add("notify"); Shown.Add($"{title}: {text}"); }
        public override string ToString() => string.Join(",", Calls);
    }

    sealed class Fake
    {
        public string Root, Game, BepInEx, Plugins, Plugin, Werkstatt, Saves, Dotnet;
        public readonly Recorder Ui = new();
        public readonly List<string> Log = new();
        public TimeSpan BuildTimeout = TimeSpan.FromMinutes(1), LockWait = TimeSpan.FromSeconds(1);

        public Fake(string name, bool trucks = true)
        {
            Root = Path.Combine(Path.GetTempPath(), $"loader-plan-{Environment.ProcessId}-{name}");
            if (Directory.Exists(Root)) Directory.Delete(Root, true);
            Game = Path.Combine(Root, "steamapps", "common", "over the hill");
            BepInEx = Path.Combine(Game, "BepInEx");
            Plugins = Path.Combine(BepInEx, "plugins");
            Plugin = Path.Combine(BepInEx, "VehicleMods");
            Werkstatt = Path.Combine(Root, "werkstatt");
            Saves = Path.Combine(Root, "Saves");
            Write(Path.Combine(BepInEx, "interop", "assembly-hash.txt"), "hash-v2");
            Write(Path.Combine(Plugins, "DieKollektion.Loader.dll"), "loader");
            Write(Path.Combine(Root, "steamapps", "appmanifest_2929250.acf"), "\"AppState\"\n{\n\t\"buildid\"\t\t\"200\"\n}\n");
            Write(Path.Combine(Plugin, "VehicleMods.dll"), "plugin built for v1");
            Write(Path.Combine(Werkstatt, "plugins", "VehicleMods", "Plugin.cs"), "class Plugin {}\n");
            Write(Path.Combine(Werkstatt, "plugins", "VehicleMods", "VehicleMods.csproj"), "<Project/>\n");
            Write(Path.Combine(Saves, "Player1.json"), trucks ? "{\"VehicleItemId\":3000000004}" : "{\"VehicleItemId\":2186553413}");
            WriteRecord("hash-v1");
            // A stand-in for `dotnet build ... -o <dir>`: writes the DLL there, or fails, hangs, leaves a child
            // holding its output, or leaves a folder in it that can't be removed, on request.
            Dotnet = Path.Combine(Root, "dotnet");
            Write(Dotnet, "#!/bin/sh\nhere=$(dirname \"$0\")\n" +
                          "[ -f \"$here/fail\" ] && { echo 'error CS0246: boom'; exit 1; }\n" +
                          "[ -f \"$here/hang\" ] && sleep 30\n" +
                          "out=; prev=; for a in \"$@\"; do [ \"$prev\" = -o ] && out=$a; prev=$a; done\n" +
                          "mkdir -p \"$out\"; echo 'plugin built for v2' > \"$out/VehicleMods.dll\"; echo \"  VehicleMods -> $out/VehicleMods.dll\"\n" +
                          "[ -f \"$here/stuck\" ] && { mkdir -p \"$out/stuck\"; : > \"$out/stuck/x\"; chmod 555 \"$out/stuck\"; }\n" +
                          "[ -f \"$here/linger\" ] && sleep 20 &\nexit 0\n");
            Process.Start("chmod", new[] { "+x", Dotnet }).WaitForExit();
        }

        public void WriteRecord(string interop, JsonNode interopNode = null)
        {
            var record = new JsonObject
            {
                ["werkstatt"] = Werkstatt,
                ["pluginSources"] = new JsonObject { ["sha256"] = LoaderCore.SourcesHash(Path.Combine(Werkstatt, "plugins", "VehicleMods"), Werkstatt) },
                ["game"] = new JsonObject { ["interopHash"] = interopNode ?? interop, ["steamBuild"] = "100" },
                ["files"] = new JsonArray(new JsonObject { ["path"] = "VehicleMods.dll", ["sha256"] = LoaderCore.Sha256(Path.Combine(Plugin, "VehicleMods.dll")) }),
            };
            Write(Path.Combine(Plugin, "deployed.json"), record.ToJsonString());
        }

        public void Prebuilt(string builtFor)
        {
            var dll = Path.Combine(Werkstatt, "prebuilt", "VehicleMods.dll");
            Write(dll, "prebuilt plugin");
            Write(Path.Combine(Werkstatt, "prebuilt", "VehicleMods.json"),
                  new JsonObject { ["sha256"] = LoaderCore.Sha256(dll), ["builtAgainst"] = new JsonObject { ["gameAssemblyHash"] = builtFor } }.ToJsonString());
        }

        public LoaderCore.Setup Setup => new()
        {
            GameDir = Game, BepInExDir = BepInEx, PluginsDir = Plugins, PluginDir = Plugin, SavesDir = Saves, Log = Log.Add, Ui = Ui,
            Dotnet = Dotnet, BuildTimeout = BuildTimeout, LockWait = LockWait,
        };

        public LoaderCore.Result Run() => LoaderCore.Prepare(Setup);

        public string Installed => File.ReadAllText(Path.Combine(Plugin, "VehicleMods.dll")).Trim();
        public JsonNode Record => JsonNode.Parse(File.ReadAllText(Path.Combine(Plugin, "deployed.json")));
        public void Flag(string name) => File.WriteAllText(Path.Combine(Root, name), "");

        public static void Write(string path, string text)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            File.WriteAllText(path, text);
        }
    }

    static int failures, checks;

    [DllImport("libc")]
    static extern uint geteuid();

    static void Check(string scenario, bool ok, string detail)
    {
        checks++;
        Console.WriteLine($"{(ok ? "ok  " : "FAIL")} {scenario}{(ok ? "" : ": " + detail)}");
        if (!ok) failures++;
    }

    static int Scenarios()
    {
        var all = new List<Fake>();
        Fake F(string name, bool trucks = true) { var f = new Fake(name, trucks); all.Add(f); return f; }
        LoaderCore.Result r;
        Stopwatch clock;

        var fits = F("fits");
        fits.WriteRecord("hash-v2");
        r = fits.Run();
        Check("a plugin built for this interop loads at once", r.Outcome == LoaderCore.Outcome.Load && r.RebuiltFor == null && fits.Ui.Calls.Count == 0,
              $"{r.Outcome} {r.RebuiltFor} [{fits.Ui}]");

        var prebuilt = F("prebuilt");
        prebuilt.Prebuilt("hash-v2");
        r = prebuilt.Run();
        var rec = prebuilt.Record;
        Check("after an update the release's prebuilt plugin is installed",
              r.Outcome == LoaderCore.Outcome.Load && r.RebuiltFor == "200" && prebuilt.Installed == "prebuilt plugin"
              && rec["game"]["interopHash"].GetValue<string>() == "hash-v2" && rec["afterUpdate"]["how"].GetValue<string>() == "prebuilt"
              && rec["files"][0]["sha256"].GetValue<string>() == LoaderCore.Sha256(Path.Combine(prebuilt.Plugin, "VehicleMods.dll"))
              && prebuilt.Ui.ToString() == "begin,end",
              $"{r.Outcome} {prebuilt.Installed} [{prebuilt.Ui}]");

        var compiled = F("compiled");
        compiled.Prebuilt("hash-v1");      // built for the old game: no use
        var checkoutBuild = Path.Combine(compiled.Werkstatt, "plugins", "VehicleMods", "bin", "Release", "net6.0", "VehicleMods.dll");
        Fake.Write(checkoutBuild, "the checkout's own build");
        r = compiled.Run();
        Check("without a fitting prebuilt plugin the checkout is compiled, into the loader's own folder, removed afterwards",
              r.Outcome == LoaderCore.Outcome.Load && compiled.Installed == "plugin built for v2" && compiled.Record["afterUpdate"]["how"].GetValue<string>() == "compiled"
              && File.ReadAllText(checkoutBuild) == "the checkout's own build" && !Directory.Exists(Path.Combine(compiled.BepInEx, LoaderCore.BuildDir)),
              $"{r.Outcome} {r.Message} {compiled.Installed}");

        var changed = F("sources-changed");
        File.AppendAllText(Path.Combine(changed.Werkstatt, "plugins", "VehicleMods", "Plugin.cs"), "// half done\n");
        r = changed.Run();
        Check("changed sources aren't compiled; with trucks in the save the game quits",
              r.Outcome == LoaderCore.Outcome.Quit && changed.Installed == "plugin built for v1" && changed.Ui.Calls.Contains("error"),
              $"{r.Outcome} {r.Message} [{changed.Ui}]");

        var buildInput = F("build-input");
        Fake.Write(Path.Combine(buildInput.Werkstatt, "Directory.Build.props"), "<Project/>");
        r = buildInput.Run();
        Check("a Directory.Build.props added since the deploy counts as a changed source", r.Outcome == LoaderCore.Outcome.Quit, $"{r.Outcome} {r.Message}");

        var stock = F("no-trucks", trucks: false);
        File.AppendAllText(Path.Combine(stock.Werkstatt, "plugins", "VehicleMods", "Plugin.cs"), "// half done\n");
        r = stock.Run();
        Check("without trucks in any save the game runs stock, with a notification",
              r.Outcome == LoaderCore.Outcome.Stock && stock.Ui.Calls.Contains("notify") && !stock.Ui.Calls.Contains("error"),
              $"{r.Outcome} [{stock.Ui}]");

        var profile = F("second-profile", trucks: false);
        Fake.Write(Path.Combine(profile.Saves, "Player2.json"), "{\"VehicleItemId\":3000000001}");
        File.Delete(Path.Combine(profile.Plugin, "VehicleMods.dll"));
        r = profile.Run();
        Check("trucks in another profile count too", r.Outcome == LoaderCore.Outcome.Quit, $"{r.Outcome} {r.Message}");

        var failed = F("build-fails");
        failed.Flag("fail");
        var before = failed.Record.ToJsonString();
        r = failed.Run();
        Check("a failed build leaves the installed plugin and its record as they were",
              r.Outcome == LoaderCore.Outcome.Quit && failed.Installed == "plugin built for v1" && failed.Record.ToJsonString() == before
              && failed.Log.Any(l => l.Contains("CS0246")),
              $"{r.Outcome} {failed.Installed}");

        var hang = F("build-hangs");
        hang.Flag("hang");
        hang.BuildTimeout = TimeSpan.FromSeconds(2);
        clock = Stopwatch.StartNew();
        r = hang.Run();
        Check("a build past its deadline is killed and the start goes on", r.Outcome == LoaderCore.Outcome.Quit && r.Message.Contains("timed out")
              && clock.Elapsed < TimeSpan.FromSeconds(12), $"{r.Outcome} {r.Message} {clock.Elapsed.TotalSeconds:F1}s");

        var linger = F("child-lingers");
        linger.Flag("linger");
        clock = Stopwatch.StartNew();
        r = linger.Run();
        Check("a grandchild left holding the build's output doesn't hold the start", r.Outcome == LoaderCore.Outcome.Load
              && clock.Elapsed < TimeSpan.FromSeconds(10), $"{r.Outcome} {r.Message} {clock.Elapsed.TotalSeconds:F1}s");

        const string stuckScenario = "a build folder that can't be removed is logged and leaves a good rebuild loading";
        if (geteuid() == 0)
            Console.WriteLine($"skip {stuckScenario}: running as root, where chmod 555 doesn't stop the delete");
        else
        {
            var stuck = F("build-folder-stuck");
            stuck.Flag("stuck");
            r = stuck.Run();
            Check(stuckScenario, r.Outcome == LoaderCore.Outcome.Load && stuck.Installed == "plugin built for v2"
                  && stuck.Log.Any(l => l.StartsWith("Couldn't remove", StringComparison.Ordinal)), $"{r.Outcome} {r.Message}");
        }

        var stray = F("stray-copy");
        stray.WriteRecord("hash-v2");
        Fake.Write(Path.Combine(stray.Plugins, "VehicleMods", "VehicleMods.dll"), "an old install");
        r = stray.Run();
        Check("a copy of the plugin under plugins/ stops ours from starting twice", r.Outcome == LoaderCore.Outcome.Quit && r.Message.Contains("plugins/"),
              $"{r.Outcome} {r.Message}");
        Check("an install from before the loader, in plugins/VehicleMods/, is offered `make deploy`, which moves it",
              stray.Ui.Shown.Count == 1 && stray.Ui.Shown[0].Contains("make deploy"), string.Join(" | ", stray.Ui.Shown));

        var strayStock = F("stray-copy-no-trucks", trucks: false);
        strayStock.WriteRecord("hash-v2");
        Fake.Write(Path.Combine(strayStock.Plugins, "VehicleMods.dll"), "an old install");
        r = strayStock.Run();
        Check("a stray copy without trucks names the file and doesn't claim the mod is off", r.Outcome == LoaderCore.Outcome.Stock
              && strayStock.Ui.Shown.Count == 1 && strayStock.Ui.Shown[0].Contains("BepInEx/plugins/VehicleMods.dll")
              && strayStock.Ui.Shown[0].Contains("may still load") && !strayStock.Ui.Shown[0].Contains("is off"),
              $"{r.Outcome} [{string.Join(" | ", strayStock.Ui.Shown)}]");
        Check("a stray copy elsewhere in plugins/ is only told to be deleted (`make deploy` wouldn't move it)",
              strayStock.Ui.Shown.Count == 1 && strayStock.Ui.Shown[0].Contains("Delete BepInEx/plugins/VehicleMods.dll")
              && !strayStock.Ui.Shown[0].Contains("make deploy"), string.Join(" | ", strayStock.Ui.Shown));

        var locked = F("locked");
        locked.WriteRecord("hash-v2");
        using (new FileStream(Path.Combine(locked.BepInEx, "werkstatt.lock"), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None))
            r = locked.Run();
        Check("a held Werkstatt lock (a deploy running) counts as can't start", r.Outcome == LoaderCore.Outcome.Quit && r.Message.Contains("werkstatt.lock"),
              $"{r.Outcome} {r.Message}");

        var nohash = F("no-interop-hash");
        File.Delete(Path.Combine(nohash.BepInEx, "interop", "assembly-hash.txt"));
        r = nohash.Run();
        Check("a missing interop hash can't tell: no rebuild", r.Outcome == LoaderCore.Outcome.Quit && !nohash.Ui.Calls.Contains("begin")
              && !Directory.Exists(Path.Combine(nohash.BepInEx, LoaderCore.BuildDir)), $"{r.Outcome} {r.Message} [{nohash.Ui}]");

        var odd = F("non-string");
        odd.WriteRecord(null, JsonValue.Create(42));
        File.AppendAllText(Path.Combine(odd.Werkstatt, "plugins", "VehicleMods", "Plugin.cs"), "// changed\n");
        r = odd.Run();
        Check("a non-string value in the record is handled, not thrown", r.Outcome == LoaderCore.Outcome.Quit && !r.Message.Contains("loader failed"),
              $"{r.Outcome} {r.Message}");

        var none = F("nothing");
        File.Delete(Path.Combine(none.Plugin, "VehicleMods.dll"));
        r = none.Run();
        Check("nothing deployed but trucks in the save: quit", r.Outcome == LoaderCore.Outcome.Quit, $"{r.Outcome}");
        var noneStock = F("nothing-no-trucks", trucks: false);
        File.Delete(Path.Combine(noneStock.Plugin, "VehicleMods.dll"));
        r = noneStock.Run();
        Check("nothing deployed and no trucks: stock", r.Outcome == LoaderCore.Outcome.Stock, $"{r.Outcome}");

        // The plugin's own can't-start (issue #34): no safe place for its hooks.
        const string why = "no safe place for the hooks", fix = "Start the game again.";
        var hooksAtLoad = F("no-hooks-at-load");
        r = LoaderCore.PluginCantStart(hooksAtLoad.Setup, why, fix, atLoad: true);
        Check("no safe pages at the plugin's Load with trucks in a save: quit there, with the restart advice",
              r.Outcome == LoaderCore.Outcome.Quit && hooksAtLoad.Ui.Shown.Count == 1 && hooksAtLoad.Ui.Calls.SequenceEqual(new[] { "error" })
              && hooksAtLoad.Ui.Shown[0].Contains(fix) && hooksAtLoad.Ui.Shown[0].Contains("close now"),
              $"{r.Outcome} [{string.Join(" | ", hooksAtLoad.Ui.Shown)}]");
        var hooksAtLoadStock = F("no-hooks-at-load-no-trucks", trucks: false);
        r = LoaderCore.PluginCantStart(hooksAtLoadStock.Setup, why, fix, atLoad: true);
        Check("no safe pages at Load without trucks: the plugin goes on and tries again, nothing shown yet",
              r.Outcome == LoaderCore.Outcome.Load && hooksAtLoadStock.Ui.Calls.Count == 0, $"{r.Outcome} [{hooksAtLoadStock.Ui}]");
        var hooksLate = F("no-hooks-late");
        r = LoaderCore.PluginCantStart(hooksLate.Setup, why, fix, atLoad: false);
        Check("no safe pages after Load with trucks: no quit (a save may be being written); the player is told not to load it",
              r.Outcome == LoaderCore.Outcome.Stock && hooksLate.Ui.Calls.SequenceEqual(new[] { "error" })
              && hooksLate.Ui.Shown[0].Contains("without loading your save") && !hooksLate.Ui.Shown[0].Contains("close now"),
              $"{r.Outcome} [{string.Join(" | ", hooksLate.Ui.Shown)}]");
        var hooksLateStock = F("no-hooks-late-no-trucks", trucks: false);
        r = LoaderCore.PluginCantStart(hooksLateStock.Setup, why, fix, atLoad: false);
        Check("no safe pages after Load without trucks: stock, with the notification", r.Outcome == LoaderCore.Outcome.Stock
              && hooksLateStock.Ui.Calls.SequenceEqual(new[] { "notify" }) && hooksLateStock.Ui.Shown[0].Contains(fix),
              $"{r.Outcome} [{string.Join(" | ", hooksLateStock.Ui.Shown)}]");
        var rotated = F("no-hooks-late-save-rotates", trucks: false);
        var reads = 0;
        var rotatedSetup = rotated.Setup;
        rotatedSetup.ReadSave = path => ++reads == 1 ? File.ReadAllText(path) : throw new IOException("the save was rotated");
        r = LoaderCore.PluginCantStart(rotatedSetup, why, fix, atLoad: false);
        Check("after Load the saves are read once, so a save that turns unreadable on a second read can't make a quit",
              r.Outcome == LoaderCore.Outcome.Stock && reads == 1 && rotated.Ui.Calls.SequenceEqual(new[] { "notify" }),
              $"{r.Outcome}, {reads} read(s) [{rotated.Ui}]");
        var hooksUnreadable = F("no-hooks-unreadable-save", trucks: false);
        Process.Start("chmod", new[] { "000", Path.Combine(hooksUnreadable.Saves, "Player1.json") }).WaitForExit();
        r = LoaderCore.PluginCantStart(hooksUnreadable.Setup, why, fix, atLoad: true);
        if (geteuid() == 0)
            Console.WriteLine("skip an unreadable save counts as holding trucks at Load: running as root, where chmod 000 doesn't stop a read");
        else
            Check("an unreadable save counts as holding trucks at Load", r.Outcome == LoaderCore.Outcome.Quit, $"{r.Outcome}");

        var legacy = F("legacy-record");
        var old = legacy.Record.AsObject();
        old.Remove("werkstatt");
        File.WriteAllText(Path.Combine(legacy.Plugin, "deployed.json"), old.ToJsonString());
        r = legacy.Run();
        Check("a record without its Werkstatt folder can't be rebuilt", r.Outcome == LoaderCore.Outcome.Quit, $"{r.Outcome} {r.Message}");

        foreach (var f in all)
        {
            Process.Start("chmod", new[] { "-R", "u+w", f.Root }).WaitForExit();
            Directory.Delete(f.Root, true);
        }
        Console.WriteLine(failures == 0 ? $"loader: all {checks} scenarios pass" : $"loader: {failures} scenario(s) failed");
        return failures == 0 ? 0 : 1;
    }
}
