using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;

namespace VehicleMods;

/// <summary>
/// A vehicle derived from a stock donor car, read from vehicles/&lt;name&gt;.json next to the plugin.
/// The same file drives tools/build_vehicle.py, which builds the meshes listed in <see cref="Meshes"/>.
/// All coordinates are car-root space in metres.
/// </summary>
sealed class VehicleDefinition
{
    public string Codename { get; set; }
    /// <summary>True to modify the donor itself (no clone, no new item); codename equals donor.</summary>
    public bool Patch { get; set; }
    public string DisplayName { get; set; }
    public string Description { get; set; }
    public uint ItemId { get; set; }
    public string Donor { get; set; }
    public AxleZ DonorAxleZ { get; set; }
    public float Wheelbase { get; set; }
    public float Track { get; set; }
    public float MaxSteerAngle { get; set; }
    /// <summary>Height-stepped cut: [[y, z], ...]; a point at height y uses the z of the highest y_i &lt;= y.</summary>
    public float[][] BodyCut { get; set; }
    /// <summary>Node path under the donor prefab root -> OBJ file in <see cref="MeshDirectory"/>.
    /// In the JSON an entry is a file name or {"file", ...build options}.</summary>
    public Dictionary<string, string> Meshes { get; set; }
    /// <summary>Node path -> placement applied after the reshape, in Unity car-root space (x right).</summary>
    public Dictionary<string, Placement> Transforms { get; set; } = new();
    /// <summary>Wheel suspension values replacing the donor's, or null to keep them.</summary>
    public SuspensionOverrides Suspension { get; set; }
    /// <summary>The donor's tyre as modelled ("wheel"): radius, width and hub height.</summary>
    public WheelSize Wheel { get; set; }
    /// <summary>A different tyre size fitted to this vehicle ("tyre"), or null for the donor's:
    /// it sets the wheel colliders' radius and scales the wheel meshes from <see cref="Wheel"/>.</summary>
    public WheelSize Tyre { get; set; }
    /// <summary>A spare wheel cloned from one of the donor's wheel visuals ("spare"), or null for none.</summary>
    public SpareWheel Spare { get; set; }
    /// <summary>Headlight colour and brightness for this vehicle ("headlights"), or null for the game's.</summary>
    public HeadlightSettings Headlights { get; set; }
    /// <summary>Moves, turns and copies of prefab nodes from placements.json beside the deployed meshes
    /// (<see cref="PlacementPlan"/>); empty when there is no file, null when it is malformed.</summary>
    public PlacementPlan Placements { get; set; }
    /// <summary>Nodes shown while the loadout carries a tool ("toolNodes", <see cref="VehicleMods.ToolNodes"/>);
    /// empty for a patch, which is the stock car, and when the block is missing or malformed.</summary>
    public ToolNodes ToolNodes { get; set; }

    public string MeshDirectory { get; private set; }
    public string CatalogName => Codename.ToLowerInvariant();
    public string DonorCatalogName => Donor.ToLowerInvariant();
    public float DonorWheelbase => DonorAxleZ.Front - DonorAxleZ.Rear;
    /// <summary>The most forward cut; transforms (lights, axles, mounts) behind it move with the rear.</summary>
    public float TransformCut => BodyCut.Length == 0 ? float.NegativeInfinity : BodyCut.Max(step => step[1]);

    public sealed class Placement
    {
        public UnityEngine.Vector3? Position { get; set; }
        /// <summary>Degrees about the car's up axis, added to the node's current rotation.</summary>
        public float Yaw { get; set; }
    }

    /// <summary>VPP wheel-collider suspension values; unset fields keep the donor's.</summary>
    public sealed class SuspensionOverrides
    {
        public float? Travel { get; set; }
        /// <summary>Where the prefab wheel pose sits in the travel, as a fraction up from full extension.</summary>
        public float? Anchor { get; set; }
        public float? SpringRate { get; set; }
        public float? DamperRate { get; set; }
        public float? PreloadDistance { get; set; }
        /// <summary>Length of the bump-stop zone at the top of the travel.</summary>
        public float? BumpTravelOffset { get; set; }
    }

