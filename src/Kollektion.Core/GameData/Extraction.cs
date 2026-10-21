using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using AssetsTools.NET.Extra;

namespace Kollektion.Core.GameData
{
    /// <summary>What tools/export_game_data.sh extracts from the player's own install, into the same tree: the
    /// Mammoth's body, colliders, axles, wheel and tyre (mammoth/), the mechanic's truck (merchant/), the Mammoth's
    /// atlas maps (textures/) and icon (icons/), node facts and upgrade nodes for every donor, every car's parts list
    /// (parts.json), each other donor a manifest names (export_donor.py, with its upgrades, wheel and tyre), and each
    /// donor's composite atlas. None of it may ever be committed or shipped.</summary>
    public static class Extraction
    {
        public const string Mammoth = "Mammoth";

        static readonly string[] MammothNodes =
        {
            "Parts/Mammoth/Mammoth_body_LOD0", "Parts/Mammoth/Mammoth_body_LOD1", "Parts/Mammoth/Mammoth_body_LOD2",
            "Parts/Mammoth/Mammoth_body_LOD3", "Collider/Top", "Collider/Base",
            "Axles/SuspensionRigidFront/SuspensionRigidMesh_LOD0", "Axles/SuspensionRigidFront/SuspensionRigidMesh_LOD1",
            "Axles/SuspensionRigidFront/SuspensionRigidMesh_LOD2", "Axles/SuspensionRigidFront/SuspensionRigidMesh_LOD3",
            "Axles/SuspensionRigidRear/SuspensionRigidMesh_LOD0", "Axles/SuspensionRigidRear/SuspensionRigidMesh_LOD1",
            "Axles/SuspensionRigidRear/SuspensionRigidMesh_LOD2", "Axles/SuspensionRigidRear/SuspensionRigidMesh_LOD3",
        };

        // The mechanic's truck fits the Mammoth at scale 100, offset (0, -0.071, 0.086) in OBJ space.
        static readonly double[] MerchantOffset = { 0, -0.071, 0.086 };

        /// <summary>The game's Addressables folder: StandaloneLinux64, else StandaloneWindows64.</summary>
        public static string AddressablesFolder(string game)
        {
            var aa = Path.Combine(game, Platform.GameFolderName + "_Data", "StreamingAssets", "aa");
            foreach (var platform in new[] { "StandaloneLinux64", "StandaloneWindows64" })
                if (Directory.Exists(Path.Combine(aa, platform))) return Path.Combine(aa, platform);
            throw new DirectoryNotFoundException($"no Addressables folder under {game}; pass the game folder");
        }

        static string BundlePath(string aa, string pattern)
        {
            var found = Directory.GetFiles(aa, pattern).OrderBy(p => p, StringComparer.Ordinal).ToList();
            if (found.Count == 0) throw new FileNotFoundException($"missing bundle {Path.Combine(aa, pattern)}");
            return found[0];
        }

        /// <summary>The donors the vehicle manifests name (vehicles/*/vehicle.json "donor"), sorted, the Mammoth
        /// left out (it has its own list).</summary>
        public static List<string> ManifestDonors(string vehiclesDir)
        {
            var donors = new SortedSet<string>(StringComparer.Ordinal);
            if (vehiclesDir == null) return donors.ToList();
            foreach (var dir in Directory.GetDirectories(vehiclesDir))
            {
                var path = Path.Combine(dir, "vehicle.json");
                if (!File.Exists(path)) continue;
                using var doc = JsonDocument.Parse(File.ReadAllBytes(path));
                if (!doc.RootElement.TryGetProperty("donor", out var donor) || donor.ValueKind != JsonValueKind.String)
                    throw new InvalidDataException($"{path}: no \"donor\"");
                donors.Add(donor.GetString());
            }
            donors.Remove(Mammoth);
            return donors.ToList();
        }

