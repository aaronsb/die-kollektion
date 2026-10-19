using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Numerics;
using System.Text.Json;

namespace VehicleMods;

/// <summary>A vehicle's placements file (vehicles/&lt;name&gt;/placements.json): moves, turns and scales prefab
/// nodes (upgrade options, their pieces, whole slot groups) and adds copies of upgrade pieces, each with its own
/// placement. Pure logic over System.Numerics, so tools/placement-check can test it offline against the fixtures
/// the Blender add-on's model is tested against (tests/placements/).</summary>
/// <remarks>
/// Each entry is a delta from the node's pose after the reshape, so it survives game updates and the wheelbase
/// sweep:
/// <list type="bullet">
/// <item><c>offset</c>: metres, in car-root axes (x right, y up, z forward) as turned by the placements of the
/// node's ancestors;</item>
/// <item><c>rotation</c>: Euler degrees in Unity's order (z, then x, then y), in those same axes, about the node's
/// own pivot;</item>
/// <item><c>scale</c>: a factor on the node's local scale.</item>
/// </list>
/// An offset goes through its placed ancestors' turns and scales exactly, as a child's location does under its
/// parent in Blender, which is what the add-on shows. A turn under an ancestor scaled differently on different
/// axes would shear in Blender and can't in Unity; the plugin turns it rigidly, so avoid non-uniform scale on a
/// group whose children you turn. Entries
/// apply parents first. A copy (<c>copies</c>, keyed by the copy's own node path) is made from <c>source</c>
/// before any entry applies: a copy of an upgrade option becomes a child of that option, a copy of one of its
/// pieces becomes the piece's sibling, so the game shows it exactly when it shows the item.
/// </remarks>
sealed class PlacementPlan
{
    public sealed class Entry
    {
        public string Path;
        /// <summary>The node a copy is made from, or null for a node of the prefab.</summary>
        public string Source;
        public Vector3 Offset;
        public Vector3 Rotation;
        public Vector3 Scale = Vector3.One;
    }

    /// <summary>One entry resolved to car-root space: add <see cref="Offset"/> to the node's position, turn it by
    /// <see cref="Turn"/> about its pivot (pre-multiplied in car-root space) and multiply its local scale.</summary>
    public readonly struct Step
    {
        public readonly Entry Entry;
        public readonly Vector3 Offset;
        public readonly Quaternion Turn;
        public Step(Entry entry, Vector3 offset, Quaternion turn) { Entry = entry; Offset = offset; Turn = turn; }
    }

    public readonly List<Entry> Nodes = new();
    public readonly List<Entry> Copies = new();

    public IEnumerable<Entry> All => Copies.Concat(Nodes);

    /// <summary>Reads a placements file. Throws <see cref="FormatException"/> with a reader-friendly message.</summary>
    // Limits a hand edit can't sensibly exceed: an item moved 10 m, turned past a full turn, scaled 100x.
    public const float MaxOffset = 10f, MaxRotation = 360f, MinScale = 0.01f, MaxScale = 100f;
    static readonly string[] FileKeys = { "notes", "nodes", "copies" };
    static readonly string[] EntryKeys = { "notes", "offset", "rotation", "scale" };
    static readonly string[] CopyKeys = { "notes", "source", "offset", "rotation", "scale" };

    public static PlacementPlan Read(string json)
    {
        var plan = new PlacementPlan();
        using var document = JsonDocument.Parse(json, new JsonDocumentOptions { AllowTrailingCommas = false });
        var root = document.RootElement;
        if (root.ValueKind != JsonValueKind.Object) throw new FormatException($"the file is {root.ValueKind}, not an object");
        Keys(root, "the file", FileKeys);
        if (root.TryGetProperty("nodes", out var nodes))
            foreach (var property in Members(nodes, "nodes"))
                plan.Nodes.Add(ReadEntry(property.Name, property.Value, copy: false));
        if (root.TryGetProperty("copies", out var copies))
            foreach (var property in Members(copies, "copies"))
                plan.Copies.Add(ReadEntry(property.Name, property.Value, copy: true));
        foreach (var copy in plan.Copies)
            if (plan.Nodes.Exists(n => n.Path == copy.Path))
                throw new FormatException($"{copy.Path}: in both nodes and copies");
        return plan;
    }

    /// <summary>Refuses a duplicate key or one the format doesn't have (notes are free text anywhere).</summary>
    static void Keys(JsonElement obj, string where, string[] allowed)
    {
        var seen = new HashSet<string>();
        foreach (var property in obj.EnumerateObject())
        {
            if (!seen.Add(property.Name)) throw new FormatException($"{where}: duplicate key \"{property.Name}\"");
            if (allowed != null && Array.IndexOf(allowed, property.Name) < 0) throw new FormatException($"{where}: unknown key \"{property.Name}\"");
        }
    }

    public static PlacementPlan Load(string path) => File.Exists(path) ? Read(File.ReadAllText(path)) : new PlacementPlan();

