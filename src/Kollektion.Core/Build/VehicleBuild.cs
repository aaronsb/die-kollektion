using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;

namespace Kollektion.Core.Build
{
    /// <summary>
    /// Builds a vehicle's meshes from its definition, as tools/build_vehicle.py does: each "meshes" entry maps a
    /// donor node path to an output file, or to {"file", "stretch", "ops"}. The donor mesh
    /// (extracted/&lt;donor&gt;/&lt;node path with / as __&gt;.obj) is lengthened behind the body cut by the wheelbase
    /// difference unless "stretch" is false or the cut is empty, then each op runs in order, and the result is
    /// written to the output folder. Part files a definition names are relative to its folder, except those under
    /// extracted/ (resolved against the extracted folder) and, when a generated folder is given, those under
    /// generated/.
    /// </summary>
    public sealed class VehicleBuild
    {
        readonly string vehicleDir, extractedDir, generatedDir;
        readonly TextWriter log;

        public VehicleBuild(string manifestPath, string extractedDir, string generatedDir, TextWriter log)
        {
            vehicleDir = Path.GetDirectoryName(Path.GetFullPath(manifestPath));
            this.extractedDir = extractedDir;
            this.generatedDir = generatedDir;
            this.log = log;
        }

        /// <summary>A part file named in the definition: a game part under extracted/, else the vehicle's own.</summary>
        public string PartPath(string file)
        {
            if (file.StartsWith("extracted/", StringComparison.Ordinal))
                return Path.Combine(extractedDir, file.Substring("extracted/".Length));
            if (generatedDir != null && file.StartsWith("generated/", StringComparison.Ordinal))
                return Path.Combine(generatedDir, file.Substring("generated/".Length));
            return Path.Combine(vehicleDir, file);
        }

        /// <summary>Builds every mesh into outDir. Returns the game meshes missing (nothing is built then), else an
        /// empty list.</summary>
        public List<string> Run(JsonElement definition, string outDir)
        {
            var front = definition.GetProperty("donorAxleZ").GetProperty("front").GetDouble();
            var rear = definition.GetProperty("donorAxleZ").GetProperty("rear").GetDouble();
            var wheelbase = definition.GetProperty("wheelbase").GetDouble();
            var donorWheelbase = front - rear;
            var shift = -(wheelbase - donorWheelbase);
            var srcDir = Path.Combine(extractedDir, definition.GetProperty("donor").GetString().ToLowerInvariant());
            var meshes = definition.GetProperty("meshes");
            var bodyCut = definition.GetProperty("bodyCut");

            var missing = MissingGameMeshes(meshes, srcDir);
            if (missing.Count > 0) return missing;
            Directory.CreateDirectory(outDir);
            log.WriteLine($"{definition.GetProperty("codename").GetString()}: wheelbase {Py.Fixed(donorWheelbase, 2)} -> " +
                          $"{Py.Fixed(wheelbase, 2)} m, rear shift {Py.Signed(shift, 3)} m");
            foreach (var entry in meshes.EnumerateObject())
            {
                var spec = entry.Value;
                var file = spec.ValueKind == JsonValueKind.String ? spec.GetString() : spec.GetProperty("file").GetString();
                var obj = ObjFile.Read(DonorMesh(srcDir, entry.Name));
                var notes = new List<string>();
                if (Stretches(spec) && bodyCut.GetArrayLength() > 0)
                {
                    var profile = bodyCut.EnumerateArray().Select(step => step.EnumerateArray().Select(x => x.GetDouble()).ToArray()).ToArray();
                    var moved = MeshOps.Stretch(obj, profile, shift);
                    obj.Header.Add($"# lengthened {Py.Signed(shift, 3)} m behind cut {OpArgs.Repr(bodyCut)}");
                    notes.Add($"moved {moved} of {obj.V.Count} vertices");
                }
                if (spec.ValueKind == JsonValueKind.Object && spec.TryGetProperty("ops", out var ops))
                    foreach (var op in ops.EnumerateArray())
                        notes.Add(Apply(obj, new OpArgs(op)));
                obj.Write(Path.Combine(outDir, file));
                log.WriteLine($"  {file}: {(notes.Count > 0 ? string.Join("; ", notes) : "copied")}");
            }
            return missing;
        }

