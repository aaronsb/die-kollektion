using System;
using System.IO;
using System.Reflection;
using System.Threading;
using BepInEx;
using BepInEx.Logging;
using BepInEx.Unity.IL2CPP;
using FunCore.Managers;
using HarmonyLib;
using Il2CppInterop.Runtime;
using UnityEngine;

namespace VehicleMods;

/// <summary>Die Kollektion: adds vehicles to Over the Hill, the shipped-but-hidden cars and trucks derived from stock ones.</summary>
/// <remarks>
/// Constraints on this game (Unity 6000.0.75, Il2CppInterop with a substitute Class::Init):
/// class injection crashes the game, so no injected MonoBehaviours or managed delegates;
/// patching in Load crashes the render thread; patching from a background thread races
/// whatever the main thread is running. So a background thread patches one rarely-called
/// main-thread method once boot has loaded Addressables, and everything else happens on the
/// main thread when the game first calls it.
/// </remarks>
[BepInPlugin("local.overthehill.vehiclemods", "Die Kollektion", "0.6.0")]
public class Plugin : BasePlugin
{
    internal static ManualLogSource Logger;
    static readonly Harmony harmony = new("local.overthehill.vehiclemods");

    const string BootMarker = "[AddressablesPreLoader] Addressables finished loading";
    static readonly TimeSpan BootTimeout = TimeSpan.FromSeconds(60);
    // Managed work on this thread while Unity sets up the swap chain (about 1 s after Load)
    // crashed the main thread in roughly a third of launches, so the thread stays idle first.
    static readonly TimeSpan StartupQuiet = TimeSpan.FromSeconds(2);

    static bool loaded;

    // Through the loader's can't-start policy (Loader.PluginCantStartKey): issue #34, after an interop regeneration.
    const string PluginCantStartKey = "DieKollektion.PluginCantStart";
    const string NoSafePagesWhy = "the game's memory layout after an update leaves no safe place for Die Kollektion's hooks this session";
    const string NoSafePagesFix = "Start the game again; that usually fixes it.";

    public override void Load()
    {
        // Once per process: a second Load would race its own hooks. The loader refuses to start next to a stray copy
        // under plugins/, so this is only a backstop.
        if (loaded)
            return;
        loaded = true;
        Logger = Log;
        // As early as our code runs: claim the memory the hooks' jump slots will live in (native calls only).
        // Nothing to claim here almost always means nothing before the hooks either, and this is the last point
        // before the game reads a save, so with trucks in a save the loader closes the game now.
        if (!DobbyNearPages.Reserve())
            CantStart(atLoad: true);
        var unityLog = UnityLogPath();
        new Thread(() => PatchEntryWhenBooted(unityLog)) { IsBackground = true, Name = "VehicleMods.Entry" }.Start();
    }

    /// <summary>The loader's policy for a plugin that can't place its hooks; without the loader, only the log line.</summary>
    static void CantStart(bool atLoad)
    {
        if (AppDomain.CurrentDomain.GetData(PluginCantStartKey) is Action<string, string, bool> cantStart)
            cantStart(NoSafePagesWhy, NoSafePagesFix, atLoad);
    }

    // Load touches no IL2CPP types; Unity's Linux player log path is fixed.
    static string UnityLogPath()
    {
        var config = Environment.GetEnvironmentVariable("XDG_CONFIG_HOME");
        if (string.IsNullOrEmpty(config))
            config = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".config");
        return Path.Combine(config, "unity3d", "Funselektor", "over the hill", "Player.log");
    }

    // An exception escaping this thread aborts the game, so every failure is caught and logged.
    static void PatchEntryWhenBooted(string unityLog)
    {
        try
        {
            Thread.Sleep(StartupQuiet);
            if (!WaitForLogLine(unityLog, BootMarker, BootTimeout))
                Logger.LogWarning($"No '{BootMarker}' in {unityLog} after {BootTimeout.TotalSeconds}s; patching anyway");
            IL2CPP.il2cpp_thread_attach(IL2CPP.il2cpp_domain_get());
            // Without safe pages for the jump slots a hooked method would sooner or later jump through garbage,
            // so the plugin installs no hooks at all and the game runs without the mod.
            bool pagesReady;
            try
            {
                pagesReady = DobbyNearPages.Install();
            }
            catch (Exception e)
            {
                Logger.LogError($"Dobby pages failed: {e}");
                pagesReady = false;
            }
            if (!pagesReady)
            {
                Logger.LogError("No hooks installed: Die Kollektion is inactive this session");
                CantStart(atLoad: false);
                return;
            }
            harmony.CreateClassProcessor(typeof(MainThreadEntry)).Patch();
            Logger.LogInfo("Entry patch applied");
        }
        catch (Exception e)
        {
            Logger.LogError($"Entry patch failed: {e}");
        }
    }

    /// <summary>Applies every [HarmonyPatch] class except the entry patch, each independently.</summary>
    internal static void ApplyPatches()
    {
        int applied = 0, failed = 0;
        foreach (var type in Assembly.GetExecutingAssembly().GetTypes())
        {
            if (type == typeof(MainThreadEntry) || type.GetCustomAttribute<HarmonyPatch>() == null) continue;
            try
            {
                harmony.CreateClassProcessor(type).Patch();
                applied++;
            }
            catch (Exception e)
            {
                failed++;
                Logger.LogError($"Patch {type.FullName} failed: {e}");
            }
        }
        MenuSentinel.HooksFailed = failed;
        Logger.LogInfo($"Patches applied: {applied}, failed: {failed}");
    }

    // Polls without allocating: one open stream, one reused buffer, a byte-wise match. The
    // marker's first byte occurs nowhere else in it, so a mismatch restarts the match cleanly.
    static bool WaitForLogLine(string path, string marker, TimeSpan timeout)
    {
        var deadline = DateTime.UtcNow + timeout;
        var pattern = System.Text.Encoding.ASCII.GetBytes(marker);
        var buffer = new byte[64 * 1024];
        int matched = 0;
        FileStream stream = null;
        try
        {
            while (DateTime.UtcNow < deadline)
            {
                if (stream == null && File.Exists(path))
                    stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
                int read;
                while (stream != null && (read = stream.Read(buffer, 0, buffer.Length)) > 0)
                {
                    for (int i = 0; i < read; i++)
                    {
                        matched = buffer[i] == pattern[matched] ? matched + 1 : buffer[i] == pattern[0] ? 1 : 0;
                        if (matched == pattern.Length) return true;
                    }
                }
                Thread.Sleep(50);
            }
            return false;
        }
        finally
        {
            stream?.Dispose();
        }
    }
}

/// <summary>The first game-state transition after boot runs the mod's setup on the main thread.</summary>
[HarmonyPatch(typeof(GameStateManager), nameof(GameStateManager.Transition))]
static class MainThreadEntry
{
    static bool done;

    static void Prefix()
    {
        if (done)
        {
            try
            {
                DerivedVehicles.LogRestPoses();
            }
            catch (Exception e)
            {
                Plugin.Logger.LogError($"Rest pose log failed: {e}");
            }
            return;
        }
        var catalog = PlayerInventoryManager.InventoryItemsCatalog;
        if (catalog == null) return;
        done = true;
        try
        {
            Plugin.ApplyPatches();
            DobbyNearPages.LogUsage();
            Catalog.Register(catalog, Time.frameCount);
        }
        catch (Exception e)
        {
            MenuSentinel.SetupFailed = true;
            Plugin.Logger.LogError($"Setup failed: {e}");
        }
    }
}
