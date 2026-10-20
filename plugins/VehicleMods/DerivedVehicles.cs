using System;
using System.Collections.Generic;
using System.IO;
using HarmonyLib;
using UnityEngine;
using VehiclePhysics;
using Object = UnityEngine.Object;

namespace VehicleMods;

/// <summary>
/// Vehicles built on a stock donor car from definitions in vehicles/*.json. Each shares its
/// donor's prefab (Photon Fusion only spawns prefabs registered at build time) and is reshaped
/// on spawn: rear moved back to the target wheelbase, track and steering set, body and collision
/// meshes replaced with the ones tools/build_vehicle.py produced. A patch definition reshapes
/// the stock donor itself: no clone, no catalog entry, same name.
/// </summary>
static class DerivedVehicles
{
    sealed class Entry
    {
        public VehicleDefinition Definition;
        public CarInfo CarInfo;
    }

    static readonly List<Entry> entries = new();
    static readonly Dictionary<string, Mesh> meshCache = new();
    // This mod's copies of the game's light configs, by "<codename>/<group>"; the shared originals stay untouched.
    static readonly Dictionary<string, CarLightConfig> lightConfigs = new();
    static readonly HashSet<int> reshapedDummies = new();
    // The vehicle each display dummy last showed, by instance ID; a dummy last refreshed for a car without a
    // definition has none.
    static readonly Dictionary<int, Entry> dummies = new();
    // Tools: warnings already logged, by "<root instance ID>/<node path>" (no path for a missing loadout), so a
    // refresh doesn't repeat them.
    static readonly HashSet<string> toolWarnings = new();
    static readonly string[] Corners = { "FL", "FR", "RL", "RR" };
    // Spawned vehicles (not dummies) for LogRestPoses: codename, root, spawn time.
    static readonly List<(string Codename, Transform Root, float SpawnTime)> settling = new();

    // The spawned prefab carries the donor's CarInfo, so a derived spawn is recognised by the
    // prefab address redirect that precedes it in the same frame. Each Spawned hook consumes its own.
    static Entry reshapePending, carInfoPending;

    public static void Register(InventoryItemsCatalog catalog)
    {
        var pluginDirectory = Path.GetDirectoryName(typeof(Plugin).Assembly.Location);
        var directory = Path.Combine(pluginDirectory, "vehicles");
        foreach (var definition in VehicleDefinition.LoadAll(directory))
        {
            if (definition.Patch) MenuSentinel.PatchesDefined++;
            else MenuSentinel.VehiclesDefined++;
            var donor = Catalog.Find(catalog, definition.DonorCatalogName);
            if (donor == null)
            {
                Plugin.Logger.LogError($"{definition.Codename}: donor {definition.Donor} not in catalog; not registered");
                continue;
            }
            if (definition.Patch)
            {
                entries.Add(new Entry { Definition = definition, CarInfo = donor });
                MenuSentinel.PatchesApplied++;
                Plugin.Logger.LogInfo($"{definition.Codename}: patching stock {definition.Donor}");
                continue;
            }
            var car = Object.Instantiate(donor);
            car.name = definition.Codename;
            car.ItemId = definition.ItemId;
            car.hideFlags = HideFlags.DontUnloadUnusedAsset;
            var lengthening = definition.Wheelbase - definition.DonorWheelbase;
            var bounds = donor.carColliderBounds;
            var center = donor.carColliderBoundsCenter;
            car.carColliderBounds = new Vector3(bounds.x, bounds.y, bounds.z + lengthening);
            car.carColliderBoundsCenter = new Vector3(center.x, center.y, center.z - lengthening / 2);
            // A copy, so the donor keeps its own; the suspension lift upgrade reads its base travel here.
            if (definition.Suspension != null || definition.Tyre != null) car.suspensionSetup = WithOverrides(donor.suspensionSetup, definition);
            var keptDonors = false;
            try
            {
                LocalizedText.Apply(car, definition.DisplayName, definition.Description);
            }
            catch (Exception e)
            {
                keptDonors = true;
                Plugin.Logger.LogError($"{definition.Codename}: localized text failed, keeping {definition.Donor}'s: {e}");
            }
            try
            {
                ApplyIcon(car, definition.Codename, Path.Combine(pluginDirectory, "icons", $"{definition.Codename}.png"));
            }
            catch (Exception e)
            {
                keptDonors = true;
                Plugin.Logger.LogError($"{definition.Codename}: icon failed, keeping {definition.Donor}'s: {e}");
            }
            if (keptDonors) MenuSentinel.VehiclesWithDonorLooks++;
            if (Catalog.Add(catalog, car, definition.CatalogName)) MenuSentinel.VehiclesRegistered++;
            entries.Add(new Entry { Definition = definition, CarInfo = car });
        }
    }

