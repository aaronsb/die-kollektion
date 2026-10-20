using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using BepInEx;
using BepInEx.Logging;
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

    [DllImport("libc", EntryPoint = "_exit")]
    static extern void Exit(int status);

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
        var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        var myGames = Environment.GetEnvironmentVariable("MY_GAMES") is { Length: > 0 } custom ? custom : Path.Combine(home, "My Games", "over the hill");
        var setup = new LoaderCore.Setup
        {
            GameDir = Paths.GameRootPath,
            BepInExDir = bepinex,
            PluginsDir = Paths.PluginPath,
            PluginDir = Path.Combine(bepinex, "VehicleMods"),
            SavesDir = Path.Combine(myGames, "Saves"),
            Log = Note,
            Ui = new DesktopUi(),
        };

        var result = LoaderCore.Prepare(setup);
        if (result.Outcome == LoaderCore.Outcome.Load)
        {
            try
            {
                if (result.RebuiltFor != null)
                    AppDomain.CurrentDomain.SetData(RebuiltForKey, result.RebuiltFor);
                var type = Assembly.LoadFrom(result.Dll).GetType("VehicleMods.Plugin", true);
                var plugin = (BasePlugin)Activator.CreateInstance(type);
                Note($"Starting {type.GetCustomAttribute<BepInPlugin>()?.Name ?? type.FullName} ({result.Message})");
                plugin.Load();
                return;
            }
            catch (Exception e)
            {
                Log.LogError(e.ToString());
                result = LoaderCore.CantStart(setup, $"starting the plugin failed ({e.GetType().Name}: {e.Message})");
            }
        }
        if (result.Outcome == LoaderCore.Outcome.Quit)
        {
            // Out at once, before the save is read: no managed shutdown or destructors while Unity's threads run.
            Note($"Closing the game: {result.Message}");
            foreach (var listener in Logger.Listeners.OfType<DiskLogListener>().ToList())
                listener.Dispose();
            Exit(0);
        }
    }
}
