using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using AssetsTools.NET.Extra;

namespace Kollektion.Core.GameData
{
    /// <summary>Every car's purchasable parts (CarInfo.UpgradesLists), as tools/export_parts.py writes parts.json:
    /// {"cars": {"&lt;CarInfo name&gt;": {"itemId", "parts": [{"kind", "name", "itemId", "dlc"}, …]}}}.</summary>
    public static class PartsList
    {
        static readonly HashSet<string> Kinds = new HashSet<string> { "VehicleCosmetic", "VehicleUpgrade", "Livery" };

        /// <summary>Reads the MonoBehaviours of the bundles in the order given (the scriptableobjects, cars and
        /// monoscripts bundles); objects are keyed by path id, as the Python keys them.</summary>
        public static void Export(Bundles b, string outPath, Action<string> log, params Bundle[] bundles)
        {
            var parts = new Dictionary<long, PyDict>();
            var lists = new Dictionary<long, List<long>>();
            var cars = new List<Asset>();
            foreach (var mb in b.OfType(AssetClassID.MonoBehaviour, null, bundles))
            {
                string kind;
                try
                {
                    kind = b.ScriptName(mb);
                }
                catch (InvalidDataException)
                {
                    continue;
                }
                if (kind != null && Kinds.Contains(kind))
                    parts[mb.PathId] = new PyDict
                    {
                        ["kind"] = kind, ["name"] = mb.F["m_Name"].AsString, ["itemId"] = mb.F["ItemId"].AsLong,
                        ["dlc"] = mb.F["RequiredDlc"].IsDummy ? 0L : mb.F["RequiredDlc"].AsLong,
                    };
                else if (kind == "UpgradesLists")
                    lists[mb.PathId] = mb.F["Parts"].IsDummy ? new List<long>()
                        : mb.F["Parts"]["Array"].Children.Select(p => p["m_PathID"].AsLong).ToList();
                else if (kind == "CarInfo")
                    cars.Add(mb);
            }
            var result = new PyDict();
            foreach (var car in cars.OrderBy(c => c.F["m_Name"].AsString, StringComparer.Ordinal))
            {
                var ids = lists.TryGetValue(car.F["UpgradesLists"]["m_PathID"].AsLong, out var l) ? l : new List<long>();
                result[car.F["m_Name"].AsString] = new PyDict
                {
                    ["itemId"] = car.F["ItemId"].AsLong,
                    ["parts"] = ids.Where(parts.ContainsKey).Select(i => (object)parts[i]).ToList(),
                };
            }
            if (result.Count == 0) throw new InvalidDataException("no CarInfo found: pass the scriptableobjects, cars and monoscripts bundles");
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(outPath)));
            PyJson.WriteFile(outPath, new PyDict { ["cars"] = result });
            log($"{outPath}: {result.Count} cars, {parts.Count} parts");
        }
    }
}
