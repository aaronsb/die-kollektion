using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.RegularExpressions;
using AssetsTools.NET.Extra;

namespace Kollektion.Core.GameData
{
    /// <summary>A donor name that can't be extracted: not a plain name, or no car of the game's has it.</summary>
    public sealed class DonorNameException : ArgumentException
    {
        public DonorNameException(string message) : base(message)
        {
        }
    }

    /// <summary>What tools/export_game_data.sh extracts from the player's own install, into the same tree: the
    /// Mammoth's body, colliders, axles, wheel and tyre (mammoth/), the mechanic's truck (merchant/), the Mammoth's
    /// atlas maps (textures/) and icon (icons/), node facts and upgrade nodes for every donor, every car's parts list
    /// (parts.json), each other donor a manifest names (export_donor.py, with its upgrades, wheel and tyre), and each
    /// donor's composite atlas. None of it may ever be committed or shipped.</summary>
    public static class Extraction
    {
        public const string Mammoth = "Mammoth";

        static readonly Regex DonorName = new Regex("^[A-Za-z0-9_]+$");

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
            if (found.Count == 0) throw new GameDataException($"missing bundle {Path.Combine(aa, pattern)}");
            return found[0];
        }

        /// <summary>The donors the vehicle manifests name (vehicles/*/vehicle.json "donor"), sorted, the Mammoth
        /// left out (it has its own list).</summary>
        public static List<string> ManifestDonors(string vehiclesDir)
        {
            var donors = new SortedSet<string>(StringComparer.Ordinal);
            if (vehiclesDir == null) return donors.ToList();
            foreach (var dir in Directory.GetDirectories(vehiclesDir).OrderBy(d => d, StringComparer.Ordinal))
            {
                var path = Path.Combine(dir, "vehicle.json");
                if (!File.Exists(path)) continue;
                try
                {
                    using var doc = JsonDocument.Parse(File.ReadAllBytes(path));
                    if (doc.RootElement.ValueKind != JsonValueKind.Object || !doc.RootElement.TryGetProperty("donor", out var donor)
                        || donor.ValueKind != JsonValueKind.String)
                        throw new InvalidDataException($"{path}: no \"donor\" name");
                    donors.Add(donor.GetString());
                }
                catch (JsonException e)
                {
                    throw new InvalidDataException($"{path}: not valid JSON ({e.Message})", e);
                }
            }
            donors.Remove(Mammoth);
            return donors.ToList();
        }

