using System;
using System.Collections.Generic;
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
    // ASCII: the game's font may lack the middle dot.
    const string Separator = " | ";
    const int RecheckFrames = 30;

    // PatchesApplied counts patch definitions whose stock car was found and registered for reshaping; the reshape
    // itself happens at each spawn, so the line says "registered" rather than claiming the patch took effect.
    internal static int VehiclesDefined, VehiclesRegistered, VehiclesWithDonorLooks, PatchesDefined, PatchesApplied, HooksFailed;
    internal static bool SetupFailed;

    static string statusLine;
    static int nextCheck;

    static string Version => typeof(Plugin).GetCustomAttribute<BepInPlugin>().Version.ToString();

    /// <summary>The status text from the setup's counts, and whether anything is short.</summary>
    internal static (string Text, bool Incomplete) Status()
    {
        var parts = new List<string> { $"{Marker} {Version}" };
        if (VehiclesDefined + PatchesDefined == 0)
            parts.Add("no vehicles found");
        else if (PatchesDefined == 0)
            parts.Add($"{Count(VehiclesRegistered, VehiclesDefined, "vehicle", "vehicles")} registered");
        else
            parts.Add($"{Count(VehiclesRegistered, VehiclesDefined, "vehicle", "vehicles")}, {Count(PatchesApplied, PatchesDefined, "patch", "patches")} registered");
        if (VehiclesWithDonorLooks > 0)
            parts.Add($"{Count(VehiclesWithDonorLooks, VehiclesWithDonorLooks, "vehicle", "vehicles")} with the donor's name or icon");
        if (HooksFailed > 0) parts.Add($"{Count(HooksFailed, HooksFailed, "game hook", "game hooks")} failed");
        if (SetupFailed) parts.Add("setup failed");
        var incomplete = SetupFailed || HooksFailed > 0 || VehiclesWithDonorLooks > 0 || VehiclesDefined + PatchesDefined == 0
            || VehiclesRegistered < VehiclesDefined || PatchesApplied < PatchesDefined;
        if (incomplete) parts.Add("see BepInEx/LogOutput.log");
        return (string.Join(Separator, parts), incomplete);
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
                        var (status, incomplete) = Status();
                        // Without rich text the tag would show as text.
                        statusLine = incomplete && label.richText ? $"<color={Amber}>{status}</color>" : status;
                        Plugin.Logger.LogInfo($"Main menu: {status} (label enabled {label.isActiveAndEnabled}, active in hierarchy {label.gameObject.activeInHierarchy})");
                    }
                    label.text = text.Length == 0 ? statusLine : text + Separator + statusLine;
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
