using System;
using System.IO;
using VehicleMods;

// Usage: dotnet run --project tools/near-plan -- <maps file>...
// Every layout must yield a placement the hooks can use, or the fail-safe decision (no hooks). A placement
// that overlaps a mapping other than coreclr's no-access reservation, or lies out of reach, fails the check.
var failed = 0;
if (args.Length == 0) { Console.WriteLine("no maps files given"); return 2; }
foreach (var file in args)
{
    var lines = File.ReadAllLines(file);
    var regions = NearBlockPlanner.Parse(lines);
    var expect = Array.Find(lines, l => l.StartsWith("# expect: "))?.Substring(10).Split(' ')[0];
    var plan = NearBlockPlanner.Choose(regions, 4 << 20, 4 * NearBlockPlanner.Page);
    var (textStart, textEnd) = NearBlockPlanner.GameAssemblyCode(regions);
    var ok = plan.Kind switch
    {
        NearBlockPlanner.Kind.None => true,
        NearBlockPlanner.Kind.Gap => Unmapped(plan.Start, plan.Length),
        _ => NearBlockPlanner.StillReserved(regions, plan.Start, plan.Length),
    } && (plan.Kind == NearBlockPlanner.Kind.None
          || (plan.Start >= textEnd - NearBlockPlanner.CodeRange && plan.Start + plan.Length <= textStart + NearBlockPlanner.CodeRange));
    if (expect != null && expect != plan.Kind.ToString()) ok = false;
    Console.WriteLine($"{(ok ? "ok  " : "FAIL")} {Path.GetFileName(file)}: {plan}{(expect != null ? $" [expected {expect}]" : "")}");
    if (plan.Kind != NearBlockPlanner.Kind.None)
        Console.WriteLine($"      {Math.Max(textStart - (plan.Start + plan.Length), plan.Start - textEnd) >> 20} MB from GameAssembly's code (0x{textStart:X}-0x{textEnd:X})");
    if (!ok) failed++;

    bool Unmapped(long start, long length)
    {
        foreach (var r in regions)
            if (r.Start < start + length && r.End > start) return false;
        return true;
    }
}
return failed == 0 ? 0 : 1;
