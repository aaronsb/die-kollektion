namespace VehicleMods;

/// <summary>Adds the mod's cars to the game's InventoryItemsCatalog.</summary>
static class Catalog
{
    public static void Register(InventoryItemsCatalog catalog, int frame)
    {
        Plugin.Logger.LogInfo($"Catalog ready at frame {frame}: {catalog.IdToSO.Count} items");
        HiddenCars.Register(catalog);
        DerivedVehicles.Register(catalog);
    }

    /// <summary>Looks up a car by its lowercase catalog name.</summary>
    public static CarInfo Find(InventoryItemsCatalog catalog, string catalogName)
    {
        if (catalog.NameToId.TryGetValue(catalogName, out var id) && catalog.IdToSO.TryGetValue(id, out var item))
            return item.TryCast<CarInfo>();
        return null;
    }

    /// <summary>Registers a car under its ItemId and lowercase catalog name; false when the ItemId belongs to another car.</summary>
    public static bool Add(InventoryItemsCatalog catalog, CarInfo car, string catalogName)
    {
        var id = car.ItemId;
        if (catalog.IdToSO.TryGetValue(id, out var existing) && existing.name != car.name)
        {
            Plugin.Logger.LogError($"{car.name}: ItemId {id} already belongs to {existing.name}; not registered");
            return false;
        }
        catalog.IdToSO[id] = car;
        catalog.IdToName[id] = catalogName;
        catalog.NameToId[catalogName] = id;
        Plugin.Logger.LogInfo($"{car.name}: registered ItemId {id}");
        return true;
    }
}
