using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using VehicleMods;

// Usage: dotnet run --project tools/toolnodes-check -- <vehicle.json>...
// Runs the reader over good and malformed blocks and the decision over every case, then reads each manifest's
// "toolNodes" the way the plugin does; a patch carrying one fails, since the plugin ignores it there.
const uint Winch = 2317836723, Other = 3771754783;
const string Node = "Parts/Mammoth_CosmeticParts/Performance/Winch/Winch_01";
var failed = 0;

void Check(bool ok, string what)
{
    Console.WriteLine($"{(ok ? "ok  " : "FAIL")} {what}");
    if (!ok) failed++;
}

ToolNodes Parse(string json)
{
    using var document = JsonDocument.Parse(json);
    return ToolNodes.Read(document.RootElement);
}

var good = Parse($"{{\"notes\": \"the bumper winch\", \"{Node}\": {Winch}}}");
Check(good.Nodes.Count == 1 && good.Nodes[0] == (Node, Winch), "a node and a note: one tool node, the note ignored");
Check(Parse("{}").Nodes.Count == 0, "an empty block: no tool nodes");

var bad = new (string Json, string Reason)[]
{
    ("[]", "not an object"),
    ($"{{\"{Node}\": \"{Winch}\"}}", "toolset ItemId"),
    ($"{{\"{Node}\": -1}}", "toolset ItemId"),
    ($"{{\"{Node}\": 0}}", "toolset ItemId"),
    ($"{{\"{Node}\": 1.5}}", "toolset ItemId"),
    ($"{{\"{Node}\": 4294967296}}", "toolset ItemId"),
    ($"{{\"{Node}\": {Winch}, \"{Node}\": {Other}}}", "duplicate key"),
    ($"{{\"Parts//Winch_01\": {Winch}}}", "not a node path"),
    ($"{{\"\": {Winch}}}", "not a node path"),
};
foreach (var (json, reason) in bad)
{
    try
    {
        Parse(json);
        Check(false, $"{json} accepted, should be refused");
    }
    catch (FormatException x)
    {
        Check(x.Message.Contains(reason), $"{json} refused: {x.Message}");
    }
}

var cases = new (bool Active, uint[] Loadout, ToolNodes.Change Expected, string What)[]
{
    (false, new[] { Other, Winch }, ToolNodes.Change.Show, "hidden, loadout carries the tool: show"),
    (true, new[] { Winch }, ToolNodes.Change.None, "shown, loadout carries the tool: keep"),
    (true, new[] { Other }, ToolNodes.Change.Hide, "shown, loadout without the tool: hide"),
    (true, new uint[0], ToolNodes.Change.Hide, "shown, empty loadout: hide"),
    (true, null, ToolNodes.Change.Hide, "shown, no VehicleItem: hide"),
    (false, null, ToolNodes.Change.None, "hidden, no VehicleItem: keep"),
    (false, new[] { Other }, ToolNodes.Change.None, "hidden, loadout without the tool: keep"),
};
foreach (var (active, loadout, expected, what) in cases)
{
    var got = ToolNodes.Decide(active, Winch, loadout);
    Check(got == expected, $"{what}{(got != expected ? $" (got {got})" : "")}");
}
Check(ToolNodes.Describe(null) == "no VehicleItem" && ToolNodes.Describe(new uint[0]) == "empty"
      && ToolNodes.Describe(new[] { Other, Winch }) == $"{Other}, {Winch}", "loadouts read as the log writes them");

// A dummy that showed one car and is refreshed for another: the old car's nodes are hidden first.
var truckA = "truck A"; var truckB = "truck B"; var stock = "stock Mammoth (its patch)";
var refreshes = new (string Previous, string Current, string Hidden, string What)[]
{
    (truckA, stock, truckA, "truck, then the stock car: the truck's nodes hidden"),
    (truckA, truckB, truckA, "truck A, then truck B: A's nodes hidden"),
    (truckA, null, truckA, "truck, then a car without a definition: the truck's nodes hidden"),
    (truckA, truckA, null, "the same truck again: nothing hidden"),
    (null, truckA, null, "a new dummy: nothing hidden"),
    (null, null, null, "an unknown car twice: nothing hidden"),
};
foreach (var (previous, current, hidden, what) in refreshes)
{
    var got = ToolNodes.Superseded(previous, current);
    Check(ReferenceEquals(got, hidden), $"{what}{(!ReferenceEquals(got, hidden) ? $" (got {got ?? "nothing"})" : "")}");
}

foreach (var path in args)
{
    using var document = JsonDocument.Parse(File.ReadAllText(path));
    var root = document.RootElement;
    if (!root.TryGetProperty("toolNodes", out var block)) continue;
    var patch = root.TryGetProperty("patch", out var p) && p.ValueKind == JsonValueKind.True;
    if (patch)
    {
        Check(false, $"{path}: a patch is the stock car; the plugin ignores its toolNodes");
        continue;
    }
    try
    {
        var tools = ToolNodes.Read(block);
        Check(true, $"{path}: {tools.Nodes.Count} tool node(s)");
        // Each node must exist on the donor: extracted/<donor>/upgrades.json (make extract) lists its nodes.
        var donor = root.GetProperty("donor").GetString().ToLowerInvariant();
        var upgrades = Path.Combine(Path.GetDirectoryName(Path.GetFullPath(path)), "..", "..", "extracted", donor, "upgrades.json");
        if (!File.Exists(upgrades))
        {
            Console.WriteLine($"skip {path}: no extracted/{donor}/upgrades.json (make extract), node paths not checked");
            continue;
        }
        using var nodes = JsonDocument.Parse(File.ReadAllText(upgrades));
        var known = new HashSet<string>();
        foreach (var node in nodes.RootElement.GetProperty("nodes").EnumerateArray())
            known.Add(node.GetProperty("path").GetString());
        foreach (var (node, _) in tools.Nodes)
            Check(known.Contains(node), $"{path}: {node} {(known.Contains(node) ? "is" : "is not")} a node of {donor} ({known.Count} nodes)");
    }
    catch (FormatException x)
    {
        Check(false, $"{path}: toolNodes {x.Message}");
    }
}
return failed == 0 ? 0 : 1;
