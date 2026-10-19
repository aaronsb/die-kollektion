# Die Kollektion

A BepInEx 6 IL2CPP mod for *Over the Hill* (Funselektor; Unity 6000.0.75, native Linux tested) that adds trucks built on a stock donor (the Mammoth): Das Glyptodon (two-door) and Das Megaloceros (crew cab) of the Glyptodon family, Das Mastodon and Das Megatherium of the Mammoth family, and a patch on the stock Mammoth. The authoring toolkit being designed (Blender add-on, vehicle templates, CLI authoring commands) is Die Kollektion Werkstatt.

Read `docs/engine.md` first (engine facts, crash rules, mesh pipeline), then `docs/vehicle_factory.md` (design draft). `plugins/VehicleMods/CLAUDE.md` covers the plugin; `meshes/glyptodon/CLAUDE.md` covers the cab masters.

## How it works

Two halves meet at `vehicles/<name>.json` and the OBJ meshes beside it.

- **Offline (Python and Blender, `tools/`).** `tools/export_game_data.sh` extracts the donor meshes, textures and stock icon from the player's own install into gitignored folders. The Glyptodon family is generated: `tools/make_glyptodon.py` / `make_megaloceros.py` (sharing `tools/glyptodon_family.py`) write `vehicles/<name>.json`; the Mastodon, Megatherium and Mammoth definitions are hand-written. `tools/build_vehicle.py` builds each vehicle's body, collider and part meshes into `plugins/VehicleMods/vehicles/<name>/`. Cabs come from the Blender masters in `meshes/glyptodon/`. Icons: `tools/draw_icons.py` (Glyptodon family), `tools/trace_icons.py` (Mammoth family, traced locally from the stock icon), then `tools/rasterize_icons.py`.
- **In the game (`plugins/VehicleMods`).** The plugin clones the donor, reshapes wheelbase, track and suspension, swaps in the meshes and registers a new item ID.

## Commands

- Extract game data once per game update: `tools/export_game_data.sh "<game folder>"` (needs `.venv` from `requirements.txt`).
- Build a truck: `python3 tools/make_megaloceros.py && python3 tools/build_vehicle.py vehicles/megaloceros.json` (or `make_glyptodon` / `glyptodon.json`). Preview: `tools/preview_vehicle.sh vehicles/<name>.json`.
- Gates after any mesh change: `python3 tools/check_holes.py` on each body LOD, `python3 tools/check_slivers.py` on the built OBJs, and `python3 tools/check_names.py`. After a definition's `listing` changes: `python3 tools/catalogue.py`.
- Deploy: `cd plugins/VehicleMods && dotnet build -c Release -p:GameDir="<game folder>"` copies the DLL, every `vehicles/*` and the icons into the game folder; `-p:Deploy=false` only compiles. Deploy only with the game closed: `ps -eo comm,args | grep -F "over the hill.x86_64"` matches the grep itself, so read the process names.
- Add a truck to a save: `python3 tools/add_vehicle_to_save.py "$HOME/My Games/over the hill/Saves/Player1.json" <ItemId>` (backs up first; game closed).
- Logs: `<game>/BepInEx/LogOutput.log`, `~/.config/unity3d/Funselektor/over the hill/Player.log`.

## Working rules

- Never launch, kill or loop the game yourself; the person may be playing. Ask first.
- Nothing from the game is ever committed: extracted meshes, textures and icons stay in the gitignored folders.
- Nothing real reaches the game: in-game names, descriptions, categories and assets stay fictional, and so do file, part, tool and identifier names. Die Kollektion's own catalogue (README, CLI, pack listing) presents the real vehicle data, from each definition's `listing` block (`listing.real`: make, model, series, variant, years, description, basis); `tools/check_names.py` enforces it. `listing.real.description` is factual: what the real vehicle is, its cab, wheelbase and tyres; no personal stories. Whether the game shows real names is the player's local choice, never something a pack ships.
- Commit by path (`git add <paths>`, `git commit -- <paths>`), not `git add -A`.
- Detail target: a little above the stock vehicles. Fix visible faults and wasted triangles before adding fidelity.
