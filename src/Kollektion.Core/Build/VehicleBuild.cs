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
    /// difference unless "stretch" is false or the cut is empty, then each op runs in order (Operations), and the
    /// results are written to the output folder. Part files a definition names are relative to its folder, except
    /// those under extracted/ (resolved against the extracted folder) and, when a generated folder is given, those
    /// under generated/.
    ///
    /// A definition is untrusted input (packs are shared): every path it names must stay inside its folder (the
    /// vehicle's, extracted/ or generated/; outputs are bare *.obj names in the output folder), every operation must
    /// leave finite numbers, and JSON is read strictly (no key twice). Any failure is a <see cref="BuildException"/>
    /// saying where, thrown before anything is written; the outputs are then written each to a temporary file and
    /// moved into place, so a failed build leaves the previous one as it was.
    /// </summary>
    public sealed class VehicleBuild
    {
        readonly string vehicleDir, extractedDir, generatedDir;
        readonly TextWriter log;

        public VehicleBuild(string manifestPath, string extractedDir, string generatedDir, TextWriter log)
        {
            vehicleDir = Path.GetDirectoryName(Path.GetFullPath(manifestPath));
            this.extractedDir = Path.GetFullPath(extractedDir);
            this.generatedDir = generatedDir == null ? null : Path.GetFullPath(generatedDir);
            this.log = log;
        }

        /// <summary>A definition's text as strict JSON (no comments, no trailing commas); BuildException if it isn't.</summary>
        public static JsonDocument Parse(string text)
        {
            try
            {
                return JsonDocument.Parse(text);
            }
            catch (JsonException e)
            {
                throw new BuildException("not strict JSON: " + e.Message, e);
            }
        }

        /// <summary>One "meshes" entry, its paths resolved and checked.</summary>
        sealed class MeshPlan
        {
            public string NodePath, Source, Display, File;
            public bool Stretch;
            public List<JsonElement> Ops = new List<JsonElement>();
        }

        /// <summary>Builds every mesh into outDir. Returns the game meshes missing, as the definition names them
        /// (extracted/..., generated/..., meshes/...) with / between folders; nothing is built then. Else an empty
        /// list. Throws BuildException for anything else.</summary>
        public List<string> Run(JsonElement definition, string outDir)
        {
            RefuseDuplicateKeys(definition, "the definition");
            if (definition.ValueKind != JsonValueKind.Object) throw new BuildException("the definition must be a JSON object");
            var axleZ = Field(definition, "donorAxleZ", "");
            var front = Number(axleZ, "front", "donorAxleZ.");
            var rear = Number(axleZ, "rear", "donorAxleZ.");
            var wheelbase = Number(definition, "wheelbase", "");
            var codename = Text(definition, "codename");
            var donorWheelbase = front - rear;
            var shift = -(wheelbase - donorWheelbase);
            var donor = Text(definition, "donor");
            if (!IsName(donor)) throw new BuildException($"\"donor\" {BuildException.Quote(donor)} must be a car's internal name (no / \\ : or ..)");
            var donorDir = donor.ToLowerInvariant();
            outDir = Path.GetFullPath(outDir);

            var plans = Plan(Field(definition, "meshes", ""), donorDir, outDir);
            var missing = new SortedSet<string>(StringComparer.Ordinal);
            foreach (var plan in plans)
            {
                if (!File.Exists(plan.Source)) missing.Add(plan.Display);
                foreach (var op in plan.Ops)
                    if (op.GetProperty("op").GetString() == "insertPart")
                    {
                        var file = op.GetProperty("file").GetString();
                        if (!File.Exists(PartPath(file))) missing.Add(file);
                    }
            }
            if (missing.Count > 0) return missing.ToList();

            double[][] cut = null;
            JsonElement cutElement = default;
            var lines = new List<string>
            {
                $"{codename}: wheelbase {Py.Fixed(donorWheelbase, 2)} -> {Py.Fixed(wheelbase, 2)} m, rear shift {Py.Signed(shift, 3)} m",
            };
            var built = new List<(MeshPlan Plan, ObjFile Obj)>();
            foreach (var plan in plans)
            {
                var obj = Step(plan.NodePath, -1, "read", () =>
                {
                    var read = ObjFile.Read(plan.Source);
                    RefuseNonFinite(read);
                    return read;
                });
                var notes = new List<string>();
                if (plan.Stretch)
                {
                    if (cut == null) (cut, cutElement) = BodyCut(definition, plan.NodePath);
                    if (cut.Length > 0)
                    {
                        var moved = Step(plan.NodePath, -1, "stretch", () =>
                        {
                            var count = MeshOps.Stretch(obj, cut, shift);
                            RefuseNonFinite(obj);
                            return count;
                        });
                        obj.Header.Add($"# lengthened {Py.Signed(shift, 3)} m behind cut {OpArgs.Repr(cutElement)}");
                        notes.Add($"moved {moved} of {obj.V.Count} vertices");
                    }
                }
                for (var i = 0; i < plan.Ops.Count; i++)
                {
                    var args = new OpArgs(plan.Ops[i]);
                    notes.Add(Step(plan.NodePath, i, args.Op, () =>
                    {
                        var note = Operations.Apply(obj, args, ReadPart);
                        RefuseNonFinite(obj);
                        return note;
                    }));
                }
                built.Add((plan, obj));
                lines.Add($"  {plan.File}: {(notes.Count > 0 ? string.Join("; ", notes) : "copied")}");
            }
            Write(built, outDir);
            foreach (var line in lines) log.WriteLine(line);
            return new List<string>();
        }

        /// <summary>Runs one step of a mesh's build, any failure becoming a BuildException that says where.</summary>
        static T Step<T>(string mesh, int opIndex, string step, Func<T> run)
        {
            try
            {
                return run();
            }
            catch (Exception e) when (!(e is BuildException))
            {
                throw new BuildException(mesh, opIndex, step, e);
            }
        }

        /// <summary>Each "meshes" entry's donor mesh, output and operations, every path checked against its folder and
        /// every operation named, before anything is read.</summary>
        List<MeshPlan> Plan(JsonElement meshes, string donorDir, string outDir)
        {
            if (meshes.ValueKind != JsonValueKind.Object) throw new BuildException("\"meshes\" must be an object");
            var srcDir = Inside(extractedDir, donorDir, () => new BuildException($"\"donor\" {BuildException.Quote(donorDir)} leaves the extracted folder"));
            var plans = new List<MeshPlan>();
            foreach (var entry in meshes.EnumerateObject())
            {
                var plan = new MeshPlan { NodePath = entry.Name };
                BuildException Refuse(string message) => new BuildException(entry.Name, -1, null, message);
                var spec = entry.Value;
                if (spec.ValueKind == JsonValueKind.String) plan.File = spec.GetString();
                else if (spec.ValueKind == JsonValueKind.Object)
                {
                    plan.File = spec.TryGetProperty("file", out var file) && file.ValueKind == JsonValueKind.String
                        ? file.GetString()
                        : throw Refuse("needs \"file\", the output's name");
                    if (spec.TryGetProperty("ops", out var ops))
                    {
                        if (ops.ValueKind != JsonValueKind.Array) throw Refuse("\"ops\" must be a list of operations");
                        plan.Ops.AddRange(ops.EnumerateArray());
                    }
                }
                else throw Refuse("must be an output file name or {\"file\", \"stretch\", \"ops\"}");
                plan.Stretch = Stretches(spec);

                var name = entry.Name.Replace("/", "__") + ".obj";
                if (entry.Name.Length == 0 || !IsName(name))
                    throw Refuse("a node path names the donor's mesh with / between nodes; \\ and : aren't allowed");
                plan.Source = Inside(srcDir, name, () => Refuse("the node path leaves the donor's folder"));
                plan.Display = $"extracted/{donorDir}/{name}";
                if (!IsName(plan.File) || !plan.File.EndsWith(".obj", StringComparison.OrdinalIgnoreCase) || plan.File.Length == 4)
                    throw Refuse($"the output file {BuildException.Quote(plan.File)} must be a plain file name ending in .obj (no folders)");
                Inside(outDir, plan.File, () => Refuse($"the output file {BuildException.Quote(plan.File)} leaves the output folder"));

                for (var i = 0; i < plan.Ops.Count; i++)
                {
                    string opName = null;
                    try
                    {
                        var args = new OpArgs(plan.Ops[i]);
                        opName = args.Op;
                        if (!Operations.Exists(args.Op)) throw new FormatException($"unknown operation \"{args.Op}\"");
                        if (args.Op == "insertPart") PartPath(args.Str("file") ?? throw args.Error("needs \"file\""));
                    }
                    catch (Exception e) when (!(e is BuildException))
                    {
                        throw new BuildException(entry.Name, i, opName, e);
                    }
                }
                plans.Add(plan);
            }
            return plans;
        }

        /// <summary>Python's <c>entry.get("stretch", True)</c>: false, null and 0 turn it off.</summary>
        static bool Stretches(JsonElement spec) =>
            spec.ValueKind != JsonValueKind.Object || !spec.TryGetProperty("stretch", out var s) ||
            !(s.ValueKind == JsonValueKind.False || s.ValueKind == JsonValueKind.Null || (s.ValueKind == JsonValueKind.Number && s.GetDouble() == 0));

        /// <summary>"bodyCut", read when a mesh first stretches as build_vehicle.py reads it: [[y, z], ...]; null or []
        /// for none (the mesh isn't lengthened); missing is an error, as Python's KeyError.</summary>
        static (double[][], JsonElement) BodyCut(JsonElement definition, string mesh)
        {
            if (!definition.TryGetProperty("bodyCut", out var cut))
                throw new BuildException(mesh, -1, "stretch", "the mesh stretches (\"stretch\" isn't false) and the definition has no \"bodyCut\"");
            if (cut.ValueKind == JsonValueKind.Null) return (Array.Empty<double[]>(), cut);
            var shape = new BuildException("\"bodyCut\" must be a list of [y, z] steps, each a pair of numbers");
            if (cut.ValueKind != JsonValueKind.Array) throw shape;
            var steps = new List<double[]>();
            foreach (var step in cut.EnumerateArray())
            {
                if (step.ValueKind != JsonValueKind.Array || step.GetArrayLength() != 2) throw shape;
                var yz = new double[2];
                var k = 0;
                foreach (var x in step.EnumerateArray())
                    yz[k++] = x.ValueKind == JsonValueKind.Number && x.TryGetDouble(out var d) && double.IsFinite(d) ? d : throw shape;
                steps.Add(yz);
            }
            return (steps.ToArray(), cut);
        }

        /// <summary>A part file named in the definition: a game part under extracted/, a generated one under generated/
        /// (when a generated folder is given), else the vehicle's own; the path must stay inside that folder.</summary>
        string PartPath(string file)
        {
            string root = vehicleDir, rest = file;
            if (file.StartsWith("extracted/", StringComparison.Ordinal))
            {
                root = extractedDir;
                rest = file.Substring("extracted/".Length);
            }
            else if (generatedDir != null && file.StartsWith("generated/", StringComparison.Ordinal))
            {
                root = generatedDir;
                rest = file.Substring("generated/".Length);
            }
            var problem = file.IndexOf('\\') >= 0 ? "uses \\; separate folders with /"
                : Path.IsPathRooted(file) || file.StartsWith("/", StringComparison.Ordinal) || file.IndexOf(':') >= 0 ? "is an absolute path"
                : rest.Split('/').Any(s => s == ".." || s == "." || s.Length == 0) ? "must not climb out with .., nor hold empty or . folders"
                : file.Any(char.IsControl) ? "holds a control character"
                : null;
            if (problem != null)
                throw new FormatException($"\"file\" {BuildException.Quote(file)} {problem}: part files are relative to the vehicle's folder, extracted/ or generated/");
            return Inside(root, rest, () => new FormatException($"\"file\" {BuildException.Quote(file)} leaves its folder"));
        }

        ObjFile ReadPart(string file)
        {
            var part = ObjFile.Read(PartPath(file));
            RefuseNonFinite(part);
            return part;
        }

        /// <summary>A file or folder name (no separators, no drive or stream colon, not . or ..).</summary>
        static bool IsName(string name) =>
            name.Length > 0 && name != "." && name != ".." && name.IndexOfAny(new[] { '/', '\\', ':' }) < 0 && !name.Any(char.IsControl);

        /// <summary>root/relative, which must lie strictly inside root once resolved.</summary>
        static string Inside(string root, string relative, Func<Exception> refuse)
        {
            var full = Path.GetFullPath(Path.Combine(root, relative));
            var prefix = Path.TrimEndingDirectorySeparator(Path.GetFullPath(root)) + Path.DirectorySeparatorChar;
            var comparison = OperatingSystem.IsWindows() || OperatingSystem.IsMacOS() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
            return full.Length > prefix.Length && full.StartsWith(prefix, comparison) ? full : throw refuse();
        }

        /// <summary>Every position, UV and normal finite: an operation making NaN or infinity (a degenerate shape,
        /// coordinates out of range) fails where Python would have raised, rather than writing a broken mesh.</summary>
        static void RefuseNonFinite(ObjFile obj)
        {
            foreach (var (rows, what) in new[] { (obj.V, "vertex"), (obj.Vt, "UV"), (obj.Vn, "normal") })
                for (var i = 0; i < rows.Count; i++)
                    foreach (var x in rows[i])
                        if (!double.IsFinite(x))
                            throw new InvalidOperationException(
                                $"{what} {i + 1} came out as {Py.Repr(x)}; the parameters make a degenerate shape or numbers out of range");
        }

        /// <summary>Writes each mesh to a temporary file in outDir, then moves them all into place: a failure leaves
        /// the previous build's files as they were, and no temporary file behind.</summary>
        static void Write(List<(MeshPlan Plan, ObjFile Obj)> built, string outDir)
        {
            var temps = new List<(string Temp, string Final)>();
            try
            {
                Directory.CreateDirectory(outDir);
                foreach (var (plan, obj) in built)
                {
                    var temp = Path.Combine(outDir, $".{plan.File}.{Guid.NewGuid():N}.tmp");
                    temps.Add((temp, Path.Combine(outDir, plan.File)));
                    obj.Write(temp);
                }
                foreach (var (temp, final) in temps) File.Move(temp, final, true);
            }
            catch (Exception e)
            {
                foreach (var (temp, _) in temps)
                    try
                    {
                        File.Delete(temp);      // gone already when it was moved into place
                    }
                    catch (Exception cleanup) when (cleanup is IOException || cleanup is UnauthorizedAccessException)
                    {
                        // Best effort: the error below is the one to report.
                    }
                throw new BuildException($"can't write {outDir}: {e.Message}", e);
            }
        }

        static void RefuseDuplicateKeys(JsonElement e, string where)
        {
            if (e.ValueKind == JsonValueKind.Object)
            {
                var seen = new HashSet<string>(StringComparer.Ordinal);
                foreach (var p in e.EnumerateObject())
                {
                    if (!seen.Add(p.Name))
                        throw new BuildException($"{where} names {BuildException.Quote(p.Name)} twice; strict JSON names each key once");
                    RefuseDuplicateKeys(p.Value, $"{where}[{BuildException.Quote(p.Name)}]");
                }
            }
            else if (e.ValueKind == JsonValueKind.Array)
            {
                var i = 0;
                foreach (var x in e.EnumerateArray()) RefuseDuplicateKeys(x, $"{where}[{i++}]");
            }
        }

        static JsonElement Field(JsonElement obj, string name, string where)
        {
            if (obj.ValueKind != JsonValueKind.Object) throw new BuildException($"\"{where.TrimEnd('.')}\" must be an object");
            return obj.TryGetProperty(name, out var v) ? v : throw new BuildException($"the definition needs \"{where}{name}\"");
        }

        static double Number(JsonElement obj, string name, string where)
        {
            var v = Field(obj, name, where);
            return v.ValueKind == JsonValueKind.Number && v.TryGetDouble(out var x) && double.IsFinite(x)
                ? x
                : throw new BuildException($"\"{where}{name}\" must be a number");
        }

        static string Text(JsonElement obj, string name)
        {
            var v = Field(obj, name, "");
            return v.ValueKind == JsonValueKind.String ? v.GetString() : throw new BuildException($"\"{name}\" must be a string");
        }
    }
}
