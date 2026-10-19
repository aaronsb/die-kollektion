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
2. **Name:** `Die Kollektion Werkstatt`. **Version:** `0.6.0`. **Author:** your name.
3. **Category:** Vehicles if the game page offers it; otherwise Gameplay or Modding Tools.
4. **Summary:** paste `summary.txt`.
5. **Description:** paste `description.bbcode` in BBCode mode, then preview it.
6. **Tags:** set the **AI generated** tag, plus Vehicles, Linux and Open source (or the nearest ones offered).
7. **File:** first publish the GitHub release with `make release VERSION=0.6.0` (on a machine with the game; `DRY_RUN=1` first to see what it builds). Then download `die-kollektion-werkstatt-0.6.0.zip` from the release (https://github.com/aaronsb/die-kollektion/releases/tag/v0.6.0) and upload that file. File name `Die Kollektion Werkstatt 0.6.0`, category Main file, version `0.6.0`, description: "Werkstatt with the plugin ready-made, plus the Die Kollektion trucks' sources. Unzip, open a terminal in the folder, run `make start`. Checksums: SHA256SUMS on the GitHub release." Leave mod manager download off: there is nothing to drop into the game folder until `make start` builds the trucks on your machine. Only the first upload is by hand; later versions go up from CI (below).
8. **Images:** the banner and the gallery as `images.md` lists (regenerate them with `make nexus-images`); the in-game screenshots go first.
9. **Requirements:** paste `requirements.txt` (BepInEx is installed by `make bepinex`, so the page needs no Nexus requirement link).
10. **Permissions:** paste `permissions.txt`; set the toggles to match it (others may use, modify and redistribute under the licences; credit required; commercial use only under the licences' terms).
11. **Changelog:** paste `changelog.txt` for version 0.6.0.
12. **Links:** add the GitHub repository, https://github.com/aaronsb/die-kollektion, as the source or homepage link, and the mirror link to the latest release, https://github.com/aaronsb/die-kollektion/releases/latest (already in `description.bbcode`; per file, link that version's tag, https://github.com/aaronsb/die-kollektion/releases/tag/vX.Y.Z).
13. Preview, then publish.

On later releases: write the version's entry in `changelog.txt` here, then `make release VERSION=x.y.z` (after bumping the plugin, the pack manifest and CHANGELOG.md together; CI checks they agree). Releasing it on GitHub (not a prerelease) starts `.github/workflows/nexus.yml`, which runs its tools from its own ref and takes only the tag's changelogs and the release's zip: it waits for the release workflow's checks on the tag, downloads the Werkstatt zip and checks it against the release's SHA256SUMS, checks the mod and the main file's versions on Nexus, and uploads with Nexus Mods' official upload action as a new version of the main file (`Die Kollektion Werkstatt x.y.z`, mod manager download off, the previous version archived, the mod's version updated). The mod's changelog gets the version's `changelog.txt` bullets (without the version line; or the CHANGELOG.md section when there is no entry). It skips a version Nexus already has (without posting its changelog again) and refuses one older than the newest x.y.z version there, so an old tag can't archive a newer file. To upload a release again, run the workflow from the Actions tab with its tag. It authenticates with the repository secret `NEXUSMODS_API_KEY`, a Nexus API key (https://www.nexusmods.com/settings/api-keys) the maintainer keeps in a local `.env*` file, which git ignores. The description, images and permissions stay by hand on Nexus.
