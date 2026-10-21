# Vehicle factory: packs, pipelines, lifecycle, tools

**Design draft (October 2026).** Nothing here is final or built yet unless it says so. **Die Kollektion Werkstatt** is the vehicle mod system: the plugin and the Python and Blender toolchain today, the CLI and its hub, packs, vehicle templates and Blender add-on designed here. **Die Kollektion** is an example set of vehicle packs built with it. **[research]** marks a question offline research answers (findings are summarised at the end); **[decide]** marks an open choice; **[test]** marks one only an in-game run settles.

## Direction (author, 2026-10-19)

- **What the project is:** it began as "better trucks in the game" and became a vehicle mod system, Werkstatt, with Die Kollektion's trucks as an example set of vehicle packs for it. The repo name stays `die-kollektion`. Each vehicle pack is inspectable on GitHub: its folder's `README.md` is its contact sheet, and the root README's catalogue links every pack folder.
- **A factory, not a fixed set.** Die Kollektion's own trucks are the first content, built with the same pipeline anyone else uses.
- **Two pipelines:**
  - **Patch:** change an existing vehicle (its meshes, upgrade objects, suspension, steering). The factory exposes the vehicle's slots, states and geometry for authoring in Blender and as an editor.
  - **New vehicle:** a new item on a stock donor, in a vehicle category of its own. A pack can create a category: ours is "Die Kollektion", and anyone can make another.