    /// <summary>
    /// Replaces the clone's Icon (InventoryItemScriptableObject.Icon, which the vehicle-select
    /// screens show) with icons/&lt;Codename&gt;.png from tools/make_icons.py. The stock icons are
    /// 256x256 sprites at 50 px/unit with a centred pivot; the new sprite copies the donor's
    /// pixels-per-unit. Without the file the clone keeps the donor's icon.
    /// </summary>
    static void ApplyIcon(CarInfo car, string codename, string path)
    {
        if (!File.Exists(path))
        {
            Plugin.Logger.LogInfo($"{codename}: no {path}; keeping the donor's icon");
            return;
        }
        var texture = new Texture2D(2, 2, TextureFormat.RGBA32, false)
        {
            name = $"{codename}_Icon",
            wrapMode = TextureWrapMode.Clamp,
            filterMode = FilterMode.Bilinear,
            hideFlags = HideFlags.DontUnloadUnusedAsset,
        };
        if (!ImageConversion.LoadImage(texture, File.ReadAllBytes(path), true))
        {
            Plugin.Logger.LogError($"{codename}: {path} is not a readable image; keeping the donor's icon");
            return;
        }
        var stock = car.Icon;
        var pixelsPerUnit = stock != null ? stock.pixelsPerUnit : 50f;
        var sprite = Sprite.Create(texture, new Rect(0, 0, texture.width, texture.height), new Vector2(0.5f, 0.5f),
            pixelsPerUnit, 0, SpriteMeshType.FullRect);
        sprite.name = texture.name;
        sprite.hideFlags = HideFlags.DontUnloadUnusedAsset;
        car.Icon = sprite;
        Plugin.Logger.LogInfo($"{codename}: icon {texture.width}x{texture.height} at {pixelsPerUnit} px/unit from {path}" +
            (stock != null ? $" (replaces {stock.name})" : ""));
    }

    static Entry Find(string codename) =>
        entries.Find(e => string.Equals(e.Definition.Codename, codename, StringComparison.OrdinalIgnoreCase));

    [HarmonyPatch(typeof(GameConstants.ADDRESSABLES_PATHS), nameof(GameConstants.ADDRESSABLES_PATHS.GetCarPrefabAddress))]
    static class PrefabAddress
    {
        static void Postfix(string carName, ref string __result)
        {
            var entry = RedirectToDonor("prefab", carName, ref __result);
            if (entry != null) reshapePending = carInfoPending = entry;
        }
    }

    [HarmonyPatch(typeof(GameConstants.ADDRESSABLES_PATHS), nameof(GameConstants.ADDRESSABLES_PATHS.GetCarDummyPrefabAddress))]
    static class DummyPrefabAddress
    {
        static void Postfix(string carName, ref string __result) => RedirectToDonor("dummy prefab", carName, ref __result);
    }

    [HarmonyPatch(typeof(GameConstants.ADDRESSABLES_PATHS), nameof(GameConstants.ADDRESSABLES_PATHS.GetBrokenCarPrefabAddress))]
    static class BrokenPrefabAddress
    {
        static void Postfix(string carName, ref string __result) => RedirectToDonor("broken prefab", carName, ref __result);
    }

    static Entry RedirectToDonor(string kind, string carName, ref string address)
    {
        var entry = Find(carName);
        if (entry == null) return null;
        // A patch's codename is its donor, so its address is unchanged; the spawn is still flagged.
        var redirected = address.Replace(carName, entry.Definition.Donor, StringComparison.OrdinalIgnoreCase);
        if (redirected != address) Plugin.Logger.LogInfo($"{entry.Definition.Codename}: {kind} address {address} -> {redirected}");
        address = redirected;
        return entry;
    }

    // VPP initialises its wheels in Spawned, so the vehicle is reshaped before that runs.
    [HarmonyPatch(typeof(VehicleBase), nameof(VehicleBase.Spawned))]
    static class OnVehicleSpawned
    {
        static void Prefix(VehicleBase __instance)
        {
            var entry = reshapePending;
            if (entry == null || !__instance.gameObject.name.StartsWith($"Car_{entry.Definition.Donor}")) return;
            reshapePending = null;
            try
            {
                Reshape(__instance.transform, entry.Definition);
            }
            catch (Exception e)
            {
                Plugin.Logger.LogError($"{entry.Definition.Codename}: reshape failed: {e}");
            }
        }
    }

