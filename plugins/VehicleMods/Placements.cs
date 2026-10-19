using System;
using System.Collections.Generic;
using UnityEngine;
using Object = UnityEngine.Object;

namespace VehicleMods;

/// <summary>Applies a vehicle's placements file (<see cref="PlacementPlan"/>) to a spawned car or a display
/// dummy, after the reshape: first the copies, then every entry, parents first.</summary>
/// <remarks>
/// A copy is <c>Object.Instantiate</c> of the game's own node, so no class is injected. A copy of an upgrade
/// option is parented to that option, with its VehicleUpgradeObject removed, so the game neither registers nor
/// toggles it; it shows while the option shows. A copy of a piece inside an option sits beside the piece.
/// </remarks>
static class Placements
{
    public static void Apply(Transform root, VehicleDefinition definition)
    {
        var plan = definition.Placements;
        if (plan == null || (plan.Nodes.Count == 0 && plan.Copies.Count == 0)) return;
        var made = 0;
        foreach (var copy in plan.Copies)
            if (MakeCopy(root, definition.Codename, copy)) made++;
        var applied = 0;
        foreach (var step in plan.Steps())
        {
            var node = root.Find(step.Entry.Path);
            if (node == null)
            {
                Plugin.Logger.LogWarning($"Placements: {definition.Codename}: no {step.Entry.Path} on {root.name}; skipped");
                continue;
            }
            var e = step.Entry;
            if (e.Offset != System.Numerics.Vector3.Zero)
                node.position += root.TransformVector(new Vector3(step.Offset.X, step.Offset.Y, step.Offset.Z));
            if (e.Rotation != System.Numerics.Vector3.Zero)
            {
                var turn = new Quaternion(step.Turn.X, step.Turn.Y, step.Turn.Z, step.Turn.W);
                node.rotation = root.rotation * turn * Quaternion.Inverse(root.rotation) * node.rotation;
            }
            if (e.Scale != System.Numerics.Vector3.One)
                node.localScale = Vector3.Scale(node.localScale, new Vector3(e.Scale.X, e.Scale.Y, e.Scale.Z));
            applied++;
            Plugin.Logger.LogInfo($"Placements: {definition.Codename}: {node.name} {Signed(e.Offset)} m" +
                (e.Rotation != System.Numerics.Vector3.Zero ? $", turned {Signed(e.Rotation)}°" : "") +
                (e.Scale != System.Numerics.Vector3.One ? $", scaled {e.Scale.X:0.###},{e.Scale.Y:0.###},{e.Scale.Z:0.###}" : "") +
                (e.Source != null ? $" (copy of {e.Source})" : ""));
        }
        Plugin.Logger.LogInfo($"Placements: {definition.Codename}: {applied} of {plan.Nodes.Count + plan.Copies.Count} entries on {root.name}, {made} copies made");
    }

    static bool MakeCopy(Transform root, string codename, PlacementPlan.Entry copy)
    {
        if (root.Find(copy.Path) != null) return false;     // already made on this instance
        var source = root.Find(copy.Source);
        if (source == null)
        {
            Plugin.Logger.LogWarning($"Placements: {codename}: no {copy.Source} on {root.name}; copy {copy.Path} skipped");
            return false;
        }
        var isOption = source.GetComponent<VehicleUpgradeObject>() != null;
        if (!isOption && !InsideOption(source))
        {
            Plugin.Logger.LogWarning($"Placements: {codename}: {copy.Source} is neither an upgrade option nor inside one; copy {copy.Path} skipped");
            return false;
        }
        var parent = isOption ? source : source.parent;
        var clone = Object.Instantiate(source.gameObject, parent).transform;
        clone.name = copy.Path.Substring(copy.Path.LastIndexOf('/') + 1);
        if (isOption)
        {
            var upgrade = clone.GetComponent<VehicleUpgradeObject>();
            if (upgrade != null) Object.DestroyImmediate(upgrade);
            clone.localPosition = Vector3.zero;
            clone.localRotation = Quaternion.identity;
            clone.localScale = Vector3.one;
            clone.gameObject.SetActive(true);
        }
        return true;
    }

    static bool InsideOption(Transform node)
    {
        for (var t = node.parent; t != null; t = t.parent)
            if (t.GetComponent<VehicleUpgradeObject>() != null) return true;
        return false;
    }

    static string Signed(System.Numerics.Vector3 v) => $"{v.X:+0.000;-0.000},{v.Y:+0.000;-0.000},{v.Z:+0.000;-0.000}";

    /// <summary>The placements file beside a vehicle's deployed meshes, or null (with a log line) when it is
    /// malformed: a bad file costs only that vehicle its placements.</summary>
    public static PlacementPlan Read(string directory, string codename)
    {
        var path = System.IO.Path.Combine(directory, "placements.json");
        try
        {
            return PlacementPlan.Load(path);
        }
        catch (Exception e) when (e is FormatException || e is System.Text.Json.JsonException || e is InvalidOperationException)
        {
            Plugin.Logger.LogWarning($"Placements: {codename}: {path} can't be used ({e.Message}); no placements for this vehicle");
            return null;
        }
    }
}
