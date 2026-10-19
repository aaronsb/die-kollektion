# Die Kollektion Werkstatt: guide for agents

You are probably helping a person mod *Over the Hill* (Funselektor; Unity 6000.0.75, native Linux tested) with **Die Kollektion Werkstatt**, a vehicle mod system: a BepInEx 6 IL2CPP plugin that adds vehicles built on a stock donor and changes stock ones, plus the Python and Blender toolchain that builds them. The CLI (`kollektion`), packs and the Blender add-on are designed, not built. **Die Kollektion** is the example set of vehicle packs made with it: Das Glyptodon (two-door) and Das Megaloceros (crew cab) of the Glyptodon family, Das Mastodon and Das Megatherium of the Mammoth family, all on the Mammoth as donor, and a patch on the stock Mammoth. Everything in this project was written with AI; it is agent-friendly on purpose, so people who love a truck can get it into the game without learning the whole toolchain first.

Read `docs/engine.md` (engine facts, crash rules, mesh pipeline) and `docs/vehicle_factory.md` (design draft) before changing anything substantial. `plugins/VehicleMods/CLAUDE.md` covers the plugin; `vehicles/glyptodon/CLAUDE.md` covers both cab masters.

## First: which help does the person want?

Work out which of two modes fits; if the first message doesn't make it clear, ask once ("Do you want me to just make it work, or do you want to build it yourself with me explaining as we go?"). The person can switch at any time; follow them.

**"I just love that truck and want to play."** You drive.
- Ask only what you can't decide: which car, what change, and what "done" looks like to them.
- Pick safe defaults for everything else and say what you picked in one line.
- Use plain words. Explain a concept only when the person needs it to make a choice.
- Aim for a working result in their game, then offer what's next.

**"I want to build a vehicle, I don't know where to start, and I want creative control."** You coach.
- Explain each idea as it comes up (kinds, base, parts, attach points, groups; see Glossary), briefly and with this project's real examples.
- Offer choices with your recommendation; let the person decide anything that shapes how the vehicle looks or drives.
- Work in small steps the person can follow, and show the vehicle's contact sheet (`vehicles/<name>/README.md`, or `tools/preview_vehicle.sh` renders) before anything is final.
- Never override a creative decision. If it will break something (a gate, the game, the rules below), say what breaks and offer alternatives.

## Rules in every mode

- **The game must be closed** before deploying or touching a save. Never launch, kill or loop the game yourself; ask the person to start it and tell you what they see. To check whether it runs, `ps -eo comm,args | grep -F "over the hill.x86_64"` matches the grep itself, so read the process names.
- **Back up the save** before any save edit (`tools/add_vehicle_to_save.py` backs up first). Saves live in `~/My Games/over the hill/Saves/`; Steam Cloud syncs that folder, so mention it.
- **Nothing extracted from the game ships or gets committed.** Meshes, textures and icons from the player's install are the game developer's assets; they stay in `extracted/` and in each vehicle's gitignored `build/` and `generated/`. A shared vehicle carries only its own parts and the differences from its base, rebuilt on each player's machine from their own copy of the game.
- **Nothing real reaches the game.** In-game names, descriptions, categories and assets stay fictional, and so do file, part, tool and identifier names. The real vehicle data lives only in each manifest's `listing` block (`listing.real`: make, model, series, variant, years, description, basis), which feeds the README catalogue; `tools/check_names.py` enforces it. `listing.real.description` is factual, with no personal stories. Showing real names in-game is the player's own local choice, never something a pack ships.
- **Plugin code has crash rules** learned the hard way: no class injection (no `AddComponent<T>` of plugin types, no managed delegates handed to the game); patches are applied only from the `GameStateManager.Transition` entry hook, never in `Load`; `Load` touches no IL2CPP type; keep `DobbyNearPages`. Read `plugins/VehicleMods/CLAUDE.md` and `docs/engine.md` before editing the plugin.
- **Commit by path** (`git add <paths>`, `git commit -- <paths>`), never `git add -A` or `git commit -a`: other agents may have half-finished files in the tree.
- **Detail target:** a little above the stock vehicles. Fix visible faults and wasted triangles before adding fidelity.
- **Look before you call it done:** after any mesh change, regenerate the vehicle's contact sheet (Commands) and read it: the renders, the rig view and the gate results. In coach mode, show it to the person.

## What runs today, and what doesn't yet

Today Werkstatt is the plugin plus Python and Blender scripts, built from source. **The `kollektion` CLI, packs (`.kpack`), the Blender add-on and the vehicle templates are designed but not built** (`docs/vehicle_factory.md`). Never tell a person to run a `kollektion` command; use the commands below.