    [HarmonyPatch(typeof(VehicleCustomizationController), nameof(VehicleCustomizationController.Spawned))]
    static class OnCustomizationSpawned
    {
        static void Postfix(VehicleCustomizationController __instance)
        {
            var entry = carInfoPending;
            var info = __instance.CurrentCarInfo;
            if (entry == null || info == null || info.name != entry.Definition.Donor) return;
            carInfoPending = null;
            __instance.currentCarInfo = entry.CarInfo;
            var odometer = __instance.GetComponent<Odometer>();
            if (odometer != null) odometer.carInfo = entry.CarInfo;
            Plugin.Logger.LogInfo($"{entry.Definition.Codename}: {__instance.gameObject.name} now carries CarInfo {entry.CarInfo.name} ({entry.CarInfo.ItemId})");
            SyncToolNodes(__instance.transform, entry, "on spawn", dummy: false);
        }
    }

    // Menu and merchant display dummies (Car_<Donor>_Dummy) share the address redirect, but several
    // can be requested before any spawns. RefreshMountedUpgrades names the car being displayed; the
    // dummy is reshaped once, and its tool nodes follow that car's loadout on every refresh.
    [HarmonyPatch(typeof(LocalVehicleCustomizationController), nameof(LocalVehicleCustomizationController.RefreshMountedUpgrades))]
    static class OnDummyRefresh
    {
        static void Postfix(LocalVehicleCustomizationController __instance, Car car)
        {
            var itemId = car?.CarInfo?.ItemId;
            var entry = entries.Find(e => e.CarInfo.ItemId == itemId);
            var id = __instance.GetInstanceID();
            dummies.TryGetValue(id, out var previous);
            // The stock donor shares our trucks' dummy prefab, so a dummy may show another car than it did.
            var superseded = ToolNodes.Superseded(previous, entry);
            if (superseded != null) SyncToolNodes(__instance.transform, superseded, "on dummy refresh for another car", dummy: true, hide: true);
            if (entry == null)
            {
                dummies.Remove(id);
                return;
            }
            dummies[id] = entry;
            if (reshapedDummies.Add(id))
            {
                try
                {
                    Reshape(__instance.transform, entry.Definition);
                }
                catch (Exception e)
                {
                    Plugin.Logger.LogError($"{entry.Definition.Codename}: dummy reshape failed: {e}");
                }
            }
            SyncToolNodes(__instance.transform, entry, "on dummy refresh", dummy: true);
        }
    }

    // Adding or removing a tool in the mechanic's Tools screen ends here; the displayed dummy follows at once,
    // when it shows the vehicle whose loadout the screen edits.
    [HarmonyPatch(typeof(StateMerchantMenu), nameof(StateMerchantMenu.RefreshToolsPanels))]
    static class OnToolsPanelsRefresh
    {
        static void Postfix(StateMerchantMenu __instance)
        {
            try
            {
                var dummy = __instance.dummyChosenCarGameObject;
                var edited = __instance.currentVehicleItem;
                var controller = dummy == null ? null : dummy.GetComponentInChildren<LocalVehicleCustomizationController>(true);
                if (controller == null || edited == null || !dummies.TryGetValue(controller.GetInstanceID(), out var entry)
                    || edited.ItemId != entry.CarInfo.ItemId) return;
                SyncToolNodes(controller.transform, entry, "in the Tools screen", dummy: true, edited);
            }
            catch (Exception e)
            {
                Plugin.Logger.LogError($"Tools: the Tools screen's dummy: {e}");
            }
        }
    }

    /// <summary>The layer the game gave fitted options on a display dummy when this was written; used only when the
    /// dummy has no fitted option to copy it from.</summary>
    const int DummyPartLayer = 16;