    static IEnumerable<JsonProperty> Members(JsonElement element, string name)
    {
        if (element.ValueKind != JsonValueKind.Object) throw new FormatException($"\"{name}\" is {element.ValueKind}, not an object");
        Keys(element, $"\"{name}\"", null);
        return element.EnumerateObject();
    }

    static Entry ReadEntry(string path, JsonElement value, bool copy)
    {
        if (value.ValueKind != JsonValueKind.Object) throw new FormatException($"{path}: {value.ValueKind}, not an object");
        if (path.Length == 0 || Array.IndexOf(path.Split('/'), "") >= 0) throw new FormatException($"\"{path}\" is not a node path");
        Keys(value, path, copy ? CopyKeys : EntryKeys);
        var entry = new Entry { Path = path };
        if (copy)
        {
            if (!value.TryGetProperty("source", out var source) || source.ValueKind != JsonValueKind.String)
                throw new FormatException($"{path}: a copy needs a \"source\" node path");
            entry.Source = source.GetString();
            if (entry.Source.Length == 0 || Array.IndexOf(entry.Source.Split('/'), "") >= 0)
                throw new FormatException($"{path}: \"{entry.Source}\" is not a node path");
            if (Parent(path) != Parent(entry.Source) && Parent(path) != entry.Source)
                throw new FormatException($"{path}: a copy sits beside its source or inside it (source {entry.Source})");
            if (path == entry.Source) throw new FormatException($"{path}: a copy needs its own name");
        }
        if (value.TryGetProperty("offset", out var offset)) entry.Offset = Vector(offset, path, "offset", -MaxOffset, MaxOffset);
        if (value.TryGetProperty("rotation", out var rotation)) entry.Rotation = Vector(rotation, path, "rotation", -MaxRotation, MaxRotation);
        if (value.TryGetProperty("scale", out var scale)) entry.Scale = Vector(scale, path, "scale", MinScale, MaxScale);
        return entry;
    }

    static Vector3 Vector(JsonElement element, string path, string name, float min, float max)
    {
        if (element.ValueKind != JsonValueKind.Array || element.GetArrayLength() != 3)
            throw new FormatException($"{path}: \"{name}\" must be three numbers");
        var v = new float[3];
        var i = 0;
        foreach (var item in element.EnumerateArray())
        {
            if (item.ValueKind != JsonValueKind.Number) throw new FormatException($"{path}: \"{name}\" must be three numbers");
            var f = item.GetSingle();
            if (!float.IsFinite(f) || f < min || f > max) throw new FormatException($"{path}: \"{name}\" out of range ({min} to {max})");
            v[i++] = f;
        }
        return new Vector3(v[0], v[1], v[2]);
    }

    public static string Parent(string path)
    {
        var slash = path.LastIndexOf('/');
        return slash < 0 ? "" : path.Substring(0, slash);
    }

    /// <summary>Unity's Quaternion.Euler: z degrees about z, then x about x, then y about y.</summary>
    public static Quaternion Euler(Vector3 degrees)
    {
        const float rad = MathF.PI / 180f;
        return Quaternion.CreateFromAxisAngle(Vector3.UnitY, degrees.Y * rad)
             * Quaternion.CreateFromAxisAngle(Vector3.UnitX, degrees.X * rad)
             * Quaternion.CreateFromAxisAngle(Vector3.UnitZ, degrees.Z * rad);
    }

    /// <summary>The entries in the order they apply (copies are made earlier), each resolved to car-root space
    /// through the placements of its ancestors: the offset through their turns and scales (exactly), the turn
    /// through their turns.</summary>
    public List<Step> Steps()
    {
        // Per placed node, its frame: the turn so far, and the linear map (turns and scales so far) that takes an
        // offset in its children's frame to car-root space. Matrices act on row vectors (System.Numerics).
        var frames = new Dictionary<string, (Quaternion Turn, Matrix4x4 Map)>();
        var steps = new List<Step>();
        foreach (var entry in All.OrderBy(e => e.Path.Count(c => c == '/')).ThenBy(e => e.Path, StringComparer.Ordinal))
        {
            var (ancestorTurn, ancestorMap) = Ancestor(frames, entry.Path);
            var offset = Vector3.Transform(entry.Offset, ancestorMap);
            var own = Euler(entry.Rotation);
            var turn = ancestorTurn * own * Quaternion.Inverse(ancestorTurn);
            frames[entry.Path] = (ancestorTurn * own, Matrix4x4.CreateScale(entry.Scale) * Matrix4x4.CreateFromQuaternion(own) * ancestorMap);
            steps.Add(new Step(entry, offset, turn));
        }
        return steps;
    }

    static (Quaternion, Matrix4x4) Ancestor(Dictionary<string, (Quaternion, Matrix4x4)> frames, string path)
    {
        for (var parent = Parent(path); parent.Length > 0; parent = Parent(parent))
            if (frames.TryGetValue(parent, out var found)) return found;
        return (Quaternion.Identity, Matrix4x4.Identity);
    }
}
