using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;

namespace Kollektion.Core.Build
{
    /// <summary>
    /// The operations a mesh's "ops" may name, as build_vehicle.py's OPS table: each reads its parameters (refusing
    /// what would make a mesh that isn't one: a zero-length tube segment, a decal facing nowhere), runs the
    /// MeshOps function and returns the note for the build log, worded as build_vehicle.py words it.
    /// </summary>
    static class Operations
    {
        /// <summary>One operation. readPart reads an insertPart "file", resolved and contained by VehicleBuild.</summary>
        delegate string Handler(ObjFile obj, OpArgs a, Func<string, ObjFile> readPart);

        static readonly Dictionary<string, Handler> Table = new Dictionary<string, Handler>(StringComparer.Ordinal)
        {
            ["coilSprings"] = CoilSprings,
            ["portalAxle"] = PortalAxle,
            ["relocatePiece"] = RelocatePiece,
            ["stretchPieces"] = StretchPieces,
            ["movePieces"] = MovePieces,
            ["scalePieces"] = ScalePieces,
            ["widenPieces"] = WidenPieces,
            ["removeRegion"] = RemoveRegion,
            ["removePieces"] = RemovePieces,
            ["insertPart"] = InsertPart,
            ["paint"] = Paint,
            ["addBoxes"] = AddBoxes,
            ["addTubes"] = AddTubes,
            ["addPlates"] = AddPlates,
            ["addDecals"] = AddDecals,
            ["addProfileBands"] = AddProfileBands,
            ["removeNearAxle"] = RemoveNearAxle,
        };

        public static bool Exists(string name) => Table.ContainsKey(name);

        /// <summary>Runs one operation on obj, returning its note for the build log.</summary>
        public static string Apply(ObjFile obj, OpArgs a, Func<string, ObjFile> readPart) =>
            Table.TryGetValue(a.Op, out var handler) ? handler(obj, a, readPart) : throw new FormatException($"unknown operation \"{a.Op}\"");

        static string CoilSprings(ObjFile obj, OpArgs a, Func<string, ObjFile> readPart)
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
            if (o.Sides < 3) throw a.Error($"\"sides\" must be 3 or more, not {o.Sides}");
            if (!(o.Turns > 0) || (int)(o.Turns * o.SegmentsPerTurn) < 1)
                throw a.Error($"\"turns\" {Py.Repr(o.Turns)} times \"segmentsPerTurn\" {o.SegmentsPerTurn} must make at least one segment");
            if (!(o.OuterDiameter > o.WireDiameter)) throw a.Error("\"outerDiameter\" must be larger than \"wireDiameter\"");
            var (removed, coils) = MeshOps.CoilSprings(obj, o);
            return $"removed {removed} leaf-spring vertices, added {coils} coils";
        }

        static string PortalAxle(ObjFile obj, OpArgs a, Func<string, ObjFile> readPart)
        {
            var o = new PortalAxleOptions();
            foreach (var name in a.Names())
                switch (name)
                {
                    case "lift": o.Lift = a.Num(name); break;
                    case "tubeScale": o.TubeScale = a.Num(name); break;
                    case "diffScale":
                        o.DiffScale = a.Get(name).ValueKind == JsonValueKind.Array ? a.Vector(name, 3) : Enumerable.Repeat(a.Num(name), 3).ToArray();
                        break;
                    case "diffOffset": o.DiffOffset = a.Num(name); break;
                    case "housingWidth": o.HousingWidth = a.Num(name); break;
                    case "housingDepth": o.HousingDepth = a.Num(name); break;
                    case "housingSegments": o.HousingSegments = a.Int(name, o.HousingSegments); break;
                    case "bodyBone": o.BodyBone = a.Int(name, o.BodyBone); break;
                    default: throw a.Error($"unknown parameter \"{name}\"");
                }
            if (o.HousingDepth == 0) throw a.Error("\"housingDepth\" must not be 0");
            if (o.HousingSegments < 3) throw a.Error($"\"housingSegments\" must be 3 or more, not {o.HousingSegments}");
            var (lifted, housings) = MeshOps.PortalAxle(obj, o);
            return $"lifted {lifted} axle vertices, added {housings} portal housings";
        }

        static string RelocatePiece(ObjFile obj, OpArgs a, Func<string, ObjFile> readPart)
        {
            double?[] anchorTo = null;
            if (a.Has("anchorTo"))
            {
                var v = a.Get("anchorTo");
                if (v.ValueKind != JsonValueKind.Array || v.GetArrayLength() != 3)
                    throw a.Error("\"anchorTo\" must be [x, y, z], each a number or null");
                anchorTo = v.EnumerateArray().Select(x => x.ValueKind == JsonValueKind.Null ? (double?)null : a.Num(x, "anchorTo")).ToArray();
            }
            var (lo, hi) = MeshOps.RelocatePiece(obj, a.Selection(a.Get("select"), "select"), a.Num("rotateY", 0.0), anchorTo);
            return "piece now at " + string.Join(" ", Enumerable.Range(0, 3)
                .Select(k => $"{"xyz"[k]} {Py.Signed(lo[k], 2)}..{Py.Signed(hi[k], 2)}"));
        }

