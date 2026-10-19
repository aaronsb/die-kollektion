using System;
using System.IO;
using System.Text.Json;
using VehicleMods;

// Usage: dotnet run --project tools/placement-check -- <fixture.json> <expect.json> [<bad.json>...]
// The fixture must resolve to the expected steps (order, paths, offsets, turns within 1e-5); every further file
// is a malformed placements file the reader must refuse with a message.
if (args.Length < 2) { Console.WriteLine("usage: placement-check <fixture.json> <expect.json> [<bad.json>...]"); return 2; }
var failed = 0;
var steps = PlacementPlan.Read(File.ReadAllText(args[0])).Steps();
using var expect = JsonDocument.Parse(File.ReadAllText(args[1]));
var expected = expect.RootElement.GetProperty("steps");
if (expected.GetArrayLength() != steps.Count)
{
    Console.WriteLine($"FAIL {steps.Count} steps, expected {expected.GetArrayLength()}");
    return 1;
}
var i = 0;
foreach (var e in expected.EnumerateArray())
{
    var step = steps[i++];
    var path = e.GetProperty("path").GetString();
    var o = e.GetProperty("offset");
    var t = e.GetProperty("turn");
    var dOffset = Math.Max(Math.Abs(step.Offset.X - o[0].GetSingle()), Math.Max(Math.Abs(step.Offset.Y - o[1].GetSingle()), Math.Abs(step.Offset.Z - o[2].GetSingle())));
    // q and -q are the same turn
    var dot = step.Turn.X * t[0].GetSingle() + step.Turn.Y * t[1].GetSingle() + step.Turn.Z * t[2].GetSingle() + step.Turn.W * t[3].GetSingle();
    var ok = step.Entry.Path == path && dOffset < 1e-5 && Math.Abs(Math.Abs(dot) - 1) < 1e-5;
    Console.WriteLine($"{(ok ? "ok  " : "FAIL")} {step.Entry.Path}{(step.Entry.Path != path ? $" (expected {path})" : "")}");
    if (!ok) failed++;
}
// Each bad file's expected reason: tests/placements/reasons.json, beside bad/.
JsonDocument reasons = null;
if (args.Length > 2)
    reasons = JsonDocument.Parse(File.ReadAllText(Path.Combine(Path.GetDirectoryName(Path.GetDirectoryName(Path.GetFullPath(args[2]))), "reasons.json")));
for (var k = 2; k < args.Length; k++)
{
    var name = Path.GetFileName(args[k]);
    if (!reasons.RootElement.TryGetProperty(name, out var wanted))
    {
        Console.WriteLine($"FAIL {name}: no reason listed in reasons.json");
        failed++;
        continue;
    }
    try
    {
        PlacementPlan.Read(File.ReadAllText(args[k]));
        Console.WriteLine($"FAIL {name}: accepted, should be refused");
        failed++;
    }
    catch (Exception x) when (x is FormatException || x is JsonException || x is InvalidOperationException)
    {
        var matched = false;
        foreach (var phrase in wanted.EnumerateArray())
            matched |= x.Message.Contains(phrase.GetString());
        Console.WriteLine($"{(matched ? "ok  " : "FAIL")} {name} refused: {x.Message}");
        if (!matched) failed++;
    }
}
return failed == 0 ? 0 : 1;