        static bool Stretches(JsonElement spec) =>
            spec.ValueKind != JsonValueKind.Object || !spec.TryGetProperty("stretch", out var s) ||
            !(s.ValueKind == JsonValueKind.False || s.ValueKind == JsonValueKind.Null || (s.ValueKind == JsonValueKind.Number && s.GetDouble() == 0));

        static string DonorMesh(string srcDir, string nodePath) => Path.Combine(srcDir, nodePath.Replace("/", "__") + ".obj");

        /// <summary>The donor and part OBJs this definition reads that aren't on disk: they come from the player's own
        /// game install and are never in the repository.</summary>
        List<string> MissingGameMeshes(JsonElement meshes, string srcDir)
        {
            var paths = new SortedSet<string>(StringComparer.Ordinal);
            foreach (var entry in meshes.EnumerateObject())
            {
                paths.Add(DonorMesh(srcDir, entry.Name));
                if (entry.Value.ValueKind == JsonValueKind.Object && entry.Value.TryGetProperty("ops", out var ops))
                    foreach (var op in ops.EnumerateArray())
                        if (op.TryGetProperty("op", out var name) && name.ValueKind == JsonValueKind.String && name.GetString() == "insertPart")
                            paths.Add(PartPath(op.GetProperty("file").GetString()));
            }
            return paths.Where(p => !File.Exists(p)).ToList();
        }

