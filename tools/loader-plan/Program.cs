using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
using System.Text.Json.Nodes;
using DieKollektion.Loader;

// tools/loader-plan: `scenarios` runs LoaderCore.Prepare over fake game folders; `sources <dir>` prints the plugin
// sources hash; `references <dll>` fails when the loader references anything but BepInEx's own assemblies.
static class Program
{
    static readonly HashSet<string> Allowed = new() { "BepInEx.Core", "BepInEx.Unity.IL2CPP", "Il2CppInterop.Runtime" };

    static int Main(string[] args)
    {
        switch (args.FirstOrDefault())
        {
            case "sources":
                Console.WriteLine(LoaderCore.SourcesHash(args[1]));
                return 0;
            case "references":
                return References(args[1]);
            case "scenarios":
                return Scenarios();
            case "prepare":
                return PrepareFolder(args[1], args.Contains("--ui"));
            default:
                Console.Error.WriteLine("usage: loader-plan scenarios | sources <project dir> | references <loader dll>");
                return 2;
        }
    }

    // Runs the loader's Prepare on a real (copied) game folder, as the loader would at a start; for rehearsals.
    static int PrepareFolder(string game, bool ui)
    {
        var bepinex = Path.Combine(game, "BepInEx");
        var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        var r = LoaderCore.Prepare(new LoaderCore.Setup
        {
            GameDir = game, BepInExDir = bepinex, PluginDir = Path.Combine(bepinex, "VehicleMods"),
            SaveFile = Environment.GetEnvironmentVariable("SAVE_FILE") ?? Path.Combine(home, "My Games", "over the hill", "Saves", "Player1.json"),
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
            if (!Allowed.Contains(name) && !name.StartsWith("System") && name != "mscorlib" && name != "netstandard")
                bad.Add(name);
        }
        Console.WriteLine(bad.Count == 0 ? "ok: BepInEx and framework assemblies only" : "references outside BepInEx: " + string.Join(", ", bad));
        return bad.Count == 0 ? 0 : 1;
    }

    sealed class Recorder : LoaderCore.IUi
    {
        public readonly List<string> Calls = new();
        public void Begin(string text) => Calls.Add("begin");
        public void End() => Calls.Add("end");
        public void Error(string title, string text) => Calls.Add("error");
        public void Notify(string title, string text) => Calls.Add("notify");
    }

    sealed class Fake
    {
        public string Root, Game, BepInEx, Plugin, Werkstatt, Save, Dotnet;
        public readonly Recorder Ui = new();
        public readonly List<string> Log = new();

        public Fake(string name, bool trucks = true)
        {
            Root = Path.Combine(Path.GetTempPath(), $"loader-plan-{Environment.ProcessId}-{name}");
            if (Directory.Exists(Root)) Directory.Delete(Root, true);
            Game = Path.Combine(Root, "steamapps", "common", "over the hill");
            BepInEx = Path.Combine(Game, "BepInEx");
            Plugin = Path.Combine(BepInEx, "VehicleMods");
            Werkstatt = Path.Combine(Root, "werkstatt");
            Save = Path.Combine(Root, "Player1.json");
            Write(Path.Combine(BepInEx, "interop", "assembly-hash.txt"), "hash-v2");
            Write(Path.Combine(Root, "steamapps", "appmanifest_2929250.acf"), "\"AppState\"\n{\n\t\"buildid\"\t\t\"200\"\n}\n");
            Write(Path.Combine(Plugin, "VehicleMods.dll"), "plugin built for v1");
            Write(Path.Combine(Werkstatt, "plugins", "VehicleMods", "Plugin.cs"), "class Plugin {}\n");
            Write(Path.Combine(Werkstatt, "plugins", "VehicleMods", "VehicleMods.csproj"), "<Project/>\n");
            Write(Save, trucks ? "{\"VehicleItemId\":3000000004}" : "{\"VehicleItemId\":2186553413}");
            WriteRecord("hash-v1", LoaderCore.SourcesHash(Path.Combine(Werkstatt, "plugins", "VehicleMods")));
            // A stand-in for `dotnet build`: writes the output where MSBuild would, or fails on request.
            Dotnet = Path.Combine(Root, "dotnet");
            Write(Dotnet, "#!/bin/sh\n[ -f \"$(dirname \"$0\")/fail\" ] && { echo 'error CS0246: boom'; exit 1; }\n" +
                          "out=\"$2/bin/Release/net6.0\"; mkdir -p \"$out\"; echo 'plugin built for v2' > \"$out/VehicleMods.dll\"\n" +
                          "echo \"  VehicleMods -> $out/VehicleMods.dll\"\n");
            if (!OperatingSystem.IsWindows())
                File.SetUnixFileMode(Dotnet, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
        }

        public void WriteRecord(string interop, string sources)
        {
            var record = new JsonObject
            {
                ["werkstatt"] = Werkstatt,
                ["pluginSources"] = new JsonObject { ["sha256"] = sources },
                ["game"] = new JsonObject { ["interopHash"] = interop, ["steamBuild"] = "100" },
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

        public LoaderCore.Result Run() => LoaderCore.Prepare(new LoaderCore.Setup
        {
            GameDir = Game, BepInExDir = BepInEx, PluginDir = Plugin, SaveFile = Save, Log = Log.Add, Ui = Ui, Dotnet = Dotnet,
        });

        public string Installed => File.ReadAllText(Path.Combine(Plugin, "VehicleMods.dll")).Trim();
        public JsonNode Record => JsonNode.Parse(File.ReadAllText(Path.Combine(Plugin, "deployed.json")));

        static void Write(string path, string text)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            File.WriteAllText(path, text);
        }
    }

    static int failures;

    static void Check(string scenario, bool ok, string detail)
    {
        Console.WriteLine($"{(ok ? "ok  " : "FAIL")} {scenario}{(ok ? "" : ": " + detail)}");
        if (!ok) failures++;
    }

    static int Scenarios()
    {
        var all = new List<Fake>();
        Fake F(string name, bool trucks = true) { var f = new Fake(name, trucks); all.Add(f); return f; }

        var fits = F("fits");
        fits.WriteRecord("hash-v2", "x");
        var r = fits.Run();
        Check("a plugin built for this interop loads at once", r.Outcome == LoaderCore.Outcome.Load && r.RebuiltFor == null && fits.Ui.Calls.Count == 0,
              $"{r.Outcome} {r.RebuiltFor} [{string.Join(",", fits.Ui.Calls)}]");

        var prebuilt = F("prebuilt");
        prebuilt.Prebuilt("hash-v2");
        r = prebuilt.Run();
        var rec = prebuilt.Record;
        Check("after an update the release's prebuilt plugin is installed",
              r.Outcome == LoaderCore.Outcome.Load && r.RebuiltFor == "200" && prebuilt.Installed == "prebuilt plugin"
              && rec["game"]["interopHash"].GetValue<string>() == "hash-v2" && rec["afterUpdate"]["how"].GetValue<string>() == "prebuilt"
              && rec["files"][0]["sha256"].GetValue<string>() == LoaderCore.Sha256(Path.Combine(prebuilt.Plugin, "VehicleMods.dll"))
              && string.Join(",", prebuilt.Ui.Calls) == "begin,end",
              $"{r.Outcome} {prebuilt.Installed} {rec.ToJsonString()} [{string.Join(",", prebuilt.Ui.Calls)}]");

        var compiled = F("compiled");
        compiled.Prebuilt("hash-v1");      // built for the old game: no use
        r = compiled.Run();
        Check("without a fitting prebuilt plugin the checkout is compiled",
              r.Outcome == LoaderCore.Outcome.Load && compiled.Installed == "plugin built for v2" && compiled.Record["afterUpdate"]["how"].GetValue<string>() == "compiled",
              $"{r.Outcome} {r.Message} {compiled.Installed}");

        var changed = F("sources-changed");
        File.AppendAllText(Path.Combine(changed.Werkstatt, "plugins", "VehicleMods", "Plugin.cs"), "// half done\n");
        r = changed.Run();
        Check("changed sources aren't compiled; with trucks in the save the game quits",
              r.Outcome == LoaderCore.Outcome.Quit && changed.Installed == "plugin built for v1" && changed.Ui.Calls.Contains("error"),
              $"{r.Outcome} {r.Message} [{string.Join(",", changed.Ui.Calls)}]");

        var stock = F("no-trucks", trucks: false);
        File.AppendAllText(Path.Combine(stock.Werkstatt, "plugins", "VehicleMods", "Plugin.cs"), "// half done\n");
        r = stock.Run();
        Check("without trucks in the save the game runs stock, with a notification",
              r.Outcome == LoaderCore.Outcome.Stock && stock.Ui.Calls.Contains("notify") && !stock.Ui.Calls.Contains("error"),
              $"{r.Outcome} [{string.Join(",", stock.Ui.Calls)}]");

        var failed = F("build-fails");
        File.WriteAllText(Path.Combine(failed.Root, "fail"), "");
        var before = failed.Record.ToJsonString();
        r = failed.Run();
        Check("a failed build leaves the installed plugin and its record as they were",
              r.Outcome == LoaderCore.Outcome.Quit && failed.Installed == "plugin built for v1" && failed.Record.ToJsonString() == before
              && failed.Log.Any(l => l.Contains("CS0246")),
              $"{r.Outcome} {failed.Installed}");

        var none = F("nothing");
        File.Delete(Path.Combine(none.Plugin, "VehicleMods.dll"));
        r = none.Run();
        Check("nothing deployed: stock, no questions", r.Outcome == LoaderCore.Outcome.Stock && none.Ui.Calls.Count == 0, $"{r.Outcome}");

        var legacy = F("legacy-record");
        var old = legacy.Record.AsObject();
        old.Remove("werkstatt");
        File.WriteAllText(Path.Combine(legacy.Plugin, "deployed.json"), old.ToJsonString());
        r = legacy.Run();
        Check("a record without its Werkstatt folder can't be rebuilt", r.Outcome == LoaderCore.Outcome.Quit, $"{r.Outcome} {r.Message}");

        foreach (var f in all)
            Directory.Delete(f.Root, true);
        Console.WriteLine(failures == 0 ? "loader: all scenarios pass" : $"loader: {failures} scenario(s) failed");
        return failures == 0 ? 0 : 1;
    }
}
