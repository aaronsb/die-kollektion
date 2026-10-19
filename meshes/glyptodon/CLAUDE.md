# Glyptodon-family cab masters: editing and content creation

The two cabs are Blender masters: `cab_glyptodon_master.blend` (two-door, Das Glyptodon) and `cab_megaloceros_master.blend` (crew cab, Das Megaloceros). They are independent files; a change meant for both is made in both.

## Who owns which part

The masters started from the reference model, imported and decimated, and were frozen as Blender files. Three idempotent scripts own the parts they generate and rewrite them on every run, in this order:

1. `tools/cab_roof.py`: `RoofFront`, `RoofRear`, `Hatch`; the plain front variant in the `Variants` collection (excluded from export).
2. `tools/cab_doors.py`: the door design (one outline for every door, front doors with the arch cutout), the shell cut, `BPillar`, jambs, seals, `SideHeader`.
3. `tools/cab_fixes.py`: rear-wall sill, intake clipping, hinge knuckles, pull handles, trims near the shut lines.

Run each as `blender -b <master> --python tools/<script>.py -- --save`. Each writes its own far LODs (`src_hash`/`far_hash`), so `build_cab_part.sh --derive` leaves them alone. A hand edit to a part a script owns is lost on its next run: change the script. Everything else (`Shell`, `Hood`, `Grille`, `Bumper`, lamps, mirrors, flares...) is reference-model geometry edited by hand.

## Layout

- Collections `LOD0`..`LOD3` (LOD1-3 hidden), one object per part, named `<Part>.LOD<n>`; `Variants` is excluded from export.
- Materials are the classes. `Paint`, `Hood`, `Glass`, `Black`, `Lamp` and `Amber` are flat colours: the export writes their atlas point (`atlas_uv` on the material) on every corner, so hand-made faces need no UVs. `HeadlampLens` keeps its own UVs (the lens graphic). Lenses must use a lamp-lens part of the donor atlas; green alone is glass.
- The integer face attribute `two_sided` marks faces written twice, back to back, for thin open parts the game would cull from behind.
- Coordinates: Z up, front toward −Y, +X is the truck's left. The OBJ export converts to car-root metres (x negated, y up, z forward).

## Editing by hand

1. Edit the `LOD0` objects only. Keep names as `<Part>.LOD<n>`, materials as the classes above, and the `two_sided` face attribute and custom props (`ratio`, `src_hash`, `far_hash`) intact.
2. Save, then `tools/build_cab_part.sh meshes/glyptodon/<cab>_master.blend --derive`: it rebuilds the far LODs of changed parts and writes `<cab>_LOD0-3.obj`.
3. Rebuild the truck (`make_*.py` + `build_vehicle.py`) and run the gates (root `CLAUDE.md`).

## Gotchas

- Blender shades the masters with the exporter's rule (smooth within 35 degrees, flat for lenses). With plain shade-smooth the reference-model panels look like melted plastic even though the game is fine.
- Part names inherited from the reference model don't always match their contents. Measure geometry before trusting a name.
- The `Shell` is open, non-manifold triangle soup: boolean modifiers misbehave on it. Cut with plane bisects and face deletion.
- Renders sample only the colour texture unless composited with the shader's mask (`tools/composite_atlas.py`): green-only mask is glass, red+green a lamp lens, blue paintable.
- File, part and tool names stay fictional; real vehicle data lives only in each definition's `listing` block.
