# The Werkstatt Blender add-on

The add-on opens a vehicle from its folder as parts, attach points and upgrade nodes, lets you fit each accessory with stepped nudges, and saves the result to the vehicle's `placements.json`. The plugin applies that file in game, on the truck and in the mechanic's preview (format and engine facts: `docs/engine.md`, "Upgrade nodes"). The add-on only writes files; committing them is yours.

## Install

You need Blender 4.2 or newer (tested on 5.2), a Werkstatt checkout with `make extract` run (it writes `extracted/<donor>/upgrades.json`), and the vehicle built (`make build`, or `make all`).

- **From the checkout (recommended).** In Blender, open Edit > Preferences > File Paths > Script Directories, add the checkout's `blender/` folder, restart Blender, and enable "Die Kollektion Werkstatt" under Add-ons. The add-on then runs from whatever branch that checkout has open and works on that checkout.
- **From a zip.** Run `make blender-addon`, then in Blender use Edit > Preferences > Add-ons > Install from Disk on `dist/werkstatt-blender-addon.zip`. In the add-on's preferences, set "Werkstatt folder" to your checkout.

The panel is in the 3D view's sidebar (press N), tab "Werkstatt". At the top it shows the checkout, its branch and whether `vehicles/` has uncommitted changes.

## Open a vehicle

Pick the vehicle and press Open. The add-on builds one collection, "Werkstatt: <Codename>", from the vehicle's files, and leaves the rest of your scene alone:

| Collection | What it holds |
|---|---|
| `Part: <name>` | One per part (the body, the axles, the colliders), its LOD0 mesh inside, with the part's node path and source file as custom properties. The colliders are wireframes, hidden. |
| `Attach points` | Empties at the winch points, lights, wheel hubs, water detectors and centre of mass, parented to the body. |
| `References (donor, read-only)` | The donor's wheels and tyres, which the game keeps live. They're shown but can't be selected. |
| `Upgrades/<slot>` | An empty for every upgrade node, mirroring the game's tree: slot groups (plain axes), options (arrows), pieces inside an option (cubes), and copies. Each option's meshes hang under its pieces, coloured by slot. Options start hidden. |
| `Ghost` | The donor's stock body as a wireframe, beside the truck when "Ghost of the donor" is on. Set "Beside by" to 0 to overlay it. |

Everything sits where the game puts it after the reshape, including the wheelbase sweep that moves nodes behind the body cut back with the rear.

## Fit an item

1. Type a slot into the filter (e.g. `Roof`, `FrontBumper`, `Winch`, `Bed`) and press "Show slot", or use the eye on an item's row.
2. Click the item in the list. "Frame on select" points the view at it.
3. Nudge it. Pick a step (1 mm, 1 cm or 10 cm) and a multiplier (×1, ×5, ×10, ×20 or ×50), then press Left/Right, Down/Up or Back/Forward. Turn it with Pitch, Yaw and Roll, in steps of 0.1°, 0.5°, 1° or 5° times the same multiplier. Moving the empty with Blender's own G, R and S keys counts too.
4. Reset puts the item back at the donor's pose.

Directions are the truck's: right, up and forward. An item on a slot group moves every item in it. On Das Megaloceros, for example, every roof item sits about 22 cm into the taller square-cab roof, so one nudge of the `Roof` group fixes them all. Turns are about the item's own pivot. A child's moves happen in its group's frame: turn the group and its items' moves turn with it, as in game.

## Copies

Duplicate adds a copy of the selected option, or of a piece inside one: a second keg pile in Das Mastodon's bed, say. The copy starts on top of its source, so nudge it into place. In game it shows whenever the item is fitted. "Delete copy" removes a copy; an original can only be reset.

## Save, then check in game

Save placements writes `vehicles/<name>/placements.json`. Only nodes that moved are written, one line per entry, keys sorted and numbers rounded (0.1 mm, 0.001°). A nudge changes one line of the diff, and saving without changes changes no byte. With nothing moved and no copies, the file is removed.

To see it in game:

