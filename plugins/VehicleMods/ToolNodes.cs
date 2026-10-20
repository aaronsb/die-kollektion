using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;

namespace VehicleMods;

/// <summary>A definition's tool-driven nodes (<c>toolNodes</c> in vehicle.json: node path -> toolset ItemId): prefab
/// nodes the game never shows, which this vehicle shows while its loadout carries that tool. Pure logic over
/// System.Text.Json, so tools/toolnodes-check tests it offline.</summary>
/// <remarks>The loadout is the save's <c>VehicleItem.ToolsetIDs</c> for the vehicle's ItemId: the list the car's
/// inventory is filled from at spawn, and the one the mechanic's Tools screen edits. A loadout changes only at the
/// mechanic, whose Close respawns the car, so the spawned car follows it from the spawn alone.</remarks>
sealed class ToolNodes
{
    public readonly List<(string Path, uint Tool)> Nodes = new();

    public enum Change { None, Show, Hide }

    /// <summary>Reads the <c>toolNodes</c> object. Throws <see cref="FormatException"/> with a reader-friendly
    /// message; a <c>notes</c> key is free text and ignored.</summary>
    public static ToolNodes Read(JsonElement element)
    {
        if (element.ValueKind != JsonValueKind.Object) throw new FormatException($"is {element.ValueKind}, not an object");
        var tools = new ToolNodes();
        var seen = new HashSet<string>();
        foreach (var property in element.EnumerateObject())
        {
            var path = property.Name;
            if (!seen.Add(path)) throw new FormatException($"duplicate key \"{path}\"");
            if (path == "notes") continue;
            if (path.Length == 0 || Array.IndexOf(path.Split('/'), "") >= 0) throw new FormatException($"\"{path}\" is not a node path");
            var value = property.Value;
            if (value.ValueKind != JsonValueKind.Number || !value.TryGetUInt32(out var tool) || tool == 0)
                throw new FormatException($"{path}: the tool must be a toolset ItemId (a whole number above 0), not {value.GetRawText()}");
            tools.Nodes.Add((path, tool));
        }
        return tools;
    }

    /// <summary>What a node needs: shown while the loadout carries the tool, hidden otherwise and when there is no
    /// loadout (null: no VehicleItem for the vehicle); <see cref="Change.None"/> when it already is.</summary>
    public static Change Decide(bool active, uint tool, IReadOnlyCollection<uint> loadout)
    {
        var carries = loadout != null && loadout.Contains(tool);
        return carries == active ? Change.None : carries ? Change.Show : Change.Hide;
    }

    /// <summary>A display dummy refreshed for <paramref name="current"/> after it showed <paramref name="previous"/>
    /// (either null for a car without a definition): the vehicle whose tool nodes must be hidden first, or null.
    /// The game may refresh one dummy for another car, and the stock donor shares our trucks' dummy prefab.</summary>
    public static T Superseded<T>(T previous, T current) where T : class =>
        previous != null && !ReferenceEquals(previous, current) ? previous : null;

    /// <summary>A loadout for the log: its ItemIds, "empty", or "no VehicleItem".</summary>
    public static string Describe(IReadOnlyCollection<uint> loadout) =>
        loadout == null ? "no VehicleItem" : loadout.Count == 0 ? "empty" : string.Join(", ", loadout);
}