    /// <summary>Shows each of the definition's tool nodes while the vehicle's loadout carries its tool and hides it
    /// otherwise (<see cref="ToolNodes"/>), logging each change; with <paramref name="hide"/>, hides them all. The
    /// loadout is <paramref name="known"/>'s when the caller has the exact VehicleItem (<see cref="VehicleItemFor"/>).
    /// On a dummy a shown node takes the layer of the dummy's fitted options. Patches and stock cars have no tool
    /// nodes.</summary>
    static void SyncToolNodes(Transform root, Entry entry, string trigger, bool dummy, VehicleItem known = null, bool hide = false)
    {
        var definition = entry.Definition;
        if (definition.ToolNodes == null || definition.ToolNodes.Nodes.Count == 0) return;
        var codename = definition.Codename;
        string rootName = null;
        try
        {
            rootName = root.name;
            List<uint> loadout = new();
            if (!hide)
            {
                var vehicle = VehicleItemFor(entry.CarInfo.ItemId, known);
                loadout = vehicle == null ? null : Loadout(vehicle);
                if (vehicle == null)
                    WarnOnce(root, "", $"Tools: {codename}: no VehicleItem {entry.CarInfo.ItemId} in the inventory; tool nodes hidden");
            }
            foreach (var (path, tool) in definition.ToolNodes.Nodes)
            {
                var node = root.Find(path);
                if (node == null)
                {
                    WarnOnce(root, path, $"Tools: {codename}: no {path} on {rootName}");
                    continue;
                }
                var part = node.GetComponent<VehicleUpgradeObject>()?.vehiclePartReference;
                if (part != null)
                {
                    WarnOnce(root, path, $"Tools: {codename}: {node.name} now carries a part reference ({part.name}); leaving it to the game");
                    continue;
                }
                var active = node.gameObject.activeSelf;
                var change = ToolNodes.Decide(active, tool, loadout);
                // A spawn always says where the node stands; a dummy, refreshed often, only when it changes.
                if (change == ToolNodes.Change.None && dummy) continue;
                var layer = "";
                if (change == ToolNodes.Change.Show && dummy)
                {
                    var (value, source) = FittedOptionLayer(root);
                    foreach (var t in node.GetComponentsInChildren<Transform>(true))
                        t.gameObject.layer = value;
                    layer = $", layer {value} {source}";
                }
                if (change != ToolNodes.Change.None) node.gameObject.SetActive(change == ToolNodes.Change.Show);
                var state = change switch
                {
                    ToolNodes.Change.Show => "shown",
                    ToolNodes.Change.Hide => "hidden",
                    _ => active ? "stays shown" : "stays hidden",
                };
                Plugin.Logger.LogInfo($"Tools: {codename}: {node.name} {state} on {rootName} {trigger} (tool {tool}, loadout {ToolNodes.Describe(loadout)}{layer})");
            }
        }
        catch (Exception e)
        {
            Plugin.Logger.LogError($"Tools: {codename}: failed on {rootName ?? "a car"} {trigger}: {e}");
        }
    }

    /// <summary>The VehicleItem whose loadout a vehicle shows: <paramref name="known"/> when it is that vehicle's (the
    /// one the mechanic's Tools screen edits), else the current vehicle when it is (the one the spawned car's inventory
    /// is filled from, and the main menu's), else the inventory's item with that ItemId; null when there is none.</summary>
    static VehicleItem VehicleItemFor(uint itemId, VehicleItem known)
    {
        if (known != null && known.ItemId == itemId) return known;
        var current = InventoryUtility.GetCurrentVehicle()?.TryCast<VehicleItem>();
        if (current != null && current.ItemId == itemId) return current;
        var items = PlayerInventoryManager.Instance?.Inventory?.Items;
        for (var i = 0; items != null && i < items.Count; i++)
        {
            var item = items[i];
            if (item == null || item.ItemId != itemId) continue;
            var vehicle = item.TryCast<VehicleItem>();
            if (vehicle != null) return vehicle;
        }
        return null;
    }

    /// <summary>A VehicleItem's toolset loadout (its ToolsetIDs), copied out of the game's list.</summary>
    static List<uint> Loadout(VehicleItem vehicle)
    {
        var ids = vehicle.ToolsetIDs;
        var loadout = new List<uint>();
        for (var k = 0; ids != null && k < ids.Count; k++) loadout.Add(ids[k]);
        return loadout;
    }

    /// <summary>The layer of a fitted option on this dummy (a node the game matched to a part), or
    /// <see cref="DummyPartLayer"/> when it has none or they can't be read; with where it came from, for the log.</summary>
    static (int Layer, string Source) FittedOptionLayer(Transform root)
    {
        try
        {
            var parts = root.GetComponent<LocalVehicleCustomizationController>()?.totalPartsDictionary;
            if (parts != null)
                foreach (var pair in parts)
                {
                    var nodes = pair.Value;
                    for (var i = 0; nodes != null && i < nodes.Count; i++)
                        if (nodes[i] != null) return (nodes[i].layer, $"as the fitted option {nodes[i].name}");
                }
            return (DummyPartLayer, "(no fitted option to copy it from)");
        }
        catch (Exception e)
        {
            return (DummyPartLayer, $"(the fitted options can't be read: {e.Message})");
        }
    }

