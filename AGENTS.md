# Die Kollektion Werkstatt: guide for agents

You are probably helping a person mod *Over the Hill* (Funselektor; Unity 6000.0.75, native Linux tested) with **Die Kollektion Werkstatt**, a vehicle mod system: a BepInEx 6 IL2CPP plugin that adds vehicles built on a stock donor and changes stock ones, plus the Python and Blender toolchain that builds them. The CLI (`kollektion`), packs and the Blender add-on are designed, not built. **Die Kollektion** is the example set of vehicle packs made with it: Das Glyptodon (two-door) and Das Megaloceros (crew cab) of the Glyptodon family, Das Mastodon and Das Megatherium of the Mammoth family, all on the Mammoth as donor, and a patch on the stock Mammoth. Everything in this project was written with AI; it is agent-friendly on purpose, so people who love a truck can get it into the game without learning the whole toolchain first.

Read `docs/engine.md` (engine facts, crash rules, mesh pipeline) and `docs/vehicle_factory.md` (design draft) before changing anything substantial. `plugins/VehicleMods/CLAUDE.md` covers the plugin; `vehicles/glyptodon/CLAUDE.md` covers both cab masters.

## First: which help does the person want?

Work out which of two modes fits; if the first message doesn't make it clear, ask once ("Do you want me to just make it work, or do you want to build it yourself with me explaining as we go?"). The person can switch at any time; follow them.

**"I just love that truck and want to play."** You drive.
- Ask only what you can't decide: which car, what change, and what "done" looks like to them.
- Pick safe defaults for everything else and say what you picked in one line.
- Use plain words. Explain a concept only when the person needs it to make a choice.
- Setting up means running `make start` again and again and doing what it says. It checks the system and prints one next step with the exact command or Steam click path. Run the commands you can run yourself (`make setup`, `make bepinex`, `make all`), and hand the person the steps only they can do (installing system packages with `sudo`, the Steam launch option, starting the game once) in plain words: what it is, why it's needed, exactly what to type or click. Then run `make start` again.
- Aim for a working result in their game, then offer what's next.

**"I want to build a vehicle, I don't know where to start, and I want creative control."** You coach.
- Explain each idea as it comes up (kinds, base, parts, attach points, groups; see Glossary), briefly and with this project's real examples.
- Offer choices with your recommendation; let the person decide anything that shapes how the vehicle looks or drives.
- Work in small steps the person can follow, and show the vehicle's contact sheet (`vehicles/<name>/README.md`, or `tools/preview_vehicle.sh` renders) before anything is final.
- Never override a creative decision. If it will break something (a gate, the game, the rules below), say what breaks and offer alternatives.

## Rules in every mode

- **The game must be closed** before deploying or touching a save. Never launch, kill or loop the game yourself; ask the person to start it and tell you what they see. The main menu's build label ends with a `Die Kollektion …` status line when the mod is working (amber when something is short; no line means stock). On a working install with no line, the log's `Main menu:` line says whether the label was active (`plugins/VehicleMods/CLAUDE.md`). To check whether it runs, `ps -eo comm,args | grep -F "over the hill.x86_64"` matches the grep itself, so read the process names.
- **Back up the save** before any save edit (`tools/add_vehicle_to_save.py` backs up first, to `~/My Games/over the hill/DieKollektion/backups/`, and only when it changes something). Saves live in `~/My Games/over the hill/Saves/`; Steam Cloud syncs that folder, so mention it.
- **Nothing extracted from the game ships or gets committed.** Meshes, textures and icons from the player's install are the game developer's assets; they stay in `extracted/` and in each vehicle's gitignored `build/` and `generated/`. A shared vehicle carries only its own parts and the differences from its base, rebuilt on each player's machine from their own copy of the game.
- **Nothing real reaches the game.** In-game names, descriptions, categories and assets stay fictional, and so do file, part, tool and identifier names. The real vehicle data lives only in each manifest's `listing` block (`listing.real`: make, model, series, variant, years, description, basis), which feeds the README catalogue; `tools/check_names.py` enforces it. `listing.real.description` is factual, with no personal stories. Showing real names in-game is the player's own local choice, never something a pack ships.
- **Plugin code has crash rules** learned the hard way: no class injection (no `AddComponent<T>` of plugin types, no managed delegates handed to the game); patches are applied only from the `GameStateManager.Transition` entry hook, never in `Load`; `Load` touches no IL2CPP type; keep `DobbyNearPages`. Read `plugins/VehicleMods/CLAUDE.md` and `docs/engine.md` before editing the plugin.
- **Commit by path** (`git add <paths>`, `git commit -- <paths>`), never `git add -A` or `git commit -a`: other agents may have half-finished files in the tree.
- **Detail target:** a little above the stock vehicles. Fix visible faults and wasted triangles before adding fidelity.
- **Look before you call it done:** after any mesh change, regenerate the vehicle's contact sheet (Commands) and read it: the renders, the rig view and the gate results. In coach mode, show it to the person.