        static string StretchPieces(ObjFile obj, OpArgs a, Func<string, ObjFile> readPart)
        {
            var (count, moved) = MeshOps.StretchPieces(obj, a.Selections("select"), a.Num("cutZ"), a.Num("shift"), a.Str("move"));
            return $"moved {moved} vertices of {count} pieces {Py.Signed(a.Num("shift"), 3)} m past z {OpArgs.Repr(a.Get("cutZ"))}";
        }

        static string MovePieces(ObjFile obj, OpArgs a, Func<string, ObjFile> readPart)
        {
            var (count, moved) = MeshOps.MovePieces(obj, a.Selections("select"), a.Vector("offset", 3));
            return $"moved {moved} vertices of {count} pieces by {OpArgs.Repr(a.Get("offset"))}";
        }

        static string ScalePieces(ObjFile obj, OpArgs a, Func<string, ObjFile> readPart)
        {
            var moved = MeshOps.ScalePieces(obj, a.Selections("select"), a.Vector("origin", 3), a.Vector("scale", 3), a.OptBox("box"));
            return $"scaled {moved} vertices by {OpArgs.Repr(a.Get("scale"))} about {OpArgs.Repr(a.Get("origin"))}";
        }

        static string WidenPieces(ObjFile obj, OpArgs a, Func<string, ObjFile> readPart)
        {
            var moved = MeshOps.WidenPieces(obj, a.Selections("select"), a.Num("cutX"), a.Num("shift"), a.OptBox("box"));
            return $"moved {moved} vertices {Py.Signed(a.Num("shift"), 3)} m outward past |x| {OpArgs.Repr(a.Get("cutX"))}";
        }

        static string RemoveRegion(ObjFile obj, OpArgs a, Func<string, ObjFile> readPart)
        {
            var removed = MeshOps.RemoveRegion(obj, a.Box(a.Get("box"), "box"), a.Num("unitSize", 0.5));
            return $"removed {removed} faces in {OpArgs.Repr(a.Get("box"))}";
        }

        static string RemovePieces(ObjFile obj, OpArgs a, Func<string, ObjFile> readPart) =>
            $"removed {MeshOps.RemovePieces(obj, a.Selections("select"))} pieces matching {OpArgs.Repr(a.Get("select"))}";

        static string InsertPart(ObjFile obj, OpArgs a, Func<string, ObjFile> readPart)
        {
            var file = a.Str("file") ?? throw a.Error("needs \"file\"");
            var part = readPart(file);
            var exclude = a.Has("exclude") ? a.Selections("exclude") : Array.Empty<Selection>();
            // meshlib's `box or {}`: no box, and an empty one ([] or {}), insert everything.
            var box = a.Has("box") && IsEmpty(a.Get("box")) ? null : a.OptBox("box");
            var added = MeshOps.InsertPart(obj, part, box, a.OptSelections("include"), exclude, a.Num("unitSize", 0.5));
            return $"inserted {added} faces from {file}";
        }

        static bool IsEmpty(JsonElement v) =>
            (v.ValueKind == JsonValueKind.Array && v.GetArrayLength() == 0) ||
            (v.ValueKind == JsonValueKind.Object && !v.EnumerateObject().Any());

        static string Paint(ObjFile obj, OpArgs a, Func<string, ObjFile> readPart)
        {
            var choice = new PaintChoice
            {
                Select = a.OptSelections("select"),
                Box = a.OptBox("box"),
                Whole = a.Bool("whole", false),
                UvRect = a.Has("uvRect") ? UvRect(a, a.Get("uvRect"), "uvRect") : null,
                Facing = a.Has("facing") ? a.Vector("facing", 3) : null,
            };
            if (a.Has("uvExclude"))
            {
                var v = a.Get("uvExclude");
                if (v.ValueKind != JsonValueKind.Array) throw a.Error("\"uvExclude\" must be a list of [[u0, u1], [v0, v1]]");
                choice.UvExclude = v.EnumerateArray().Select(r => UvRect(a, r, "uvExclude")).ToList();
            }
            var painted = MeshOps.Paint(obj, a.Vector("uv", 2), choice);
            return $"painted {painted} faces from uv {OpArgs.Repr(a.Get("uv"))}";
        }

        static double[][] UvRect(OpArgs a, JsonElement v, string name)
        {
            var rect = a.Points(v, name, 2);
            return rect.Length == 2 ? rect : throw a.Error($"\"{name}\" must be [[u0, u1], [v0, v1]]");
        }

