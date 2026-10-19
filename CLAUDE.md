# Die Kollektion

A BepInEx 6 IL2CPP mod for *Over the Hill* (Funselektor; Unity 6000.0.75, native Linux tested) that adds trucks built on a stock donor (the Mammoth): Das Glyptodon (two-door) and Das Megaloceros (crew cab) of the Glyptodon family, Das Mastodon and Das Megatherium of the Mammoth family, and a patch on the stock Mammoth. The authoring toolkit being designed (Blender add-on, vehicle templates, CLI authoring commands) is Die Kollektion Werkstatt.

Read `docs/engine.md` first (engine facts, crash rules, mesh pipeline), then `docs/vehicle_factory.md` (design draft). `plugins/VehicleMods/CLAUDE.md` covers the plugin; `vehicles/glyptodon/CLAUDE.md` covers both cab masters.

## How it works

Each vehicle is one portable folder, `vehicles/<name>/`: `vehicle.json` (the manifest; `kind` is `novel`, `based` on a shipped vehicle, or a `patch` to one, with a `base` block naming that vehicle), its own geometry (`meshes/`, Blender masters), `icon.svg`/`icon.png`, and two gitignored folders: `generated/` (parts made from extracted game data) and `build/` (what `tools/build_vehicle.py` writes and the plugin deploys). Game parts extracted from the player's install live in `extracted/` (gitignored). Part files a manifest names are relative to its folder, except those under `extracted/`.

- **Offline (Python and Blender, `tools/`).** `tools/export_game_data.sh` extracts the donor meshes, textures and stock icon from the player's own install into `extracted/`. The Glyptodon family is generated: `tools/make_glyptodon.py` / `make_megaloceros.py` (sharing `tools/glyptodon_family.py`) write `vehicles/<name>/vehicle.json`; the Mastodon, Megatherium and Mammoth manifests are hand-written. `tools/build_vehicle.py` builds each vehicle's body, collider and part meshes into its `build/`. Cabs come from the Blender masters in `vehicles/glyptodon/` and `vehicles/megaloceros/`. Icons: `tools/draw_icons.py` (Glyptodon family), `tools/trace_icons.py` (Mammoth family, traced locally from the stock icon), then `tools/rasterize_icons.py`; each writes into the vehicle's folder.
- **In the game (`plugins/VehicleMods`).** The plugin clones the donor, reshapes wheelbase, track and suspension, swaps in the meshes and registers a new item ID.

## Commands

- Extract game data once per game update: `tools/export_game_data.sh "<game folder>"` (needs `.venv` from `requirements.txt`).
- Build a truck: `python3 tools/make_megaloceros.py && python3 tools/build_vehicle.py vehicles/megaloceros/vehicle.json` (or `make_glyptodon` / `vehicles/glyptodon/vehicle.json`). Preview: `tools/preview_vehicle.sh vehicles/<name>/vehicle.json`.
- Gates after any mesh change: `python3 tools/check_holes.py` on each body LOD, `python3 tools/check_slivers.py` on the built OBJs (`vehicles/*/build/*.obj`), and `python3 tools/check_names.py`. After a definition's `listing` changes: `python3 tools/catalogue.py`.
- Deploy: `cd plugins/VehicleMods && dotnet build -c Release -p:GameDir="<game folder>"` copies the DLL and each vehicle folder's manifest, built meshes and icon into the game folder (`-p:DeployDir=<dir>` deploys elsewhere, e.g. to inspect what would ship); `-p:Deploy=false` only compiles. Deploy only with the game closed: `ps -eo comm,args | grep -F "over the hill.x86_64"` matches the grep itself, so read the process names.
- Add a truck to a save: `python3 tools/add_vehicle_to_save.py "$HOME/My Games/over the hill/Saves/Player1.json" <ItemId>` (backs up first; game closed).
- Logs: `<game>/BepInEx/LogOutput.log`, `~/.config/unity3d/Funselektor/over the hill/Player.log`.

## Working rules

- Never launch, kill or loop the game yourself; the person may be playing. Ask first.
- Nothing from the game is ever committed: extracted meshes, textures and icons stay in `extracted/`, and what is made from them in each vehicle's `generated/` and `build/`.
- Vehicle-centred layout: everything a vehicle owns lives in its folder; no top-level `meshes/` or `icons/`.
- Nothing real reaches the game: in-game names, descriptions, categories and assets stay fictional, and so do file, part, tool and identifier names. Die Kollektion's own catalogue (README, CLI, pack listing) presents the real vehicle data, from each definition's `listing` block (`listing.real`: make, model, series, variant, years, description, basis); `tools/check_names.py` enforces it. `listing.real.description` is factual: what the real vehicle is, its cab, wheelbase and tyres; no personal stories. Whether the game shows real names is the player's local choice, never something a pack ships.
- Commit by path (`git add <paths>`, `git commit -- <paths>`), not `git add -A`.
- Detail target: a little above the stock vehicles. Fix visible faults and wasted triangles before adding fidelity.