    static void WarnOnce(Transform root, string key, string message)
    {
        if (toolWarnings.Add($"{root.GetInstanceID()}/{key}")) Plugin.Logger.LogWarning(message);
    }

    /// <summary>Reshapes a spawned car or a display dummy; parts a dummy lacks are skipped.</summary>
    static void Reshape(Transform root, VehicleDefinition definition)
    {
        var frontZ = RootZ(root, root.Find("Axles/WheelMeshes/FL"));
        var rearZ = RootZ(root, root.Find("Axles/WheelMeshes/RL"));
        var donorWheelbase = frontZ - rearZ;
        if (Math.Abs(donorWheelbase - definition.DonorWheelbase) > 0.02f)
            Plugin.Logger.LogWarning($"{definition.Codename}: donor wheelbase is {donorWheelbase:0.000} m, definition says {definition.DonorWheelbase:0.000} m; meshes may not line up");
        var shift = -(definition.Wheelbase - donorWheelbase);

        // Meshes are in the donor's root space, so they are mapped through the donor layout before
        // any node (the rear axle, for one) moves.
        foreach (var (path, file) in definition.Meshes)
            ReplaceMesh(root, definition, path, file);
        root.Find($"Parts/{definition.Donor}")?.GetComponent<LODGroup>()?.RecalculateBounds();

        var com = root.Find("CoM");
        var comTarget = com == null ? 0f : rearZ + shift + (RootZ(root, com) - rearZ) * (definition.Wheelbase / donorWheelbase);
        var moved = Sweep(root, root, definition.TransformCut, shift);
        if (com != null) Move(root, com, 0f, comTarget - RootZ(root, com));

        var halfTrack = definition.Track / 2;
        var widen = halfTrack - Math.Abs(root.InverseTransformPoint(root.Find("Axles/WheelMeshes/FR").position).x);
        foreach (var corner in Corners)
        {
            var dx = corner[1] == 'L' ? -widen : widen;
            foreach (var path in new[] { $"Axles/WheelColliders/Wheel{corner}", $"Axles/WheelMeshes/{corner}", $"Effects/TerrainParticles/{corner}Wheel", $"Audio/{corner}Wheel" })
                Move(root, root.Find(path), dx, 0f);
        }

        ScaleTyres(root, definition);
        AddSpare(root, definition);

        foreach (var (path, placement) in definition.Transforms)
        {
            var node = root.Find(path);
            if (node == null) continue; // display dummies lack effects and colliders
            if (placement.Position.HasValue) node.position = root.TransformPoint(placement.Position.Value);
            if (placement.Yaw != 0f) node.rotation = Quaternion.AngleAxis(placement.Yaw, root.up) * node.rotation;
        }
        try
        {
            Placements.Apply(root, definition);
        }
        catch (Exception e)
        {
            Plugin.Logger.LogError($"Placements: {definition.Codename}: failed: {e}");
        }

        var vehicle = root.GetComponent<VPVehicleController>();
        if (vehicle != null && definition.MaxSteerAngle > 0) vehicle.steering.maxSteerAngle = definition.MaxSteerAngle;
        ApplySuspension(root, definition);
        try
        {
            ApplyHeadlights(root, definition);
        }
        catch (Exception e)
        {
            Plugin.Logger.LogError($"Lights: {definition.Codename}: failed: {e}");
        }

        Plugin.Logger.LogInfo($"{definition.Codename}: reshaped {root.name}: wheelbase {donorWheelbase:0.00} -> {definition.Wheelbase:0.00} m ({moved} nodes moved), track {definition.Track:0.00} m" +
            (vehicle != null ? $", max steer {vehicle.steering.maxSteerAngle:0.0}°" : ""));
    }