        /// <summary>Runs the whole extraction into outDir. extraDonors are stock cars no manifest names, extracted as
        /// tools/export_donor.py alone extracts them (body, colliders, axles, node facts, atlas maps).</summary>
        public static void Run(string game, string vehiclesDir, IEnumerable<string> extraDonors, string outDir, Action<string> log)
        {
            var aa = AddressablesFolder(game);
            var carsPath = BundlePath(aa, "cars_assets_all_*.bundle");
            var objectsPath = BundlePath(aa, "scriptableobjects_assets_all_*.bundle");
            var scenePath = BundlePath(aa, "r1_canada_scenes_all_*.bundle");
            var monoscriptsPaths = Directory.GetFiles(aa, "*_monoscripts_*.bundle");
            if (monoscriptsPaths.Length != 1)
                throw new FileNotFoundException($"expected one *_monoscripts_*.bundle in {aa}, found {monoscriptsPaths.Length}");
            var donors = ManifestDonors(vehiclesDir);
            var mammothDir = Path.Combine(outDir, "mammoth");
            var textures = Path.Combine(outDir, "textures");

            using (var b = new Bundles())
            {
                var cars = b.Load(carsPath);
                var root = b.FindRoots("Car_" + Mammoth, cars).FirstOrDefault()
                           ?? throw new InvalidDataException("no root GameObject named Car_Mammoth");
                Directory.CreateDirectory(mammothDir);
                foreach (var path in MammothNodes)
                    ObjExport.CarMesh(b, root, "Car_" + Mammoth, path, mammothDir, log);
            }
            using (var b = new Bundles())
            {
                var scene = b.Load(scenePath);
                ObjExport.NamedMeshes(b, scene, Path.Combine(outDir, "merchant"), 100, MerchantOffset,
                                      new[] { "Merchant_LOD0", "Merchant_LOD1", "Merchant_LOD2", "Merchant_LOD3" }, log);
            }
            using (var b = new Bundles())
            {
                var cars = b.Load(carsPath);
                var objects = b.Load(objectsPath);
                var monoscripts = b.Load(monoscriptsPaths[0]);
                var scripts = NodeFacts.ScriptsByPathId(b, monoscripts);
                var lods = new[] { "LOD0", "LOD1", "LOD2", "LOD3" };
                ObjExport.NamedMeshes(b, cars, mammothDir, 1, new double[] { 0, 0, 0 },
                                      lods.Select(l => "Mammoth_tyre_" + l).Concat(lods.Select(l => "Mammoth_wheel_" + l)).ToList(), log);
                Images(b, cars, textures, new[] { "Mammoth_masks", "Mammoth_skin00", "Mammoth_AO" }, log);
                Images(b, objects, Path.Combine(outDir, "icons"), new[] { "Mammoth_Icon" }, log);
                NodeFacts.Export(b, cars, scripts, "Car_" + Mammoth, Path.Combine(mammothDir, "nodes.json"), log);
                Upgrades.Export(b, cars, mammothDir, "Car_" + Mammoth, log);
                PartsList.Export(b, Path.Combine(outDir, "parts.json"), log, objects, cars, monoscripts);
                foreach (var donor in donors)
                {
                    var dir = Path.Combine(outDir, donor.ToLowerInvariant());
                    Donor(b, cars, scripts, donor, dir, textures, log);
                    Upgrades.Export(b, cars, dir, "Car_" + donor, log);
                    // The donor's wheel and tyre, for renders; the plugin uses the car's own in game.
                    ObjExport.NamedMeshes(b, cars, dir, 1, new double[] { 0, 0, 0 }, new[] { donor + "_tyre_LOD0", donor + "_wheel_LOD0" }, log);
                }
                foreach (var donor in extraDonors ?? Enumerable.Empty<string>())
                    if (!donors.Contains(donor) && donor != Mammoth)
                        Donor(b, cars, scripts, donor, Path.Combine(outDir, donor.ToLowerInvariant()), textures, log);
            }

            // Each atlas as the game shades it (glass dark). A donor without masks gets none.
            if (!Directory.Exists(textures)) return;
            foreach (var skin in Directory.GetFiles(textures, "*_skin00.png").OrderBy(p => p, StringComparer.Ordinal))
            {
                var d = Path.GetFileName(skin);
                d = d.Substring(0, d.Length - "_skin00.png".Length);
                if (!File.Exists(Path.Combine(textures, d + "_masks.png")))
                    log($"{d}: no {d}_masks.png, no composite (the add-on shows the bare livery)");
                else
                    Composite.Write(textures, d, log);
            }
        }

