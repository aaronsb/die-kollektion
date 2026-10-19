# Die Kollektion

New vehicles for *Over the Hill*, built on the game's own trucks.

Die Kollektion is a BepInEx 6 IL2CPP mod that adds trucks to the game's merchant: each one is a stock donor reshaped at runtime (wheelbase, track, suspension, steering, tyres) and re-meshed with our own parts, under a new item ID. It is early: four trucks and a patch for the stock Mammoth, tested on the native Linux build. It is heading toward a vehicle factory, where anyone can author new vehicles and patches as packs with **Die Kollektion Werkstatt**, the authoring toolkit (Blender add-on, vehicle templates and a cross-platform CLI); the design draft is in [`docs/vehicle_factory.md`](docs/vehicle_factory.md).

## The catalogue

In the game every vehicle has a fictional name. Here is what each one is modelled on.

<!-- catalogue -->
| In game | Family | Variant | Real vehicle | Series | About the real vehicle | How faithful |
|---|---|---|---|---|---|---|
| Das Glyptodon | Glyptodon | two-door | Mercedes-Benz Unimog U 1300 L, two-door cab | 435 | A two-door truck of the 435 series with an angular cab on a 3.25 m wheelbase and a 1.86 m track, on 14.5R20 tyres (1090 mm across). Steel drop-side bed, black plastic fender flares, slatted black grille, black steel bumper carrying the headlamps, and a raised air intake on the right A-pillar. | Modelled from photos and a dimensioned drawing: wheelbase, track, tyre size, bed length and ride height follow them. |
| Das Megaloceros | Glyptodon | crew cab | Mercedes-Benz Unimog U 1300 L (styled), crew cab | 435 | No crew-cab U 1300 L was built. The nearest real reference is the U 1550 L/37 crew cab: 3.70 m wheelbase, 5.56 m overall, 1.01 m front overhang, a 2.70 m body starting 70 mm behind the cab, and a 15.8 m turning circle on 12.5R20 tyres. | Fictional: this model never came as a crew cab. The two-door's front and running gear with a crew cab, on the 3.70 m wheelbase of the U 1550 L/37 crew-cab drawing. |
| Das Mastodon | Mammoth | two-door, long wheelbase | Mercedes-Benz Unimog U 1100 L, two-door cab | 416 | A two-door truck of the 416 series with the rounded cab. | The game's Mammoth on a 2.90 m wheelbase with the mechanic truck's single cab and front, portal axles, coil springs and a ribbed steel bed. |
| Das Megatherium | Mammoth | crew cab, long wheelbase | Mercedes-Benz Unimog U 1100, crew cab | 416 | A crew-cab truck of the 416 series with the rounded cab. | The game's Mammoth crew cab on a 2.90 m wheelbase with portal axles, coil springs, a side-exit exhaust and a ribbed steel bed. |
| Mammoth (patch on the stock car) | Mammoth | stock, patched | – | – | – | A patch on the game's stock Mammoth: portal axles, coil springs, side-exit exhaust and more steering lock. |
<!-- /catalogue -->

## Making your own

Most people will want to tweak a stock car rather than build a new one, so that is the shortest path in Die Kollektion Werkstatt: `kollektion new patch <Car>` writes a patch listing every chassis and suspension value with the car's current number as a commented default. Change a number, build, install; no Blender. Geometry and upgrade changes add Blender on top of the same patch. The CLI isn't built yet; [`docs/vehicle_factory.md`](docs/vehicle_factory.md) has the design.

## Installing

There are no release builds yet; build from source (below). Releases will be published here on GitHub first.

1. Install [BepInEx 6 IL2CPP](https://builds.bepinex.dev/projects/bepinex_be) (tested with be.789, linux-x64) into the game folder, and on Linux set the Steam launch options to `"./run_bepinex.sh" %command%`. In `BepInEx/config/BepInEx.cfg`, set `UnityLogListening = false`; the game crashes with it on.
2. Build and deploy Die Kollektion with the game closed (below).
3. Buy the trucks at the merchant, or add them to a save with `tools/add_vehicle_to_save.py`.

**Your save.** Back up `~/My Games/over the hill/Saves/` before you start, and edit a save only with the game closed (and Steam Cloud in mind). A save that holds one of these trucks still lists it after the mod is removed; how the game treats that is not yet tested.

## Building from source

You need the game installed, Python 3 with the packages in `requirements.txt`, Blender 5.x, `rsvg-convert` and the .NET SDK.

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
tools/export_game_data.sh "<game folder>"    # donor meshes, textures and icons from your own install
python3 tools/make_glyptodon.py && python3 tools/make_megaloceros.py
for v in vehicles/*.json; do python3 tools/build_vehicle.py "$v"; done
python3 tools/trace_icons.py && python3 -I tools/rasterize_icons.py
cd plugins/VehicleMods && dotnet build -c Release -p:GameDir="<game folder>"
```

The last step deploys into `<game folder>/BepInEx/plugins/VehicleMods/`; add `-p:Deploy=false` to only compile. Nothing taken from the game is committed here: the export step writes it into gitignored folders on your machine.

## Documentation

- [`docs/engine.md`](docs/engine.md): what we know about the game as a modding target, the crash rules the plugin follows, and the mesh pipeline.
- [`docs/vehicle_factory.md`](docs/vehicle_factory.md): the design draft for packs, the two pipelines (new vehicles and patches), lifecycle, and Die Kollektion Werkstatt.
- [`CLAUDE.md`](CLAUDE.md): commands, gates and working rules.

## Licence

Code is GPL-3.0-or-later; art (models, meshes, icons, vehicle definitions) is CC BY-SA 4.0. Packs are data, not derivative works of the plugin. See [`COPYING.md`](COPYING.md). Not affiliated with Funselektor or with any vehicle manufacturer.