- Each item is a definition (strict JSON, following the game's official livery manifest pattern; see Manifests) and a directory. Items ship in **packs**: one compressed file each.
- **Lifecycle:** packs install and uninstall, and removing them brings the game back to stock, or at least to a stable state that survives Steam's "verify integrity of game files".
- **Cross-platform tools:** the CLI and the plugin run on Linux and Windows; `kollektion` is built on each OS's own CI runner (Architecture).

## Players, tinkerers, creators (author, 2026-10-20)

People are picking the mod up, and most players want a turnkey mod experience like Minecraft's: install a loader once, drop mods in, play. Distribution is compiled artifacts.

**First principle: keep setup and use on Linux (the author's own case) and Windows (most people's) as similar as possible.** Same steps, same order, same words on both: download one zip, run `kollektion` (the hub), Setup, then play (the hub's Start modded, or Steam's Play). The hub and the CLI have identical screens, commands and messages on both OSes; per-OS differences live only in Core's platform layer, and each remaining one is named under Parity below. The layout under `<game>/BepInEx/` and `<mygames>/DieKollektion/` is the same on both.

| Tier | What they use | What they install |
|---|---|---|
| **Player** | The release zip: run `kollektion` → Setup → Start modded (Distribution). Nexus carries the same zip | Nothing else: no Python, make, .NET SDK or Blender |
| **Tinkerer** | The hub: the mod's lifecycle, import and verify packs, turn items on and off, a vehicle's stats table, start modded or stock, names | Nothing else |
| **Creator** | The hub's wizard and Edit, which open Blender with the Werkstatt add-on for geometry and fitting, and the user's image or vector editor for textures | Blender 5, and an editor of their choice |
| Scripts and agents | The `kollektion` CLI: every hub action, by name | Nothing else |

- **Nothing reaches the game before Setup (author, 2026-10-21).** Unzipping changes nothing in the game folder. `kollektion setup` is the one step that installs BepInEx, the loader and the plugin, builds the trucks from the player's game and records it all in `installed.json`; the loader starts the plugin only for an install Setup recorded, built for the game build in place. Otherwise the game runs stock, or, with our trucks in a save, closes with the loader's message (`docs/engine.md`, BepInEx), and the hub says to run Setup. There is no by-hand install.
- **After Setup, a game update just works (author, 2026-10-21).** Setup is needed once. When the game updates, the next start rebuilds what the update made stale before the trucks load, with no step from the player: the plugin rebuilds the trucks from the updated game into the cache (Packs) with the same Core code Setup runs, and the loader fits the plugin to the new interop. Only an install Setup recorded is rebuilt. The second half is open for players: today the loader recompiles the plugin with the .NET SDK, which players won't have (below, 2).
- **Setup's minimum is the requirements checks (author, 2026-10-21).** Setup runs every check first and changes nothing until they all pass: the game found (Steam library or a chosen folder) and closed; its Steam build; write access to the game folder and the documents folder; free space; BepInEx present at the pinned build or fetchable; on Linux the launch option, on Windows Doorstop's `winhttp.dll`; BepInEx has prepared its interop (the game started once with it); a release plugin that fits that interop. Each failed check says what is wrong and the one thing to do, as `make start` does today. The first `kollektion setup` is these checks alone, read-only; installing and building join it as they land.
- **Players and creators need neither Python nor .NET.** The exe is self-contained, Blender carries its own Python, and the truck build moves into the plugin. Our Python tools stay internal, for building our own trucks.
- **One engine, three faces.** The hub and the add-on both run `kollektion` commands (the hub's rule, The hub), so neither can do what the CLI can't. The add-on stops calling `make` (today "Build and check" runs `make loop`) once the CLI covers it.
- **BepInEx stays out of our zip.** `kollektion setup` fetches the pinned, checksum-verified build (as `make bepinex` does today from `tools/bepinex.json`) and installs it.

| Minecraft | Die Kollektion |
|---|---|
| Loader installer (Fabric, Forge) | BepInEx plus our loader, installed by Setup |
| `mods/` | Packs (`BepInEx/DieKollektion/packs/`) |
| Launcher | The hub (`kollektion` with no arguments) |
| Blockbench | The Blender add-on, opened by the hub |
| Datapacks | Packs are data: no code |

**What stands between today and the player tier:**
1. **Trucks are built on the player's machine from their game by Python tools** (`make extract`, `make build`). `kollektion setup` builds them instead, and after a game update the plugin rebuilds them at the next start, both with Core's operations and its managed bundle reader (Architecture; Research findings, "Reading donor meshes at run time"), into the cache (Packs).
2. **A plugin built against old interop hangs the game,** and it stands between players and "a game update just works". The loader rebuilds it with the .NET SDK, which players won't have, and CI can't compile the plugin (the interop is generated from the game). So a maintainer with the game publishes a release per game update (`tools/release.py build`), and between an update and that release a player's game runs stock or, with our trucks in the save, closes with the loader's message (`docs/engine.md`, BepInEx). **[research]** Why a stale plugin hangs: if the cause is narrow (a type or signature our code touches that the update changed), a release might survive minor updates, and the loader could check that offline instead of recompiling.
3. **Windows** has never been run, and today's loader and plugin would fail there in three ways (Windows).

### Parity: the OS differences and how each is hidden

| Difference | Linux | Windows | Hidden by |
|---|---|---|---|
| Steam launch option | `"./run_bepinex.sh" %command%` is required | None: Doorstop's `winhttp.dll` beside the exe loads on a plain Steam Play | Setup sets it (below); when it can't, the hub shows the exact line with a Copy button and the click path |
| Start stock | `enabled="0"` in `run_bepinex.sh` (the file `make bepinex` already edits), or `--doorstop-enabled false` in the launch option | `enabled = false` in `doorstop_config.ini` | The hub's "Start modded" / "Start stock" set that flag and launch through `steam://rungameid/2929250`, so Steam's own launch (overlay, DRM) is kept; both refuse while the game runs. The flag stays set, so a plain Steam Play after Start stock is stock too: Check and Status show "next start: stock", and Start modded sets it back |
| Dialogs (can't start, progress) | zenity, notify-send | A native message box | One text in Core, shown by each |
| Plugin after a game update | The loader can rebuild with a host SDK | No rebuild | The player path on both is a release built for the new game version; the SDK rebuild stays a developer path |
| Paths | Steam in `~/.local/share/Steam`, `~/.steam/steam`, `~/.steam/debian-installation` or Flatpak's `~/.var/app/com.valvesoftware.Steam/.local/share/Steam` (all of `werkstatt.py`'s `steam_roots`); `~/My Games/over the hill` | Steam from `HKCU\Software\Valve\Steam\SteamPath`, else `C:\Program Files (x86)\Steam`; `Documents\My Games\over the hill` | Core resolves both; other libraries from `libraryfolders.vdf` |
| Process checks | `/proc` by process name | The process list | Core's game-running and Steam-running checks |

**Setting the Linux launch option (feasibility, from the file format, 2026-10-20).** Steam keeps it in `<steam>/userdata/<account id>/config/localconfig.vdf`, a text KeyValues file, at `UserLocalConfigStore/Software/Valve/Steam/apps/2929250/LaunchOptions`, the value with `\"` escapes; `tools/werkstatt.py` already reads it (`launch_options()`). Steam rewrites the file when it exits, so Setup writes only with Steam closed (it says so and waits), picks the account from `config/loginusers.vdf` (`MostRecent`; that file is keyed by SteamID64, and the `userdata/<account id>` folder is the 32-bit account ID, SteamID64 − 76561197960265728), backs the file up to `<mygames>/DieKollektion/backups/`, changes only that one value (adding the app's block if it has none), parses the result back before renaming it over the original, and keeps any options the player already had in front of `%command%`. Anything unexpected (no `apps` block, several matching accounts, a parse failure) falls back to Copy. Setup never writes it while Steam runs. **[test]** once with the author: Steam keeps the written value after its next start.

### The hub (author, 2026-10-20)

`kollektion` is one self-contained single-file binary per OS (linux-x64, win-x64), .NET with an Avalonia GUI, sharing Kollektion.Core with the plugin. With no arguments it opens the hub; with arguments it is the CLI. The author chose .NET over Python: players install nothing, there is no PyInstaller bundle (Windows Defender false positives), and the pack, save and ItemId rules live once in Core. Python stays inside Blender (the add-on) and in our internal tools.
- **The hub's rule (author): every form and wizard only collects the arguments of one `kollektion` command and runs it; there is no hub-only logic.** Each result shows the command it ran, with Copy, so a click can be repeated by a script or an agent and pasted into a bug report.
- **A thin launcher of commands, not an editor.** Geometry and fitting stay in Blender; images and SVGs open in the user's editors (Editor launchers).
- **No git** (author): too much to ask a modder. Versioning is the workspace copy and the packs; the repo's own git workflow stays for contributors.
- **The hub never starts the game to test anything.** It starts it only when the player presses Start.

**Actions:**
- **Lifecycle:** Check (`doctor`, the first step of Setup), Setup (`setup`: find the game, fetch BepInEx, set `UnityLogListening = false` in `BepInEx/config/BepInEx.cfg` (with it on, this game crashes at start), on Linux set `run_bepinex.sh`'s `executable_name` and execute bit (the archive ships neither), install the loader, plugin and pack, set the Linux launch option, then "start the game once" so BepInEx prepares the interop), Status (`status`), Update (`update`: the newest release's loader, plugin and pack, and whether a release exists for the current game build), Start modded / Start stock (`start --modded|--stock`), Stock (`stock`: every pack uninstalled, the save cleaned, the plugin kept; Stable states 1), Remove the mod (`remove`: the loader, plugin, packs and cache too, BepInEx kept unless ticked; Stable states 2). Removing BepInEx on Linux also restores the launch option Setup replaced, from its backup and with Steam closed, or shows the click path for clearing it; `"./run_bepinex.sh" %command%` with no script left would stop the game starting.
- **New…** (the wizard, below): `new variant|patch|vehicle`.
- **Import** (`install <file|url|github:owner/repo[@tag]>`): anyone's pack, a `.kpack` or a traded zip (Import, below).
- **Per item:** Info (`info`: the real-vehicle listing and the item's `checks` with their game builds beside this game's), Stats (`stats`, below), Edit (`edit`), Rebuild (`build --install`), Preview (`preview`), Verify (`verify`), Refresh (`refresh`), Fix on a game-asset warning (`check --fix`; Game assets: help, don't police), Activate / Deactivate (`enable` / `disable`), Delete (`uninstall <pack>/<item>`, the save cleaned; `--workspace` also deletes its workspace folder, a tickbox in the hub).
- **Settings** (`config get|set`): the game folder, Blender and the other editor launchers (each with a Test button, `config test <launcher>`), in-game names fictional or real (`names`), "Install for this user" (`self install`).

**Kinds as the hub shows them,** the same three names in the wizard, the vehicle list and Import: "Variant of a stock car" (`based`, as ours are; `new variant`), "Stock car mod" (`patch`; `new patch`), "Unique vehicle" (`novel`; `new vehicle`).

**The wizard** is the guided face of `kollektion new`, three starting points:
- **Variant of a stock car** (`kollektion new variant <Codename> --donor <Car> --name … --category …`, kind `based`): a new item that references the stock car. Its pack holds the reference (the `base` block with its stock snapshot), the differences, own parts and own textures.
- **Stock car mod** (`new patch <Car>`, kind `patch`): the stock car itself changed, with no new name or ItemId; otherwise the same.
- **Unique vehicle** (`new vehicle <Codename> --template <type> --name … --category …`, kind `novel`): own meshes and textures only, from the mesh template (`examples/template-vehicle/`), on the stock rig used live (prefab, physics, wheels, lights, points).

Steps: kind → stock car (from `kollektion extract --list`) → fictional name and description (the names check runs here) → ItemId issued, category → starting stats copied from the stock car → the item created in the workspace → the stats editor or Blender. Variants and patches give a portable pack of a stock vehicle with no game assets in it: the geometry is rebuilt from each player's own install. The only image such a pack ships is the author's own texture (Textures).

**Import** (`install`) runs, in order, and stops at the first failure with its reason; a warning (step 3, a changed stock value in step 4) is shown and Import goes on:
1. Unpack; the manifest and schema; the in-game names check; ItemId collisions with stock items, our block and installed packs.
2. Mesh gates: holes, slivers, a triangle budget per LOD (**[decide]** the budget, likely relative to the template type's donor).
3. Provenance: warn on game geometry or a copy of a game texture, naming each file and what it matches, and carry on (Game assets: help, don't police, in Items and the two pipelines; Textures). The warning is skipped for a pack made on this machine: `installed.json` records it as made here (`extract --pack` or `pack`), or every extracted file's hash matches this install's own extraction. A pack's own `origin: extracted` (What ships) grants nothing by itself, since anyone can write it.
4. Build against the local game (`based`, `patch`) and the round-trip check (Verify).
5. Record it in `installed.json`; the hub shows "built and checked, waiting for first play" until the next play's status turns it green (In-game status).

**Stats:** a table of the definition's chassis and suspension fields, the stock car's current value beside each (the stock snapshot column). Edits go to the workspace copy (shipped and imported items are copied there first), are range-checked (**[decide]** ranges in Core's schema, per field and template type), then Rebuild installs them. `kollektion stats <item> [--set <field>=<value>…]` is the same table.

**Activate / Deactivate** per item, recorded in `installed.json`:
- A patch off returns that car to stock: always safe.
- A vehicle off is safe only once the save sidecar exists: a save naming an unregistered truck's ItemId hangs the game (`KeyNotFoundException` on 3000000004, seen 2026-10-19). Until the sidecar lands (step 4 of the Migration plan) the hub refuses to deactivate a vehicle with that reason. Delete works before then: it runs `save clean` after a backup, and says the truck leaves the save.

**Verify, the round trip.** A `based` or `patch` item records the stock values it was authored against in its `base` block (Items and the two pipelines). Verify extracts the current game's data for that car and compares field by field; Core defines the check, so the plugin, the CLI and the hub agree.
- Unchanged passes.
- A changed stock value the item overrides is a warning naming the field, old and new (spring 40000 → 42000); the player keeps the pack's value (the default) or takes the new stock one, recorded in `installed.json`. A changed value the item doesn't set flows through and is listed.
- A missing node path or a mesh selection that no longer matches fails that item with a message naming the part.
- It runs on import, after a game update (the item's `base.gameBuild` or the extracted base's `hash` differs; an update that changes only assets leaves the interop hash alone), and from the Verify button.

**Refresh: keeping a pack current (author, 2026-10-20).** The game will change: stock values, meshes, upgrade options, new cars. A pack made against an older build still works where Verify passes, but it rots as its `base` falls behind. Refresh (`kollektion refresh <pack>/<item>`, a button beside Verify) rebuilds the item against the current game and rewrites its source in the workspace:
- the `base` block takes the current `gameBuild`, `hash` and stock snapshot;
- the item's own differences stay, with each Verify choice applied (keep the pack's value or take the new stock one);
- a difference that no longer applies (a node or mesh selection gone) is reported by name and left for the author, never dropped silently;
- the pack's `version` goes up (items carry none), and the result is rebuilt and gated like any build, so its `checks` record the current game (What each result was measured against, in Items and the two pipelines).
Then the author shares the refreshed pack the way they share anything (`pack`, a commit to their own repository, a new release); the hub does no git. Because a `based` or `patch` item stores only its differences, a refresh also brings in what the update added to the stock car (a new upgrade option, a fixed mesh) without the author touching it. A `novel` item rots least: only the rig and the shared wheels come from the game. New cars an update adds show in `extract --list` and become donors for the wizard. Die Kollektion's own trucks follow the same path after each game update: refresh, check, commit, release.

**In-game status.** After each start the plugin writes `<mygames>/DieKollektion/status.json`: per item registered, spawned, meshes swapped, or the failure reason, with the date and the game build. The hub shows it beside each item, so "verify it works" in game needs one play, by the player.

**Preview:**
- First, the pack's shipped contact sheets (`README.md`, `iso.png`, `rig.png`), allowed by "Contact sheets ship even when they show game geometry".
- Later, optional: a four-view render of the locally built meshes in the hub, by software raster with SkiaSharp (no Blender, no GPU), which also renders a pack whose sheets are missing or stale.

**The workspace:** `<mygames>/DieKollektion/workspace/<pack>/<item>/`, plain folders the author edits; new items go in `workspace/local/<item>/`. Installed packs are compressed and read-only, so editing a shipped or imported vehicle first copies it there. The copy keeps its ItemId and, once installed, replaces the pack's own item (`installed.json` records the override; removing the copy brings the pack's item back). Workspace items install as one local pack, rebuilt on each install. Outside `Saves/` and the game folder, like the rest of `<mygames>/DieKollektion/`.

**Editor launchers** (author, 2026-10-20). Settings hold a launcher per file type, each an editable command template with placeholders (`{file}`, `{item}`, `{blender}`, `{startup}`), kept in the persistent settings:

| File | Default on Linux | Default on Windows |
|---|---|---|
| A vehicle (an item directory) | `"{blender}" --python "{startup}"`: a startup file that enables the add-on and opens the item | The same |
| `.png` | The first found of Pinta, KolourPaint, Drawing, GIMP, Krita, else `xdg-open "{file}"` | `mspaint "{file}"` |
| `.svg` | Inkscape when found, else `xdg-open "{file}"` | Inkscape when found, else the file's default app |

- Flatpak forms work (`flatpak run org.gimp.GIMP "{file}"`). Textures are SVG-sourced (Textures), so the SVG is the file to edit; the build renders the PNG.
- `kollektion doctor` reports a launcher whose program is missing and offers its install as for any third-party item.
- After the editor saves, the hub marks the item changed since its last build, and Rebuild picks it up. `kollektion edit <item> [--file <path>]` uses the same launchers.

**Finding Blender:** PATH; Steam's Blender (`steamapps/common/Blender`); the standard install folders (Linux: `/usr/bin`, Flatpak `org.blender.Blender`, Snap; Windows: `Program Files\Blender Foundation\Blender 5.*`); or a path the user picks, remembered in Settings.

**Opening Blender with a vehicle:** the vehicle launcher's `{startup}` is a script file the hub writes, which enables the add-on and calls its API with the item directory, deferred with `bpy.app.timers` until the window exists **[test]**. What the add-on lacks for that (`blender/addons/werkstatt_addon/`, 2026-10-20):
- `api.open_vehicle(name)` takes a vehicle name in a checkout: `werkstatt_root()` comes from `WERKSTATT_DIR` or the add-on's preferences, and `model.repo_root` accepts only a folder with a `Makefile` and `vehicles/`. It needs an `open_item(path)` for an item directory anywhere.
- `model.Vehicle` reads the donor's facts from `<root>/extracted/<donor>/` (`nodes.json`, `upgrades.json`): the extract location must be passed in (`kollektion extract` writes them to `<mygames>/DieKollektion/extracted/<donor>/`).
- Opening refuses an unbuilt vehicle with "run `make build`", and `start_loop` runs `make loop V=<name>`, refusing when make is missing: both become `kollektion build` (and its check and contact sheet).
- `status()` reads the checkout's branch from `.git/HEAD` without running git and asks git only for uncommitted changes; outside a checkout both come back empty, and the panel should hide them.
- Registration: it is a legacy add-on (`bl_info`, no `blender_manifest.toml`; it declares Blender 4.2). The checker's Fix action runs one `blender -b` that asks Blender for its user add-ons folder (`bpy.utils.user_resource('SCRIPTS', path="addons")`, which differs for Flatpak and Snap Blender), copies the add-on there and enables it (`addon_enable`, `save_userpref`).

**What lands with the hub (step 3), before the in-game build (step 4).** Cheap, so it lands in step 3: Check, Setup, Status, Update, Start, Stock, Remove the mod, Import of a `novel` pack, Info, Delete, a patch's Activate / Deactivate, Preview of shipped contact sheets (`preview`), Settings, the editor launchers and self-install. These are file copies, the BepInEx fetch and the lifecycle commands, all in Core. Not cheap, so they wait for step 4: the wizard, Stats, Rebuild, Verify, Refresh, Fix and Import of a `based` or `patch` pack, which need Core's operations and bundle reader; vehicle Deactivate (Activate / Deactivate). In a developer checkout (`WERKSTATT_DIR` set), Edit and Rebuild drive today's tooling (`make loop`, the add-on's checkout mode) from step 3, since that is what the add-on already does; the hub never asks a player for Python or make.

Sketch, for the author to react to. The main window:
```
┌ Die Kollektion ───────────────────────────────────────────────── 0.x · Linux ─┐
│ Check  ✔ Game found, build N        ✔ BepInEx 6.0.0-be.789                    │
│        ✔ Plugin fits this game      ✘ Launch option not set          [Fix]    │
│ [Start modded] [Start stock]  [Status] [Update] [Stock] [Remove the mod]      │
├ Vehicles ─────────────────────────────────────────────────────────────────────┤
│ Das Megaloceros   Variant of a stock car  die-kollektion  on  ✔ played 10-20  │
│  [Info] [Stats] [Edit] [Rebuild] [Preview] [Verify] [Refresh] [Off] [Delete]  │
│ Mammoth           Stock car mod           workspace       on  … first play    │
│  [Info] [Stats] [Edit] [Rebuild] [Preview] [Verify] [Refresh] [Off] [Delete]  │
│ [ New… ]  [ Import… ]                                                         │
├───────────────────────────────────────────────────────────────────────────────┤
│ [Settings]  [Install for this user]   ran: kollektion status           [Copy] │
└───────────────────────────────────────────────────────────────────────────────┘
```
The other screens, each one form over one command:
- **New…:** 1 Kind (Variant of a stock car / Stock car mod / Unique vehicle) → 2 Stock car (list) → 3 Name and description (names check) → 4 Category, ItemId shown → 5 Starting stats → Create: `kollektion new variant Moa --donor Mammoth --name "Der Moa" --category CarCategory_05_DieKollektion`, then Stats or Edit in Blender.
- **Import…:** a file or `github:owner/repo` field → the five checks as a list that fills in (✔ passed, ⚠ a warning naming the file and what it matches, ✘ failed with the reason) → Install, or Cancel with nothing changed.
- **Stats:** field, the pack's value (editable), stock now, stock when authored, range; changed rows highlighted; Rebuild.
- **Verify:** one row per changed stock value (field, old → new, keep / take new) and per failed part.
- **Settings:** game folder, Blender, image editor, vector editor (each a command template with a Test button), names, install mode and settings location (`config`).

### Packaging of `kollektion` itself (author, 2026-10-20)

- **Portable first.** The release zip unzips anywhere, and `kollektion` / `kollektion.exe` runs from its own folder.
- **Optional per-user install, no root or UAC,** done by the exe itself: the hub's "Install for this user" with tickboxes for PATH and a shortcut, or `kollektion self install|uninstall|update` (`install`/`uninstall` stay for packs).
  - Linux: the app in `$XDG_DATA_HOME/die-kollektion/` (default `~/.local/share`), a link in `~/.local/bin`, a `.desktop` file in `$XDG_DATA_HOME/applications`, the icon in `$XDG_DATA_HOME/icons/hicolor/scalable/apps/` (and `hicolor/<size>/apps/` PNGs). The PATH tickbox helps only when `~/.local/bin` is on PATH; `doctor` says so when it isn't.
  - Windows: the app in `%LOCALAPPDATA%\Programs\DieKollektion\`, the user PATH through `HKCU\Environment` (then a `WM_SETTINGCHANGE` broadcast), a Start Menu shortcut under `%APPDATA%\Microsoft\Windows\Start Menu\Programs`, and an uninstall entry in `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\DieKollektion` (Settings → Apps).
  - Self-uninstall removes exactly what self-install recorded, and the installed settings; on Windows the running exe's own last delete goes to a short-lived helper. **Decided:** it asks first, with "Keep my settings" unticked (`--keep-settings` on the CLI), since the settings hold the user's editor commands.
  - A winget install counts as installed. `self update` and `self uninstall` defer to `winget upgrade` / `winget uninstall` for it, so the two never compete.
- **Settings follow the install mode** (author, 2026-10-20):
  - Portable: `settings.json` beside the exe, in the folder it runs from. A copy unzipped into the game folder (Distribution) keeps them in `<game>/BepInEx/DieKollektion/settings.json` instead, so nothing of ours lands in the game folder's root.
  - Installed (running from the path `self install` recorded, or from winget's package folder): Linux `$XDG_CONFIG_HOME/die-kollektion/settings.json` (default `~/.config`), Windows `%APPDATA%\DieKollektion\settings.json`, outside the app folder that an update replaces.
  - So a portable and an installed copy keep separate settings (game folder, editor launchers, names).
- **Everything else is game-tied and shared:** the workspace, extracted data, backups, `status.json` and the save sidecar live in `<mygames>/DieKollektion/`, so a portable and an installed copy share the user's vehicles, and deleting the unzipped folder loses only its settings.
- **Uninstalling the app** never touches the mod in the game or the workspace; removing packs (`uninstall`, `stock`) is separate.
- **Update:** unzip over the old folder (the zip carries no `settings.json`, so a portable copy keeps its own), or `self update`, which replaces the installed copy in its per-user folder (no UAC).

### The requirements checker (author, 2026-10-20)

The first step of Setup is `kollektion doctor`, the hub's Check screen: the same list on both OSes, scoped by tier.
- **Player:** the game found and its build; Steam and the game running or not; BepInEx present at the pinned version, `UnityLogListening = false`, and on Linux `run_bepinex.sh` ready (`executable_name`, the execute bit); the Linux launch option set; whether the next start is modded or stock; BepInEx has prepared the game once; the loader and plugin fitting the game's interop; disk space.
- **Creator:** the player's list, plus Blender 5 or newer found (see Finding Blender; the add-on itself runs from 4.2, but the contact-sheet renders need 5), the Werkstatt add-on registered, and each editor launcher's program present.
- **Developer** (this repo): that stays `make start` / `make doctor` (Linux) and isn't in the shipped exe. Today they check Python 3.10 or newer, the venv, rsvg-convert, potrace, the .NET SDK (unless the prebuilt plugin fits) and Blender; `make check` reports a missing xvfb-run; the optional Wine check (Windows) reports a missing wine.
- **Output: a shopping list,** one line per missing item with its fix.
  - Our own items (BepInEx and its two settings, the launch option, the add-on's registration) get a Fix button that `kollektion` carries out itself, with no admin rights.
  - Third-party software gets the exact command with Copy, and an Install button that runs only after the user confirms; nothing installs silently. Windows: `winget` (built into Windows 10 and 11), `--scope user` where a package supports it. Blender's winget package is an MSI with machine scope only (`BlenderFoundation.Blender` 5.2.2 in winget-pkgs, 2026-10-20), so its install asks for admin rights; the checker says so and offers Steam's Blender or the portable zip from blender.org instead. Linux: the distro's package manager through `pkexec` (or the `sudo` line printed), after checking the version it would install; for Blender also `flatpak install --user flathub org.blender.Blender` (no root) or Steam.
- **What moves into Core from `tools/werkstatt.py`'s `steps()`:** the game and Steam library search (`steam_roots`, `vdf_load`, `game_dir`), the launch-option read (`launch_options`), `my_games`, `game_running`, the BepInEx version and start-script checks (`bepinex_installed_version`, `run_script_ready`), the log-listener setting (`cfg_log_listening_off`), the `interop` step (BepInEx has prepared the game: `BepInEx/interop/Assembly-CSharp.dll`), the interop and prebuilt-plugin fit (`interop_hash`, `prebuilt_plugin`), `launch_script_target` (an old launch option naming `run_werkstatt.sh`, which Setup replaces) and the deploy state. Python, the venv, rsvg-convert, potrace, the .NET SDK, extract, build and the test save stay developer steps.

### Scripts policy (author, 2026-10-20)

No `.ps1` files and no Windows twins of shell scripts.
- **Player-facing:** `tools/run_werkstatt.sh` (the Linux Steam launch shim forwarding to BepInEx's `run_bepinex.sh`) stays Linux-only. Windows BepInEx needs no launch script, and `kollektion setup` sets or prints the Linux launch option.
- **Creator-facing:** the steps behind `make extract` (`tools/export_game_data.sh`) and behind build, check and deploy (the make targets and `werkstatt.py`) become `kollektion` subcommands in the exe, so they run the same on both OSes and the hub's buttons call them.
- **Author-only:** `build_cab_part.sh`, `preview_vehicle.sh` and `launch_test.sh` stay bash, internal, never shipped.
- **The Makefile** stays the repo's developer and CI interface; its targets thin to `kollektion` calls as the CLI grows. Windows contributors to the repo's own tooling use WSL.
- Why: two copies drift; Windows' default execution policy blocks unsigned `.ps1` files, a support burden; the logic belongs once in the tested exe, which the Windows CI job covers.

## Goals and non-goals

Goals:
- One definition per item; everything the game reads is built from it.
- Packs that need no game assets: donor-derived geometry is built on the player's machine from their own install, and the tools warn an author whose pack carries copies.
- A save that stays valid when a pack or the whole mod is removed.
- One command for each authoring and lifecycle step, refusing unsafe states (game running, no backup, failed gate).
- Authoring that starts from an exported stock vehicle in Blender.

Non-goals:
- Cheats such as money, unlock-all or fog of war; existing tools cover them.
- New physics or VPP behaviour beyond what a definition sets: wheelbase, track, steer, tyre, suspension.
- Asset bundles or new shaders. Items use a donor's prefab and shader; their textures may be their own (see Textures).
- An editor outside Blender (author, 2026-10-20). The standalone GUI is the hub (Players, tinkerers, creators), a thin launcher of `kollektion` commands with simple forms; geometry editing and fitting stay in Blender.

## Landscape (October 2026)

- **Official support:** liveries only, through mod.io and `~/My Games/over the hill/LocalLiveries/`, with Funselektor's livery docs on Notion ([Steam post](https://steamcommunity.com/app/2929250/discussions/0/571552004573301684/)). Cars and maps are "depending on reception" ([overthehill.website summary of the FAQ](https://www.overthehill.website/guides/mods)). There is no Steam Workshop; mods install by hand.
- **Nexus** ([game page](https://www.nexusmods.com/games/overthehill), about 44 mods by ID): mostly MelonLoader code mods and a few BepInEx 6 IL2CPP ones.
  - Input: TrailWheel steering wheel ([17](https://www.nexusmods.com/overthehill/mods/17)), TriggerFX DualSense ([1](https://www.nexusmods.com/overthehill/mods/1)).
  - Cameras: BonnetCam ([3](https://www.nexusmods.com/overthehill/mods/3)), Camera Angles and Speedometer ([4](https://www.nexusmods.com/overthehill/mods/4)).
  - Visual: Looks colour presets ([15](https://www.nexusmods.com/overthehill/mods/15)).
  - Vehicle tweaks: Air Ride adjustable suspension ([2](https://www.nexusmods.com/overthehill/mods/2)), Cosmetic Stacker ([8](https://www.nexusmods.com/overthehill/mods/8)), the Vehicle Flipper (BepInEx 6 IL2CPP be.788, Windows x64; "does not edit save files") ([26](https://www.nexusmods.com/overthehill/mods/26)).
  - Gameplay: On Foot ([12](https://www.nexusmods.com/overthehill/mods/12)), "Unlimited" 16-player co-op for MelonLoader and BepInEx ([9](https://www.nexusmods.com/overthehill/mods/9)).
  - Unlocks: Unlock All ([5](https://www.nexusmods.com/overthehill/mods/5)), which blocks achievements and warns that removing it doesn't remove what it unlocked from the save; an all-trucks unlocked save file ([44](https://www.nexusmods.com/overthehill/mods/44)).
- **No mod found adds a new vehicle.** Every "vehicle" mod tweaks or unlocks stock cars. Nexus mod pages return 403 to automated fetches, so this comes from search snippets, not the pages themselves.
- **Save tools:** [over-the-hill-save-patcher](https://github.com/watuqator-art/over-the-hill-save-patcher) (demo build, Python GUI).
  - Reads `Saves/<profile>.json` as plain JSON with no checksum, compression or encryption, and writes it back with `indent=1`.
  - Patches `Profile.Inventory.Items` (`InventoryItem` for money and tools, `VehicleItem` for cars, `VehicleSpecificItem` with `VehicleStates` for cosmetics) and `VirtualItems` (`PointOfInterestData`).
  - Makes a timestamped backup before every apply, and says to close the game first and turn Steam Cloud off.
  - Item IDs are baked into its `data.json`.
- **Where we differ:**
  - We add vehicles: new `CarInfo` items cloned from a stock donor at runtime, reshaped and re-meshed from OBJ, with no asset bundles.
  - We run on BepInEx 6 IL2CPP (be.789, linux-x64), while most Nexus mods target MelonLoader on Windows.
  - We have hard-won crash constraints: no class injection, patch only from the `GameStateManager.Transition` entry hook, Load touches no IL2CPP type, and `DobbyNearPages`.

## Current state

Data flow today:

1. **Game data → donor meshes.** `export_car_mesh.py <bundle> Car_<Donor>` writes `extracted/<donor>/*.obj` from the player's own install (`export_game_data.sh` runs it and the other exporters). `hierarchy.py` and `cars_summary.py` give node paths, axle Z and car facts, kept by hand in `docs/engine.md`.
2. **Cab masters → cab OBJs.** `vehicles/{glyptodon,megaloceros}/cab_<name>_master.blend` started from the reference model, imported and decimated, then edited by hand; `cab_roof.py`, `cab_doors.py` and `cab_fixes.py` rewrite them in place. `build_cab_part.sh <master> [--derive]` runs `export_master.py`, which derives far LODs and writes `meshes/<cab>_LOD0-3.obj` beside the master.
3. **Family generator → definition.** `make_glyptodon.py` / `make_megaloceros.py` call `glyptodon_family.write(TRUCK)`, which writes `vehicles/<name>/vehicle.json` (about 190 KB): the runtime fields the plugin reads plus the build-only `ops` per mesh.
4. **Definition → vehicle meshes.** `build_vehicle.py vehicles/<name>/vehicle.json` stretches donor meshes behind `bodyCut`, runs the `ops` (`meshlib.py`, 787 lines) and writes the vehicle's `build/*.obj` (gitignored).
5. **Icons.** `make_icons.py` (or the trace and draw scripts, then `rasterize_icons.py`) writes the vehicle's `icon.png`.
6. **Gates, run by hand:** `check_holes.py` on each body LOD, `check_slivers.py`, regression hashes of the built OBJs, updated by hand, `preview_vehicle.sh` renders.
7. **Deploy.** `make deploy` (`werkstatt.py`), with the game closed and `BepInEx/werkstatt.lock` held, compiles the plugin and copies the DLL and, from every vehicle folder, its manifest, built OBJs and icon into `BepInEx/VehicleMods/`, outside `plugins/`; the only DLL in `BepInEx/plugins/` is Die Kollektion's loader, `DieKollektion.Loader.dll`, which starts the plugin at each launch once it fits the game (`docs/engine.md`, BepInEx).
8. **Runtime.** The entry hook runs `Catalog.Register` → `DerivedVehicles.Register`: for each JSON, clone the donor `CarInfo`, set ItemId and collider bounds, localise the name and description into all 16 locales (key 9e18 + itemId*2), set the icon, `Catalog.Add` (refuses an ItemId owned by another item). At spawn, the prefab-address redirect and the `VehicleBase.Spawned` prefix reshape and re-mesh. A `"patch": true` definition modifies the stock donor itself (`vehicles/mammoth/vehicle.json`).
9. **Save.** `add_vehicle_to_save.py <save> <ItemId>…` appends `VehicleItem` entries with a hard-coded `ToolsetIDs [2317836723]`, backs up to `Player1.json.pre-mod-<time>`, has no remove or restore, and doesn't check that the game is closed.

Save structure, from reading ours:
- `Header{Version, LastPlayed}`
- `Profile{Name, CompletedTutorialStepIds, HasSeenIntro, Inventory{Items[], VirtualItems[]}, LastArea, EquippedModLiveries, ShowLocalLiveryMods, Music*, MechanicSeenDreams}`
- `Items` entries are `{"Type": "<Class>, Assembly-CSharp", "Data": {...}}`: `VehicleItem` (ItemId, Count, MetersTravelled, ToolsetIDs), `VehicleSpecificItem` (ItemId, VehicleStates[{VehicleItemId, Count}]), `InventoryItem` (ItemId, Count).
- `VirtualItems` holds `PointOfInterestData`, `AreaItem` and `ObjectiveData`.

What this design fixes: sources mixed with outputs (each `vehicle.json` is generated, the build input and the runtime file at once); a manual build order; advisory gates; an all-or-nothing deploy with no uninstall; a plugin that trusts its files; add-only save editing; donor facts kept in prose; shipped meshes that contain game geometry; Linux-only tools.

## Architecture

**Names (author, 2026-10-19):** the mod players install is **Die Kollektion**; the authoring toolkit (the Blender add-on, the vehicle templates and the CLI's authoring commands) is **Die Kollektion Werkstatt**.

```
Kollektion.Core      net6.0 library, no BepInEx or IL2CPP references
  ├── Plugin         BepInEx 6 IL2CPP plugin: hooks, CarInfo cloning, spawn reshape, categories
  ├── kollektion     self-contained single file per OS (linux-x64, win-x64): the CLI, and with no arguments the hub
  │                  (Avalonia), whose every action runs a CLI command
Blender add-on       Python inside Blender, any OS: import an authoring scene, export an item directory
Internal tools       our Python (Glyptodon-family generator, cab scripts, gates, previews); never shipped
```

- **Core** holds everything both sides must agree on:
  - the pack format and definition schema (strict JSON with `notes` fields for comments, see Manifests; the plugin already parses with `JsonDocument`. Historical note: an earlier draft allowed comments via `JsonDocumentOptions { CommentHandling = Skip, AllowTrailingCommas = true }`);
  - OBJ reading and writing (today's `ObjMesh.cs`, with bone weights);
  - the mesh operations, ported from `meshlib.py`: stretch, stretchPieces, removeRegion, removePieces, movePieces, relocatePiece, insertPart, paint, addBoxes, portalAxle, coilSprings, widenPieces;
  - the donor reader: donor meshes and prefab facts read from the player's Addressables bundles with a managed bundle reader (AssetsTools.NET or similar, pure managed, no IL2CPP), so it is safe from the plugin's background thread. The loaded prefab is no alternative: its meshes aren't CPU-readable (Research findings, "Reading donor meshes at run time");
  - save reading and editing; ItemId issuing; per-OS paths (Steam library via `libraryfolders.vdf`, game folder, save folder, game process name).
- **Plugin** keeps today's invariants: no class injection; all patches from the `GameStateManager.Transition` entry hook; Load touches no IL2CPP type; `DobbyNearPages` is Linux-only (`/proc/self/maps`, `libdobby.so`) and must become a logged no-op elsewhere (Windows).
- **`kollektion`** (CLI and hub) is built with `dotnet publish -r <rid> --self-contained -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:InvariantGlobalization=true` for `linux-x64` and `win-x64` (SDK 10.0; Core and the plugin target net6.0, `kollektion` can target a newer framework). `IncludeNativeLibrariesForSelfExtract` folds Avalonia's SkiaSharp and HarfBuzzSharp native libraries into the one file; `InvariantGlobalization` drops .NET's need for ICU on Linux (the hub shows no culture-specific formats). The Linux exe still uses the desktop's X11 and fontconfig libraries, as any GUI does. It needs no game files, so CI will build it: each RID on its own runner (ubuntu, windows-latest) in `checks.yml`, uploaded as a workflow artifact, and the release will pack the artifact those checks tested, never a rebuild (Distribution).
- **Blender add-on**: Blender's scripting is Python on every OS, so authoring stays Python. It never touches the save or the game folder.
- **Internal tools** keep building our own trucks. As the operations move into Core, `build_vehicle.py`'s role shrinks to emitting operation lists, and `meshlib.py` retires once Core reproduces its outputs.

## Items and the two pipelines

An **item** is one thing a pack adds or changes. Every item has a directory and an `vehicle.json`.

**Vehicle item** (new vehicle):
```jsonc
{
  "schema": 1,
  "kind": "based",
  "codename": "Megaloceros",
  "itemId": 3000000004,            // ours keep their IDs; new items get a hashed ID (see ItemIds)
  "names": {"en": {"name": "Das Megaloceros", "description": "..."}},   // in-game; other locales fall back to en
  "listing": {                      // Die Kollektion's catalogue only; never written into the game
    "family": "Glyptodon", "variant": "crew cab",
    "real": {"make": "...", "model": "...", "series": "...", "variant": "...", "years": "...",
             "basis": "styled on the two-door; no factory crew cab existed, wheelbase from the long crew-cab drawing",
             "description": "..."}   // factual description of the real vehicle for the catalogue; no personal stories
  },
  "base": {"car": "Mammoth", "gameBuild": "...", "hash": "...", "stock": {...}},   // see below
  "chassis": {
    "wheelbase": 3.70, "track": 1.86, "maxSteerAngle": 37.8,
    "tyre": {"radius": 0.545, "width": 0.352},          // 14.5R20
    "suspension": {"travel": 0.40, "anchor": 0.725, "springRate": 18300, "damperRate": 4500,
                   "preloadDistance": 0.10, "bumpTravelOffset": 0.03}
  },
  "bodyCut": [...],
  "meshes": {                       // donor node path -> how to build it
    "Parts/Mammoth/Mammoth_body_LOD0": {"from": "donor", "ops": "ops/body_LOD0.json", "add": ["meshes/cab_LOD0.obj"]},
    "Collider/Base": {"from": "meshes/collider_base.obj"}
  },
  "transforms": [...], "spare": {...},
  "icon": "icon.png"
}
```

**A mod is the difference from its base (author, 2026-10-19).** Every item built on a game vehicle points at that vehicle and carries only what differs. The two kinds share one field:
```jsonc
"base": {"car": "Mammoth", "gameBuild": "<Steam build id>", "hash": "<hash of the extracted base>",
         "stock": {"wheelbase": 2.53, "track": 1.80, "suspension": {"springRate": "<stock value>", "...": "..."}}}
```
- A **patch** changes its base in place; a `based` vehicle clones its base into a new item. Both are "base plus differences": operations on base meshes, replaced or added meshes, transform overrides, chassis and suspension values, upgrade changes, textures. Anything not mentioned is the base's, so a game update that changes the base flows through.
- `hash` is taken over the extracted base data the item was authored against, and `stock` (author, 2026-10-20) is a snapshot of the base's chassis and suspension values at that time, the same numbers the stats table shows as "stock when authored". When the player's game differs (`gameBuild` or `hash`), the plugin rebuilds the item against the new base and runs Core's round-trip check (The hub, Verify): a changed stock value is a warning naming the field, old and new; an operation whose selection no longer matches, or a missing node path, fails that item with a message naming the part, rather than producing a broken mesh.
- The Blender add-on writes exactly this: it diffs the edited scene against the extracted base (`baseline.json`) and exports only the changes.
- `base` replaces today's `donor` field, in patches as in vehicles.
- **What each result was measured against (author, 2026-10-20).** A pass means nothing without the game it passed on, so every result a pack carries names that game. The manifest records, per item, `checks`: `{"gates": {"gameBuild", "date", "result"}, "verify": {…}, "played": {…}}`. `gates` is `check`'s run at `pack` time, `verify` the last round trip, and `played` the author's own last in-game status (`status.json`) when there is one. `builtAgainst` is the build the pack was made on, and `base.gameBuild` per item is the build its stock snapshot came from; Refresh moves all of them forward together. The game build is Steam's build id (`buildid` in the app's `appmanifest_<appid>.acf`), shown beside the game's own version string where the game exposes one **[research]**. Import, the hub's item list, `kollektion info` and the catalogue show these beside the player's own build, e.g. "made on 26047935, gates and Verify passed on 26047935, played on 26047935; your game is 26112040, so Verify runs now", so a player sees how fresh a pack is before installing it.

**Three kinds, declared in the manifest (author, 2026-10-19).** Each vehicle is one portable folder whose manifest (`vehicle.json`) carries `"kind"`. On the CLI and in the hub, `new variant` makes a `based` item ("Variant of a stock car"), `new patch` a `patch` ("Stock car mod") and `new vehicle` a `novel` one ("Unique vehicle"); elsewhere in this note "vehicle" means any item that adds a car, `based` or `novel`:

| Kind | What it is | What ships | In the game |
|---|---|---|---|
| `novel` | A new vehicle with everything its own: meshes, colliders, textures, icon. Built on a template type (bonneted body, bonneted pickup, flat-front body, flat-front bed truck) | Everything; the author holds the rights to distribute it | A new item, in any group |
| `based` | A new vehicle assembled from a shipped vehicle: the pipeline extracts the base on the player's machine and applies the differences, producing a local-only vehicle that behaves exactly like a novel one | Only the differences and own parts | A new item, in any group (a new category included) |
| `patch` | Changes to a shipped vehicle, updated in place | Only the differences and own parts | The stock car, changed; no new item, no save entries |

`based` and `patch` carry the `base` block. A novel vehicle still needs a stock prefab for physics and the wheel rig, which every stock car shares, so the plugin borrows its template type's donor as a rig only, with none of its geometry or textures, and nothing is extracted. Glyptodon, Megaloceros, Mastodon and Megatherium are `based` on the Mammoth today; the Mammoth changes are a `patch`; the example vehicle is `novel`.

**What counts as novel (author, 2026-10-19).** A vehicle is `novel` when everything it ships is its own and it reuses from the game only what every vehicle needs: the vehicle object definition (prefab, physics, wheel rig, lights and points) and the wheels and tyres, referenced live from the running game by node (as the spare-wheel clone already does), never extracted or edited. Any extracted game mesh that is edited and shipped as differences (a stretched body, portal-axle operations on the stock axle, a re-used bed) makes it `based`. `kollektion check` decides it from provenance: each built mesh records which faces come from own OBJs and which from extracted base meshes, and a vehicle declared `novel` fails if any extracted face survives.
- The square-cab trucks (Glyptodon, Megaloceros) are novel by design: own cab, frame, bed and undercarriage. Their builds still start from three Mammoth sources, so their manifests say `based` until those are replaced: the body mesh (most pieces removed, some kept and moved, stretched or widened), the skinned axles (portal and coil-spring operations on the stock axle) and the colliders (stretched and widened). Replacing them means own skinned axles weighted to the shared rig's bones, own colliders, and a body built only from own parts.
- The round-cab trucks (Mastodon, Megatherium) are the Mammoth body reshaped and stay `based`. The Mastodon also takes its single cab and front from the mechanic's truck, a scene prop (see What ships), so its `base` names two sources.

**Parts nest (author, 2026-10-19).** A vehicle manifest builds the vehicle as a tree of parts. Each part names a source, where it attaches, what is done to it, and its own child parts; moving a part moves everything under it. Example: the Megaloceros with the mechanic's camper body as a bed option.
```jsonc
"parts": [
  {"id": "frame", "source": {"family": "glyptodon", "generate": "frame"}, "attach": "root",
   "points": {"bed.mount": [0, 1.225, -0.10]},
   "parts": [
     {"id": "cab", "source": {"own": "meshes/cab_megaloceros_LOD{0..3}.obj"}, "attach": "root"},
     {"id": "bed", "source": {"family": "glyptodon", "generate": "bed"}, "attach": "bed.mount",
      "points": {"bed.floor": [0, 0, -1.40]},
      "parts": [
        {"id": "camper", "slot": "Bed", "option": "camper",             // an upgrade option, shown when fitted
         "source": {"prop": {"bundle": "r1_canada", "path": "<scene path of the camper body>", "lods": 4}},
         "transform": {"scale": 100, "offset": [0, 0, 0]}, "attach": "bed.floor",
         "ops": [{"op": "fitToBed"}], "hides": ["roof.hatch"]}       // the camper selects the plain roof
      ]}
   ]}
]
```
- **Sources:** `own` (OBJs in the vehicle folder), `family` (generated by the family code), `vehicle` (a part of an extracted game vehicle, by node path), `prop` (an extracted prop). Each part gets LODs, material class or own textures, and operations.
- **Points:** a part may declare named attach points relative to itself; children attach to their parent's points, and the vehicle's attach points (hubs, winch, lights, slot anchors) are points too, so the attach-point check sees the whole tree.
- **Upgrade options:** a part with `slot` and `option` becomes an option in that upgrade slot instead of always-on geometry; `hides` lists parts it switches off when fitted (the camper hides the roof hatch).
- **Kind per part:** provenance is tracked per part. A vehicle is `novel` when every always-on part is its own; an optional part from an extracted source (the camper) makes only that option `based`. Its geometry is built on the player's machine like any based part, and a player without the source sees the option missing with a log line, not a broken vehicle.

**The main manifest composes the pack (author, 2026-10-19).** Vehicle folders stay portable: a vehicle manifest says what the vehicle is, never where it goes. The pack's main manifest (`manifest.json` at the pack root; see Manifests) defines everything loaded into the game: the pack's id, version and author; its groups (the merchant categories: id, names, sort position, base category to clone); which vehicle and patch folders it includes and which group each vehicle sits in; and the load order for patches on the same car. Moving a vehicle folder into another pack means adding one line to that pack's main manifest. A vehicle no main manifest places in a group falls back to its base or template donor's category.

**Tweaking a stock vehicle is the main path (author):** most people only want to change an existing car, so that path is the shortest. `kollektion new patch <Car>` writes an item with the `base` pointer and an empty difference, listing every chassis and suspension value with the base's current number as a comment. Changing a number and running `kollektion build && kollektion install` is the whole job, with no Blender. Geometry and upgrade changes add Blender on top of the same item.

**Names: fictional in the game, real in the catalogue (author, 2026-10-19).** Nothing real reaches Over the Hill: in-game names, descriptions, category names, icons, liveries and textures stay fictional, and so do file, part and tool names. Die Kollektion itself always presents the real data: `listing.real` (make, model, series, variant, years, `basis` saying how faithful the item is, and `description`, a factual description of the real vehicle; no personal stories) feeds the README catalogue, `kollektion list`/`info`, `manifest.json` and the Nexus page text. `kollektion check` fails an item whose in-game strings contain any word of its `listing.real` make or model, or of a fixed list of manufacturer and model names. Showing the real name in the game is the player's choice, never the pack's: `kollektion names real|fictional [item…]` writes a local override file (`<mygames>/DieKollektion/names.json`) that the plugin applies over the pack's in-game names, built from `listing.real`. Packs never ship it, and the check doesn't apply to it.

**Patch item** (existing vehicle): the same blocks, with `"kind": "patch"` and the `base` block, and no codename, itemId, names or category. Mesh, transform and chassis changes never get an ItemId or touch the save, so removing them returns the car to stock. Upgrade changes, cheapest first:
1. Full rotation and scale on transforms (today: position and yaw only).
2. Withdraw an option for one car: the car gets its own copy of its upgrade list (derived trucks share the donor's today).
3. Conditional visibility: a node shown or hidden by what else is mounted (the hatch versus the AC unit or camper).
4. New options: a new upgrade item with its own ItemId, which the save then holds, so it falls under the same lifecycle rules as a vehicle item.

The upgrade model: an upgrade node (`VehicleUpgradeObject`, all off in the prefab) names one item (`vehiclePartReference`) and shows when that item is mounted. The slot is the item's `CosmeticType` (the Mammoth uses 11: FrontSection, RearSection, FrontBumper, RearBumper, Roof, RoofLights, Bed, Fenders, SideSection, SideStep, Antenna). One item can drive several nodes, and `LinkedParts` pulls in other items (antenna toppers show the base). Each car offers its own `UpgradesLists` (209 entries on the Mammoth). The mounted state is a 256-bit set, inferred to index that list, which would leave room for about 40-55 new options per car **[test or disassembly]**. Item catalogue and cosmetic meshes are shared across cars; placement (full TRS, often non-uniform scale) is per car.

**Groups** (the game's vehicle categories), defined in the main manifest: an id, an asset name and names in all locales.
- A category is a `VehicleControllerSetup` asset that `CarInfo.carCategorySetup` points at. The four stock ones are `CarCategory_01_Trail` .. `04_Expedition`, each with a `CategoryName` (Content table string), a `HapticCategory` enum and a physics template (mass, steering, gearbox, engine tiers, tyre, suspension). No runtime reader of the physics block was found.
- The merchant's `InitializeSelectVehicleScreen` groups every catalog vehicle by its category object, sorts the categories by asset name (ordinal), and makes one section per category, with no cap. A null category throws there.
- The plugin clones a base category (default: the donor's) with `Object.Instantiate`, unedited apart from its name and `CategoryName`, marks it `DontUnloadUnusedAsset`, and points each item's `CarInfo` at it. The asset name sets the order, so it follows `CarCategory_NN_<Name>`; ours is `CarCategory_05_DieKollektion`. Items naming the same category share one instance. An unresolvable category falls back to the donor's.
- Stock categories have no filter buttons in the merchant; the filter buttons belong to the mod.io livery browser, which lists only cars with mod.io tags.

**Mesh sources.** A mesh is built from one of:
- `from: "donor"` plus `ops`: the donor's own mesh, read from the player's install, then edited. This is how donor geometry reaches the game without shipping it.
- `from: "<file>.obj"`: the item's own geometry (cabs, boxes, frames, beds we modelled).
- both, merged: `add` lists own OBJs appended after the donor's ops.

**Game assets: help, don't police (author, 2026-10-20).** The tools help authors keep copies of game assets out of what they share; they warn and never block. `check`, `build`, `pack` and Import compare each own OBJ with the donor meshes (Core compares vertex sets and flags a high match) and each texture with the extracted maps (Textures), and print a warning naming the file and what it matches, then carry on. The usual case is an accidental copy the pack doesn't need, so the warning says why it isn't needed (every player's game provides that part) and offers the fix: replace the copy with a reference to the stock part (`from: "donor"`, or the base block for a whole car), which also makes the pack smaller. The warning names the fix's command, `kollektion check <pack>/<item> --fix [<file>…]`, which rewrites the workspace item (every flagged copy, or the files named), and the hub's Fix button beside the warning runs it; nothing changes unless the author chooses it. It is distinct from `doctor --fix`, which repairs the install. The Blender export already writes only what differs from the extracted base (`baseline.json`), so untouched stock parts never leave Blender; the warning mostly catches files added by hand. Die Kollektion's own pack is held to the rule by its release gate: today `make pack` (`tools/pack.py`) refuses any file byte-identical to one in `extracted/`; once `kollektion pack` replaces it, our release runs `kollektion pack --strict`, which turns every warning into a failure, so the rule lives once in Core and binds only packs built with that flag.

**Families.** The Glyptodon-family generator (`tools/glyptodon_family.py`) stays Python on our side. It writes the item directory: `vehicle.json`, the operation lists and our own OBJs. Families are an authoring convenience; the runtime sees only items.

## Textures (author, 2026-10-19)

A vehicle pack can carry its own texture maps, so our geometry gets real UV-mapped detail (ribs, grilles, decals, wear) instead of flat atlas points, and nothing in a pack is cut from the donor's atlas.
- **Source is SVG (author):** each map is drawn as an SVG over the item's UV layout (Blender exports the UV layout as SVG), one SVG per map or one layer per map. `kollektion build` renders it to the bitmap; the plugin never renders SVG. The CLI needs an SVG rasteriser on both OSes (e.g. Svg.Skia with SkiaSharp's linux-x64 and win-x64 native assets) so maps and icons render the same way; today's icons use `rsvg-convert` (`tools/rasterize_icons.py`), which Windows lacks **[decide at implementation]**.
- **Editable in any SVG editor (author):** the point of SVG is that anyone with Inkscape, Illustrator or similar can open a map and recolour it, add gradients, or paint detail. So the file is laid out for people: named layers per map channel (`skin`, `masks/paint`, `masks/glass`, `ao`), the UV layout as a locked reference layer that isn't rendered, colours as named swatches, text converted to paths. The renderer must support what editors produce: linear and radial gradients, opacity, clipping and masks, and Gaussian blur; anything outside that subset fails the build with a message instead of rendering differently. `kollektion texture render <item>` re-renders after an edit, so a player can restyle an installed pack locally.
- **The maps**: every car part uses `Shader Graphs/CarMainShader`. The Mammoth body is one material with four 2048² DXT1 maps: `skin` (the livery, `_Livery_Texture`), `masks` (blue paint 89%, green glass 5%, red lenses 1%; alpha unused), `AO` and `lights`; two damage textures are shared by all cars. There are no separate glass or lamp materials. Every car texture is flagged sRGB, masks and AO included, so ours are created sRGB too. An item draws the same four maps.
- **In the pack:** the SVG source, the rendered PNG (for preview and diffs), and a runtime file the build encodes to BC1 (BC3 where alpha is used) with mipmaps, about 2.7 MB per 2048² map against 21 MB as RGBA. The plugin loads it on the main thread with `LoadRawTextureData`.
- **Material:** the item gets its own copy of the donor's material with its four maps and `_IsSwitchable` set to 0, so liveries leave it alone; the plugin removes the renderer from the game's `PropertyBlockSetter` around the swap and adds it back, so weather, damage and lights keep working. Meshes name their material: the item's own, or the donor's atlas (flat colour points, as our cabs use today). An item can mix both.
- **Liveries:** a livery is a per-car asset pointing at a skin texture, applied by `PropertyBlockSetter.SetLiveryTexture` as a property-block override of `_Livery_Texture` on every renderer whose material had `_IsSwitchable` at spawn. For an item with its own UVs, a donor skin would land on the wrong layout, so the item ships its own livery skins (also SVG-sourced), and a prefix on `SetLiveryTexture` maps the donor livery chosen to the item's matching skin, falling back to its default. Player-made liveries (LocalLiveries PNGs, matched by car name) may already work for our clones, whose `CarInfo.name` is the codename **[test]**.
- **[test]** A runtime material copy renders like the donor's; weather and lights survive the renderer swap; which `lights` channel drives which lamp; multiplayer livery sync; memory and load time.
- **Authoring:** the Blender template carries the UV-layout SVG per map at the donor's resolution and a material preview of the rendered maps that mimics the mask behaviour. Textures are our own work, CC BY-SA in our packs.
- **Size:** keep to the donor's resolution per map unless a reason is shown; textures dominate pack size.
- **Own textures only (author, 2026-10-20).** A texture the author painted ships, including one painted on a stock car's UV layout (the official livery guide provides the UV templates): it is their texture. A texture made by editing the game's own skin is a game asset. A texture identical to an extracted game map, or a near match by perceptual hash, is a warning (Game assets: help, don't police): `build`, `pack` and Import name the texture and the game map it matches or resembles, and carry on. A livery painted on the stock UV layout can look alike without being a copy.

## What ships (author, 2026-10-19)

Die Kollektion's first release:

| Kind | Item | Built from |
|---|---|---|
| Patch | Das Mammoth: coil springs (with the portal axles), side exhaust, suspension parameters (with the steering lock); each its own item, added and removed independently | operations on the player's Mammoth |
| Patch | Canary: one golf bag with clubs, strapped to the roof of the first vehicle a new player drives | our own geometry and SVG map |
| Patch | Patch template: an empty, commented patch item to fill in | nothing |
| Vehicle (`based`) | The Mammoth-family pair, Das Mastodon and Das Megatherium | the player's Mammoth, and for the Mastodon the mechanic's truck cab (a prop), extracted locally, plus operations |
| Vehicle (`based` today, `novel` by design) | The Glyptodon-family pair, Das Glyptodon and Das Megaloceros | our own cabs and parts, plus the Mammoth body pieces, axles and colliders extracted locally until they are replaced |
| Template (`novel`) | The example vehicle (also the integration test) | our own geometry on its template type's rig |
| Category | Die Kollektion | a clone of the donor's category |

**Nothing extracted from the game ships.** The Mastodon and Megatherium are mostly Mammoth and mechanic's-truck geometry, so their packs carry only operations and our own parts. **The extractor** (Core's donor reader) pulls the parts out of the player's own install: the plugin runs it on first load to fill its cache, and Werkstatt exposes it for anyone who wants to mod their own thing:
- `kollektion extract --list` enumerates every vehicle in the player's install: catalogued cars, CatalogExcluded ones (Baguette, Grizzly), mesh-only leftovers (`BullV1`, `DingDing_SUV_CosmeticParts`) and scene vehicles (the mechanic's truck), with template type, category, dimensions and slot counts.
- `kollektion extract <Car> <dir>` writes the car as an item directory: body LODs, colliders, axles with bone weights, wheels, every upgrade option, its four texture maps as PNG, attach points and node facts. This is what the Blender add-on imports.
- `kollektion extract <Car> --pack <file>.kpack` (or `--all`) writes a pack from the game: a stock car as a ready-made patch item that changes nothing, to copy and edit.
- **Vehicles and props.** A source is either a **vehicle** (a car prefab: body, colliders, axles, wheels, lights, points and upgrade slots, with the shared rig) or a **prop** (any mesh in a scene or asset bundle, such as the mechanic's truck in `r1_canada`, a building, a cabin: geometry and its material only, no rig and no attach points). `kollektion extract --props [<bundle>]` lists props by bundle, scene path and size; `kollektion extract <prop> <dir>` writes its meshes at their scene scale. The Mastodon uses both: the Mammoth (vehicle) and the mechanic's truck cab (prop, scale 100, offset (0, -0.071, 0.086) onto the Mammoth).
- **`base` can list several sources,** each with `type` (`vehicle` or `prop`), its asset path and bundle, a transform onto the vehicle (scale, offset, rotation) and which pieces are used. Exactly one source is the rig: a vehicle, or for a vehicle built only from props, the template type's donor.
- **Attach-point validation.** Props bring no attach points, so a vehicle built from them gets its points from the rig source or the author, and `kollektion check` validates the result against the template type: wheel hubs on the wheel colliders and inside the wheel arches of the geometry, centre of mass inside the colliders, colliders enclosing the visible body, winch and water points on the body surface at plausible heights, lights on lamp faces, each upgrade-slot anchor on or near the body, nothing floating or buried beyond a tolerance. The same check runs on every kind, so a novel vehicle is held to it too.
- Anything can become a vehicle this way, a cabin from a map included: extract it as a prop, pick a template type for the rig, place the points, and build. It is `based` (it ships as differences against the player's own extracted prop).
- Everything extracted is marked `"origin": "extracted"` in its item and file hashes. Such packs install locally, and `kollektion pack` warns when a pack it builds contains an extracted file, naming each one (Game assets: help, don't police). It reads the cars bundle (vehicle prefabs) and the scene bundles (the mechanic's truck and camper body live in the `r1_canada` scene bundle, at scale 100 with an offset; see `docs/engine.md`), and writes OBJ with bone weights and node facts in the same form `export_car_mesh.py` and `export_named_mesh.py` do today, which it replaces.

## Examples and the integration test (author, 2026-10-19)

A newcomer learns the factory from two worked examples that ship with Werkstatt, and the same two are the integration test.

- **Example vehicle** (`examples/template-vehicle/`): one new vehicle that uses every component once: a template type and donor, attach points, own geometry with LODs and colliders, an SVG texture map, an upgrade slot with an option, a category, names and `listing`. A newcomer builds it with one command and gets a pack that installs and spawns. CI builds and gates it on every push (the build needs donor data, so CI uses a small fixture extracted from the donor and kept out of the public repo, or runs only the steps that don't need it **[decide at implementation]**); a release is preceded by one in-game spawn of it, run by the author.
- **Canary patch** (`examples/first-patch/`): a trivial patch on the vehicle a new player drives first (which car that is: **[research]**): one golf bag with clubs strapped to the roof, own geometry at the roof attach point with its own SVG map. No ItemId, no save change; installing shows the bag, uninstalling removes it.
- **Our Mammoth patch becomes separate patch items** that install and uninstall independently: coil springs with the portal axles, the side-exit exhaust, and the suspension parameters with the steering lock. Each is its own `vehicle.json` in Die Kollektion's pack, and `kollektion install/uninstall <pack>/<item>` toggles one.

**Patch composition.** Several patches may target one car. Each patch item declares what it touches (mesh nodes, transforms, chassis fields). Operation lists on the same donor mesh compose in install order; a whole-mesh replacement or two values for the same chassis field conflict, and `kollektion install` refuses the second with both names unless the author sets an order. Removing a patch rebuilds the car from stock plus the remaining patches, so removal never leaves residue. Later, a patch could become an in-game upgrade option (coil springs as a garage choice), which gives it an ItemId and puts it under the save rules.

## Contact sheets (author, 2026-10-19)

A contact sheet shows a build at a glance, for human review, for AI evaluation loops (an agent reads the sheet to judge a build and decide the next change), and for the pack's page. **Built:** `tools/contact_sheet.py` is the prototype of `kollektion contact`. It writes `vehicles/<name>/contact/contact.json` and renders the vehicle folder's `README.md` from it, so GitHub shows the sheet when the folder is opened, with `iso.png`, `rig.png` and `gaps.png` beside the JSON. In a pack it travels with the vehicle.
- **Views:** a simple isometric layout on a fixed grid, the same angles for every vehicle: one isometric render per corner (front-left, front-right, rear-left, rear-right) at LOD0, and the same four corners again as a rig view: the body ghosted, with the colliders, wheel colliders, attach points (hubs, centre of mass, winch and water points, lights, exhaust, spare, upgrade-slot pivots) and part boundaries drawn and labelled. Upgrade options, liveries and LOD strips are left out until there's a reason.
- **Analysis:** the mesh checks drawn and listed: open edges and gaps (`check_holes` on every body LOD: area per gap, location, a highlighted render), slivers, faces culled from behind, triangle counts per LOD, and the attach-point check (each point plotted, failures marked). The stock donor breaks naive rules (its centre of mass sits below its colliders, part of its body lies outside them), so collider coverage and slot pivots are judged against the stock donor, and the centre of mass must lie between the wheels.
- **Facts:** kind and base, dimensions (length, width, height, wheelbase, track, ground clearance), chassis and suspension values, and the listing's family and variant. The real-vehicle data stays in the catalogue.
- **Reproducible:** fixed target, scale, angles and resolution, so two builds' sheets compare image by image; `--diff <a/contact.json> <b/contact.json>` writes a side-by-side comparison for a change review.
- **Data first, Markdown second:** every fact, gate result, point, collider and gap goes into `contact.json` with coordinates, and the Markdown is rendered from it. Every CLI command gets a `--json` output the same way.
- **Towards an editor (an idea, not a plan):** an editor could read the same JSON and show the same views live. It would be a panel inside the Blender add-on: the hub (author, 2026-10-20) is the one standalone app, and it is a launcher of commands, not this editor. Its role is clear either way: **Blender edits geometry; the editor edits everything else and verifies.** It edits the manifest's metadata and attach points (move a point, set a value, assign a group) and acts as the linter for the game: when a file in the vehicle folder is saved (from Blender, a text editor or the editor itself) it reruns the build steps and gates through the CLI's JSON output and shows what changed: gaps, failed points, triangle counts, a contact-sheet diff. The contact sheet is its static snapshot, so building it now fixes the data model an editor would use.
- **Contact sheets ship even when they show game geometry** (a based vehicle, a patch, a stock car extracted into a pack): a sheet is pictures and numbers, like a screenshot, with no mesh data. "Nothing extracted ships" covers meshes and textures, not contact sheets.

## The official livery format

Funselektor's [Official Livery Modding Guide](https://mod.io/g/over-the-hill/r/official-livery-modding-guide) (mod.io game ID 13441) defines the game's only official mod format:
- A livery mod is a zip (mod.io) or a plain folder (local) holding exactly one `manifest.json` and PNGs: `{"liveries": [{"car": "GrandWoodman", "name": "Sunset Racer", "texture": "sunset_racer.png", "icon": "sunset_racer_preview.png"}]}`. `car` and `texture` are required; files are found by filename, recursively. Strict JSON: no comments, no trailing commas; a malformed manifest fails the whole mod, a bad entry is skipped.
- Textures: PNG (or JPG), sRGB, RGBA, power-of-two square, 2048×2048 like the shipped skins; icons 512×512. Painted on the car's UV template; the guide links the templates.
- `car` is the internal name without spaces, case-insensitive (BlastWagon, Boar, Bull, Burro, Tinny, GrandWoodman, Lynx, Woodman, Ding, Marshal, Polyana, Protector, Wombat, Roamer, RustOx, Mammoth, Timberbox, Brick, TrailBurner, Trailrat, Cumbre); the mod.io vehicle tag is the same name with spaces and drives the in-game filter. Untagged mods still work when subscribed directly.
- Local liveries: one subfolder per pack in `~/My Games/over the hill/LocalLiveries/` (Linux native) or `Documents\My Games\over the hill\LocalLiveries\` (Windows). Hidden until "Show local mods"; "Refresh local mods" reloads edited PNGs without a restart. Local liveries are never shared in multiplayer; mod.io liveries are downloaded temporarily by teammates.

What it means for Werkstatt:
- **Our liveries use the official format.** A vehicle's liveries live in `vehicles/<name>/liveries/` as a valid official livery pack (`manifest.json` + PNGs rendered from the SVG sources), with `car` set to the vehicle's codename. Our clones' `CarInfo.name` is the codename, so the game's own loader may list them for our trucks with no plugin help **[test]**; the plugin's `SetLiveryTexture` prefix is then only needed for vehicles with their own UV layout. Players can drop the folder into `LocalLiveries`, and the edit-and-refresh loop works for our trucks too.
- **Based vehicles that keep the donor's UVs** (Mastodon, Megatherium on the Mammoth body) can wear any Mammoth livery, including mod.io ones; the official templates are their UV templates.
- **mod.io stays livery-only for us.** A livery for one of our trucks could be published on mod.io, but without a vehicle tag (Funselektor owns the tag list) it only works when subscribed directly, and only for players who have the truck.
- **Multiplayer:** a teammate without Werkstatt has no Megaloceros; what their game does when ours drives past is untested **[test]**.

## Manifests follow the official pattern, extended (author, 2026-10-19)

Werkstatt's manifests are a superset of the official livery `manifest.json`, so a modder who has made a livery already knows the shape.
- **Strict JSON** everywhere, as the game requires: no `//` comments, no trailing commas. **Comments are data instead:** any object may carry a `"notes"` field, a string or an array of strings (one per line) for longer text, which every loader ignores and `kollektion check` never flags. Templates use it to explain each field, authors to say why a value is what it is, and an editor would show it beside the field. The tweak path's stock values go in the `base` block's `"stock"` object of real fields (Items and the two pipelines).
- **The pack's `manifest.json`** (lowercase, exactly one, at the pack root) holds typed arrays in the official style: `"liveries"` (the official entries, unchanged), plus `"vehicles"`, `"patches"`, `"groups"` and a `"pack"` object (id, version, author, schema). A pack holding only `"liveries"` is a valid official livery mod. Whether the game's own loader accepts our extra keys, so that a Werkstatt pack's liveries also load from `LocalLiveries`, is **[test]**.
- **Official conventions carried over:** `car` is a car's internal name without spaces, case-insensitive (so `"base": {"car": "Mammoth"}`); file fields hold a filename or a relative path; an entry missing a required field is skipped with a log line while the rest load; a malformed manifest fails the whole pack; a duplicate entry is ignored. The plugin and `kollektion check` both report each of these the way the game's loader does.
- **Vehicle folders keep `vehicle.json`**, not `manifest.json`: the game's loader takes the first `manifest.json` it finds when searching recursively, so only the pack root and each vehicle's `liveries/` folder (an official livery pack) carry that name.

## Packs

A pack is a zip with the extension `.kpack`:

```
manifest.json            # the pack manifest: id ("<author>/<pack>"), version, schema, title, author, requires (plugin version range),
                         # builtAgainst (game build), groups, items[] (directory, kind, group, codename/base, itemId, checks), patch order, file hashes
items/<item>/vehicle.json
items/<item>/meshes/*.obj
items/<item>/ops/*.json
items/<item>/icon.png
items/<item>/README.md, contact/contact.json, contact/*.png  # contact sheet (see Contact sheets)
items/<item>/liveries/manifest.json, *.png  # an official livery pack (see The official livery format)
items/<item>/textures/*.svg, *.png  # optional own texture maps: SVG source, rendered PNG (see Textures)
```

- The plugin reads entries in place (`System.IO.Compression.ZipArchive`); nothing is unzipped into the game folder.
- Meshes `kollektion setup` builds from donor plus ops go to a cache, `BepInEx/cache/DieKollektion/<pack>/<hash>/`, keyed by the item's file hashes, the Core version and the game build; Setup builds it first (author, 2026-10-21: nothing reaches the game before Setup). After a game update the plugin finds the cache built for another build and rebuilds it on its background thread before the entry hook, for an install Setup recorded, so that start is slower (a game update just works). Deleting the cache only costs that rebuild.
- One pack can hold many items. Die Kollektion's pack holds four vehicles, the Mammoth patch and the "Die Kollektion" category.

## Install layout and lifecycle

```
<game>/BepInEx/plugins/DieKollektion.Loader.dll  # the only DLL BepInEx loads; starts the plugin once it fits the game
<game>/BepInEx/DieKollektion/            # outside plugins/, so BepInEx never loads it itself
  DieKollektion.dll, Kollektion.Core.dll, <bundle-reader>.dll
  packs/*.kpack                          # installed packs
  installed.json                         # what the CLI installed: packs, versions, ItemIds, hashes, items on or off,
                                         # workspace overrides, the player's keep/take choices from Verify
<game>/BepInEx/cache/DieKollektion/      # built meshes; disposable
<mygames>/DieKollektion/<profile>.json  # mod-owned save entries (the sidecar)
<mygames>/DieKollektion/backups/         # save backups, last 10 per profile; Steam config backups
<mygames>/DieKollektion/status.json     # the plugin's per-item report after each start
<mygames>/DieKollektion/workspace/<pack>/<item>/  # items being edited (see The hub)
<mygames>/DieKollektion/extracted/<donor>/       # `kollektion extract` output for the add-on; never shipped
```

The hub's settings aren't in this layout: they follow its install mode (Packaging of `kollektion` itself).

`<mygames>` is the game's documents folder: `~/My Games/over the hill` on Linux, `Documents\My Games\over the hill` on Windows (confirmed by the official livery guide). Our files sit outside `Saves/`, so Steam Cloud, which syncs the whole `Saves` folder, never carries them, and outside the game folder, so verify and uninstall leave them alone. (`tools/add_vehicle_to_save.py`'s backups, `Player1.json.pre-mod-*`, sit in `Saves/` and are cloud-synced; they move.)

Stable states, from most to least modded:
1. **Pack removed:** its items are gone and the save is valid.
2. **Die Kollektion removed** (delete `plugins/DieKollektion.Loader.dll`, `BepInEx/DieKollektion/` and the cache): the save is valid, and only BepInEx remains.
3. **BepInEx removed** (or its Steam launch option dropped): stock game. BepInEx belongs to the author; the README explains it.

Steam's verify restores the game's own files and leaves extra files and the saves alone (expected; **[test]** once). Nothing here modifies a game file, so verify neither breaks nor uninstalls the mod. On Linux, BepInEx runs only through the launch option `"./run_bepinex.sh" %command%`.

**The save**. The game loads with `StateProfileManagementSystem.Open` → `OverlandSaver.LoadGame` → `ProfileSave.Deserialize`, `ProfileSaveMigration.Migrate`, `DlcManager.EnforceEntitlements` (falling back to `Player1.json.bak`), and saves with `OverlandSaver.SaveGame` → `ProfileSave.Serialize` → `SaveJson`. The first load and first save of a session both happen before our entry hook. Our IDs 3000000001-4 survive load, migration, entitlements and save every session today, though they are registered only later, at the entry hook. A session in which they are never registered hangs the game (`KeyNotFoundException` on 3000000004, seen 2026-10-19; `docs/engine.md`, BepInEx), which is why the loader's can't-start policy closes the game when a save holds them, and why the sidecar keeps them out of the file. That the exception fires after deserialize, when something looks the vehicle up, is inferred from these two facts, not observed. What the menus do when the restored current vehicle is a mod truck is untested **[test]**.

Save fields that name a vehicle: `VehicleItem` (`InUse: true` marks the current vehicle; there is no separate field), `VehicleSpecificItem.VehicleStates` (for example a kayak and its bed rack, or an engine stage, fitted to a mod truck), and `Profile.EquippedModLiveries` (keyed by car name). `LastArea`, area, objective and point-of-interest data, and the Animals and FogOfWar files hold none. `ToolsetIDs` lists the tools the vehicle carries (2317836723 portable winch, 3771754783 portable plank) and the player changes it in-game; a new vehicle gets the current stock vehicle's toolset, else the winch.

**Sidecar (the design).** The file on disk never names a mod ItemId, so states 1-3 always hold a valid save, and reinstalling a pack brings its vehicles back.
- **Strip:** a postfix on `ProfileSave.Serialize` rewrites the JSON text it returns (the pattern our address redirects already use). It removes mod `VehicleItem`s, mod `VehicleStates` (and part entries left empty), mod-defined items and liveries equipped on mod cars, saves them to the sidecar, and moves `InUse` to a stock vehicle if a mod truck was current.
- **Restore:** once per session in the entry hook, after registration, building the entries directly in `PlayerInventoryManager.Instance.Inventory.Items` as loading does (`AddVehicleItem` would try to load an asset our clones lack). The current mod truck becomes current again.
- **Safety:** the sidecar is rewritten only after a successful restore in that session, so a failed session can't empty it.
- **Confidence:** high on the call graph, timing and fields; medium-high on the restore target and the `Serialize` postfix; to confirm with an inventory-count log line and one look at the written file and `.bak` **[test]**.

**Cleanup (fallback and for saves from before the sidecar).** `kollektion save clean` removes the same list from `Player1.json` and `Player1.json.bak`, with the game closed, after a backup. The plugin logs a warning at start for any save entry naming an unregistered ItemId in our ranges.

Either way the save code shares Core's rules: refuse while the game runs, refuse an unknown `Header.Version`, back up to `<mygames>/DieKollektion/backups/` keeping the last 10, write to a temp file and rename, keep the game's formatting (`indent=1`, non-ASCII unescaped).

## ItemIds

- Stock IDs look like hashed 32-bit values (Baguette 2077913603, Grizzly 2940455280).
- Die Kollektion's four keep 3000000001-3000000004: saves already hold them.
- New items get `fnv1a32("<author>/<pack>/<codename>")`, moved out of the stock values and our block on collision, issued once by `kollektion new` and written into `vehicle.json`. After that the ID is the item's identity: renaming the item doesn't change it.
- `Catalog.Add` already refuses an ItemId owned by another item; the plugin logs both claimants and skips the later pack.

## Runtime contract (plugin)

- At Load (no IL2CPP): list `packs/*.kpack`, read each `manifest.json`, check `schema` and `requires` against the plugin, check `builtAgainst` against the running game build (a mismatch is one warning), and build stale cache entries on the background thread.
- At the entry hook: register categories, then items, each in its own try/catch so one bad item never stops the others or the game. Log lines start with `<pack>/<item>` so `grep` finds them.
- Validation before any IL2CPP work for an item: files present, OBJs parse, ItemId free, codename unique, the `base` car (or the template type's donor) in the catalog, category resolvable. Node paths are checked on the first spawn of the donor prefab; a missing node disables that item's reshape with a log line.
- Patch items apply to the stock car's spawns; vehicle items work as derived vehicles do today.

## CLI surface

Every hub form and wizard collects the arguments of one of these commands and runs it, and the hub shows the command it ran (The hub).

Setup and the app:
- `kollektion doctor`: the requirements checker; `--fix` carries out our own fixes, never third-party installs.
- `kollektion setup`: find the game, fetch and install BepInEx, set its two settings (`UnityLogListening`, on Linux `run_bepinex.sh`), install the loader, plugin and pack, set the Linux launch option.
- `kollektion start --modded|--stock`: toggle Doorstop and launch through Steam.
- `kollektion update`: the newest release's loader, plugin and pack; says whether a release exists for the current game build.
- `kollektion config get|set <key> [<value>]`: the settings (the game folder, the Blender path, the editor launchers as `launcher.<type>`); `config test <launcher>` opens a sample file with it.
- `kollektion names real|fictional [item…]`: the local names override.
- `kollektion self install|uninstall|update`: the per-user install of the app itself.

Authoring:
- `kollektion edit <pack>/<item> [--file <path>]`: copy the item into the workspace if it isn't there, then open it in Blender with the add-on, or open one of its files in that file type's editor.
- `kollektion new variant|patch|vehicle …`, the wizard's three kinds: `new variant <Codename> --donor <Car> --name … --category …` (`based`), `new patch <Car>` (`patch`), `new vehicle <Codename> --template <type> --name … --category …` (`novel`). An item directory in the workspace from a template, the stock snapshot taken, ItemId issued. `new category <Name>` makes a group.
- `kollektion stats <item> [--set <field>=<value>…]`: the stats table, the stock car's current value beside each field, range-checked.
- `kollektion verify [<pack>/<item>]`: the round trip against the current game (The hub, Verify).
- `kollektion refresh <pack>/<item>`: rebuild the item's source against the current game, rebase its `base` block, report differences that no longer apply (The hub, Refresh).
- `kollektion preview <pack>/<item>`: the item's contact sheet; later the hub's own render.
- `kollektion extract --list | <Car> <dir> | <Car> --pack <file>`: enumerate the install's vehicles, or extract one as an item directory or a local pack (see What ships). Output contains game assets and stays on the author's machine.
- `kollektion build <pack>/<item>|<dir> [--install]`: run the operations against the local donor, write the cache, run the gates; `<pack>/<item>` names a workspace item, as every per-item command does, and a path works for a folder outside the workspace; `--install` then installs it (the hub's Rebuild).
- `kollektion check [<pack>/<item>|<dir>] [--fix [<file>…]]`: gates only: holes, slivers, triangle budget, node paths, ItemId, codename; the donor-copy check for meshes and textures prints warnings, never failures, and `--fix` swaps each flagged copy for a reference to the stock part (Game assets: help, don't police).
- `kollektion pack <dir> -o <file>.kpack [--strict]`: refuses on a failed gate; donor-copy warnings don't stop it unless `--strict`, which makes every warning a failure (our release runs it).
- `kollektion diff <a.kpack> <b.kpack>`: item and file changes between two pack versions.

Lifecycle (each refuses while the game runs):
- `kollektion install <file|url|github:owner/repo[@tag]>` (the import checks, The hub), `kollektion uninstall <pack>[/<item>] [--workspace]` (runs `save clean` for saves written before the sidecar; `--workspace` also deletes the item's workspace folder), `kollektion enable|disable <pack>/<item>` (a vehicle only once the sidecar exists), `kollektion list`, `kollektion info <pack>[/<item>]` (the real-vehicle listing, and each item's `checks` with their game builds beside the player's), `kollektion status` (packs, cache, save agreement, game running, the last play's `status.json`).
- `kollektion save list|add|remove|clean|backup|restore`.
- `kollektion stock`: uninstall every pack, clean the save, remove the cache, leave the plugin.
- `kollektion remove`: `stock`, then the loader, plugin and `BepInEx/DieKollektion/` too (`--bepinex` removes BepInEx as well and, on Linux, restores the launch option Setup replaced).

Ours only, not shipped: `tools/preview_vehicle.sh`, the cab scripts and `tools/launch_test.sh`, which always asks first.

## Patch authoring in Blender

The add-on imports `kollektion extract` output as a scene laid out like our cab masters (Z up, front toward -Y, `<Part>.LOD<n>`, material classes as atlas points, `two_sided` faces):
- `LOD0`..`LOD3` for the body; `Colliders`; `Axles` (bones as vertex groups); `Wheels`; `Lights`; `Points` (winch, CoM and similar empties);
- `Upgrades/<CosmeticType>/<Option>`, keeping Unity's parent hierarchy under each option;
- an excluded `Library` collection holding the shared cosmetic meshes once, instanced by the options.

Every object carries its game node path as a custom property; option objects also carry the item ID, slot type and linked items. The export writes `baseline.json` beside the .blend, and `kollektion build` diffs the edited scene against it, so the author never marks what changed: an edited donor mesh becomes operations where they fit, else own geometry; a moved node becomes a transform; a deleted option becomes a withdrawal. Wombat and Marshal share the Mammoth's layout and slot groups (Wombat adds Hood and BushCables; neither has Bed), so one exporter covers the roster.

## Blender vehicle template (author, 2026-10-19)

A `.blend` template for a new vehicle, so an author starts from a scene that already has every attach point the plugin and the game use, rather than from node paths in a JSON file. The add-on creates it with `New Kollektion vehicle from donor…`:
- **Attach points as named empties**, each carrying its game node path and role as custom properties: wheel hubs (FL, FR, RL, RR) and axle centres, centre of mass, winch points front and rear, lights (head, position/brake, reverse, indicators, work lamps), spare-wheel mount, exhaust exit, camera and seat points where the donor has them, and one anchor per upgrade slot (Roof, RoofLights, FrontBumper, RearBumper, Bed, SideSection, SideStep, Antenna, Fenders, FrontSection, RearSection, Snorkel).
- **Chassis as editable parameters** on a root empty: wheelbase, track, tyre radius and width, suspension values, steer angle. Moving a hub empty updates wheelbase and track, and the reverse.
- **Collections ready to fill:** `LOD0`..`LOD3`, `Colliders` (box and mesh), `Upgrades/<slot>/<option>`, `Variants` (excluded, for alternatives such as a plain roof).
- **Materials preset** as the donor atlas classes (Paint, Glass, Black, Lamp, Amber, LampLens), so faces need no UVs.
- **A donor ghost:** the donor's body, wheels and upgrade parts, imported locally by the add-on from the player's install into an excluded, unselectable collection for scale and fit. The ghost never saves into anything the add-on exports.
- **Validation in Blender:** a panel that runs the gates (holes, slivers, missing LODs, empties off the donor's node list, in-game names against `listing.real`) before export.

**Template types (author, 2026-10-19).** All 23 stock cars share one skeleton: a body with LOD0-3, `Collider/Top` and `Collider/Base`, four wheels on two solid axles with the same bones (4WD, front steer), four winch points, seven water-depth points (the intake heights matter for snorkels), 20 sound emitters, an exhaust point and the same light layout. Names drift (`BullV1`, `TrailRat`, `Polyana_bodu`, lower-case wheel names; RustOx has split rear wheels and a wider rear track), so the exporter matches by tree position, not by name. Category is a tuning preset (each car's handling matches its category exactly) and doesn't predict the body, so it's a separate template setting. The types differ only in upgrade slots:

| Type | Hood, BushCables | Roof | Bed | Cars | Donor |
|---|---|---|---|---|---|
| Bonneted body | yes | yes | no | 17 (Lynx .. Timberbox) | Wombat (Lynx short, Roamer long) |
| Bonneted pickup | yes | no | 13 bed loads | Burro, Cumbre, BlastWagon | Burro |
| Flat-front body | no | yes | no | Marshal, RustOx | Marshal |
| Flat-front bed truck | no | yes | 7 bed bodies | Mammoth | Mammoth |

Every type has FrontSection, RearSection, both bumpers, RoofLights, Fenders, SideSection, SideStep, Antenna and Snorkel; extra spotlight pairs and reverse lights are optional. Open: what shows the upgrade nodes with no item (the winch on every car, the roll cage on 18, the built-in bullbars on Brick, Grizzly and Marshal); whether an option from one type works on another (a pickup's bed loads on a bed truck); whether every car runs the solid-axle rig at runtime.

The template file in the repo holds only empties, collections, materials and properties (our own work, CC BY-SA); everything from the game comes in locally. Export writes the item directory that `kollektion build` reads.

## Windows

- The CLI and hub cross-compile; the plugin is AnyCPU net6.0 and loads under BepInEx 6 IL2CPP win-x64.
- **Supported only after a volunteer runs it (author, 2026-10-20).** A volunteer collaborator, found among current users, runs the release on their own Windows machine with the game (the checklist below); until then every Windows artifact is marked experimental (its file name, the release notes, the README and the Nexus page). No Windows setup goes on the author's machine unless no volunteer is found (Open questions). CI and Wine don't count: they never run the game. The Vehicle Flipper (be.788, Windows x64) shows BepInEx 6 IL2CPP runs there.
- **Launch policy (author, 2026-10-20).** No Steam launch option on Windows. BepInEx win-x64's Doorstop is `winhttp.dll` (with `doorstop_config.ini`) in the game folder, which Windows loads from the exe's folder on a plain Steam Play; `kollektion setup` installs it, into `C:\Program Files (x86)\Steam\steamapps\common\over the hill\` by default, other libraries from `libraryfolders.vdf`.
  - `kollektion` doesn't wrap the launch. `"…\kollektion.exe" %command%` would work on Windows Steam, but it is rejected: the loader already does the version check, the plugin swap and the can't-start dialog in-process; a wrapper option goes stale when the exe moves, puts our exe on every game start, and draws Defender's attention.
  - Playing stock: BepInEx's own `--doorstop-enabled false` launch option, or the hub's Start stock (Parity).
- **Linux-only pieces the Windows path replaces:**
  - The loader's rebuild after a game update runs the host's .NET SDK inside Steam's pressure-vessel container (`/run/host`, `LD_LIBRARY_PATH`). Windows has no container, and players have no SDK, so there the loader only installs a release's prebuilt plugin; without a fitting one it can't start. The rebuild stays a developer path on Linux.
  - The loader's progress window, errors and notifications use zenity and notify-send. Windows shows the same text in a native dialog (a P/Invoke to `MessageBoxW` hands the game no managed delegate) **[decide at implementation]**.
  - The can't-start path ends with libc's `_exit(0)` so no managed shutdown runs while Unity's threads do. The Windows equivalent is `TerminateProcess` on the current process **[test]**.
  - **Three failures in today's code on Windows** (2026-10-20; the fixes are code, tracked in [#45](https://github.com/aaronsb/die-kollektion/issues/45)):
    - The loader builds the saves folder from `UserProfile` + `My Games` (`plugins/Loader/Loader.cs`), which on Windows is `%USERPROFILE%\My Games`, not `Documents\My Games`. `LoaderCore.SavesHoldTrucks` returns false for a missing folder, so a can't-start with our trucks in the save would run stock and hang: the case the policy exists for.
    - The plugin waits for the boot marker in the Linux `Player.log` path (`Plugin.UnityLogPath`, `$XDG_CONFIG_HOME/unity3d/…`). On Windows the log is in `%USERPROFILE%\AppData\LocalLow\Funselektor\over the hill\`, so the entry thread waits out the 60 s timeout and patches without the marker, against the entry-hook timing rule.
    - `NearBlockPlanner.ReadSelf` reads `/proc/self/maps` unconditionally, so `DobbyNearPages.Install` fails and the plugin installs no hooks: the mod is inactive on Windows. `DobbyNearPages` (`/proc/self/maps`, `libdobby.so`) must become a logged no-op off Linux; whether Windows needs its own guard against Dobby's near pages colliding with coreclr is unknown, since Windows' allocator and layout differ.
  - `tools/bepinex.json` has no sha256 for the win-x64 build yet, so `make bepinex` refuses it; `kollektion setup` needs one recorded first.
- **The prebuilt plugin is matched by interop hash.** Whether the Windows build of a Steam build gives BepInEx the same interop hash as the Linux build is **[test]** on the volunteer's run; if not, a release carries one prebuilt plugin per OS, the Windows one compiled against interop from a Windows install.
- Paths: the documents folder on Windows is `Documents\My Games\over the hill` (official livery guide); the Steam library from `libraryfolders.vdf` on both; the bundles in `StreamingAssets/aa/StandaloneWindows64/` (`tools/export_game_data.sh` already falls back to it).

**Windows testing (author, 2026-10-20).**
- **CI is the Windows check.** GitHub-hosted runners are free for public repos, `windows-latest` included. A `windows-latest` job in `checks.yml` builds and tests the win-x64 `kollektion` natively: paths and `Documents\My Games\over the hill` against a fixture game folder, Steam library discovery (`libraryfolders.vdf`), a setup, install, uninstall and status round trip, `self install|uninstall` (the HKCU PATH, the Start Menu shortcut, the Uninstall entry, the final-delete helper), and the hub's window in a UI test. The parity script, the same CLI commands, runs on both the ubuntu and the windows runners, and their outputs are compared with paths masked. The runner is Windows Server with no GPU and never gets game files, so it can't run the game.
- **Wine, optional and local:** when wine is installed, a make target runs the win-x64 exe under Wine in a scratch `WINEPREFIX` (the same fixtures and parity script), as a fast pre-push check inside `make check`; without wine it is skipped with a notice. CI doesn't install wine.
- **Covered without a Windows player** (Wine and the Windows CI job): the CLI, the hub, paths, self install and uninstall, `doctor`, pack import and its gates, parity, and the loader's and plugin's path choices (the saves folder, `Player.log`), tested offline through `LoaderCore` and a path helper.
- **Left for the volunteer**, the checklist a collaborator call can quote:
  1. BepInEx win-x64 starts through Doorstop (`winhttp.dll`, no launch option), and our loader starts the plugin; the loader finds the saves and the plugin finds `Player.log` (the first two failures above, fixed).
  2. The plugin installs its hooks on the Windows build (`DobbyNearPages` a no-op there, the third failure fixed); the trucks spawn and render.
  3. The memory layout: whether Windows needs a counterpart to `DobbyNearPages`.
  4. The can't-start dialog shows over the game's window.
  5. Whether the Windows build's interop hash equals Linux's: one prebuilt plugin, or one per OS.

## Compatibility

- We patch `GameStateManager.Transition`, `VehicleBase.Spawned`, `VehicleCustomizationController.Spawned`, `LocalVehicleCustomizationController.RefreshMountedUpgrades`, `StateMerchantMenu.RefreshToolsPanels`, the prefab-address getters, and, depending on research, the save path. Categories need no patch.
- Mods touching the same (Air Ride's suspension, Cosmetic Stacker, camera mods reading car bounds) need a joint test.
- BepInEx only for now. Core has no loader references, so a MelonLoader build later rewrites only the hooks.

## Distribution: GitHub first, Nexus mirrors it (author, 2026-10-19)

The mod is always installable straight from GitHub; Nexus is where players find it, and nothing depends on it.
- **GitHub Releases are the source of every artifact.** The plugin compiles against the interop BepInEx generates from the game, so a maintainer with the game builds and publishes each release (`make release`, `tools/release.py build`); CI checks the release's tag, versions and assets. Today `release.py build` compiles the plugin and loader on the maintainer's machine, zips the tracked files and creates the tag itself. For the player tier it will also take `kollektion` from CI: `checks.yml` runs on pull requests and pushes to main, never on tags, so `release.py build` downloads the `kollektion` artifacts from the passing `checks.yml` run on HEAD of main (`gh run download`), and refuses when that run is missing or failed or its artifacts have expired (90 days by default); then it tags. Today's release is `die-kollektion-werkstatt-<ver>.zip` (the tracked files plus the prebuilt plugin, driven by `make`), the pack zip and `SHA256SUMS`; the player-tier release (Players, tinkerers, creators) is:
  - `DieKollektion-<ver>-linux-x64.zip` and `DieKollektion-<ver>-win-x64.zip` (the Windows one experimental, Windows): `kollektion` / `kollektion.exe` at the top, beside the `BepInEx/` folder holding the loader `BepInEx/plugins/DieKollektion.Loader.dll` and `BepInEx/DieKollektion/` (DLLs, our `.kpack`, README), with no BepInEx inside. It also carries `BepInEx/config/BepInEx.cfg` holding only `UnityLogListening = false`, which BepInEx keeps when it writes the rest. Unzipped anywhere, it installs nothing until `kollektion` → Setup does (Players, tinkerers, creators). The two zips differ in the exe, and in the prebuilt plugin if the Windows interop hash differs from Linux's (Windows);
  - **A player zip holds only what a player runs or the game loads (author, 2026-10-21):** the exe, `README.txt` and the licence texts (the GPL for the code, CC BY-SA 4.0 for the art) at the top, all plain text (a `.md` opens as an unfamiliar file on Windows), and the `BepInEx/` payload. No scripts, sources or repository files (`.py`, `.sh`, `.ps1`, `.cs`, `Makefile`, `.github/`, `AGENTS.md`): a player who meets a `.py` asks whether they need Python, double-clicks it and gets Notepad. `release.py build` refuses a player zip holding one. The source, the Makefile and the Python tools reach tinkerers and contributors through the repository and its source zip;
  - `die-kollektion-<ver>.kpack` on its own, for importing with the hub or CLI;
  - `SHA256SUMS`.
- **Nexus** gets the same zips, uploaded by `.github/workflows/nexus.yml` once the GitHub release's checks pass, with the page linking to GitHub. No Vortex-only install path and no Nexus-only files.
- **winget, later** (author, 2026-10-20), after the first Windows release the volunteer has tested: a winget-pkgs manifest for `kollektion` with `InstallerType: zip`, `NestedInstallerType: portable` and `NestedInstallerFiles: kollektion.exe` (with `PortableCommandAlias: kollektion`), pointing at the release's `DieKollektion-<ver>-win-x64.zip`: winget extracts the whole zip, payload included, into its per-user package folder, puts `kollektion` on PATH with no UAC, and `winget upgrade` updates it. There is no bare-exe artifact. On PATH, `kollektion` is winget's alias in `…\WinGet\Links`, so Core finds the payload beside the exe and tells an installed copy from a portable one by the exe's real folder (`Environment.ProcessPath` resolved with `ResolveLinkTarget(returnFinalTarget: true)`), never the alias's **[test]**. The GitHub release already provides the stable asset URL and `SHA256SUMS` the manifest needs. The first submission is by hand, a pull request to microsoft/winget-pkgs that moderators review, with the author's go-ahead; after that `release.yml` opens the update pull request on each tag (`wingetcreate update --submit` or the winget-releaser action, the token in a repo secret), as `nexus.yml` follows the GitHub release. The GitHub zip stays the source of every artifact.
- **The README** in the repo is the install guide, the same steps on both OSes (download the zip, run `kollektion`, Setup, Start modded), what Setup changes in the game folder, removing the mod, and Steam Cloud.
- **Third-party packs** publish on their own GitHub releases (or anywhere): `kollektion install <file|url>`, where `github:<owner>/<repo>[@tag]` fetches the release's `.kpack` asset. No central index for now.

What is public: the factory (Core, plugin, CLI, add-on), our pack sources (`vehicle.json`, operations, our own OBJs, icons we drew), our Python tools, and the notes with branding removed. What never is: meshes, textures and icons extracted from the game, reference photos and drawings, and real manufacturer or model names outside the catalogue.

Decided (author, 2026-10-19):
- **A public repository** with a clean history from its first commit.
- **Code** (Core, plugin, CLI, Blender add-on, tools): **GPL-3.0-or-later**. Commercial reuse is allowed only with the complete source under the same licence.
- **Art** (cab models, generated parts, icons, our pack content): **CC BY-SA 4.0**.
- The licence text states that packs are data, not derivative works of the plugin; pack authors license their packs as they choose.

## Migration plan

Each step is reversible and has a check. **The order puts players first (author, 2026-10-21):** players want to download a zip, run one program and play, on Linux or Windows; so one source is built for both, the truck build leaves Python, the player's lifecycle and the hub over it come next, then Windows and a release with a Linux and a Windows zip; the tinkerer and creator tiers follow. It replaces the tier order of 2026-10-20 (the CLI, the hub, the in-game build, Windows, the release), which kept players waiting behind the whole CLI.

Done before this plan was reordered: the public GitHub repo, the release workflow (`make release`, CI on every push, the Nexus upload of the same zip); Die Kollektion's loader (fit check, rebuild after a game update, the can't-start policy; `docs/engine.md`, BepInEx); the pack manifest and its zip (`make pack`); `make check` failing on any failed gate; the Blender add-on's placements (`docs/blender_addon.md`).

1. **Design:** this note. *Check:* done (2026-10-20).
2. **One source, two targets (author, 2026-10-21: the same code, a different build target).** `Kollektion.Core` (`src/Kollektion.Core/`) with the per-OS paths: Steam libraries through `libraryfolders.vdf`, the game folder, the saves folder, `Player.log`. `kollektion status` (`src/kollektion/`) reports them. `make kollektion` publishes it for linux-x64 and win-x64 into `build/kollektion/<rid>/`. `tests/test_kollektion.py` runs the same checks on the Linux build natively, on the Windows build under Wine when wine is installed (`python3 tools/release.py ci`, in a prefix of its own), and on each build natively in CI (`checks.yml`, ubuntu and windows-latest), which keeps each passing build as an artifact. *Check:* a planted path bug, the Windows saves folder without `Documents` (#45's first failure), turns the Wine run red (2026-10-21).
3. **The truck build leaves Python** (the long pole).
   - Golden outputs first: hash every built file (OBJs, the runtime fields of each JSON, icons) into `build/golden.json`. *Check:* a rebuild with today's commands reproduces it.
   - Core reads the donor from the player's bundles with a managed bundle reader (Architecture; Research findings, "Reading donor meshes at run time") and runs the operations ported from `meshlib.py` and `build_vehicle.py`, with OBJ I/O from today's `ObjMesh.cs`: `kollektion extract` and `kollektion build`. Our pack drops donor geometry. *Check:* the output matches golden geometry within float tolerance, on both targets, with no Python installed.
   - **Where the build runs (author, 2026-10-21):** in `kollektion setup` for the first install, with the game closed, as `make all` does today; and in the plugin on its background thread at the first start after a game update, so the update just works (Players, tinkerers, creators). Both run the same Core code into the cache (Packs). *Check:* the Setup build first; then a fixture with the cache keyed to another game build is rebuilt by the plugin's code path offline, and once in game by the author.
4. **The player's lifecycle, and the hub over it.**
   - The install layout moves (Install layout): the loader starts `BepInEx/DieKollektion/DieKollektion.dll` as `installed.json` records it, in place of `BepInEx/VehicleMods/` and `deployed.json`, and takes a fitting prebuilt plugin from the installed release payload, with no Werkstatt folder; the developer rebuild from a checkout stays. *Check:* `tools/loader-plan`'s scenarios pass against the new layout, an old `VehicleMods/` install moves over once, and a folder with no checkout starts the plugin.
   - The plugin reads packs, falling back to the vehicle folders for one release; per-item validation and fail-soft registration; per-item results in `<mygames>/DieKollektion/status.json` after each start. *Check:* the author spawns each truck once, and `status.json` names each as spawned.
   - The win-x64 BepInEx sha256 recorded in `tools/bepinex.json`, which `setup` needs on Windows.
   - `kollektion setup` first as the requirements checks alone, read-only (Players, tinkerers, creators), with `doctor` running the same checks; *check:* each check has a fixture game folder that fails it, on the Linux, Wine and windows-latest runs. Then `kollektion setup | status | update | start | stock | remove` doing the work, refusing while the game runs, taking over `make bepinex`, `deploy`, `undeploy` and `status`; `save clean` for `stock` and `remove`; Setup's BepInEx settings and the Linux launch option written or shown (Parity), and restored by `remove --bepinex`. *Check:* a running-game probe refuses; setup then remove leaves the game folder as before; a `localconfig.vdf` fixture round-trips with only the one value changed.
   - The hub (Avalonia, the same single file) with the lifecycle: Check, Setup, Status, Update, Start, Stock, Remove the mod; self-install. *Check:* each form runs the command it shows; the hub's window opens in the UI test on both runners; `self install` then `self uninstall` leaves no file, registry entry or shortcut behind on either.
   - *Check (the step):* a folder holding only the Linux player zip, pointed at a copy of the game folder and the documents folder (`GAME_DIR`, `MY_GAMES`), sets up and spawns each truck with no Python, make or .NET SDK installed.
5. **The Windows path and the volunteer's run.** Replace the Linux-only pieces (Windows), the three failures in today's code (#45) first, each with a test on the Wine and windows-latest runs; mark the Windows artifacts experimental; rehearse under Proton on the author's machine (Open questions, Fallback); a volunteer collaborator runs the release on their Windows machine. *Check:* the volunteer runs `kollektion` → Setup → Start modded from the release zip and works through the checklist (Windows, "Left for the volunteer"), the interop hash included; spawns a truck, deletes it, and the game runs stock.
6. **Release with both:** the Linux and the Windows player zip (Distribution), the README's install guide for both, the Nexus upload; the experimental mark comes off once step 5's volunteer run passes; winget after that. Today's `die-kollektion-werkstatt-<ver>.zip` becomes `die-kollektion-werkstatt-<ver>-source.zip`, for tinkerers on Linux, and leaves Nexus. *Check:* a clean BepInEx install in a copy of the game folder (not a player's own) loads the pack from the GitHub release zip, on Linux by the author and on Windows by the volunteer; `release.py build` refuses a player zip holding a planted `.py`.
7. **The tinkerer tier.**
   - `kollektion install | uninstall | enable | disable | list` (`disable` for patches only until the sidecar), and the hub's Import, Info, Delete, a patch's Activate / Deactivate, Preview of shipped sheets, Settings with the editor launchers. *Check:* a portable and an installed copy keep separate settings and list the same workspace.
   - The mesh gates ported from `check_holes.py` and `check_slivers.py` plus the triangle budget; gates fail `pack`; `kollektion pack` packages built outputs as a private local pack (`origin: extracted`, not for release). *Check:* the ported gates give `make check`'s results on every built LOD; a planted hole fails; unpacking reproduces golden.
   - The round-trip check in Core (the `base` block's stock snapshot) and, on it, the hub's wizard, Stats, Rebuild, Verify, Refresh and Import of `based` and `patch` packs; the texture check and its Fix (`check --fix`). *Check:* a variant made in the wizard installs and shows in game; a fixture game with one stock value changed gives that one warning; a planted copy of a game texture gives the warning, naming the file and the game map, and `pack` completes; `pack --strict` (our release gate) refuses it.
   - The save: the sidecar, then the restored-current-vehicle **[test]** (Open questions); only after it, the hub's vehicle Deactivate. *Check:* a save round trip (install, drive, deactivate, start, reactivate) on a copy of a real save, the game starting each time.
   - The "Die Kollektion" category. *Check:* the author sees a fifth merchant section holding our four, and every section still navigates.

Alongside, once step 3's `kollektion extract` and `build` exist: **the creator tier.** Edit a vehicle (the workspace copy, Blender opened with the item); each add-on action moves onto its `kollektion` command, "Build and check" first (today `make loop`), and the add-on gains `open_item(path)` and the other pieces The hub lists; then export and the vehicle template, starting with the Mammoth (the upgrade-slot audit is the first use). *Check:* the hub opens a shipped vehicle in Blender from its workspace copy with no checkout, no git and no `make` on PATH; export, import, export again without edits gives an empty patch.

## Open questions

- **[test]** The sidecar's restore when the current vehicle is a mod truck (`InUse` moved to a stock car on save and back on restore): what the menus show in between. An unregistered ItemId in the save hangs the game (The save); one launch with a test save, run by hand, settles the rest.
- **[test]** Steam verify leaves extra files in the game folder.
- **Fallback** if no Windows volunteer is found: a rehearsal of the game's Windows build under Proton (a separate folder from steamcmd, never the author's real install) or in a KVM guest on the author's machine, the one exception to keeping Windows off it. Neither is real Windows (memory layout, the Dobby question), so neither lifts the experimental mark.
- **[decide]** Which donors after the Mammoth for templates and export.
- **[test or disassembly]** For upgrades: whether nodes added in the `VehicleBase.Spawned` prefix register in time; whether the 256-bit mounted state indexes the car's upgrade list; whether the garage enforces one option per slot; how the lights controller finds its lights (decides whether a cloned light works). No disassembler is installed; one logged launch would answer most.
- Research on categories, save, patch export is done (Research findings, below). Categories: one remaining scan for every reader of `carCategorySetup` beyond the merchant, livery browser and haptics.

## Research findings

Offline research from October 2026: UnityPy over the game's bundles, the interop assemblies, and call lists from the game binary. No method bodies were decompiled in full, so call-order details are inferred. The questions an in-game run must settle are marked **[test]** above.

### Vehicle categories

- There is no category type of its own. `CarInfo.carCategorySetup` points at a `VehicleControllerSetup` ScriptableObject, which is both the category label and a physics template. Fields: `CategoryName` (a LocalizedString in the Content table, the same table as car names), `mass`, `winchMaxTension`, `HapticCategory` (a four-value controller-rumble enum), `inertia`, the differentials, `torqueSplitter`, `steering`, `brakes`, `engineTiers` (three `EngineTier` references) and `clutch`.

| Asset | Name | Mass | Max steer | Cars |
|---|---|---|---|---|
| `CarCategory_01_Trail` | Trail | 1600 | 38 | Brick, DingDing, Bull, Tinny, Wombat, Protector, Lynx, Polyana, Trailrat |
| `CarCategory_02_Wagon` | Wagon | 2000 | 33 | Roamer, Woodman, GrandWoodman, Cumbre, TrailBurner |
| `CarCategory_03_Workhorse` | Workhorse | 2800 | 28 | Burro, Boar, Timberbox, RustOx, BlastWagon |
| `CarCategory_04_Expedition` | Expedition | 3200 | 28 | Marshal, Mammoth |

- Baguette and Grizzly ship with a null category. The Expedition asset's tyre and suspension values equal the Mammoth prefab's, value for value: the physics block looks like an authoring template copied into prefabs. No runtime reader of it was found, but not every reader was scanned, so packs clone categories unedited.
- The merchant (`StateMerchantMenu.InitializeSelectVehicleScreen`) takes every catalog vehicle allowed by the demo and DLC filters, owned or not, groups them by category object in a dictionary (a null category throws there), sorts the categories with `string.CompareOrdinal` on the asset name, and fills one section per category, showing `CategoryName` or, if that is empty, the asset name. Section blocks come from a pool that grows on demand.
- Other readers: the controller-haptics adapter copies `HapticCategory` (null-guarded); the mod.io livery browser groups cars by category but lists only cars whose names appear in its mod.io tag lookup. No code names a category asset; categories are identified by object.

### The save

- Load: `StateProfileManagementSystem.Open` → `OverlandSaver.LoadGame` → `ProfileSave.Deserialize`, then `ProfileSaveMigration.Migrate` and `DlcManager.EnforceEntitlements`, falling back to `Player1.json.bak` if the main file fails. Save: `OverlandSaver.SaveGame` → `ProfileSave.Serialize` → `SaveJson`, the only caller of both.
- The first load and the first save of a session happen before the plugin's entry hook. Mod ItemIds pass through load, migration, entitlements and save intact.
- The save folder is the documents folder plus `My Games/over the hill/Saves`, falling back to the game's data folder if that isn't writable. Steam Cloud syncs the whole `Saves` folder.
- `ToolsetIDs` are the tools a vehicle carries: 2317836723 is the portable winch, 3771754783 the portable plank.

### Upgrades and patch authoring

- Car_Mammoth has 196 upgrade nodes, all off in the prefab: 192 cosmetic, 2 snorkel, and 2 (`rollcage`, `Winch_01`) that name no item. A node names one item (`vehiclePartReference`) and shows when that item is mounted; the node itself is the option. The slot is the item's `CosmeticType`.
- One item can drive several nodes (each mudflap item shows on all four corners, each side item on both sides). `LinkedParts` makes one item pull in another, with a count (every antenna topper shows the antenna base).
- Each car offers its own `UpgradesLists`. The networked mounted state is a 256-bit set, inferred to index that list **[test]**.
- The item catalogue and cosmetic meshes are shared: the Mammoth and the Wombat use the same mesh asset for all 409 cosmetic meshes they have in common. Placement is per car, with full position, rotation and often non-uniform scale, so an export keeps the whole transform.

### The roster: one rig, four slot profiles

Every stock car (23: 21 catalogued plus Baguette and Grizzly) is built on the same rig:

| Subsystem | All 23 cars |
|---|---|
| Top level | The same 16 children: `Parts`, `Collider`, `Axles`, `Lights`, `Winch`, `WaterDetector`, `Effects`, `Audio`, `CoM`, `AckermanRef`, the camera points, `FrameIndicators`, `POITriggerCollider` |
| Body | `Parts/<C>/<C>_body_LOD0..3` under one LODGroup, with no separate doors, hardtop or glass |
| Colliders | `Collider/Top` and `Collider/Base`, both MeshColliders |
| Axles | Four raycast wheel colliders and two skinned solid axles with the same bones (`BoneBody`, `BoneFrontPosAdjust`, `BoneRearPosAdjust`, `BoneWheelHub{L,R}`) |
| Driveline | Two driven axles, front steering |
| Winch | `Winch/WinchAttachPoints/{Front,Rear,Left,Right}` |
| Water | Seven detection points: three intake heights, front and back submerged, touching water, tyres submerged |
| Audio | The same 20 emitters |
| Effects | Collision and exhaust particle managers; the exhaust exit is the exhaust manager's position |

Lights differ only by extras: the Mammoth and BlastWagon add a spotlight-flare pair, Baguette two spotlight pairs, and Protector and Timberbox have no reverse lights.

Tuning follows the category exactly, so a template takes its category as a tuning preset, chosen separately from its type:

| Category | Max steer | Peak torque | Speed limit |
|---|---|---|---|
| Trail | 38 | 100 | 7.5 |
| Wagon | 33 | 125 | 8.0 |
| Workhorse | 28 | 175 | 6.0 |
| Expedition | 28 | 200 | 5.5 |

Quirks an exporter tolerates by matching tree position, not names: `BullV1`, `TrailRat`, `Polyana_bodu_LOD*`, lower-case `<C>_wheel` on BlastWagon and Timberbox, RustOx's separate rear wheels. Null-item upgrade nodes: `Winch_01` on every car, `rollcage` on 18, built-in bullbars on Brick, Grizzly and Marshal, and a few one-offs on BlastWagon and Cumbre.

### Materials, textures and liveries

- One shader for everything on a car, `Shader Graphs/CarMainShader`. Its maps: `_Livery_Texture` (the skin liveries swap), `_Main_Texture` (albedo for non-livery parts), `_Mask_Texture` (material classes), `_AO_Texture`, `_Lights_Texture` (lamp emission, scaled by four light intensities), and shared damage maps. Toggles: `_IsSwitchable` (takes liveries), `_RenderBackfaces`. Weather, dirt, snow, wetness, damage and fade are driven per frame.
- The Mammoth body is one material with four 2048² DXT1 maps (skin, masks, AO, lights); its wheels and spares use the same four with `_IsSwitchable` set; the axles have their own `Suspension` material; about 90 cosmetic materials carry their own maps and take no livery. Glass, lenses and paint are mask classes, not materials.
- Every car texture is flagged sRGB, masks and AO included, so replacements are created sRGB too.
- Liveries are per-car assets whose effect loads a skin texture and calls `PropertyBlockSetter.SetLiveryTexture`. The `PropertyBlockSetter` collects the car's renderers by material at `Awake` and overrides `_Livery_Texture` through a property block on every renderer whose material had `_IsSwitchable` set; weather, damage and lights go through the same blocks. It has `AddRenderer` and `RemoveRenderer`, which the game never calls.
- Player-made liveries (mod.io and `LocalLiveries`) are keyed by car name and load a full skin image through the same `SetLiveryTexture`.
- Runtime textures: create on the main thread, with mipmaps and sRGB. RGBA32 at 2048² with mips is 21 MB per map; BC1 is 2.7 MB, so the build encodes BCn and the plugin uploads it with `LoadRawTextureData`.

### Reading donor meshes at run time (2026-10-20)

The question: can the plugin take donor meshes from the loaded prefab (`Mesh.vertices`, `GetVertices`, `AcquireReadOnlyMeshData`) instead of carrying a bundle reader? In a player build Unity allows CPU reads only on meshes whose `m_IsReadable` is set; a non-readable mesh keeps its data on the GPU alone. Probed offline with UnityPy over the player's bundles, read-only:

| Source | Distinct meshes | Readable |
|---|---|---|
| `Car_Mammoth`: body LOD0-3, axles (front and rear share 4), colliders, 462 upgrade-option meshes, 2 effect meshes | 474 | 1 |
| `Car_DingDing`, the same parts with 479 upgrade-option meshes | 491 | 1 |
| The mechanic's truck in the `r1_canada` scene bundle (`Merchant_LOD0..3`) | 4 | 0 |
| The whole cars bundle | 884 | 2 |

- Every body LOD, axle and collider is non-readable, and so are the Mammoth's wheel and tyre LODs, which the prefab doesn't reference directly. The one readable option mesh on each car is a roof Christmas tree's billboard impostor; the other readable meshes in the bundles are vegetation impostors, rocks and river splines.
- Each prefab also references one built-in mesh from Unity's default resources (`FrameIndicators/ResimulateIndicator`), not in the bundles.
- **So the bundle reader stays** (Architecture, Core): the plugin reads the donor's meshes from the player's bundle files with a managed reader on its background thread. The creator side needs one too, or UnityPy in Blender's Python. Reading a non-readable mesh back from the GPU (`Mesh.GetVertexBuffer`) would be main-thread IL2CPP work and is untested; not pursued.
