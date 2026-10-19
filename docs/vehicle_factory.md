# Vehicle factory: packs, pipelines, lifecycle, tools

**Design draft (October 2026).** Nothing here is final or built yet unless it says so. Die Kollektion is the mod players install; Die Kollektion Werkstatt is the authoring toolkit (the Blender add-on, the vehicle templates and the CLI's authoring commands). **[research]** marks a question offline research answers (findings are summarised at the end); **[decide]** marks an open choice; **[test]** marks one only an in-game run settles.

## Direction (author, 2026-10-19)

- **A factory, not a fixed set.** Die Kollektion's own trucks are the first content, built with the same pipeline anyone else uses.
- **Two pipelines:**
  - **Patch:** change an existing vehicle (its meshes, upgrade objects, suspension, steering). The factory exposes the vehicle's slots, states and geometry for authoring in Blender and as an editor.
  - **New vehicle:** a new item on a stock donor, in a vehicle category of its own. A pack can create a category: ours is "Die Kollektion", and anyone can make another.
- Each item is a definition (JSON with comments) and a directory. Items ship in **packs**: one compressed file each.
- **Lifecycle:** packs install and uninstall, and removing them brings the game back to stock, or at least to a stable state that survives Steam's "verify integrity of game files".
- **Cross-platform tools:** the CLI and the plugin run on Linux and Windows, cross-compiled from Linux.

## Goals and non-goals

Goals:
- One definition per item; everything the game reads is built from it.
- Packs that carry no game assets: donor-derived geometry is built on the player's machine from their own install.
- A save that stays valid when a pack or the whole mod is removed.
- One command for each authoring and lifecycle step, refusing unsafe states (game running, no backup, failed gate).
- Authoring that starts from an exported stock vehicle in Blender.

Non-goals:
- Cheats such as money, unlock-all or fog of war; existing tools cover them.
- New physics or VPP behaviour beyond what a definition sets: wheelbase, track, steer, tyre, suspension.
- Asset bundles or new shaders. Items use a donor's prefab and shader; their textures may be their own (see Textures).
- A standalone GUI for now. The Blender add-on is the visual editor; a GUI can wrap the CLI later.

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
7. **Deploy.** `dotnet build -c Release` copies the DLL and, from every vehicle folder, its manifest, built OBJs and icon into `BepInEx/plugins/VehicleMods/`, with no check that the game is closed.
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
  ├── CLI            `kollektion`, self-contained single file per OS (linux-x64, win-x64)
Blender add-on       Python inside Blender, any OS: import an authoring scene, export an item directory
Internal tools       our Python (Glyptodon-family generator, cab scripts, gates, previews); never shipped
```

- **Core** holds everything both sides must agree on:
  - the pack format and definition schema (JSON with comments: the plugin already parses with `JsonDocument` and needs only `JsonDocumentOptions { CommentHandling = Skip, AllowTrailingCommas = true }`);
  - OBJ reading and writing (today's `ObjMesh.cs`, with bone weights);
  - the mesh operations, ported from `meshlib.py`: stretch, stretchPieces, removeRegion, removePieces, movePieces, relocatePiece, insertPart, paint, addBoxes, portalAxle, coilSprings, widenPieces;
  - the donor reader: donor meshes and prefab facts read from the player's Addressables bundles with a managed bundle reader (AssetsTools.NET or similar, pure managed, no IL2CPP), so it is safe from the plugin's background thread;
  - save reading and editing; ItemId issuing; per-OS paths (Steam library via `libraryfolders.vdf`, game folder, save folder, game process name).
- **Plugin** keeps today's invariants: no class injection; all patches from the `GameStateManager.Transition` entry hook; Load touches no IL2CPP type; `DobbyNearPages` is Linux-only (`/proc/self/maps`, `libdobby.so`) and must be a logged no-op elsewhere.
- **CLI** is built with `dotnet publish -r <rid> --self-contained -p:PublishSingleFile=true` for `linux-x64` and `win-x64` from this machine (SDK 10.0; Core and the plugin target net6.0, the CLI can target a newer framework). Building for Windows needs no Windows; running there does (see Windows).
- **Blender add-on**: Blender's scripting is Python on every OS, so authoring stays Python. It never touches the save or the game folder.
- **Internal tools** keep building our own trucks. As the operations move into Core, `build_vehicle.py`'s role shrinks to emitting operation lists, and `meshlib.py` retires once Core reproduces its outputs.

## Items and the two pipelines

An **item** is one thing a pack adds or changes. Every item has a directory and an `item.json`.

**Vehicle item** (new vehicle):
```jsonc
{
  "schema": 1,
  "kind": "vehicle",
  "codename": "Megaloceros",
  "itemId": 3000000004,            // ours keep their IDs; new items get a hashed ID (see ItemIds)
  "names": {"en": {"name": "Das Megaloceros", "description": "..."}},   // in-game; other locales fall back to en
  "listing": {                      // Die Kollektion's catalogue only; never written into the game
    "family": "Glyptodon", "variant": "crew cab",
    "real": {"make": "...", "model": "...", "series": "...", "variant": "...", "years": "...",
             "basis": "styled on the two-door; no factory crew cab existed, wheelbase from the long crew-cab drawing",
             "description": "..."}   // factual description of the real vehicle for the catalogue; no personal stories
  },
  "category": "kollektion/die-kollektion",   // a category from this or another pack, or a stock one
  "donor": "Mammoth",
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
"base": {"car": "Mammoth", "gameBuild": "<Steam build id>", "hash": "<hash of the extracted base>"}
```
- A **patch** changes its base in place; a **vehicle** clones its base into a new item. Both are "base plus differences": operations on base meshes, replaced or added meshes, transform overrides, chassis and suspension values, upgrade changes, textures. Anything not mentioned is the base's, so a game update that changes the base flows through.
- `hash` is taken over the extracted base data the item was authored against. When the player's game differs (`gameBuild` or `hash`), the plugin rebuilds the item against the new base and logs one warning; an operation whose selection no longer matches fails that item with a message naming the part, rather than producing a broken mesh.
- The Blender add-on writes exactly this: it diffs the edited scene against the extracted base (`baseline.json`) and exports only the changes.
- This replaces the separate `donor` (vehicle) and `target` (patch) fields below.

**Tweaking a stock vehicle is the main path (author):** most people only want to change an existing car, so that path is the shortest. `kollektion new patch <Car>` writes an item with the `base` pointer and an empty difference, listing every chassis and suspension value with the base's current number as a comment. Changing a number and running `kollektion build && kollektion install` is the whole job, with no Blender. Geometry and upgrade changes add Blender on top of the same item.

**Names: fictional in the game, real in the catalogue (author, 2026-10-19).** Nothing real reaches Over the Hill: in-game names, descriptions, category names, icons, liveries and textures stay fictional, and so do file, part and tool names. Die Kollektion itself always presents the real data: `listing.real` (make, model, series, variant, years, `basis` saying how faithful the item is, and `description`, a factual description of the real vehicle; no personal stories) feeds the README catalogue, `kollektion list`/`info`, `pack.json` and the Nexus page text. `kollektion check` fails an item whose in-game strings contain any word of its `listing.real` make or model, or of a fixed list of manufacturer and model names. Showing the real name in the game is the player's choice, never the pack's: `kollektion names real|fictional [item…]` writes a local override file (`<mygames>/DieKollektion/names.json`) that the plugin applies over the pack's in-game names, built from `listing.real`. Packs never ship it, and the check doesn't apply to it.

**Patch item** (existing vehicle): the same blocks, with `"kind": "patch"` and `"target": "Mammoth"` in place of codename, itemId, names, category and donor. Mesh, transform and chassis changes never get an ItemId or touch the save, so removing them returns the car to stock. Upgrade changes, cheapest first:
1. Full rotation and scale on transforms (today: position and yaw only).
2. Withdraw an option for one car: the car gets its own copy of its upgrade list (derived trucks share the donor's today).
3. Conditional visibility: a node shown or hidden by what else is mounted (the hatch versus the AC unit or camper).
4. New options: a new upgrade item with its own ItemId, which the save then holds, so it falls under the same lifecycle rules as a vehicle item.

The upgrade model: an upgrade node (`VehicleUpgradeObject`, all off in the prefab) names one item (`vehiclePartReference`) and shows when that item is mounted. The slot is the item's `CosmeticType` (the Mammoth uses 11: FrontSection, RearSection, FrontBumper, RearBumper, Roof, RoofLights, Bed, Fenders, SideSection, SideStep, Antenna). One item can drive several nodes, and `LinkedParts` pulls in other items (antenna toppers show the base). Each car offers its own `UpgradesLists` (209 entries on the Mammoth). The mounted state is a 256-bit set, inferred to index that list, which would leave room for about 40-55 new options per car **[test or disassembly]**. Item catalogue and cosmetic meshes are shared across cars; placement (full TRS, often non-uniform scale) is per car.

**Category item**: an id, an asset name and names in all locales.
- A category is a `VehicleControllerSetup` asset that `CarInfo.carCategorySetup` points at. The four stock ones are `CarCategory_01_Trail` .. `04_Expedition`, each with a `CategoryName` (Content table string), a `HapticCategory` enum and a physics template (mass, steering, gearbox, engine tiers, tyre, suspension). No runtime reader of the physics block was found.
- The merchant's `InitializeSelectVehicleScreen` groups every catalog vehicle by its category object, sorts the categories by asset name (ordinal), and makes one section per category, with no cap. A null category throws there.
- The plugin clones a base category (default: the donor's) with `Object.Instantiate`, unedited apart from its name and `CategoryName`, marks it `DontUnloadUnusedAsset`, and points each item's `CarInfo` at it. The asset name sets the order, so it follows `CarCategory_NN_<Name>`; ours is `CarCategory_05_DieKollektion`. Items naming the same category share one instance. An unresolvable category falls back to the donor's.
- Stock categories have no filter buttons in the merchant; the filter buttons belong to the mod.io livery browser, which lists only cars with mod.io tags.

**Mesh sources.** A mesh is built from one of:
- `from: "donor"` plus `ops`: the donor's own mesh, read from the player's install, then edited. This is how donor geometry reaches the game without shipping it.
- `from: "<file>.obj"`: the item's own geometry (cabs, boxes, frames, beds we modelled).
- both, merged: `add` lists own OBJs appended after the donor's ops.

Gates and the pack build refuse an own OBJ that is a copy of donor geometry: Core compares vertex sets against the donor mesh and flags a high match **[decide: threshold, or advisory only]**.

**Families.** The Glyptodon-family generator (`tools/glyptodon_family.py`) stays Python on our side. It writes the item directory: `item.json`, the operation lists and our own OBJs. Families are an authoring convenience; the runtime sees only items.

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

## What ships (author, 2026-10-19)

Die Kollektion's first release:

| Kind | Item | Built from |
|---|---|---|
| Patch | Das Mammoth: coil springs (with the portal axles), side exhaust, suspension parameters (with the steering lock); each its own item, added and removed independently | operations on the player's Mammoth |
| Patch | Canary: one golf bag with clubs, strapped to the roof of the first vehicle a new player drives | our own geometry and SVG map |
| Patch | Patch template: an empty, commented patch item to fill in | nothing |
| Vehicle | The Mammoth-family pair, Das Mastodon and Das Megatherium | the player's Mammoth and the mechanic's truck, extracted locally, plus operations |
| Vehicle | The Glyptodon-family pair, Das Glyptodon and Das Megaloceros | our own cabs and parts, plus Mammoth axles, wheels and bed parts extracted locally |
| Template | The example vehicle (also the integration test) | our own geometry plus the donor, extracted locally |
| Category | Die Kollektion | a clone of the donor's category |

**Nothing extracted from the game ships.** The Mastodon and Megatherium are mostly Mammoth and mechanic's-truck geometry, so their packs carry only operations and our own parts. **The extractor** (Core's donor reader) pulls the parts out of the player's own install: the plugin runs it on first load to fill its cache, and Werkstatt exposes it for anyone who wants to mod their own thing:
- `kollektion extract --list` enumerates every vehicle in the player's install: catalogued cars, CatalogExcluded ones (Baguette, Grizzly), mesh-only leftovers (`BullV1`, `DingDing_SUV_CosmeticParts`) and scene vehicles (the mechanic's truck), with template type, category, dimensions and slot counts.
- `kollektion extract <Car> <dir>` writes the car as an item directory: body LODs, colliders, axles with bone weights, wheels, every upgrade option, its four texture maps as PNG, attach points and node facts. This is what the Blender add-on imports.
- `kollektion extract <Car> --pack <file>.kpack` (or `--all`) writes a pack from the game: a stock car as a ready-made patch item that changes nothing, to copy and edit.
- Everything extracted is marked `"origin": "extracted"` in its item and file hashes. Such packs install locally, and `kollektion pack` refuses to build a distributable pack containing any extracted file, so the tool itself enforces the rule. It reads the cars bundle (vehicle prefabs) and the scene bundles (the mechanic's truck and camper body live in the `r1_canada` scene bundle, at scale 100 with an offset; see `docs/engine.md`), and writes OBJ with bone weights and node facts in the same form `export_car_mesh.py` and `export_named_mesh.py` do today, which it replaces.

## Examples and the integration test (author, 2026-10-19)

A newcomer learns the factory from two worked examples that ship with Werkstatt, and the same two are the integration test.

- **Example vehicle** (`examples/template-vehicle/`): one new vehicle that uses every component once: a template type and donor, attach points, own geometry with LODs and colliders, an SVG texture map, an upgrade slot with an option, a category, names and `listing`. A newcomer builds it with one command and gets a pack that installs and spawns. CI builds and gates it on every push (the build needs donor data, so CI uses a small fixture extracted from the donor and kept out of the public repo, or runs only the steps that don't need it **[decide at implementation]**); a release is preceded by one in-game spawn of it, run by the author.
- **Canary patch** (`examples/first-patch/`): a trivial patch on the vehicle a new player drives first (which car that is: **[research]**): one golf bag with clubs strapped to the roof, own geometry at the roof attach point with its own SVG map. No ItemId, no save change; installing shows the bag, uninstalling removes it.
- **Our Mammoth patch becomes separate patch items** that install and uninstall independently: coil springs with the portal axles, the side-exit exhaust, and the suspension parameters with the steering lock. Each is its own `item.json` in Die Kollektion's pack, and `kollektion install/uninstall <pack>/<item>` toggles one.

**Patch composition.** Several patches may target one car. Each patch item declares what it touches (mesh nodes, transforms, chassis fields). Operation lists on the same donor mesh compose in install order; a whole-mesh replacement or two values for the same chassis field conflict, and `kollektion install` refuses the second with both names unless the author sets an order. Removing a patch rebuilds the car from stock plus the remaining patches, so removal never leaves residue. Later, a patch could become an in-game upgrade option (coil springs as a garage choice), which gives it an ItemId and puts it under the save rules.

## Packs

A pack is a zip with the extension `.kpack`:

```
pack.json                # id ("<author>/<pack>"), version, schema, title, author, requires (plugin version range),
                         # builtAgainst (game build), items[] (directory, kind, codename/target, itemId), file hashes
items/<item>/item.json
items/<item>/meshes/*.obj
items/<item>/ops/*.json
items/<item>/icon.png
items/<item>/textures/*.svg, *.png  # optional own texture maps: SVG source, rendered PNG (see Textures)
categories/<id>.json
```

- The plugin reads entries in place (`System.IO.Compression.ZipArchive`); nothing is unzipped into the game folder.
- Meshes it builds from donor plus ops go to a cache, `BepInEx/cache/DieKollektion/<pack>/<hash>/`, keyed by the item's file hashes, the Core version and the game build. Deleting the cache only costs a rebuild on the next start. Building runs on the plugin's background thread before the entry hook, so the first launch after an install or game update is slower.
- One pack can hold many items. Die Kollektion's pack holds four vehicles, the Mammoth patch and the "Die Kollektion" category.

## Install layout and lifecycle

```
<game>/BepInEx/plugins/DieKollektion/
  DieKollektion.dll, Kollektion.Core.dll, <bundle-reader>.dll
  packs/*.kpack                          # installed packs
  installed.json                         # what the CLI installed: packs, versions, ItemIds, hashes
<game>/BepInEx/cache/DieKollektion/      # built meshes; disposable
<mygames>/DieKollektion/<profile>.json  # mod-owned save entries (the sidecar)
<mygames>/DieKollektion/backups/         # save backups, last 10 per profile
```

`<mygames>` is the game's documents folder: `~/My Games/over the hill` on Linux, probably `Documents\My Games\over the hill` on Windows (inferred). Our files sit outside `Saves/`, so Steam Cloud, which syncs the whole `Saves` folder, never carries them, and outside the game folder, so verify and uninstall leave them alone. (`tools/add_vehicle_to_save.py`'s backups, `Player1.json.pre-mod-*`, sit in `Saves/` and are cloud-synced; they move.)

Stable states, from most to least modded:
1. **Pack removed:** its items are gone and the save is valid.
2. **Die Kollektion removed** (delete `plugins/DieKollektion` and the cache): the save is valid, and only BepInEx remains.
3. **BepInEx removed** (or its Steam launch option dropped): stock game. BepInEx belongs to the author; the README explains it.

Steam's verify restores the game's own files and leaves extra files and the saves alone (expected; **[test]** once). Nothing here modifies a game file, so verify neither breaks nor uninstalls the mod. On Linux, BepInEx runs only through the launch option `"./run_bepinex.sh" %command%`.

**The save**. The game loads with `StateProfileManagementSystem.Open` → `OverlandSaver.LoadGame` → `ProfileSave.Deserialize`, `ProfileSaveMigration.Migrate`, `DlcManager.EnforceEntitlements` (falling back to `Player1.json.bak`), and saves with `OverlandSaver.SaveGame` → `ProfileSave.Serialize` → `SaveJson`. The first load and first save of a session both happen before our entry hook. Our IDs 3000000001-4 survive load, migration, entitlements and save every session today, so an unknown ID doesn't break loading or saving; what the menus do with an unknown *current* vehicle is untested **[test]**.

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
- New items get `fnv1a32("<author>/<pack>/<codename>")`, moved out of the stock values and our block on collision, issued once by `kollektion new` and written into `item.json`. After that the ID is the item's identity: renaming the item doesn't change it.
- `Catalog.Add` already refuses an ItemId owned by another item; the plugin logs both claimants and skips the later pack.

## Runtime contract (plugin)

- At Load (no IL2CPP): list `packs/*.kpack`, read each `pack.json`, check `schema` and `requires` against the plugin, check `builtAgainst` against the running game build (a mismatch is one warning), and build stale cache entries on the background thread.
- At the entry hook: register categories, then items, each in its own try/catch so one bad item never stops the others or the game. Log lines start with `<pack>/<item>` so `grep` finds them.
- Validation before any IL2CPP work for an item: files present, OBJs parse, ItemId free, codename unique, donor or target in the catalog, category resolvable. Node paths are checked on the first spawn of the donor prefab; a missing node disables that item's reshape with a log line.
- Patch items apply to the stock car's spawns; vehicle items work as derived vehicles do today.

## CLI surface

Authoring:
- `kollektion new vehicle|patch|category <Codename> --donor <Car>`: an item directory from a template, ItemId issued.
- `kollektion extract --list | <Car> <dir> | <Car> --pack <file>`: enumerate the install's vehicles, or extract one as an item directory or a local pack (see What ships). Output contains game assets and stays on the author's machine.
- `kollektion build <item dir|pack dir>`: run the operations against the local donor, write the cache, run the gates.
- `kollektion check`: gates only: holes, slivers, node paths, ItemId, codename, donor-copy check.
- `kollektion pack <dir> -o <file>.kpack`: refuses on a failed gate.
- `kollektion diff <a.kpack> <b.kpack>`: item and file changes between two pack versions.

Lifecycle (each refuses while the game runs):
- `kollektion install <file>.kpack`, `kollektion uninstall <pack>` (runs `save clean` for saves written before the sidecar), `kollektion list`, `kollektion status` (packs, cache, save agreement, game running).
- `kollektion save list|add|remove|clean|backup|restore`.
- `kollektion stock`: uninstall every pack, clean the save, remove the cache, leave the plugin.

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

- The CLI cross-compiles; the plugin is AnyCPU net6.0 and loads under BepInEx 6 IL2CPP win-x64.
- `DobbyNearPages` is a logged no-op off Linux. Whether Windows needs its own guard against Dobby's near pages colliding with coreclr is unknown; Windows' allocator and layout differ.
- Paths: the documents folder on Windows (inferred: `Documents\\My Games\\over the hill`) **[test]**; the Steam library from `libraryfolders.vdf` on both.
- A Windows run (machine or VM) is required before a release says it supports Windows. The Vehicle Flipper (be.788, Windows x64) shows BepInEx 6 IL2CPP runs there.

## Compatibility

- We patch `GameStateManager.Transition`, `VehicleBase.Spawned`, `VehicleCustomizationController.Spawned`, `LocalVehicleCustomizationController.RefreshMountedUpgrades`, the prefab-address getters, and, depending on research, the save path. Categories need no patch.
- Mods touching the same (Air Ride's suspension, Cosmetic Stacker, camera mods reading car bounds) need a joint test.
- BepInEx only for now. Core has no loader references, so a MelonLoader build later rewrites only the hooks.

## Distribution: GitHub first, Nexus mirrors it (author, 2026-10-19)

The mod is always installable straight from GitHub; Nexus is where players find it, and nothing depends on it.
- **GitHub Releases are the source of every artifact,** built by a tag-triggered Actions workflow on an Ubuntu runner (which cross-compiles both OSes):
  - `DieKollektion-<ver>.zip`: the `BepInEx/plugins/DieKollektion/` folder (DLLs, our `.kpack`, README), extracted into the game folder by hand;
  - `kollektion-<ver>-linux-x64` and `kollektion-<ver>-win-x64.exe`;
  - `die-kollektion-<ver>.kpack` on its own, for installing with the CLI;
  - `checksums.txt`.
- **Nexus** gets the same zip, uploaded by hand per release, with the page linking to GitHub. No Vortex-only install path and no Nexus-only files.
- **The README** in the repo is the install guide: BepInEx 6 IL2CPP version, the Linux launch option, extract, uninstall order, Steam Cloud.
- **Third-party packs** publish on their own GitHub releases (or anywhere): `kollektion install <file|url>`, where `github:<owner>/<repo>[@tag]` fetches the release's `.kpack` asset. No central index for now.

What is public: the factory (Core, plugin, CLI, add-on), our pack sources (`item.json`, operations, our own OBJs, icons we drew), our Python tools, and the notes with branding removed. What never is: meshes, textures and icons extracted from the game, reference photos and drawings, and real manufacturer or model names outside the catalogue.

Decided (author, 2026-10-19):
- **A public repository** with a clean history from its first commit.
- **Code** (Core, plugin, CLI, Blender add-on, tools): **GPL-3.0-or-later**. Commercial reuse is allowed only with the complete source under the same licence.
- **Art** (cab models, generated parts, icons, our pack content): **CC BY-SA 4.0**.
- The licence text states that packs are data, not derivative works of the plugin; pack authors license their packs as they choose.

## Migration plan

Each step is reversible and has a check. Steps 1-4 change no game-visible behaviour.

1. **Golden outputs.** Hash every built file (OBJs, the runtime fields of each JSON, icons) into `build/golden.json`. *Check:* a rebuild with today's commands reproduces it.
2. **Core and CLI skeleton.** `Kollektion.Core` with the definition schema, OBJ I/O and pack read/write; `kollektion pack` packages today's built outputs, donor-derived meshes included, as a private pack (not for release). *Check:* unpacking reproduces golden.
3. **Plugin reads packs,** falling back to `vehicles/*.json` for one release; per-item validation and fail-soft registration. *Check:* the author spawns each truck once.
4. **Lifecycle commands:** install, uninstall, list, status, refusing while the game runs; gates fail `pack`. *Check:* a planted hole fails; a running-game probe refuses; install then uninstall leaves the plugin folder as before.
5. **Save:** the sidecar and `save clean`, then the unknown-current-vehicle **[test]**. *Check:* a save round trip (install, drive, uninstall, reinstall) on a copy of a real save.
6. **Categories:** the "Die Kollektion" category. *Check:* the author sees a fifth merchant section holding our four, and every section still navigates.
7. **Operations in Core:** port `meshlib.py`; the plugin builds donor-derived meshes from the player's bundles into the cache; our pack drops donor geometry. *Check:* cache OBJs match golden geometry within float tolerance.
8. **Export, Blender add-on and vehicle template,** starting with the Mammoth (the upgrade-slot audit is the first use). *Check:* export, import, export again without edits gives an empty patch.
9. **Windows and release:** the public GitHub repo, the release workflow, the win-x64 CLI, a Windows test, the README, then the Nexus upload of the same zip. *Check:* a clean BepInEx install in a copy of the game folder (not a player's own) loads the pack from the GitHub release zip.

## Open questions

- **[test]** What the game does with a save entry for an unknown ItemId. Needs one launch with a test save; run by hand.
- **[test]** Steam verify leaves extra files in the game folder.
- **[decide]** The donor-copy check: a threshold that fails the pack, or advisory only.
- **[decide]** Which donors after the Mammoth for templates and export.
- **[test or disassembly]** For upgrades: whether nodes added in the `VehicleBase.Spawned` prefix register in time; whether the 256-bit mounted state indexes the car's upgrade list; whether the garage enforces one option per slot; what drives the `rollcage` and `Winch_01` nodes (no item); how the lights controller finds its lights (decides whether a cloned light works). No disassembler is installed; one logged launch would answer most.
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
