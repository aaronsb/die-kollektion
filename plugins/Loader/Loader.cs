using System;
using System.IO;
using System.Linq;
using System.Reflection;
using BepInEx;
using BepInEx.Unity.IL2CPP;

namespace DieKollektion.Loader;

/// <summary>The only Die Kollektion DLL in BepInEx/plugins/: it references BepInEx's own assemblies and no
/// interop, so a game update can't break it, and it starts the real plugin from BepInEx/VehicleMods/ once that
/// plugin fits the game (LoaderCore).</summary>
/// <remarks>Load runs on Unity's main thread inside BepInEx's chainloader, before the swap chain is set up, and
/// touches no IL2CPP type. The real plugin is started the way BepInEx's own chainloader starts one: created, then
/// its Load called, with its own Log and Config from its BepInPlugin attribute.</remarks>
[BepInPlugin("local.overthehill.dk-loader", "Die Kollektion Loader", "1.0.0")]
public class Loader : BasePlugin
{
    /// <summary>AppDomain data the real plugin's main-menu line reads: the Steam build it was rebuilt for this launch.</summary>
    public const string RebuiltForKey = "DieKollektion.RebuiltFor";

    public override void Load()
    {
        var bepinex = Paths.BepInExRootPath;
        var launchLog = Path.Combine(bepinex, "werkstatt-launch.log");
        void Note(string message)
        {
            Log.LogInfo(message);
            try { File.AppendAllText(launchLog, $"{DateTimeOffset.Now:yyyy-MM-dd HH:mm:ss} Loader: {message}\n"); }
            catch (Exception) { }
        }

        LoaderCore.Result result;
        try
        {
            var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
            result = LoaderCore.Prepare(new LoaderCore.Setup
            {
                GameDir = Paths.GameRootPath,
                BepInExDir = bepinex,
                PluginDir = Path.Combine(bepinex, "VehicleMods"),
                SaveFile = Path.Combine(home, "My Games", "over the hill", "Saves", "Player1.json"),
                Log = Note,
                Ui = new DesktopUi(),
            });
        }
        catch (Exception e)
        {
            Log.LogError($"Die Kollektion's loader failed, so the plugin isn't loaded: {e}");
            return;
        }

        switch (result.Outcome)
        {
            case LoaderCore.Outcome.Quit:
                Note($"Closing the game: {result.Message}");
                Environment.Exit(0);
                return;
            case LoaderCore.Outcome.Stock:
                Note($"Not loading Die Kollektion: {result.Message}");
                return;
        }

        try
        {
            if (result.RebuiltFor != null)
                AppDomain.CurrentDomain.SetData(RebuiltForKey, result.RebuiltFor);
            var assembly = Assembly.LoadFrom(result.Dll);
            var type = assembly.GetTypes().First(t => typeof(BasePlugin).IsAssignableFrom(t) && !t.IsAbstract
                                                     && t.GetCustomAttribute<BepInPlugin>() != null);
            var plugin = (BasePlugin)Activator.CreateInstance(type);
            Note($"Starting {type.GetCustomAttribute<BepInPlugin>().Name} ({result.Message})");
            plugin.Load();
        }
        catch (Exception e)
        {
            Log.LogError($"Starting Die Kollektion failed: {e}");
        }
    }
}