    /// <summary>A copy of a wheel visual fixed to the car root: <see cref="Source"/> is the node to
    /// clone (meshes and LODGroup only), placed at <see cref="Position"/> with Euler
    /// <see cref="Rotation"/> in Unity car-root space and scaled from the donor's tyre
    /// (<see cref="Wheel"/>) to <see cref="Size"/>, or to the fitted <see cref="Tyre"/> if unset.</summary>
    public sealed class SpareWheel
    {
        public string Source { get; set; }
        public UnityEngine.Vector3 Position { get; set; }
        public UnityEngine.Vector3 Rotation { get; set; }
        public WheelSize Size { get; set; }
    }

    /// <summary>Headlight colour and brightness, applied to this vehicle's own copies of the game's shared
    /// headlight and bounce-light configs (docs/engine.md, "Lights").</summary>
    public sealed class HeadlightSettings
    {
        /// <summary>Target headlight colour temperature in kelvin (1000-40000; outside, clamped), or null to
        /// keep the game's colour. The bounce light moves by the same step from the game's headlight.</summary>
        public float? Kelvin { get; set; }
        /// <summary>Factor on the game's intensity, above 0.</summary>
        public float Intensity { get; set; } = 1f;
    }

    public sealed class WheelSize
    {
        public float Radius { get; set; }
        public float Width { get; set; }
    }

    public sealed class AxleZ
    {
        public float Front { get; set; }
        public float Rear { get; set; }
    }

    // JsonDocument rather than JsonSerializer: the serializer generates converter code at runtime,
    // which intermittently fails under BepInEx's runtime with "Illegal definition for runtime
    // implemented delegate method".
    public static List<VehicleDefinition> LoadAll(string directory)
    {
        var definitions = new List<VehicleDefinition>();
        if (!Directory.Exists(directory)) return definitions;
        foreach (var path in Directory.GetFiles(directory, "*.json"))
        {
            using var document = JsonDocument.Parse(File.ReadAllText(path));
            var root = document.RootElement;
            var definition = new VehicleDefinition
            {
                Codename = root.GetProperty("codename").GetString(),
                DisplayName = OptionalString(root, "displayName"),
                Description = OptionalString(root, "description"),
                Patch = root.TryGetProperty("patch", out var patch) && patch.GetBoolean(),
                ItemId = root.TryGetProperty("itemId", out var itemId) ? itemId.GetUInt32() : 0,
                Donor = root.GetProperty("donor").GetString(),
                DonorAxleZ = new AxleZ
                {
                    Front = root.GetProperty("donorAxleZ").GetProperty("front").GetSingle(),
                    Rear = root.GetProperty("donorAxleZ").GetProperty("rear").GetSingle(),
                },
                Wheelbase = root.GetProperty("wheelbase").GetSingle(),
                Track = root.GetProperty("track").GetSingle(),
                MaxSteerAngle = root.TryGetProperty("maxSteerAngle", out var steer) ? steer.GetSingle() : 0f,
                BodyCut = ReadSteps(root.GetProperty("bodyCut")),
                Meshes = ReadMap(root.GetProperty("meshes")),
                Transforms = root.TryGetProperty("transforms", out var transforms) ? ReadPlacements(transforms) : new(),
                Suspension = root.TryGetProperty("suspension", out var suspension) ? ReadSuspension(suspension) : null,
                Wheel = root.TryGetProperty("wheel", out var wheel) ? ReadWheel(wheel) : null,
                Tyre = root.TryGetProperty("tyre", out var tyre) ? ReadWheel(tyre) : null,
                Spare = root.TryGetProperty("spare", out var spare) ? ReadSpare(spare) : null,
                Headlights = root.TryGetProperty("headlights", out var headlights) ? ReadHeadlights(headlights, root.GetProperty("codename").GetString()) : null,
            };
            definition.MeshDirectory = Path.Combine(directory, definition.CatalogName);
            definition.Placements = VehicleMods.Placements.Read(definition.MeshDirectory, definition.Codename);
            definition.ToolNodes = root.TryGetProperty("toolNodes", out var toolNodes) ? ReadToolNodes(toolNodes, definition) : new();
            definitions.Add(definition);
        }
        return definitions;
    }

    static float[][] ReadSteps(JsonElement array)
    {
        var steps = new List<float[]>();
        foreach (var step in array.EnumerateArray())
        {
            var values = new List<float>();
            foreach (var value in step.EnumerateArray()) values.Add(value.GetSingle());
            steps.Add(values.ToArray());
        }
        return steps.ToArray();
    }

    static Dictionary<string, string> ReadMap(JsonElement obj)
    {
        var map = new Dictionary<string, string>();
        foreach (var property in obj.EnumerateObject())
            map[property.Name] = property.Value.ValueKind == JsonValueKind.String
                ? property.Value.GetString()
                : property.Value.GetProperty("file").GetString();
        return map;
    }