    /// <summary>Scales each corner's wheel-mesh node from the donor's tyre to the fitted one: radius
    /// on the node's y and z, width on its x. Tyre upgrades mount their meshes under these nodes,
    /// so they keep the scale.</summary>
    static void ScaleTyres(Transform root, VehicleDefinition definition)
    {
        if (definition.Tyre == null || definition.Wheel == null) return;
        var r = definition.Tyre.Radius / definition.Wheel.Radius;
        var scale = new Vector3(definition.Tyre.Width / definition.Wheel.Width, r, r);
        foreach (var corner in Corners)
        {
            var node = root.Find($"Axles/WheelMeshes/{corner}");
            if (node != null) node.localScale = Vector3.Scale(node.localScale, scale);
        }
    }

    /// <summary>Clones the definition's spare wheel visual (meshes and LODGroup, no wheel scripts)
    /// onto the car root, so it keeps the tyre material and neither steers nor spins. Runs after
    /// the sweep, so the clone is never moved with the rear.</summary>
    static void AddSpare(Transform root, VehicleDefinition definition)
    {
        var spare = definition.Spare;
        if (spare == null) return;
        var source = root.Find(spare.Source);
        if (source == null)
        {
            Plugin.Logger.LogInfo($"{definition.Codename}: no {spare.Source} on {root.name}; no spare");
            return;
        }
        var size = spare.Size ?? definition.Tyre ?? definition.Wheel;
        var clone = Object.Instantiate(source.gameObject, root).transform;
        clone.name = "KollektionSpare";
        clone.localPosition = spare.Position;
        clone.localRotation = Quaternion.Euler(spare.Rotation);
        clone.localScale = definition.Wheel == null || size == null
            ? Vector3.one
            : new Vector3(size.Width / definition.Wheel.Width, size.Radius / definition.Wheel.Radius, size.Radius / definition.Wheel.Radius);
        Placements.Register(Placements.PropertyBlocks(root), clone.gameObject, definition.Codename);
        var renderers = clone.GetComponentsInChildren<Renderer>(true).Length;
        var behaviours = clone.GetComponentsInChildren<MonoBehaviour>(true).Length;
        Plugin.Logger.LogInfo($"{definition.Codename}: spare cloned from {spare.Source} onto {root.name}: {renderers} renderers, " +
            $"{behaviours} scripts, at {spare.Position} rotated {spare.Rotation} scaled {clone.localScale}");
    }

    static VehicleControllerSetup.SuspensionSetup WithOverrides(VehicleControllerSetup.SuspensionSetup donor, VehicleDefinition definition)
    {
        var overrides = definition.Suspension ?? new VehicleDefinition.SuspensionOverrides();
        return new()
        {
            radius = definition.Tyre?.Radius ?? donor.radius,
            inertia = donor.inertia,
            center = donor.center,
            suspensionTravel = overrides.Travel ?? donor.suspensionTravel,
            suspensionAnchor = overrides.Anchor ?? donor.suspensionAnchor,
            springRate = overrides.SpringRate ?? donor.springRate,
            damperRate = overrides.DamperRate ?? donor.damperRate,
            preloadDistance = overrides.PreloadDistance ?? donor.preloadDistance,
            unsprungMass = donor.unsprungMass,
            bumpStopRate = donor.bumpStopRate,
            bumpTravelOffset = overrides.BumpTravelOffset ?? donor.bumpTravelOffset,
            numberOfExtraRays = donor.numberOfExtraRays,
            physicsGroundPenetration = donor.physicsGroundPenetration,
        };
    }

    /// <summary>The game's headlight colour, (0.996, 0.833, 0.659), as a colour temperature: the reference a
    /// definition's kelvin is measured from (docs/engine.md, "Lights").</summary>
    const float GameHeadlightKelvin = 4200f;