        /// <summary>Runs one op, returning its note for the build log.</summary>
        string Apply(ObjFile obj, OpArgs a)
        {
            switch (a.Op)
            {
                case "coilSprings":
                {
                    var (removed, coils) = MeshOps.CoilSprings(obj, CoilOptions(a));
                    return $"removed {removed} leaf-spring vertices, added {coils} coils";
                }
                case "portalAxle":
                {
                    var (lifted, housings) = MeshOps.PortalAxle(obj, PortalOptions(a));
                    return $"lifted {lifted} axle vertices, added {housings} portal housings";
                }
                case "relocatePiece":
                {
                    double?[] anchorTo = null;
                    if (a.Has("anchorTo"))
                        anchorTo = a.Get("anchorTo").EnumerateArray()
                            .Select(x => x.ValueKind == JsonValueKind.Null ? (double?)null : a.Num(x, "anchorTo")).ToArray();
                    var (lo, hi) = MeshOps.RelocatePiece(obj, a.Selection(a.Get("select"), "select"), a.Num("rotateY", 0.0), anchorTo);
                    return "piece now at " + string.Join(" ", Enumerable.Range(0, 3)
                        .Select(k => $"{"xyz"[k]} {Py.Signed(lo[k], 2)}..{Py.Signed(hi[k], 2)}"));
                }
                case "stretchPieces":
                {
                    var (count, moved) = MeshOps.StretchPieces(obj, a.Selections("select"), a.Num("cutZ"), a.Num("shift"), a.Str("move"));
                    return $"moved {moved} vertices of {count} pieces {Py.Signed(a.Num("shift"), 3)} m past z {OpArgs.Repr(a.Get("cutZ"))}";
                }
                case "scalePieces":
                {
                    var moved = MeshOps.ScalePieces(obj, a.Selections("select"), a.Vector("origin", 3), a.Vector("scale", 3), a.OptBox("box"));
                    return $"scaled {moved} vertices by {OpArgs.Repr(a.Get("scale"))} about {OpArgs.Repr(a.Get("origin"))}";
                }
                case "movePieces":
                {
                    var (count, moved) = MeshOps.MovePieces(obj, a.Selections("select"), a.Vector("offset", 3));
                    return $"moved {moved} vertices of {count} pieces by {OpArgs.Repr(a.Get("offset"))}";
                }
                case "widenPieces":
                {
                    var moved = MeshOps.WidenPieces(obj, a.Selections("select"), a.Num("cutX"), a.Num("shift"), a.OptBox("box"));
                    return $"moved {moved} vertices {Py.Signed(a.Num("shift"), 3)} m outward past |x| {OpArgs.Repr(a.Get("cutX"))}";
                }
                case "removeRegion":
                {
                    var removed = MeshOps.RemoveRegion(obj, a.Box(a.Get("box"), "box"), a.Num("unitSize", 0.5));
                    return $"removed {removed} faces in {OpArgs.Repr(a.Get("box"))}";
                }
                case "removePieces":
                    return $"removed {MeshOps.RemovePieces(obj, a.Selections("select"))} pieces matching {OpArgs.Repr(a.Get("select"))}";
                case "paint":
                {
                    var choice = new PaintChoice
                    {
                        Select = a.OptSelections("select"),
                        Box = a.OptBox("box"),
                        Whole = a.Bool("whole", false),
                        UvRect = a.Has("uvRect") ? a.Points("uvRect", 2) : null,
                        Facing = a.Has("facing") ? a.Vector("facing", 3) : null,
                    };
                    if (a.Has("uvExclude"))
                        choice.UvExclude = a.Get("uvExclude").EnumerateArray().Select(r => a.Points(r, "uvExclude", 2)).ToList();
                    var painted = MeshOps.Paint(obj, a.Vector("uv", 2), choice);
                    return $"painted {painted} faces from uv {OpArgs.Repr(a.Get("uv"))}";
                }
                case "addBoxes":
                {
                    var boxes = a.Get("boxes").EnumerateArray().Select(b => BoxCorners(a, b)).ToList();
                    return $"added {MeshOps.AddBoxes(obj, boxes, a.Vector("uv", 2))} boxes";
                }
                case "addTubes":
                {
                    var tubes = a.Get("tubes").EnumerateArray().Select(t => new Tube
                    {
                        Points = a.Points(Field(a, t, "points"), "points", 3),
                        Radius = a.Num(Field(a, t, "radius"), "radius"),
                        Sides = t.TryGetProperty("sides", out var sides) ? sides.GetInt32() : 8,
                        Square = t.TryGetProperty("square", out var square) && square.ValueKind == JsonValueKind.True,
                        BendRadius = t.TryGetProperty("bendRadius", out var bend) ? a.Num(bend, "bendRadius") : (double?)null,
                    }).ToList();
                    var (count, rings) = MeshOps.AddTubes(obj, tubes, a.Vector("uv", 2));
                    return $"added {count} tubes ({rings} rings)";
                }
                case "addPlates":
                {
                    var plates = a.Get("plates").EnumerateArray().Select(p => new Plate
                    {
                        Corners = a.Points(Field(a, p, "corners"), "corners", 3),
                        Thickness = a.Num(Field(a, p, "thickness"), "thickness"),
                    }).ToList();
                    return $"added {MeshOps.AddPlates(obj, plates, a.Vector("uv", 2))} plates";
                }
                case "addDecals":
                {
                    var decals = a.Get("decals").EnumerateArray().Select(d => new Decal
                    {
                        Corners = a.Points(Field(a, d, "corners"), "corners", 3),
                        Uvs = a.Points(Field(a, d, "uvs"), "uvs", 2),
                        Facing = a.Vector(Field(a, d, "facing"), "facing", 3),
                        DoubleSided = d.TryGetProperty("doubleSided", out var two) && two.ValueKind == JsonValueKind.True,
                    }).ToList();
                    return $"added {MeshOps.AddDecals(obj, decals)} decals";
                }
                case "addProfileBands":
                {
                    var bands = a.Get("bands").EnumerateArray().Select(b =>
                    {
                        var y = a.Vector(Field(a, b, "y"), "y", 2);
                        return new Band
                        {
                            Inner = a.Points(Field(a, b, "inner"), "inner", 2),
                            Outer = a.Points(Field(a, b, "outer"), "outer", 2),
                            Y0 = y[0],
                            Y1 = y[1],
                        };
                    }).ToList();
                    return $"added {MeshOps.AddProfileBands(obj, bands, a.Vector("uv", 2))} profile bands";
                }
                case "removeNearAxle":
                    return $"removed {MeshOps.RemoveNearAxle(obj, a.Vector("centre", 2), a.Num("radius"), a.OptBox("box"))} faces near the axle";
                case "insertPart":
                {
                    var file = a.Str("file") ?? throw a.Error("needs \"file\"");
                    var part = ObjFile.Read(PartPath(file));
                    var exclude = a.Has("exclude") ? a.Selections("exclude") : Array.Empty<Selection>();
                    var added = MeshOps.InsertPart(obj, part, a.OptBox("box"), a.OptSelections("include"), exclude, a.Num("unitSize", 0.5));
                    return $"inserted {added} faces from {file}";
                }
                default:
                    throw new FormatException($"unknown operation \"{a.Op}\"");
            }
        }