        /// <summary>Textures and sprites by exact name into outDir (tools/export_images.py), the first object of each
        /// name in file order; a sprite &lt;Car&gt;_Icon is written as &lt;Car&gt;.png.</summary>
        static void Images(Bundles b, Bundle bundle, string outDir, IReadOnlyCollection<string> names, Action<string> log)
        {
            Directory.CreateDirectory(outDir);
            var wanted = new HashSet<string>(names);
            var found = new HashSet<string>();
            foreach (var asset in b.OfTypes(new[] { AssetClassID.Texture2D, AssetClassID.Sprite }, wanted.Contains, bundle))
            {
                if (!found.Add(asset.Name)) continue;
                var path = Path.Combine(outDir, Textures.FileName(asset) + ".png");
                Png.Write(path, asset.Type == AssetClassID.Sprite ? Textures.Sprite(b, asset) : Textures.Decode(b, asset));
                log($"{asset.Type} {asset.Name} -> {path}");
            }
            var missing = wanted.Except(found).OrderBy(n => n, StringComparer.Ordinal).ToList();
            if (missing.Count > 0) throw new InvalidDataException("not found: " + string.Join(", ", missing));
        }

        /// <summary>A stock car another vehicle is built on (tools/export_donor.py): the body LODs under
        /// Parts/&lt;group&gt;/&lt;group&gt;_body_LOD0..3 (the group's spelling varies: Car_Trailrat keeps its body
        /// under Parts/TrailRat), Collider/Top and Base, the solid axles at LOD0 when it has them, nodes.json, and the
        /// atlas maps &lt;Donor&gt;_skin00 and _masks into textures/.</summary>
        static void Donor(Bundles b, Bundle cars, Dictionary<long, string> scripts, string donor, string outDir, string textures,
                          Action<string> log)
        {
            var rootName = "Car_" + donor;
            var root = b.FindRoots(rootName, cars).FirstOrDefault() ?? throw new InvalidDataException($"no root GameObject named {rootName}");
            var group = BodyGroup(b, root);
            var paths = Enumerable.Range(0, 4).Select(n => $"Parts/{group}/{group}_body_LOD{n}").ToList();
            paths.Add("Collider/Top");
            paths.Add("Collider/Base");
            foreach (var side in new[] { "Front", "Rear" })
            {
                var path = $"Axles/SuspensionRigid{side}/SuspensionRigidMesh_LOD0";
                if (b.TryFindChild(root, path) != null) paths.Add(path);
                else log($"{donor}: no {path}; skipped");
            }
            Directory.CreateDirectory(outDir);
            foreach (var path in paths)
                ObjExport.CarMesh(b, root, rootName, path, outDir, log);

            Directory.CreateDirectory(textures);
            var wanted = new Dictionary<string, string>();
            foreach (var m in new[] { "skin00", "masks" })
            {
                wanted[$"{group}_{m}".ToLowerInvariant()] = $"{donor}_{m}";
                wanted[$"{donor}_{m}".ToLowerInvariant()] = $"{donor}_{m}";
            }
            var found = new HashSet<string>();
            foreach (var tex in b.OfTypes(new[] { AssetClassID.Texture2D }, n => wanted.ContainsKey(n.ToLowerInvariant()), cars))
            {
                var name = wanted[tex.Name.ToLowerInvariant()];
                if (!found.Add(name)) continue;
                Png.Write(Path.Combine(textures, name + ".png"), Textures.Decode(b, tex));
                log($"Texture2D {tex.Name} -> {Path.Combine(textures, name + ".png")}");
            }
            var missing = wanted.Values.Distinct().Where(n => !found.Contains(n)).OrderBy(n => n, StringComparer.Ordinal).ToList();
            if (missing.Count > 0) log($"{donor}: atlas maps not found: {string.Join(", ", missing)}");

            NodeFacts.Export(b, cars, scripts, rootName, Path.Combine(outDir, "nodes.json"), log);
        }

        /// <summary>The Parts child whose children include &lt;name&gt;_body_LOD0.</summary>
        static string BodyGroup(Bundles b, Asset root)
        {
            var parts = b.FindChild(root, "Parts");
            foreach (var t in b.Children(parts))
            {
                var name = b.NodeName(t);
                if (b.Children(t).Any(c => b.NodeName(c) == name + "_body_LOD0")) return name;
            }
            throw new InvalidDataException("no Parts/<group>/<group>_body_LOD0 under the prefab");
        }
    }
}