        static string AddBoxes(ObjFile obj, OpArgs a, Func<string, ObjFile> readPart)
        {
            var boxes = a.Items("boxes").Select(b =>
            {
                var lo = new double[3];
                var hi = new double[3];
                for (var k = 0; k < 3; k++)
                {
                    var range = b.Vector("xyz".Substring(k, 1), 2);
                    lo[k] = range[0];
                    hi[k] = range[1];
                }
                return (lo, hi);
            }).ToList();
            return $"added {MeshOps.AddBoxes(obj, boxes, a.Vector("uv", 2))} boxes";
        }

        static string AddTubes(ObjFile obj, OpArgs a, Func<string, ObjFile> readPart)
        {
            var tubes = a.Items("tubes").Select(t =>
            {
                var tube = new Tube
                {
                    Points = t.Points("points", 3),
                    Radius = t.Num("radius"),
                    Sides = t.Int("sides", 8),
                    Square = t.Bool("square", false),
                    BendRadius = t.OptNum("bendRadius"),
                };
                if (tube.Points.Length < 2) throw t.Error("\"points\" must hold two points or more");
                for (var i = 0; i + 1 < tube.Points.Length; i++)
                    if (Vec.Length(Vec.Sub(tube.Points[i + 1], tube.Points[i])) == 0)
                        throw t.Error($"\"points\" {i} and {i + 1} are the same point");
                if (tube.Sides < 3) throw t.Error($"\"sides\" must be 3 or more, not {tube.Sides}");
                return tube;
            }).ToList();
            var (count, rings) = MeshOps.AddTubes(obj, tubes, a.Vector("uv", 2));
            return $"added {count} tubes ({rings} rings)";
        }

        static string AddPlates(ObjFile obj, OpArgs a, Func<string, ObjFile> readPart)
        {
            var plates = a.Items("plates").Select(p =>
            {
                var plate = new Plate { Corners = p.Points("corners", 3), Thickness = p.Num("thickness") };
                var q = plate.Corners;
                if (q.Length != 4) throw p.Error("\"corners\" must be four points, in order round the plate");
                if (Vec.Length(Vec.Cross(Vec.Sub(q[1], q[0]), Vec.Sub(q[3], q[0]))) == 0)
                    throw p.Error("\"corners\" 0, 1 and 3 must span a plane (two coincide, or they lie in a line)");
                return plate;
            }).ToList();
            return $"added {MeshOps.AddPlates(obj, plates, a.Vector("uv", 2))} plates";
        }

        static string AddDecals(ObjFile obj, OpArgs a, Func<string, ObjFile> readPart)
        {
            var decals = a.Items("decals").Select(d =>
            {
                var decal = new Decal
                {
                    Corners = d.Points("corners", 3),
                    Uvs = d.Points("uvs", 2),
                    Facing = d.Vector("facing", 3),
                    DoubleSided = d.Bool("doubleSided", false),
                };
                if (decal.Corners.Length < 3) throw d.Error("\"corners\" must hold three points or more");
                if (decal.Uvs.Length != decal.Corners.Length) throw d.Error("\"uvs\" must hold one UV per corner");
                if (Vec.Length(decal.Facing) == 0) throw d.Error("\"facing\" must not be [0, 0, 0]");
                return decal;
            }).ToList();
            return $"added {MeshOps.AddDecals(obj, decals)} decals";
        }

        static string AddProfileBands(ObjFile obj, OpArgs a, Func<string, ObjFile> readPart)
        {
            var bands = a.Items("bands").Select(b =>
            {
                var y = b.Vector("y", 2);
                var band = new Band { Inner = b.Points("inner", 2), Outer = b.Points("outer", 2), Y0 = y[0], Y1 = y[1] };
                if (band.Inner.Length < 2) throw b.Error("\"inner\" must hold two points or more");
                if (band.Outer.Length != band.Inner.Length) throw b.Error("\"outer\" must hold as many points as \"inner\"");
                for (var i = 0; i + 1 < band.Inner.Length; i++)
                    if (band.Inner[i][0] == band.Inner[i + 1][0] && band.Inner[i][1] == band.Inner[i + 1][1])
                        throw b.Error($"\"inner\" {i} and {i + 1} are the same point");
                return band;
            }).ToList();
            return $"added {MeshOps.AddProfileBands(obj, bands, a.Vector("uv", 2))} profile bands";
        }

        static string RemoveNearAxle(ObjFile obj, OpArgs a, Func<string, ObjFile> readPart) =>
            $"removed {MeshOps.RemoveNearAxle(obj, a.Vector("centre", 2), a.Num("radius"), a.OptBox("box"))} faces near the axle";
    }
}