        static JsonElement Field(OpArgs a, JsonElement item, string name) =>
            item.TryGetProperty(name, out var v) ? v : throw a.Error($"each item needs \"{name}\"");

        static (double[] Lo, double[] Hi) BoxCorners(OpArgs a, JsonElement box)
        {
            var lo = new double[3];
            var hi = new double[3];
            for (var k = 0; k < 3; k++)
            {
                var range = a.Vector(Field(a, box, "xyz".Substring(k, 1)), "boxes", 2);
                lo[k] = range[0];
                hi[k] = range[1];
            }
            return (lo, hi);
        }

        static CoilSpringsOptions CoilOptions(OpArgs a)
        {
            var o = new CoilSpringsOptions();
            foreach (var name in a.Names())
                switch (name)
                {
                    case "outerDiameter": o.OuterDiameter = a.Num(name); break;
                    case "wireDiameter": o.WireDiameter = a.Num(name); break;
                    case "turns": o.Turns = a.Num(name); break;
                    case "top": o.Top = a.Num(name); break;
                    case "height": o.Height = a.OptNum(name); break;
                    case "leafX": o.LeafX = a.Vector(name, 2); break;
                    case "sides": o.Sides = a.Int(name, o.Sides); break;
                    case "segmentsPerTurn": o.SegmentsPerTurn = a.Int(name, o.SegmentsPerTurn); break;
                    case "bodyBone": o.BodyBone = a.Int(name, o.BodyBone); break;
                    case "x": o.X = a.OptNum(name); break;
                    default: throw a.Error($"unknown parameter \"{name}\"");
                }
            return o;
        }

        static PortalAxleOptions PortalOptions(OpArgs a)
        {
            var o = new PortalAxleOptions();
            foreach (var name in a.Names())
                switch (name)
                {
                    case "lift": o.Lift = a.Num(name); break;
                    case "tubeScale": o.TubeScale = a.Num(name); break;
                    case "diffScale":
                        var v = a.Get(name);
                        o.DiffScale = v.ValueKind == JsonValueKind.Array ? a.Vector(name, 3) : Enumerable.Repeat(a.Num(name), 3).ToArray();
                        break;
                    case "diffOffset": o.DiffOffset = a.Num(name); break;
                    case "housingWidth": o.HousingWidth = a.Num(name); break;
                    case "housingDepth": o.HousingDepth = a.Num(name); break;
                    case "housingSegments": o.HousingSegments = a.Int(name, o.HousingSegments); break;
                    case "bodyBone": o.BodyBone = a.Int(name, o.BodyBone); break;
                    default: throw a.Error($"unknown parameter \"{name}\"");
                }
            return o;
        }
    }
}