What a person can do today:
- Build and install our four trucks and the Mammoth patch (Commands).
- Tweak the Mammoth patch: edit `vehicles/mammoth/vehicle.json` (`maxSteerAngle`, `track`, `wheel`, `transforms`, and a `suspension` block shaped like the trucks', which the Mammoth patch hasn't used yet, so check it in-game), rebuild, deploy.
- Tweak one of our trucks: for the Glyptodon family, change the constants in `tools/make_glyptodon.py` / `make_megaloceros.py` (they regenerate the manifest); for the Mastodon and Megatherium, edit their manifests directly.
- A patch on a stock car other than the Mammoth means a new manifest shaped like `vehicles/mammoth/vehicle.json` with that car as `donor`. That path is untested: say so, keep the change small, and have the person check it in-game and read the logs with you.

## Liveries

The game's only official mod type is the livery, in the format of Funselektor's [Official Livery Modding Guide](https://mod.io/g/over-the-hill/r/official-livery-modding-guide):
- A livery pack is a folder (local) or a zip (mod.io) with exactly one `manifest.json` and PNGs: `{"liveries": [{"car": "Mammoth", "name": "My Paint", "texture": "my_paint.png", "icon": "my_paint_preview.png"}]}`. `car` and `texture` are required; `car` is the internal name without spaces, case-insensitive. Strict JSON.
- Textures are 2048×2048 sRGB PNGs painted on the car's UV template (the guide links the templates); icons 512×512.
- Local liveries go in their own subfolder of `~/My Games/over the hill/LocalLiveries/` (Windows: `Documents\My Games\over the hill\LocalLiveries\`). In the garage, "Show local mods" reveals them and "Refresh local mods" reloads edited PNGs without a restart. Local liveries are never shared in multiplayer.
- The Mastodon and Megatherium keep the Mammoth's UV layout, so Mammoth liveries fit them. Whether a local livery with `"car": "<our codename>"` (for example `"Megaloceros"`) shows on our trucks is **untested**: say so, and have the person check it in-game.

## Commands

- Set up once: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`; you also need Blender 5.x, `rsvg-convert` and the .NET SDK.
- Extract game data once per game update: `tools/export_game_data.sh "<game folder>"` (into `extracted/`).
- Build a truck: `python3 tools/make_megaloceros.py && python3 tools/build_vehicle.py vehicles/megaloceros/vehicle.json` (or `make_glyptodon` / `vehicles/glyptodon/vehicle.json`; the Mastodon, Megatherium and Mammoth have hand-written manifests, so only `build_vehicle.py`). Preview renders: `tools/preview_vehicle.sh vehicles/<name>/vehicle.json`.
- Icons: `python3 tools/draw_icons.py` (Glyptodon family), `python3 tools/trace_icons.py` (Mammoth family, traced locally from the stock icon), then `.venv/bin/python -I tools/rasterize_icons.py`.
- Contact sheet (needs Blender; run `python3 tools/composite_atlas.py Mammoth` once first, or bodies render flat grey): `python3 tools/contact_sheet.py vehicles/<name>` writes `vehicles/<name>/contact/contact.json`, renders `vehicles/<name>/README.md` from it, and puts `iso.png`, `rig.png` and `gaps.png` in `contact/`. `--no-render` / `--no-holes` skip the slow parts while iterating. Compare two builds: `python3 tools/contact_sheet.py --diff <a/contact.json> <b/contact.json> [--out <file.md>]`.
- Gates after any mesh change: `python3 tools/check_holes.py` on each body LOD, `python3 tools/check_slivers.py` on the built OBJs (`vehicles/*/build/*.obj`), `python3 tools/check_names.py`. After a manifest's `listing` changes: `python3 tools/catalogue.py` (rewrites the README catalogue; `--check` only checks).
- Deploy (game closed): `cd plugins/VehicleMods && dotnet build -c Release -p:GameDir="<game folder>"` copies the DLL and each vehicle folder's manifest, built meshes and icon into `<game folder>/BepInEx/plugins/VehicleMods/`. `-p:DeployDir=<dir>` deploys elsewhere to inspect what would ship; `-p:Deploy=false` only compiles.
- Add a truck to a save (game closed; backs up first): `python3 tools/add_vehicle_to_save.py "$HOME/My Games/over the hill/Saves/Player1.json" <ItemId>`. ItemIds: Megatherium 3000000001, Mastodon 3000000002, Glyptodon 3000000003, Megaloceros 3000000004.
- Logs: `<game folder>/BepInEx/LogOutput.log`, `~/.config/unity3d/Funselektor/over the hill/Player.log`.
- First-time BepInEx setup (the README has it in full): BepInEx 6 IL2CPP be.789 in the game folder, Steam launch option `"./run_bepinex.sh" %command%` on Linux, and `UnityLogListening = false` in `BepInEx/config/BepInEx.cfg`.

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