## What runs today, and what doesn't yet

Today Werkstatt is the plugin plus Python and Blender scripts, built from source and driven by the Makefile. **The `kollektion` CLI, the plugin loading packs, the Blender add-on and the vehicle templates are designed but not built**; a pack's manifest and its shareable zip exist (`packs/die-kollektion/`, `make pack`), but the plugin still installs from the vehicle folders (`docs/vehicle_factory.md`). Never tell a person to run a `kollektion` command; use the commands below.

What a person can do today:
- Set up from scratch and install our four trucks and the Mammoth patch: `make start`, repeated (Commands).
- Tweak the Mammoth patch: edit `vehicles/mammoth/vehicle.json` (`maxSteerAngle`, `track`, `wheel`, `transforms`, and a `suspension` block shaped like the trucks', which the Mammoth patch hasn't used yet, so check it in-game), rebuild, deploy.
- Tweak one of our trucks: for the Glyptodon family, change the constants in `tools/make_glyptodon.py` / `make_megaloceros.py` (they regenerate the manifest); for the Mastodon and Megatherium, edit their manifests directly. Headlight colour and brightness are the manifest's `headlights` block (`kelvin`, `intensity` as a factor on the game's; the Glyptodon family's lives in `tools/glyptodon_family.py`).
- A patch on another stock car: copy `vehicles/dingding/` (the canary, a golf bag on The Ding's roof) and set `codename`, `donor` and `base.car` to that car's internal name (the CarInfo name, e.g. `Protector`, `Trailrat`), with its `donorAxleZ`, `wheelbase` and `track` from `extracted/<car>/nodes.json` (`Axles/WheelMeshes/FL` and `RL`). `make extract` then pulls that car's parts (`tools/export_donor.py`). The canary is the first patch on a car other than the Mammoth and is unconfirmed in game until the person has driven it: say so, keep the change small, and read the logs with them.

## The workshop loop

How a change to a vehicle is made and shown. The Werkstatt part needs no git and no GitHub; how a change travels through this repository (branch, pull request, review, merge) is in [CONTRIBUTING.md](CONTRIBUTING.md).

1. **Know what to change.** The person tells you, or reports it: the Drive report form on GitHub (`.github/ISSUE_TEMPLATE/drive-report.yml`) holds the vehicle, the build driven and what felt off.
2. **Make the change:** a manifest value, a generator constant, a placement in `transforms`.
3. **`make loop V=<vehicle>`** builds that vehicle, runs its gates, regenerates its contact sheet and writes `contact/CHANGES.md`: facts, points moved (with distances), checks changed and triangle counts, compared with the committed sheet (where the branch left main; the last commit on main; nothing outside a git checkout). Read the sheet's renders and rig view yourself before going on.
4. **Show it.** The updated contact sheet and `CHANGES.md` are what the person reviews; in this repository they go into a pull request (CONTRIBUTING.md). The person may drive it (`make all`) or review from the sheets alone.

`make status` shows what is installed and, in a git checkout, which branch and commit it came from.

## Liveries

The game's only official mod type is the livery, in the format of Funselektor's [Official Livery Modding Guide](https://mod.io/g/over-the-hill/r/official-livery-modding-guide):
- A livery pack is a folder (local) or a zip (mod.io) with exactly one `manifest.json` and PNGs: `{"liveries": [{"car": "Mammoth", "name": "My Paint", "texture": "my_paint.png", "icon": "my_paint_preview.png"}]}`. `car` and `texture` are required; `car` is the internal name without spaces, case-insensitive. Strict JSON.
- Textures are 2048×2048 sRGB PNGs painted on the car's UV template (the guide links the templates); icons 512×512.
- Local liveries go in their own subfolder of `~/My Games/over the hill/LocalLiveries/` (Windows: `Documents\My Games\over the hill\LocalLiveries\`). In the garage, "Show local mods" reveals them and "Refresh local mods" reloads edited PNGs without a restart. Local liveries are never shared in multiplayer.
- The Mastodon and Megatherium keep the Mammoth's UV layout, so Mammoth liveries fit them. Whether a local livery with `"car": "<our codename>"` (for example `"Megaloceros"`) shows on our trucks is **untested**: say so, and have the person check it in-game.

## Commands

The Makefile is the front door; `make help` lists every target. Run them from the repo root.

- `make start` (or plain `make`): the one next setup step, in plain words. Rerun after every step.
- `make doctor`: every check at once, with what each thing is and the install command for this distro.
- `make setup`: `.venv/` with `requirements.txt`.
- `make bepinex`: installs BepInEx 6 IL2CPP from the pin in `tools/bepinex.json` (asks before downloading in a terminal, sha256-verified; `BEPINEX_ARCHIVE=<zip>` uses a file already downloaded; the win-x64 entry has no sha256 yet, so it refuses there), sets `executable_name` and the execute bit on `run_bepinex.sh` (the archive ships it without either), installs Werkstatt's launch script `run_werkstatt.sh` next to it (from `tools/`, pointed at this Werkstatt folder; `make deploy` installs it too), and sets `UnityLogListening = false` (the archive ships no `BepInEx.cfg`; a file holding only this line is written before the first start, and BepInEx keeps it when it writes the rest). Prints the Steam launch option `"./run_werkstatt.sh" %command%` and its click path (Library → right-click Over the Hill → Properties → General → Launch Options). The launch script starts `run_bepinex.sh`; after a game update it starts the game without the old plugin and rebuilds the plugin's DLL once the game has exited (`docs/engine.md`, BepInEx). The script must be in the game folder before Steam's option names it: on an install that still uses `"./run_bepinex.sh" %command%`, run `make deploy` (or `make bepinex`) first, then change the option.
- `make extract`, `make build`, `make check`, `make contact`: game parts into `extracted/`; every vehicle's meshes and icons; all gates (exit 1 on any failure); contact sheets (needs Blender; textured renders also need `tools/composite_atlas.py Mammoth`, which `make contact` runs).
- `make deploy` (game closed): gates, then the plugin build and install into `BepInEx/plugins/VehicleMods/` with `deployed.json` listing every file and its sha256. It records the game's version there too, and refuses to build for an updated game until BepInEx has prepared it (start the game once). `DEPLOY_DIR=<dir>` installs elsewhere to inspect it. `make undeploy` removes exactly those files (`FORCE=1` if they changed). `make status` compares repo, build and game folder, and says whether the plugin fits the game's version.
- `make update` (game closed): after a game update, moves the plugin aside and rebuilds it once BepInEx has prepared the updated game; until then it says to start the game once. The launch script does this on its own, but only for the checkout and commit that were deployed; for any other, `make update` deploys the checkout in full, with the gates. `make status` shows which Werkstatt folder the game's launch script points at.
- `make all`: extract, build, deploy, after `werkstatt.py require` confirms setup is done.
- `make loop V=<vehicle>`: one vehicle's build, gates, contact sheet and `CHANGES.md` (the workshop loop, above).
- `make pack`: `dist/die-kollektion-<version>.zip` from `packs/die-kollektion/manifest.json` (`tools/pack.py`; `P=<pack>` for another): the manifest, the pack's README, the licences and the vehicle folders' tracked files; it refuses anything under `extracted/`, `build/` or `generated/` and any file byte-identical to one in `extracted/`. `make check` validates every pack manifest with the game's rules (strict JSON; `liveries` entries need `car` and `texture`).
- Release zips (`die-kollektion-werkstatt-<version>.zip` on GitHub Releases) carry `prebuilt/VehicleMods.dll` and `prebuilt/VehicleMods.json` (its version and the game's BepInEx assembly hash it was built against). `make deploy` installs that plugin instead of compiling when its version matches `Plugin.cs` and the game's `BepInEx/interop/assembly-hash.txt` matches; then no .NET SDK is needed and `make start` doesn't ask for one. After a game update the hash differs and the plugin is compiled (a plugin built for another game version hung the game at start once). Blender is never needed for `make all`.
- `make release VERSION=x.y.z` (maintainers, on a machine with the game; `DRY_RUN=1` builds everything and publishes nothing): refuses uncommitted changes, versions that disagree (`Plugin.cs`, `packs/die-kollektion/manifest.json`, CHANGELOG.md), an existing tag or failing gates; compiles the plugin; writes `dist/die-kollektion-werkstatt-<version>.zip`, the pack zip, the release notes from CHANGELOG.md and `SHA256SUMS`; then tags, pushes the tag and runs `gh release create`. CI (`.github/workflows/`) runs `python3 tools/release.py ci`, every check that needs no game files, on each pull request and push, and checks each release's tag, versions and assets; once those pass, `.github/workflows/nexus.yml` uploads the Werkstatt zip to Nexus Mods as the new main file with its changelog.
- `make save-add` (game closed; backs the save up first, outside `Saves/`; `PROFILE=<name>` for another profile; a no-op when all four are owned): adds our four trucks. ItemIds: Megatherium 3000000001, Mastodon 3000000002, Glyptodon 3000000003, Megaloceros 3000000004.
- `make save-test` (game closed): swaps in a test save, a copy of the real one in which every car, our trucks included, owns every part it offers, so the garage previews each part on each truck (the upgrade audit). The real save (and its `.bak`) waits in `~/My Games/over the hill/DieKollektion/test-save/`; `make save-real` puts it back and keeps the played test save in `DieKollektion/backups/`. `make status` says when a test save is in place. Steam Cloud syncs the test save while it is in place. The parts list comes from the player's own bundles (`extracted/parts.json`, written by `make extract`).
- Gate exceptions live in each manifest's `gates` block with `notes` saying why: `failCulledCm2` / `failGapCm2` for `check_holes`, `sliverAllow` boxes for `check_slivers`. Never raise one to make a new defect pass; fix the mesh.

Underneath (for agents who need one step): `tools/werkstatt.py` (setup checks, BepInEx, gates, deploy bookkeeping, `loop`), `tools/export_game_data.sh "<game folder>"`, `tools/make_glyptodon.py` / `make_megaloceros.py` (regenerate those manifests), `tools/build_vehicle.py vehicles/<name>/vehicle.json`, `tools/trace_icons.py` then `tools/rasterize_icons.py` (run with `-I`), `tools/draw_icons.py` (Glyptodon-family icon sources), `tools/check_holes.py`, `tools/check_slivers.py`, `tools/check_names.py`, `tools/catalogue.py` (`--check`), `tools/contact_sheet.py vehicles/<name>` (`--diff a b`, `--changes old new`), `tools/pack.py`, `tools/preview_vehicle.sh vehicles/<name>/vehicle.json`, and `dotnet build -c Release -p:GameDir="<game folder>"` in `plugins/VehicleMods/` (`-p:DeployDir=`, `-p:Deploy=false`).

Rehearsing without touching the real install: `GAME_DIR=<copy of the game folder>` and `MY_GAMES=<copy of ~/My Games/over the hill>` point every target at copies (on btrfs, `cp -a --reflink=always` copies the game folder for free). The plugin DLL is reproducible (`PathMap`), so two clones build the same bytes.

Logs: `<game folder>/BepInEx/LogOutput.log`, `~/.config/unity3d/Funselektor/over the hill/Player.log`.

## Repo map

- `vehicles/<name>/`: one portable folder per vehicle. `vehicle.json` (the manifest), its own geometry (`meshes/`, Blender masters), `icon.svg`/`icon.png`, and two gitignored folders: `generated/` (parts made from extracted game data) and `build/` (what `tools/build_vehicle.py` writes and the deploy copies). Part files a manifest names are relative to its folder, except those under `extracted/`.
- `extracted/`: game data from the player's own install (gitignored).
- `tools/`: the Python and Blender pipeline: extraction, the Glyptodon-family generator (`glyptodon_family.py`), mesh operations (`meshlib.py`, `build_vehicle.py`), cab scripts (`cab_roof.py`, `cab_doors.py`, `cab_fixes.py`, `build_cab_part.sh`), gates, renders, icons, save edits.
- `plugins/VehicleMods/`: the BepInEx plugin. It clones the donor's `CarInfo`, reshapes wheelbase, track and suspension at spawn, swaps in the built meshes and registers a new item ID.
- `docs/`: `engine.md` and `vehicle_factory.md`.

## Glossary

- **Kind** (`kind` in `vehicle.json`): `novel` (everything is the author's own; reuses only the vehicle rig and the wheels and tyres, referenced live from the game), `based` (a new vehicle assembled from a shipped vehicle plus differences; only the differences ship), or `patch` (changes a shipped vehicle in place; no new item, no save entries). Today all four trucks are `based`, the Mammoth changes are a `patch`.
- **Base** (`base` in `vehicle.json`): the shipped vehicle (and, in the design, any props) a `based` vehicle or a `patch` starts from.
- **Donor**: the stock car whose prefab a vehicle runs on (today always the Mammoth).
- **Parts tree and attach points** (design): a manifest builds a vehicle as nested parts, each with a source, an attach point on its parent and its own child parts; attach points are named positions such as wheel hubs, the winch, lights and upgrade-slot anchors.
- **Groups and the main manifest** (design): groups are merchant sections (the game's vehicle categories); a pack's main manifest, `manifest.json` at the pack root, lists its liveries, vehicles, patches and groups and puts each vehicle in a group.
- **Manifests** (`vehicle.json` today; the pack `manifest.json` in the design): strict JSON following the game's official livery manifest pattern (no comments, no trailing commas, `car` = a car's internal name without spaces, case-insensitive). For comments, any object may carry a `notes` field: a string, or an array of strings for longer text. Loaders ignore it; templates use it to explain fields.
- **Template types** (design): the stock cars' four upgrade-slot profiles (bonneted body, bonneted pickup, flat-front body, flat-front bed truck) that a new vehicle starts from.
- **Werkstatt**: Die Kollektion Werkstatt, the vehicle mod system: the plugin and toolchain today, the CLI, packs and Blender add-on planned. **Die Kollektion** is its example set of vehicle packs.
- **Contact sheet**: `vehicles/<name>/README.md`, rendered from `contact/contact.json` by `tools/contact_sheet.py`: four isometric renders, a rig view (colliders, wheel colliders and labelled attach points), the mesh gates and the vehicle's facts. GitHub shows it when the vehicle's folder is opened. It may show game geometry: it is pictures and numbers, no mesh data.
- **Gates**: the checks above; a failing gate means the build isn't ready to ship.
