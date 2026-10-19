# Security

Die Kollektion Werkstatt runs a native plugin inside the game process and edits save files, so a fault in it can crash the game or damage a save. Treat those as serious.

## What to report privately

- Anything that crashes the game or corrupts a save, when you can trigger it on purpose.
- Problems in the plugin's memory handling (`DobbyNearPages`, `NearBlockPlanner`): hooks placed where other code can overwrite them, or memory claimed over existing mappings.
- A pack, manifest or tool that can make the Werkstatt write outside the game folder, the vehicle folders or `~/My Games/over the hill/`, or run code it shouldn't.
- Anything in a release zip that shouldn't be there, such as files extracted from the game.

Report it as a [private security advisory](https://github.com/aaronsb/die-kollektion/security/advisories/new). Include what you ran, what happened, `make status` output and the relevant lines from `BepInEx/LogOutput.log`.

## What to report in the open

An ordinary crash with no security angle, a build failure, or a vehicle that looks wrong: open a [bug report](https://github.com/aaronsb/die-kollektion/issues/new/choose).

## Scope

The plugin (`plugins/VehicleMods/`), the tools under `tools/`, the Makefile, the vehicle and pack manifests, and the release zips on GitHub. BepInEx, the game and mod.io are other people's projects; report their issues to them.