    /// <summary>Gives this vehicle's headlights, and the fake bounce light that stands for their glow on the
    /// ground, copies of the game's shared light configs with the definition's colour and brightness, so
    /// stock cars keep theirs. The colour moves each config's own colour by the step from the game's
    /// headlight temperature to the definition's, channel by channel, so the bounce light stays as much
    /// whiter than the beam as the game made it. The lights' current colour is set as well, in case the
    /// game copied it from the config already.</summary>
    static void ApplyHeadlights(Transform root, VehicleDefinition definition)
    {
        var settings = definition.Headlights;
        if (settings == null) return;
        var controller = root.Find("Lights")?.GetComponent<LightsController>();
        if (controller == null) return; // display dummies may carry no lights
        var game = controller.headlights?.Config;
        if (game == null)
        {
            Plugin.Logger.LogWarning($"Lights: {definition.Codename}: {root.name} has no headlight config; headlights left as the game's");
            return;
        }
        var gameIntensity = game.Intensity;
        var kelvin = settings.Kelvin.HasValue ? Mathf.Clamp(settings.Kelvin.Value, 1000f, 40000f) : (float?)null;
        var tint = Color.white;
        if (kelvin.HasValue)
        {
            var target = KelvinColor(kelvin.Value);
            var reference = KelvinColor(GameHeadlightKelvin);
            tint = new Color(target.r / reference.r, target.g / reference.g, target.b / reference.b, 1f);
        }
        var headlights = Retune(controller.headlights, $"{definition.Codename}/headlights", tint, settings.Intensity);
        var bounce = Retune(controller.fakeBounceLights, $"{definition.Codename}/fakeBounceLights", tint, settings.Intensity);
        var applied = controller.headlights.Config;
        var colour = applied.Color;
        Plugin.Logger.LogInfo($"Lights: {definition.Codename}: {headlights} headlights and {bounce} bounce light(s) on {root.name} -> " +
            (kelvin.HasValue ? $"{kelvin.Value:0} K" + (kelvin.Value != settings.Kelvin.Value ? $" (clamped from {settings.Kelvin.Value:0} K)" : "") : "game colour") +
            $", colour ({colour.r:0.000}, {colour.g:0.000}, {colour.b:0.000}), intensity {applied.Intensity:0.0} (game's {gameIntensity:0.0}, x{settings.Intensity:0.00})");
    }

    /// <summary>Points one light group at this vehicle's copy of its config, making the copy on first use
    /// (colour times <paramref name="tint"/>, intensity times <paramref name="intensity"/>), and sets its
    /// lights' colour. Returns how many lights it set.</summary>
    static int Retune(LightsController.TurnableLights group, string key, Color tint, float intensity)
    {
        var original = group?.Config;
        if (original == null) return 0;
        if (!lightConfigs.TryGetValue(key, out var config) || config == null)
        {
            config = Object.Instantiate(original);
            config.name = key;
            config.hideFlags = HideFlags.DontUnloadUnusedAsset;
            var c = original.Color;
            var shifted = new Color(c.r * tint.r, c.g * tint.g, c.b * tint.b, c.a);
            var max = Mathf.Max(shifted.r, Mathf.Max(shifted.g, shifted.b));
            if (max > 1f) shifted = new Color(shifted.r / max, shifted.g / max, shifted.b / max, c.a);
            config.Color = shifted;
            config.Intensity = original.Intensity * intensity;
            lightConfigs[key] = config;
        }
        group.Config = config;
        var lights = group.Lights;
        var count = 0;
        for (var i = 0; lights != null && i < lights.Count; i++)
        {
            var light = lights[i];
            if (light == null) continue;
            light.color = config.Color;
            count++;
        }
        return count;
    }

    /// <summary>The colour of a black body at <paramref name="kelvin"/>, brightest channel 1 (Tanner
    /// Helland's fit to the CIE data, 1000-40000 K). 3200 K, a halogen bulb, gives about (1, 0.72, 0.48).</summary>
    static Color KelvinColor(float kelvin)
    {
        var t = Mathf.Clamp(kelvin, 1000f, 40000f) / 100f;
        var r = t <= 66f ? 255f : 329.698727446f * Mathf.Pow(t - 60f, -0.1332047592f);
        var g = t <= 66f ? 99.4708025861f * Mathf.Log(t) - 161.1195681661f : 288.1221695283f * Mathf.Pow(t - 60f, -0.0755148492f);
        var b = t >= 66f ? 255f : t <= 19f ? 0f : 138.5177312231f * Mathf.Log(t - 10f) - 305.0447927307f;
        var c = new Color(Mathf.Clamp(r, 1f, 255f) / 255f, Mathf.Clamp(g, 1f, 255f) / 255f, Mathf.Clamp(b, 1f, 255f) / 255f, 1f);
        var max = Mathf.Max(c.r, Mathf.Max(c.g, c.b));
        return new Color(c.r / max, c.g / max, c.b / max, 1f);
    }

