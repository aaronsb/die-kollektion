using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using Kollektion.Core.Build;

// Usage: dotnet run --project tools/meshops-check -- tests/meshops
// Builds the synthetic vehicle in tests/meshops/vehicle with Core and compares every OBJ and the build log with what
// build_vehicle.py made of it (expected/, expected.log), byte for byte; then the build's refusals (refusals.json)
// and Python's number semantics (numbers.json).
var dir = args.Length == 1 ? args[0] : throw new ArgumentException("usage: meshops-check <tests/meshops>");
var failed = 0;

// Quiet checks (one per file or number) print only when they fail.
void Check(bool ok, string what, bool quiet = false)
{
    if (!ok || !quiet) Console.WriteLine($"{(ok ? "ok  " : "FAIL")} {what}");
    if (!ok) failed++;
}

string Build(string manifest, string output, out List<string> missing)
{
    var log = new StringWriter { NewLine = "\n" };
    using var document = VehicleBuild.Parse(File.ReadAllText(manifest));
    missing = new VehicleBuild(manifest, Path.Combine(dir, "game"), Path.Combine(dir, "gen"), log)
        .Run(document.RootElement, output);
    return log.ToString();
}

var scratch = Path.Combine(Path.GetTempPath(), "meshops-check-" + Guid.NewGuid().ToString("N"));
try
{
    // The synthetic vehicle: every OBJ byte-identical, no file missing or extra, the same log.
    var outDir = Path.Combine(scratch, "build");
    var log = Build(Path.Combine(dir, "vehicle", "vehicle.json"), outDir, out var none);
    Check(none.Count == 0, "the synthetic vehicle's meshes are all there");
    var expected = Directory.GetFiles(Path.Combine(dir, "expected")).Select(Path.GetFileName).OrderBy(f => f, StringComparer.Ordinal).ToList();
    var built = Directory.GetFiles(outDir).Select(Path.GetFileName).OrderBy(f => f, StringComparer.Ordinal).ToList();
    Check(expected.Count > 0, $"built {built.Count} OBJs from the synthetic vehicle, {expected.Count} expected");
    var sameFiles = expected.SequenceEqual(built);
    Check(sameFiles, "the same files as build_vehicle.py" + (sameFiles ? "" : ": " + string.Join(", ", built.Except(expected).Concat(expected.Except(built)))));
    foreach (var name in expected.Intersect(built))
    {
        var want = File.ReadAllBytes(Path.Combine(dir, "expected", name));
        var got = File.ReadAllBytes(Path.Combine(outDir, name));
        var same = want.AsSpan().SequenceEqual(got);
        if (!same)
        {
            var w = File.ReadAllLines(Path.Combine(dir, "expected", name));
            var g = File.ReadAllLines(Path.Combine(outDir, name));
            var line = Enumerable.Range(0, Math.Min(w.Length, g.Length)).FirstOrDefault(i => w[i] != g[i]);
            Console.WriteLine($"     {name} line {line + 1}: {(line < g.Length ? g[line] : "(end)")} vs {(line < w.Length ? w[line] : "(end)")} expected");
        }
        Check(same, $"{name} is byte-identical", true);
    }
    Check(failed == 0, $"each of the {expected.Count} OBJs is byte-identical to build_vehicle.py's");
    var sameLog = log == File.ReadAllText(Path.Combine(dir, "expected.log")).Replace("\r\n", "\n");
    Check(sameLog, "the build log is build_vehicle.py's" + (sameLog ? "" : ":\n" + log));

    // Refusals: each definition in refusals.json fails with a BuildException saying where and why, and the previous
    // build in the output folder stays as it was, nothing written beside it or outside it.
    var bad = Path.Combine(scratch, "bad");
    var refusals = Path.Combine(scratch, "vehicle");
    Directory.CreateDirectory(Path.Combine(refusals, "meshes"));
    var part = Path.Combine(refusals, "meshes", "part.obj");
    File.Copy(Path.Combine(dir, "vehicle", "meshes", "part.obj"), part);
    File.Copy(part, Path.Combine(scratch, "outside.obj"));     // what "../outside.obj" would reach
    var manifest = Path.Combine(refusals, "refusal.json");
    const string previous = "# the previous build\n";

    void PreviousBuild()
    {
        if (Directory.Exists(bad)) Directory.Delete(bad, true);
        Directory.CreateDirectory(bad);
        File.WriteAllText(Path.Combine(bad, "a.obj"), previous);
    }

    bool Untouched() =>
        Directory.GetFileSystemEntries(bad).Select(Path.GetFileName).SequenceEqual(new[] { "a.obj" }) &&
        File.ReadAllText(Path.Combine(bad, "a.obj")) == previous && !File.Exists(Path.Combine(scratch, "escape.obj"));

    using var refusalCases = JsonDocument.Parse(File.ReadAllText(Path.Combine(dir, "refusals.json")));
    var baseDefinition = refusalCases.RootElement.GetProperty("base");
    var refused = 0;
    var failedBeforeRefusals = failed;
    foreach (var c in refusalCases.RootElement.GetProperty("cases").EnumerateArray())
    {
        var name = c.GetProperty("name").GetString();
        string text;
        if (c.TryGetProperty("text", out var raw)) text = raw.GetString();
        else
        {
            var definition = new Dictionary<string, JsonElement>();
            foreach (var p in baseDefinition.EnumerateObject()) definition[p.Name] = p.Value;
            if (c.TryGetProperty("set", out var set))
                foreach (var p in set.EnumerateObject()) definition[p.Name] = p.Value;
            if (c.TryGetProperty("drop", out var drop))
                foreach (var key in drop.EnumerateArray()) definition.Remove(key.GetString());
            definition["meshes"] = c.GetProperty("meshes");
            text = JsonSerializer.Serialize(definition);
        }
        text = text.Replace("{abs}", Path.GetFullPath(part).Replace('\\', '/'));
        var error = c.GetProperty("error").ValueKind == JsonValueKind.Null ? null : c.GetProperty("error").GetString();
        PreviousBuild();
        File.WriteAllText(manifest, text);
        try
        {
            Build(manifest, bad, out var missingHere);
            Check(error == null && missingHere.Count == 0,
                  error == null ? $"builds: {name}" : $"refuses {name}: accepted" + (missingHere.Count > 0 ? ", missing " + string.Join(", ", missingHere) : ""));
        }
        catch (BuildException e)
        {
            Check(error != null && e.Message.Contains(error, StringComparison.Ordinal) && Untouched(),
                  $"refuses {name}: {e.Message}" + (error == null ? " (it should build)" : e.Message.Contains(error, StringComparison.Ordinal) ? "" : $" (expected \"{error}\")") +
                  (Untouched() ? "" : " (and touched the output folder)"), true);
            refused++;
        }
        catch (Exception e)
        {
            Check(false, $"refuses {name}: {e.GetType().Name} instead of BuildException: {e.Message}");
        }
    }
    Check(refused > 0 && failed == failedBeforeRefusals, $"{refused} bad definitions refused, each saying where and why, the previous build untouched");

    // A missing game mesh is named as the definition names it, with /, and nothing is built.
    PreviousBuild();
    File.WriteAllText(manifest, "{\"codename\": \"T\", \"donor\": \"TestCar\", \"donorAxleZ\": {\"front\": 1.0, \"rear\": -1.0}, \"wheelbase\": 2.0, " +
                                "\"bodyCut\": [], \"meshes\": {\"Body/nothing\": \"n.obj\", \"Body/paint\": {\"file\": \"p.obj\", \"ops\": " +
                                "[{\"op\": \"insertPart\", \"file\": \"extracted/none.obj\"}]}}}");
    Build(manifest, bad, out var missing);
    Check(missing.SequenceEqual(new[] { "extracted/none.obj", "extracted/testcar/Body__nothing.obj" }) && Untouched(),
          "missing game meshes are named and nothing is built: " + string.Join(", ", missing));

    // Python's number semantics, against CPython's own results.
    using var numbers = JsonDocument.Parse(File.ReadAllText(Path.Combine(dir, "numbers.json")));
    var rows = 0;
    var failedBefore = failed;
    foreach (var row in numbers.RootElement.GetProperty("numbers").EnumerateArray())
    {
        var x = BitConverter.Int64BitsToDouble(row.GetProperty("bits").GetInt64());
        var formats = new (string Key, string Got)[]
        {
            ("f6", Py.Fixed(x, 6)), ("f3", Py.Fixed(x, 3)), ("s3", Py.Signed(x, 3)), ("f2", Py.Fixed(x, 2)), ("s2", Py.Signed(x, 2)),
            ("repr", Py.Repr(x)),
        };
        foreach (var (key, got) in formats)
            Check(got == row.GetProperty(key).GetString(), $"{key} of {row.GetProperty("repr").GetString()}: {got} vs {row.GetProperty(key).GetString()}", true);
        if (row.TryGetProperty("round4", out var n))
            Check(Py.RoundKey4(x) == n.GetInt64(), $"round({row.GetProperty("repr").GetString()}, 4): {Py.RoundKey4(x)} vs {n.GetInt64()} (x 1e-4)", true);
        rows++;
    }
    foreach (var row in numbers.RootElement.GetProperty("sums").EnumerateArray())
    {
        var sum = new Py.Sum();
        foreach (var b in row.GetProperty("bits").EnumerateArray()) sum.Add(BitConverter.Int64BitsToDouble(b.GetInt64()));
        Check(BitConverter.DoubleToInt64Bits(sum.Value) == row.GetProperty("sum").GetInt64(), $"sum of {row.GetProperty("bits")}", true);
        rows++;
    }
    foreach (var row in numbers.RootElement.GetProperty("hypots").EnumerateArray())
    {
        var ab = row.GetProperty("bits").EnumerateArray().Select(b => BitConverter.Int64BitsToDouble(b.GetInt64())).ToArray();
        Check(BitConverter.DoubleToInt64Bits(Py.Hypot(ab[0], ab[1])) == row.GetProperty("hypot").GetInt64(), $"hypot({ab[0]:R}, {ab[1]:R})", true);
        rows++;
    }
    Check(rows > 0 && failed == failedBefore, $"{rows} numbers' formats, sums and hypots match CPython's");

    // The C library's trigonometry against glibc's: informational, since a last-bit difference rarely reaches the
    // sixth decimal the OBJs print; the byte comparisons above are the gate.
    int angles = 0, differ = 0;
    foreach (var row in numbers.RootElement.GetProperty("trig").EnumerateArray())
    {
        double Bits(string key) => BitConverter.Int64BitsToDouble(row.GetProperty(key).GetInt64());
        var a = Bits("bits");
        var c = Py.Max(-1.0, Py.Min(1.0, Math.Cos(a)));
        if (Math.Cos(a) != Bits("cos") || Math.Sin(a) != Bits("sin") || Math.Tan(a / 2) != Bits("tan") || Math.Acos(c) != Bits("acos"))
            differ++;
        angles++;
    }
    Console.WriteLine($"note cos, sin, tan and acos {(differ == 0 ? "agree with glibc's" : "differ from glibc's in the last bit")} " +
                      $"on {(differ == 0 ? angles : differ)} of {angles} angles");
}
finally
{
    if (Directory.Exists(scratch)) Directory.Delete(scratch, true);
}
Console.WriteLine(failed == 0 ? "all checks passed" : $"{failed} checks failed");
return failed == 0 ? 0 : 1;