1. With the game closed, run `make deploy`. "Build and check" in the panel runs `make loop V=<vehicle>` first if you want the gates and contact sheet; its output is in the `werkstatt-loop.log` text.
2. Fit the item at the mechanic. With `make save-test`, every item is unlocked to try.
3. Commit the file on your branch and open a pull request (CONTRIBUTING.md).

## Scripts and agents

Every panel action has a scriptable equivalent, so an agent can look, nudge and save through the Blender MCP server (`execute_blender_code`), with its screenshot tools to look.

- **Operators** take plain arguments:
  - `bpy.ops.werkstatt.open_vehicle(name="megaloceros")`
  - `bpy.ops.werkstatt.nudge(node="Winch_01", axis="y", steps=2, unit="cm")`
  - `rotate(node=..., axis=..., steps=..., degrees=...)`
  - `duplicate(node=...)`, `delete_copy(node=...)`, `reset(node=...)`
  - `show(node=..., shown=...)`, `show_slot(slot=..., shown=...)`
  - `frame(node=...)`, `save()`, `run_loop()`
- **The Python API** (`from werkstatt_addon import api`) returns plain dicts that read back as JSON. A problem comes back as `{"ok": False, "error": "..."}` with a plain message, never a traceback:
  - `status()`, `vehicles()`, `open_vehicle(name, show=[...])`, `items(slot=None, kind=None)`
  - `placement(node)`, `set_placement(node, offset=, rotation=, scale=)`
  - `nudge(node, axis, steps, unit)`, `rotate(node, axis, steps, degrees)`, `scale_by(node, factor, axis=None)`
  - `reset(node)`, `show(node, shown)`, `show_slot(slot, shown)`
  - `duplicate(node)`, `delete_copy(node)`
  - `frame(node)`, which selects the item, points the view at it and returns its centre and size in game metres
  - `ghost(shown, offset)`, `save()`, `run_loop()`

  A node is a full node path or any unique end of one (`Winch_01`, `RoofSpare/RoofrackFlatA`); an ambiguous name lists its matches.

Worked example over MCP:

```python
# execute_blender_code
from werkstatt_addon import api
api.open_vehicle("megaloceros", show=["Roof/RoofSpare"])
api.frame("RoofSpare/RoofrackFlatA")        # then take a viewport screenshot and look
api.nudge("Visual/Roof", "y", 2, "cm")      # the roof slot group: every roof item 2 cm up
api.placement("Visual/Roof")                # {'ok': True, 'offset': [0.0, 0.02, 0.0], ...}
api.save()                                  # {'ok': True, 'file': 'vehicles/megaloceros/placements.json', 'result': 'written', ...}
```

`tests/blender/test_addon.py` runs the same calls headless (`blender -b`), on a scratch copy of the vehicle folder. `make check` runs it when Blender is installed.

## Later: a new vehicle from geometry

The scene is the vehicle's own structure (parts, attach points, references), not something built only for placements. A future "new vehicle" can therefore start from the same scene, with the same save writing more of it. Not built yet; the intended flow:

1. Import your mesh (OBJ, FBX, glTF).
2. Assign it as the body part, or as a part with a node path.
3. Align the axles: wheel hubs snap to the donor's references; the wheelbase and track follow from them.
4. Place the attach points (winch, lights, roof and bed anchors, upgrade slots) as empties on their parts.
5. Generate colliders and LODs from the body (simplified hulls, decimated LODs), editable like any part.
6. Save. The same writer adds the meshes into the vehicle folder and the manifest (`vehicle.json`, parts, ops) beside `placements.json`.
7. Run `make loop V=<vehicle>`, read the contact sheet, deploy, drive.

The add-on is layered for this (`blender/addons/werkstatt_addon/`): `model.py` reads and writes the files with no Blender, `scene.py` turns the model into the scene and back, and `api.py` and `ui.py` sit on top. Writing meshes or ops is a new writer in `model.py` plus what `scene.py` collects; the scene and API stay as they are.

## Limits

- Scale on a node that the game turns relative to the car shows along the car's axes in Blender but along the node's own axes in game; most upgrade nodes aren't turned, so it matches.
- Meshes are flat-coloured, without the game's textures and lights. Check the final fit in the mechanic.
- Only LOD0 is loaded. Placements move every LOD alike in game.
