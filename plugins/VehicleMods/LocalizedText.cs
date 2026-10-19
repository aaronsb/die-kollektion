using UnityEngine.Localization;
using UnityEngine.Localization.Settings;

namespace VehicleMods;

/// <summary>
/// Gives a cloned item its own name and description by adding entries to its string table in
/// every locale; the same text is used for all languages.
/// </summary>
static class LocalizedText
{
    // Key ids far above anything Unity's generator assigns, derived from the item id.
    const long KeyBase = 9_000_000_000_000_000_000;

    public static void Apply(InventoryItemScriptableObject item, string name, string description)
    {
        if (!string.IsNullOrEmpty(name)) item.Name = AddEntry(item.Name, KeyBase + item.ItemId * 2L, name);
        if (!string.IsNullOrEmpty(description)) item.Description = AddEntry(item.Description, KeyBase + item.ItemId * 2L + 1, description);
    }

    static LocalizedString AddEntry(LocalizedString template, long keyId, string text)
    {
        var tableReference = template.TableReference;
        var tables = 0;
        foreach (var locale in LocalizationSettings.AvailableLocales.Locales)
        {
            var table = LocalizationSettings.StringDatabase.GetTable(tableReference, locale);
            if (table == null) continue;
            if (table.SharedData.GetEntry(keyId) == null) table.SharedData.AddKey($"VehicleMods_{keyId}", keyId);
            table.AddEntry(keyId, text);
            tables++;
        }
        Plugin.Logger.LogInfo($"'{text[..System.Math.Min(text.Length, 40)]}' added to {tables} locale tables as key {keyId}");
        return new LocalizedString(tableReference, keyId);
    }
}
