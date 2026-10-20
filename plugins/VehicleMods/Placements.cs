using System;
using System.Collections.Generic;
using UnityEngine;
using Object = UnityEngine.Object;

namespace VehicleMods;

/// <summary>Applies a vehicle's placements file (<see cref="PlacementPlan"/>) to a spawned car or a display
/// dummy, after the reshape: first the copies, then every entry, parents first, then the copies switch on.</summary>
/// <remarks>
/// <list type="bullet">
/// <item>A copy is <c>Object.Instantiate</c> of the game's own node, so no class is injected. Every copy is cloned
/// from its untouched source into an inactive holder before any is attached, so a copy never contains another, and
/// none wakes up (no Awake, no joint set-up) until it is placed.</item>
/// <item>Its path decides its parent: a path inside its source makes it a child of the source (an option copy,
/// shown while the option is), otherwise it sits beside the source (a piece copy inside the same option). Every
/// VehicleUpgradeObject in a copy is removed, so the game neither registers nor toggles it, and options nested in a
/// copy stay hidden.</item>
/// <item>A copy whose source carries a Rigidbody or a Joint (the game's swinging and dangling items) is refused,
/// and an entry on such a node is skipped while the node is active, since its joints were set up where it was;
/// while inactive (an option not fitted yet) it is moved, and the joints set up at the new pose when it shows.</item>
/// <item>A copy's renderers are added to the car's PropertyBlockSetter (dirt, mud, snow, damage, livery, fade), as
/// the game's own parts are; that the setter drives those is inferred from its interface, not seen in game.</item>
/// </list>
/// </remarks>
static class Placements
{
    public static void Apply(Transform root, VehicleDefinition definition)
    {
        var plan = definition.Placements;
        if (plan == null || (plan.Nodes.Count == 0 && plan.Copies.Count == 0)) return;
        var codename = definition.Codename;
        var copies = MakeCopies(root, codename, plan);
        var applied = 0;
        foreach (var step in plan.Steps())
        {
            var node = root.Find(step.Entry.Path);
            if (node == null)
            {
                Plugin.Logger.LogWarning($"Placements: {codename}: no {step.Entry.Path} on {root.name}; skipped");
                continue;
            }
            if (node.gameObject.activeInHierarchy && Physics(node) is { } jointed)
            {
                Plugin.Logger.LogWarning($"Placements: {codename}: {node.name} is showing and {jointed} carries physics joints set up where it is; not moved");
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
            Plugin.Logger.LogInfo($"Placements: {codename}: {node.name} {Signed(e.Offset)} m" +
                (e.Rotation != System.Numerics.Vector3.Zero ? $", turned {Signed(e.Rotation)}°" : "") +
                (e.Scale != System.Numerics.Vector3.One ? $", scaled {e.Scale.X:0.###},{e.Scale.Y:0.###},{e.Scale.Z:0.###}" : "") +
                (e.Source != null ? $" (copy of {e.Source})" : ""));
        }
        foreach (var (clone, active) in copies)
            clone.SetActive(active);
        Plugin.Logger.LogInfo($"Placements: {codename}: {applied} of {plan.Nodes.Count + plan.Copies.Count} entries on {root.name}, {copies.Count} copies made");
    }

    /// <summary>Clones every copy from its untouched source, then attaches them all, inactive; returns each with the
    /// active state it takes once placed.</summary>
    static List<(GameObject Clone, bool Active)> MakeCopies(Transform root, string codename, PlacementPlan plan)
    {
        var made = new List<(GameObject, bool)>();
        if (plan.Copies.Count == 0) return made;
        var holder = new GameObject("KollektionCopies");
        holder.SetActive(false);
        holder.transform.SetParent(root, false);
        var pending = new List<(GameObject Clone, PlacementPlan.Entry Copy, Transform Source, bool Inside, bool Active)>();
        foreach (var copy in plan.Copies)
        {
            if (root.Find(copy.Path) != null) continue;     // made on this instance already
            var source = root.Find(copy.Source);
            if (source == null)
            {
                Plugin.Logger.LogWarning($"Placements: {codename}: no {copy.Source} on {root.name}; copy {copy.Path} skipped");
                continue;
            }
            var isOption = source.GetComponent<VehicleUpgradeObject>() != null;
            if (!isOption && !InsideOption(source))
            {
                Plugin.Logger.LogWarning($"Placements: {codename}: {copy.Source} is neither an upgrade option nor inside one; copy {copy.Path} skipped");
                continue;
            }
            if (Physics(source) is { } jointed)
            {
                Plugin.Logger.LogWarning($"Placements: {codename}: {copy.Source} carries a Rigidbody or Joint ({jointed}); copy {copy.Path} refused");
                continue;
            }
            var inside = PlacementPlan.Parent(copy.Path) == copy.Source;
            var clone = Object.Instantiate(source.gameObject, holder.transform);
            clone.name = copy.Path.Substring(copy.Path.LastIndexOf('/') + 1);
            foreach (var upgrade in clone.GetComponentsInChildren<VehicleUpgradeObject>(true))
                Object.DestroyImmediate(upgrade);
            pending.Add((clone, copy, source, inside, inside || source.gameObject.activeSelf));
        }
        var setter = PropertyBlocks(root);
        foreach (var (clone, copy, source, inside, active) in pending)
        {
            clone.SetActive(false);
            clone.transform.SetParent(inside ? source : source.parent, false);
            if (inside)
            {
                clone.transform.localPosition = Vector3.zero;
                clone.transform.localRotation = Quaternion.identity;
                clone.transform.localScale = Vector3.one;
            }
            Register(setter, clone, codename);
            made.Add((clone, active));
        }
        Object.Destroy(holder);
        return made;
    }

    /// <summary>The car's PropertyBlockSetter (the spawned car's or the display dummy's), or null.</summary>
    public static PropertyBlockSetter PropertyBlocks(Transform root)
    {
        var networked = root.GetComponent<VehicleCustomizationController>();
        if (networked != null && networked.propertyBlockSetter != null) return networked.propertyBlockSetter;
        var local = root.GetComponent<LocalVehicleCustomizationController>();
        return local != null ? local.propertyBlockSetter : null;
    }

    /// <summary>Adds an object's renderers to the car's PropertyBlockSetter, as the game's own parts are.</summary>
    public static void Register(PropertyBlockSetter setter, GameObject obj, string codename)
    {
        if (setter == null) return;
        try
        {
            foreach (var renderer in obj.GetComponentsInChildren<Renderer>(true))
                setter.AddRenderer(renderer);
        }
        catch (Exception e)
        {
            Plugin.Logger.LogWarning($"Placements: {codename}: {obj.name}'s renderers not added to the car's property blocks ({e.Message})");
        }
    }

    /// <summary>The name of a Rigidbody or Joint in the node's subtree, or null.</summary>
    static string Physics(Transform node)
    {
        var body = node.GetComponentsInChildren<Rigidbody>(true);
        if (body.Length > 0) return body[0].name;
        var joint = node.GetComponentsInChildren<Joint>(true);
        return joint.Length > 0 ? joint[0].name : null;
    }

    static bool InsideOption(Transform node)
    {
        for (var t = node.parent; t != null; t = t.parent)
            if (t.GetComponent<VehicleUpgradeObject>() != null) return true;
        return false;
    }

    static string Signed(System.Numerics.Vector3 v) => $"{v.X:+0.000;-0.000},{v.Y:+0.000;-0.000},{v.Z:+0.000;-0.000}";

    /// <summary>The placements file beside a vehicle's deployed meshes, or null (with a log line) when it can't be
    /// read: a bad or unreadable file costs only that vehicle its placements.</summary>
    public static PlacementPlan Read(string directory, string codename)
    {
        var path = System.IO.Path.Combine(directory, "placements.json");
        try
        {
            return PlacementPlan.Load(path);
        }
        catch (Exception e)
        {
            Plugin.Logger.LogWarning($"Placements: {codename}: {path} can't be used ({e.Message}); no placements for this vehicle");
            return null;
        }
    }
}