    static Dictionary<string, Placement> ReadPlacements(JsonElement obj)
    {
        var placements = new Dictionary<string, Placement>();
        foreach (var property in obj.EnumerateObject())
        {
            var placement = new Placement();
            if (property.Value.TryGetProperty("position", out var position))
            {
                var p = ReadSteps(JsonDocument.Parse($"[{position.GetRawText()}]").RootElement)[0];
                placement.Position = new UnityEngine.Vector3(p[0], p[1], p[2]);
            }
            if (property.Value.TryGetProperty("yaw", out var yaw)) placement.Yaw = yaw.GetSingle();
            placements[property.Name] = placement;
        }
        return placements;
    }

    static SuspensionOverrides ReadSuspension(JsonElement obj) => new()
    {
        Travel = OptionalFloat(obj, "travel"),
        Anchor = OptionalFloat(obj, "anchor"),
        SpringRate = OptionalFloat(obj, "springRate"),
        DamperRate = OptionalFloat(obj, "damperRate"),
        PreloadDistance = OptionalFloat(obj, "preloadDistance"),
        BumpTravelOffset = OptionalFloat(obj, "bumpTravelOffset"),
    };

    static SpareWheel ReadSpare(JsonElement obj) => new()
    {
        Source = obj.GetProperty("source").GetString(),
        Position = ReadVector(obj.GetProperty("position")),
        Rotation = ReadVector(obj.GetProperty("rotation")),
        Size = obj.TryGetProperty("radius", out _) ? ReadWheel(obj) : null,
    };

    /// <summary>The "headlights" block, or null with a log line when it is malformed or asks for no light:
    /// a bad block costs only that vehicle its headlight change, never the other definitions.</summary>
    static HeadlightSettings ReadHeadlights(JsonElement obj, string codename)
    {
        string problem = null;
        float? kelvin = null;
        var intensity = 1f;
        if (obj.ValueKind != JsonValueKind.Object) problem = $"is {obj.ValueKind}, not an object";
        else
        {
            if (obj.TryGetProperty("kelvin", out var k))
            {
                if (k.ValueKind == JsonValueKind.Number) kelvin = k.GetSingle();
                else problem = $"kelvin is {k.ValueKind}, not a number";
            }
            if (obj.TryGetProperty("intensity", out var i))
            {
                if (i.ValueKind != JsonValueKind.Number) problem = $"intensity is {i.ValueKind}, not a number";
                else if ((intensity = i.GetSingle()) <= 0f) problem = $"intensity {intensity} is not above 0";
            }
        }
        if (problem == null) return new HeadlightSettings { Kelvin = kelvin, Intensity = intensity };
        Plugin.Logger.LogWarning($"Lights: {codename}: the headlights block {problem}; headlights left as the game's");
        return null;
    }

    /// <summary>The "toolNodes" block, or none with a log line when it is malformed or on a patch: a bad block costs
    /// only that vehicle its tool nodes.</summary>
    static ToolNodes ReadToolNodes(JsonElement obj, VehicleDefinition definition)
    {
        if (definition.Patch)
        {
            Plugin.Logger.LogWarning($"Tools: {definition.Codename}: a patch is the stock car, which keeps the game's nodes; toolNodes ignored");
            return new ToolNodes();
        }
        try
        {
            return ToolNodes.Read(obj);
        }
        catch (FormatException e)
        {
            Plugin.Logger.LogWarning($"Tools: {definition.Codename}: the toolNodes block can't be used ({e.Message}); no tool nodes for this vehicle");
            return new ToolNodes();
        }
    }

    static UnityEngine.Vector3 ReadVector(JsonElement array)
    {
        var values = new List<float>();
        foreach (var value in array.EnumerateArray()) values.Add(value.GetSingle());
        return new UnityEngine.Vector3(values[0], values[1], values[2]);
    }

    static WheelSize ReadWheel(JsonElement obj) => new()
    {
        Radius = obj.GetProperty("radius").GetSingle(),
        Width = obj.GetProperty("width").GetSingle(),
    };

    static float? OptionalFloat(JsonElement obj, string name) =>
        obj.TryGetProperty(name, out var value) ? value.GetSingle() : null;

    static string OptionalString(JsonElement root, string name) =>
        root.TryGetProperty(name, out var value) ? value.GetString() : null;
}
