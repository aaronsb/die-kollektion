using System;
using System.Reflection;
using BepInEx;
using HarmonyLib;
using UnityEngine;

namespace VehicleMods;

/// <summary>Appends a status line to the main menu's build version label: the mod is loaded, and whether everything registered.</summary>
/// <remarks>
/// It edits the game's own label (ContextUIMainMenu.BuildVersionLabel) and creates nothing, so no class injection. The
/// game may set that label's text after the menu opens, so the check runs from StateMainMenu.Update rather than Open:
/// every frame until the line is in, then every <see cref="RecheckFrames"/> frames to put it back if the game rewrote
/// the text. With no line on the menu the game is stock: BepInEx or the plugin didn't load, or no hooks were installed.
/// </remarks>
static class MenuSentinel
{
    const string Marker = "Die Kollektion";
    const string Amber = "#FFB000";
    const int RecheckFrames = 30;

    internal static int VehiclesDefined, VehiclesRegistered, PatchesDefined, PatchesApplied, HooksFailed;
    internal static bool SetupFailed;

    static string statusLine;
    static int nextCheck;

    static string Version => typeof(Plugin).GetCustomAttribute<BepInPlugin>().Version.ToString();

    /// <summary>The status line, built once from the setup's counts (TMP rich text).</summary>
    internal static string Line()
    {
        var line = $"{Marker} {Version} · {Count(VehiclesRegistered, VehiclesDefined, "vehicle", "vehicles")}";
        if (PatchesDefined > 0) line += $" · {Count(PatchesApplied, PatchesDefined, "patch", "patches")}";
        if (HooksFailed > 0) line += $" · {Count(HooksFailed, HooksFailed, "game hook", "game hooks")} failed";
        if (SetupFailed) line += " · setup failed";
        var incomplete = SetupFailed || HooksFailed > 0 || VehiclesRegistered < VehiclesDefined || PatchesApplied < PatchesDefined;
        return incomplete ? $"<color={Amber}>{line} · see BepInEx/LogOutput.log</color>" : line;
    }

    static string Count(int done, int defined, string one, string many) =>
        (done == defined ? $"{defined}" : $"{done} of {defined}") + " " + (defined == 1 ? one : many);

    [HarmonyPatch(typeof(StateMainMenu), nameof(StateMainMenu.Update))]
    static class OnMainMenuUpdate
    {
        static bool failed;

        static void Postfix(StateMainMenu __instance)
        {
            if (failed || Time.frameCount < nextCheck) return;
            try
            {
                // Unity's == also catches a destroyed menu.
                var context = __instance.context;
                if (context == null) return;
                var label = context.BuildVersionLabel;
                if (label == null) return;
                var text = label.text ?? "";
                if (!text.Contains(Marker))
                {
                    if (statusLine == null)
                    {
                        statusLine = Line();
                        Plugin.Logger.LogInfo($"Main menu: {statusLine}");
                    }
                    label.text = text.Length == 0 ? statusLine : $"{text} · {statusLine}";
                }
                nextCheck = Time.frameCount + RecheckFrames;
            }
            catch (Exception e)
            {
                failed = true;
                Plugin.Logger.LogError($"Main menu status line failed; leaving the menu as it is: {e}");
            }
        }
    }
}
