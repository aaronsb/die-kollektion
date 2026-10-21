using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using Kollektion.Core.Build;

// Usage: dotnet run --project tools/meshops-check -- tests/meshops
// Builds the synthetic vehicle in tests/meshops/vehicle with Core and compares every OBJ and the build log with what
// build_vehicle.py made of it (expected/, expected.log), byte for byte; then Python's number semantics
// (numbers.json) and the build's refusals.
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
    using var document = JsonDocument.Parse(File.ReadAllText(manifest));
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

    // Refusals: a missing donor mesh is reported and nothing is built; bad operations name themselves.
    var bad = Path.Combine(scratch, "bad");
    var refusals = Path.Combine(scratch, "vehicle");
    Directory.CreateDirectory(bad);
    Directory.CreateDirectory(Path.Combine(refusals, "meshes"));
    File.Copy(Path.Combine(dir, "vehicle", "meshes", "part.obj"), Path.Combine(refusals, "meshes", "part.obj"));
    var manifest = Path.Combine(refusals, "refusal.json");
    string Manifest(string meshes) =>
        "{\"codename\": \"T\", \"donor\": \"TestCar\", \"donorAxleZ\": {\"front\": 1.0, \"rear\": -1.0}, \"wheelbase\": 2.0, " +
        "\"bodyCut\": [], \"meshes\": " + meshes + "}";
    var cases = new (string Meshes, string Error)[]
    {
        ("{\"Body/paint\": {\"file\": \"a.obj\", \"ops\": [{\"op\": \"flatten\"}]}}", "unknown operation \"flatten\""),
        ("{\"Body/paint\": {\"file\": \"a.obj\", \"ops\": [{\"op\": \"coilSprings\", \"coils\": 3}]}}", "coilSprings: unknown parameter \"coils\""),
        ("{\"Body/paint\": {\"file\": \"a.obj\", \"ops\": [{\"op\": \"relocatePiece\", \"select\": {\"x\": [5, 6]}}]}}", "matched 0 pieces"),
        ("{\"Body/paint\": {\"file\": \"a.obj\", \"ops\": [{\"op\": \"widenPieces\", \"select\": {}, \"cutX\": 0.7}]}}", "widenPieces: needs \"shift\""),
        ("{\"Axles/portal\": {\"file\": \"a.obj\", \"ops\": [{\"op\": \"insertPart\", \"file\": \"meshes/part.obj\"}]}}", "the base mesh is skinned"),
    };
    foreach (var (meshes, error) in cases)
    {
        try
        {
            File.WriteAllText(manifest, Manifest(meshes));
            Build(manifest, bad, out _);
            Check(false, $"{error}: accepted");
        }
        catch (Exception e) when (e is FormatException || e is InvalidOperationException)
        {
            Check(e.Message.Contains(error), $"refused: {e.Message}");
        }
    }
    File.WriteAllText(manifest, Manifest("{\"Body/nothing\": \"n.obj\", \"Body/paint\": {\"file\": \"p.obj\", \"ops\": " +
                                         "[{\"op\": \"insertPart\", \"file\": \"extracted/none.obj\"}]}}"));
    Build(manifest, bad, out var missing);
    Check(missing.Count == 2 && missing.All(m => m.EndsWith("Body__nothing.obj", StringComparison.Ordinal) || m.EndsWith("none.obj", StringComparison.Ordinal))
          && Directory.GetFiles(bad).Length == 0, "missing game meshes are named and nothing is built: " + string.Join(", ", missing));

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
}
finally
{
    if (Directory.Exists(scratch)) Directory.Delete(scratch, true);
}
Console.WriteLine(failed == 0 ? "all checks passed" : $"{failed} checks failed");
return failed == 0 ? 0 : 1;