    /// <summary>Sets the wheel colliders' suspension before VPP reads it in Spawned, and logs it. The
    /// prefab's own wheel values are what VPP uses; CarInfo.suspensionSetup is not applied at spawn.</summary>
    static void ApplySuspension(Transform root, VehicleDefinition definition)
    {
        var overrides = definition.Suspension;
        VPFunselektor3DRaycastWheelCollider wheel = null;
        foreach (var corner in Corners)
        {
            wheel = root.Find($"Axles/WheelColliders/Wheel{corner}")?.GetComponent<VPFunselektor3DRaycastWheelCollider>();
            if (wheel == null) return; // display dummies have no physics
            if (definition.Tyre != null) wheel.radius = definition.Tyre.Radius;
            if (overrides == null) continue;
            if (overrides.Travel.HasValue) wheel.suspensionTravel = overrides.Travel.Value;
            if (overrides.Anchor.HasValue) wheel.suspensionAnchor = overrides.Anchor.Value;
            if (overrides.SpringRate.HasValue) wheel.springRate = overrides.SpringRate.Value;
            if (overrides.DamperRate.HasValue) wheel.damperRate = overrides.DamperRate.Value;
            if (overrides.PreloadDistance.HasValue) wheel.preloadDistance = overrides.PreloadDistance.Value;
            if (overrides.BumpTravelOffset.HasValue) wheel.bumpTravelOffset = overrides.BumpTravelOffset.Value;
        }
        settling.Add((definition.Codename, root, Time.time));
        Plugin.Logger.LogInfo($"{definition.Codename}: suspension {(overrides == null ? "(donor's)" : "(overridden)")} travel {wheel.suspensionTravel:0.000} " +
            $"anchor {wheel.suspensionAnchor:0.000} spring {wheel.springRate:0} damper {wheel.damperRate:0} preload {wheel.preloadDistance:0.000} " +
            $"bump zone {wheel.bumpTravelOffset:0.000} (radius {wheel.radius:0.000}, unsprung {wheel.unsprungMass:0} kg)");
    }

    /// <summary>Logs how far each wheel hub of the spawned vehicles sits
    /// above its prefab pose (positive: body lower than modelled), once they have had 2 s to settle.
    /// Runs on game-state transitions (e.g. opening the pause menu), so no per-frame hook is needed.</summary>
    public static void LogRestPoses()
    {
        for (var i = settling.Count - 1; i >= 0; i--)
        {
            var (codename, root, spawnTime) = settling[i];
            if (root == null)
            {
                settling.RemoveAt(i);
                continue;
            }
            if (Time.time - spawnTime < 2f) continue;
            var line = $"{codename}: rest pose";
            foreach (var corner in Corners)
            {
                var hub = root.Find($"Axles/WheelColliders/Wheel{corner}/WheelHub");
                if (hub != null) line += $" {corner} hub {hub.localPosition.y:+0.000;-0.000}";
            }
            Plugin.Logger.LogInfo(line + " m from the prefab pose");
        }
    }

    /// <summary>Moves every descendant behind the cut by shift; moved nodes carry their children.</summary>
    static int Sweep(Transform parent, Transform root, float cut, float shift)
    {
        var children = new List<Transform>();
        for (var i = 0; i < parent.childCount; i++) children.Add(parent.GetChild(i));
        var moved = 0;
        foreach (var child in children)
        {
            if (RootZ(root, child) < cut)
            {
                Move(root, child, 0f, shift);
                moved++;
            }
            else
            {
                moved += Sweep(child, root, cut, shift);
            }
        }
        return moved;
    }

    static void ReplaceMesh(Transform root, VehicleDefinition definition, string path, string file)
    {
        var node = root.Find(path);
        if (node == null) return; // display dummies have no colliders
        var key = $"{definition.Codename}/{path}";
        if (!meshCache.TryGetValue(key, out var mesh))
        {
            var rootToNode = node.worldToLocalMatrix * root.localToWorldMatrix;
            mesh = ObjMesh.Build(Path.Combine(definition.MeshDirectory, file), rootToNode, $"{definition.Codename}_{node.name}");
            mesh.hideFlags = HideFlags.DontUnloadUnusedAsset;
            meshCache[key] = mesh;
        }
        var filter = node.GetComponent<MeshFilter>();
        if (filter != null) filter.sharedMesh = mesh;
        var meshCollider = node.GetComponent<MeshCollider>();
        if (meshCollider != null) meshCollider.sharedMesh = mesh;
        var skinned = node.GetComponent<SkinnedMeshRenderer>();
        if (skinned != null) skinned.sharedMesh = mesh;
    }

    static float RootZ(Transform root, Transform t) => root.InverseTransformPoint(t.position).z;

    static void Move(Transform root, Transform t, float dx, float dz)
    {
        if (t == null) return;
        t.position += root.TransformVector(new Vector3(dx, 0f, dz));
    }
}
