using System.Collections.Generic;
using UnityEngine;
using UnityEngine.AddressableAssets;
using UnityEngine.ResourceManagement.AsyncOperations;

namespace VehicleMods;

/// <summary>Registers the cars the shipped catalog leaves out (Rancho, Grizzly), so owned copies show in the garage.</summary>
static class HiddenCars
{
    // Codename -> a livery address that pulls that car's CarInfo in as a dependency.
    static readonly Dictionary<string, string> Cars = new()
    {
        ["Baguette"] = "Assets/Data/Liveries/Baguette/Baguette_livery_00.asset",
        ["Grizzly"] = "Assets/Data/Liveries/Grizzly/Grizzly_livery_00.asset",
    };
    const string ExcludedSuffix = "[CatalogExcluded]";
    // The hidden cars ship without a category (vehicle setup) or tire config; borrow both from
    // the shipping car closest in wheel size. Polyana: r=0.35 vs 0.30, Trail, small tires.
    const string DonorCatalogName = "polyana";

    public static void Register(InventoryItemsCatalog catalog)
    {
        var donor = Catalog.Find(catalog, DonorCatalogName);
        if (donor == null)
        {
            Plugin.Logger.LogError($"Donor car {DonorCatalogName} not in catalog; hidden cars left unregistered");
            return;
        }

        foreach (var (codename, liveryAddress) in Cars)
        {
            var car = FindLoaded(codename) ?? LoadViaLivery(codename, liveryAddress);
            if (car == null)
            {
                Plugin.Logger.LogWarning($"{codename}: CarInfo not found");
                continue;
            }
            car.name = codename;
            if (car.carCategorySetup == null) car.carCategorySetup = donor.carCategorySetup;
            if (car.tireAsset == null) car.tireAsset = donor.tireAsset;
            Catalog.Add(catalog, car, codename.ToLowerInvariant());
        }
    }

    static CarInfo LoadViaLivery(string codename, string address)
    {
        var handle = Addressables.LoadAssetAsync<Object>(address);
        handle.WaitForCompletion();
        if (handle.Status != AsyncOperationStatus.Succeeded)
        {
            Plugin.Logger.LogWarning($"{codename}: loading {address} failed ({handle.Status})");
            return null;
        }
        return FindLoaded(codename);
    }

    static CarInfo FindLoaded(string codename)
    {
        foreach (var car in Resources.FindObjectsOfTypeAll<CarInfo>())
        {
            if (car.name == codename || car.name == codename + ExcludedSuffix) return car;
        }
        return null;
    }
}