        /// <summary>Runs the whole extraction and puts it in place of outDir in one step (<see cref="ReplaceWhole"/>),
        /// once no bundle changed while it was read. extraDonors are stock cars no manifest names, extracted as
        /// tools/export_donor.py alone extracts them (body, colliders, axles, node facts, atlas maps). Donor names
        /// are checked before anything is written.</summary>
        public static void Run(string game, string vehiclesDir, IEnumerable<string> extraDonors, string outDir, Action<string> log)
        {
            var aa = AddressablesFolder(game);
            var paths = new BundlePaths
            {
                Cars = BundlePath(aa, "cars_assets_all_*.bundle"),
                Objects = BundlePath(aa, "scriptableobjects_assets_all_*.bundle"),
                Scene = BundlePath(aa, "r1_canada_scenes_all_*.bundle"),
            };
            var monoscripts = Directory.GetFiles(aa, "*_monoscripts_*.bundle");
            if (monoscripts.Length != 1)
                throw new GameDataException($"expected one *_monoscripts_*.bundle in {aa}, found {monoscripts.Length}");
            paths.Monoscripts = monoscripts[0];
            var donors = ManifestDonors(vehiclesDir);
            var extra = (extraDonors ?? Enumerable.Empty<string>()).Where(d => d != Mammoth && !donors.Contains(d)).Distinct().ToList();
            var bad = donors.Concat(extra).Where(d => !DonorName.IsMatch(d)).ToList();
            if (bad.Count > 0)
                throw new DonorNameException($"not a car's name: {string.Join(", ", bad.Select(d => $"\"{d}\""))} (letters, digits and _ only)");

            var stamps = new Dictionary<string, (long, DateTime)>();
            ReplaceWhole(outDir, (stage, stageLog) =>
            {
                Extract(paths, donors, extra, stage, stamps, stageLog);
                foreach (var kv in stamps)
                    if (Bundles.Stamp(kv.Key) != kv.Value)
                        throw new GameDataException($"{Path.GetFileName(kv.Key)} changed while it was read (is Steam updating the game?)");
            }, log);
        }

        /// <summary>Replaces outDir whole with what write puts in the folder it is given, or leaves it as it was:
        /// write fills a sibling &lt;out&gt;.partial-&lt;pid&gt;, which takes outDir's place only when write returns (the
        /// old tree kept until then), and is removed when write throws. Its log names files where they will be once
        /// the folder is in place. outDir must be new, empty or an earlier extraction (it has mammoth/), so a mistyped
        /// --out can't replace a folder of the player's; partial folders of runs that were killed are removed
        /// first.</summary>
        public static void ReplaceWhole(string outDir, Action<string, Action<string>> write, Action<string> log)
        {
            var target = Path.GetFullPath(outDir).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            var parent = target.Length == 0 ? null : Path.GetDirectoryName(target);
            if (string.IsNullOrEmpty(parent)) throw new IOException($"{outDir} is a drive's root; name a folder to extract into");
            CheckReplaceable(target);
            Directory.CreateDirectory(parent);
            RemoveAbandoned(target, log);
            var stage = $"{target}.partial-{Environment.ProcessId}";
            try
            {
                Directory.CreateDirectory(stage);
                write(stage, line => log(line.Replace(stage, target)));
                Swap(stage, target, log);
            }
            finally
            {
                if (Directory.Exists(stage)) TryDelete(stage, log);
            }
        }

        sealed class BundlePaths
        {
            public string Cars, Objects, Scene, Monoscripts;
        }

        static void Extract(BundlePaths p, List<string> donors, List<string> extra, string outDir,
                            Dictionary<string, (long, DateTime)> stamps, Action<string> log)
        {
            var mammothDir = Path.Combine(outDir, "mammoth");
            var textures = Path.Combine(outDir, "textures");

            Phase(stamps, b =>
            {
                var cars = b.Load(p.Cars);
                CheckDonorsExist(b, cars, donors.Concat(extra));
                var root = b.FindRoots("Car_" + Mammoth, cars).FirstOrDefault()
                           ?? throw new InvalidDataException("no root GameObject named Car_Mammoth");
                foreach (var path in MammothNodes)
                {
                    ObjExport.CarMesh(b, root, "Car_" + Mammoth, path, mammothDir, log);
                    b.Forget();
                }
            });
            Phase(stamps, b =>
            {
                var scene = b.Load(p.Scene);
                ObjExport.NamedMeshes(b, scene, Path.Combine(outDir, "merchant"), 100, MerchantOffset,
                                      new[] { "Merchant_LOD0", "Merchant_LOD1", "Merchant_LOD2", "Merchant_LOD3" }, log);
            });
            Phase(stamps, b =>
            {
                var cars = b.Load(p.Cars);
                var objects = b.Load(p.Objects);
                var monoscripts = b.Load(p.Monoscripts);
                var scripts = NodeFacts.ScriptsByPathId(b, monoscripts);
                var lods = new[] { "LOD0", "LOD1", "LOD2", "LOD3" };
                ObjExport.NamedMeshes(b, cars, mammothDir, 1, new double[] { 0, 0, 0 },
                                      lods.Select(l => "Mammoth_tyre_" + l).Concat(lods.Select(l => "Mammoth_wheel_" + l)).ToList(), log);
                Images(b, cars, textures, new[] { "Mammoth_masks", "Mammoth_skin00", "Mammoth_AO" }, log);
                Images(b, objects, Path.Combine(outDir, "icons"), new[] { "Mammoth_Icon" }, log);
                NodeFacts.Export(b, cars, scripts, "Car_" + Mammoth, Path.Combine(mammothDir, "nodes.json"), log);
                b.Forget();
                Upgrades.Export(b, cars, mammothDir, "Car_" + Mammoth, log);
                b.Forget();
                PartsList.Export(b, Path.Combine(outDir, "parts.json"), log, objects, cars, monoscripts);
                b.Forget();
                foreach (var donor in donors)
                {
                    var dir = Path.Combine(outDir, donor.ToLowerInvariant());
                    Donor(b, cars, scripts, donor, dir, textures, log);
                    Upgrades.Export(b, cars, dir, "Car_" + donor, log);
                    b.Forget();
                    // The donor's wheel and tyre, for renders; the plugin uses the car's own in game.
                    ObjExport.NamedMeshes(b, cars, dir, 1, new double[] { 0, 0, 0 }, new[] { donor + "_tyre_LOD0", donor + "_wheel_LOD0" }, log);
                }
                foreach (var donor in extra)
                    Donor(b, cars, scripts, donor, Path.Combine(outDir, donor.ToLowerInvariant()), textures, log);
            });

            // Each atlas as the game shades it (glass dark). A donor without masks gets none.
            if (!Directory.Exists(textures)) return;
            foreach (var skin in Directory.GetFiles(textures, "*_skin00.png").OrderBy(f => f, StringComparer.Ordinal))
            {
                var d = Path.GetFileName(skin);
                d = d.Substring(0, d.Length - "_skin00.png".Length);
                if (!File.Exists(Path.Combine(textures, d + "_masks.png")))
                    log($"{d}: no {d}_masks.png, no composite (the add-on shows the bare livery)");
                else
                    Composite.Write(textures, d, log);
            }
        }

        /// <summary>Runs one pass over its own Bundles, then checks its bundles didn't change while read and are the
        /// ones earlier passes read. Anything that fails while reading becomes a GameDataException naming the
        /// bundles (a bundle that changed underneath says so instead); output and donor-name errors pass as they
        /// are.</summary>
        static void Phase(Dictionary<string, (long, DateTime)> stamps, Action<Bundles> body)
        {
            using var b = new Bundles();
            try
            {
                body(b);
                b.CheckUnchanged();
            }
            catch (Exception e) when (GameDataException.IsDamage(e) && !(e is OutputException || e is DonorNameException))
            {
                b.CheckUnchanged();
                var names = string.Join(", ", b.Stamps.Keys.Select(Path.GetFileName));
                var what = e is InvalidDataException || e is NotSupportedException ? e.Message : $"{e.GetType().Name}: {e.Message}";
                throw new GameDataException($"{names}: {what}", e);
            }
            foreach (var kv in b.Stamps)
            {
                if (stamps.TryGetValue(kv.Key, out var earlier) && earlier != kv.Value)
                    throw new GameDataException($"{Path.GetFileName(kv.Key)} changed while it was read (is Steam updating the game?)");
                stamps[kv.Key] = kv.Value;
            }
        }

        /// <summary>Every donor must be a car prefab of the game's (Car_&lt;donor&gt;), spelt exactly.</summary>
        static void CheckDonorsExist(Bundles b, Bundle cars, IEnumerable<string> donors)
        {
            var wanted = donors.ToList();
            if (wanted.Count == 0) return;
            var known = new SortedSet<string>(b.RootsWhere(n => n.StartsWith("Car_", StringComparison.Ordinal), cars)
                                               .Select(r => r.Name.Substring(4)), StringComparer.Ordinal);
            b.Forget();
            var unknown = wanted.Where(d => !known.Contains(d)).ToList();
            if (unknown.Count > 0)
                throw new DonorNameException($"no car named {string.Join(", ", unknown.Select(d => $"\"{d}\""))} in the game " +
                                             $"(names are case-sensitive); the cars are: {string.Join(", ", known)}");
        }

        /// <summary>outDir is replaced whole, so it must be new, empty or an earlier extraction (it has mammoth/).</summary>
        static void CheckReplaceable(string target)
        {
            if (File.Exists(target)) throw new IOException($"{target} is a file; name a folder to extract into");
            if (Directory.Exists(target) && Directory.EnumerateFileSystemEntries(target).Any()
                && !Directory.Exists(Path.Combine(target, "mammoth")))
                throw new IOException($"{target} holds something other than an extraction (no mammoth/ folder); extract replaces " +
                                      "the whole folder, so name a new or empty one");
        }

        /// <summary>Removes &lt;out&gt;.partial-N and &lt;out&gt;.old-N folders left by runs that were killed (no process
        /// N runs any more): they hold game data, and nothing else cleans them up. A run killed in the middle of its
        /// swap leaves only &lt;out&gt;.old-N; that one is put back as &lt;out&gt;.</summary>
        static void RemoveAbandoned(string target, Action<string> log)
        {
            var name = Path.GetFileName(target);
            var pattern = new Regex("^" + Regex.Escape(name) + @"\.(partial|old)-(\d+)$");
            foreach (var dir in Directory.GetDirectories(Path.GetDirectoryName(target)).OrderBy(d => d, StringComparer.Ordinal))
            {
                var m = pattern.Match(Path.GetFileName(dir));
                if (!m.Success || !int.TryParse(m.Groups[2].Value, out int pid) || Running(pid)) continue;
                if (m.Groups[1].Value == "old" && !Directory.Exists(target))
                {
                    log($"putting back {target}, which an extraction that didn't finish had moved to {dir}");
                    Directory.Move(dir, target);
                    continue;
                }
                log($"removing {dir}, left by an extraction that didn't finish");
                TryDelete(dir, log);
            }
        }

        static bool Running(int pid)
        {
            try
            {
                using var p = Process.GetProcessById(pid);
                return !p.HasExited;
            }
            catch (Exception e) when (e is ArgumentException || e is InvalidOperationException)
            {
                return false;
            }
        }

        /// <summary>Puts stage in target's place, keeping the old tree until the new one is in.</summary>
        static void Swap(string stage, string target, Action<string> log)
        {
            string old = null;
            if (Directory.Exists(target))
            {
                old = $"{target}.old-{Environment.ProcessId}";
                Directory.Move(target, old);
            }
            try
            {
                Directory.Move(stage, target);
            }
            catch
            {
                if (old != null) Directory.Move(old, target);
                throw;
            }
            if (old != null) TryDelete(old, log);
        }

        static void TryDelete(string dir, Action<string> log)
        {
            try
            {
                Directory.Delete(dir, true);
            }
            catch (Exception e) when (e is IOException || e is UnauthorizedAccessException)
            {
                log($"couldn't remove {dir} ({e.Message}); it holds game data, so delete it by hand");
            }
        }

        /// <summary>Textures and sprites by exact name into outDir (tools/export_images.py), the first object of each
        /// name in file order; a sprite &lt;Car&gt;_Icon is written as &lt;Car&gt;.png.</summary>
        static void Images(Bundles b, Bundle bundle, string outDir, IReadOnlyCollection<string> names, Action<string> log)
        {
            var wanted = new HashSet<string>(names);
            var found = new HashSet<string>();
            foreach (var asset in b.OfTypes(new[] { AssetClassID.Texture2D, AssetClassID.Sprite }, wanted.Contains, bundle))
            {
                if (!found.Add(asset.Name)) continue;
                var path = Path.Combine(outDir, Textures.FileName(asset) + ".png");
                Png.Write(path, asset.Type == AssetClassID.Sprite ? Textures.Sprite(b, asset) : Textures.Decode(b, asset));
                b.Forget();
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
            foreach (var path in paths)
            {
                ObjExport.CarMesh(b, root, rootName, path, outDir, log);
                b.Forget();
            }

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
                b.Forget();
                log($"Texture2D {tex.Name} -> {Path.Combine(textures, name + ".png")}");
            }
            var missing = wanted.Values.Distinct().Where(n => !found.Contains(n)).OrderBy(n => n, StringComparer.Ordinal).ToList();
            if (missing.Count > 0) log($"{donor}: atlas maps not found: {string.Join(", ", missing)}");

            NodeFacts.Export(b, cars, scripts, rootName, Path.Combine(outDir, "nodes.json"), log);
            b.Forget();
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
