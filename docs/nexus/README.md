# Nexus Mods page

Everything for the mod's page on Nexus Mods ([Over the Hill on Nexus](https://www.nexusmods.com/games/overthehill)). GitHub stays the home; Nexus mirrors each release from [GitHub Releases](https://github.com/aaronsb/die-kollektion/releases). Every file here is public text and passes `tools/check_names.py`, so no real manufacturer or model names appear outside the README catalogue, which the page links to.

| File | Goes into |
|---|---|
| `summary.txt` | The page's brief overview (summary) field |
| `description.bbcode` | The description editor (switch it to BBCode) |
| `requirements.txt` | The requirements section |
| `permissions.txt` | The permissions and credits section |
| `changelog.txt` | The changelog for the uploaded version |
| `images.md` | Which images to upload, in order, with captions |

## Upload checklist

1. On the game page, choose **Upload a mod**.
2. **Name:** `Die Kollektion Werkstatt`. **Version:** `0.5.0`. **Author:** your name.
3. **Category:** Vehicles if the game page offers it; otherwise Gameplay or Modding Tools.
4. **Summary:** paste `summary.txt`.
5. **Description:** paste `description.bbcode` in BBCode mode, then preview it.
6. **Tags:** set the **AI generated** tag, plus Vehicles, Linux and Open source (or the nearest ones offered).
7. **File:** first publish the GitHub release with `make release VERSION=0.5.0` (on a machine with the game; `DRY_RUN=1` first to see what it builds). Then download `die-kollektion-werkstatt-0.5.0.zip` from https://github.com/aaronsb/die-kollektion/releases and upload that file. File name `Die Kollektion Werkstatt 0.5.0`, category Main file, version `0.5.0`, description: "Werkstatt with the plugin ready-made, plus the Die Kollektion trucks' sources. Unzip, open a terminal in the folder, run `make start`. Checksums: SHA256SUMS on the GitHub release." Leave mod manager download off: there is nothing to drop into the game folder until `make start` builds the trucks on your machine.
8. **Images:** upload as `images.md` lists; set the first as the primary image.
9. **Requirements:** paste `requirements.txt` (BepInEx is installed by `make bepinex`, so the page needs no Nexus requirement link).
10. **Permissions:** paste `permissions.txt`; set the toggles to match it (others may use, modify and redistribute under the licences; credit required; commercial use only under the licences' terms).
11. **Changelog:** paste `changelog.txt` for version 0.5.0.
12. **Links:** add the GitHub repository, https://github.com/aaronsb/die-kollektion, as the source or homepage link, and the releases page, https://github.com/aaronsb/die-kollektion/releases, in the description (already in `description.bbcode`).
13. Preview, then publish.

On later releases: `make release VERSION=x.y.z` (after bumping the plugin, the pack manifest and CHANGELOG.md together; CI checks they agree), update `changelog.txt` here, upload the new `die-kollektion-werkstatt-x.y.z.zip` as the new main file, and archive the old one.
