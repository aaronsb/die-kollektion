# VehicleMods plugin

The BepInEx 6 IL2CPP plugin ("Die Kollektion") that puts the trucks in the game. At load it reads the deployed `vehicles/*.json` (schema: `VehicleDefinition.cs`) and the OBJ meshes beside them; the deploy step copies them there from each source folder `vehicles/<name>/` (`vehicle.json`, `build/*.obj`, `icon.png`).

## Load sequence

1. `Plugin.Load` touches no IL2CPP type. It starts a background thread that sleeps 2 s, then waits for `[AddressablesPreLoader] Addressables finished loading` in Player.log.
2. `DobbyNearPages` moves Dobby's hook slots onto pages of our own, then the thread patches only `GameStateManager.Transition` (`MainThreadEntry`).
3. That hook's first call (main thread, before the main menu) applies every other `[HarmonyPatch]` class independently and registers the cars.
4. `MenuSentinel` appends a status line to the main menu's build label (`ContextUIMainMenu.BuildVersionLabel`) from a `StateMainMenu.Update` postfix: version, vehicles and patches registered out of those defined, trucks that kept the donor's name or icon, failed game hooks; amber (when the label takes rich text) with a pointer to `BepInEx/LogOutput.log` when anything is short or no vehicles were found. It writes the game's own label text and creates nothing. It checks every frame until the line is in, then every 30 frames, because the game may rewrite the label after the menu opens. No line means stock (confirmed in game 2026-10-19: the line shows at the bottom of the menu); on a working install without it the `Main menu:` log line reports whether the label was enabled and active.
5. `DerivedVehicles` clones the donor `CarInfo`, maps the new prefab addresses back to the donor's prefab, and on spawn reshapes the clone: wheelbase, track, steering, suspension, meshes, colliders, the spare wheel (`AddSpare`) and, for a definition with a `headlights` block, the headlights' colour and intensity (`ApplyHeadlights`: every stock car shares one `HeadLightConfig` asset, so the vehicle gets its own copy; the lens glow is a shader scalar and stays the game's). `HiddenCars` un-hides Rancho and Grizzly. `Catalog` and `LocalizedText` add the names.

## Invariants

- No class injection: no `AddComponent` of plugin types, no managed delegates handed to the game. It crashes the game.
- Patch only from the `GameStateManager.Transition` entry hook.
- Plugin threads catch everything; an escaping exception aborts the game.
- Photon Fusion only spawns prefabs registered at build time, so every vehicle shares its donor's prefab and is reshaped on spawn.

## Hook pages (`DobbyNearPages.cs`)

Dobby keeps each hook's 8-byte jump slot and relocated prologue in near pages that can fall inside coreclr's executable reservation; once coreclr commits that memory, the next call through a hook jumps into garbage (the mechanic twice on 2026-10-18; the logo after a game update on 2026-10-19). `Plugin.Load` calls `DobbyNearPages.Reserve()`, which claims a 4 MB block chosen by `NearBlockPlanner.cs` (pure logic over /proc/self/maps: an unmapped gap within 1 GB of GameAssembly's code, else the top of coreclr's reservation); `Install()` re-validates it before the hooks and returns false when nothing is safe, and then the plugin installs no hooks. Details and the evidence: `docs/engine.md`, "Hook pages". A healthy start logs:

- `Dobby pages: reserved at Load: Gap …` or `… ReservationTop …`
- `Dobby pages: using 0x…-0x… of the 0x…-0x… block`
- `Dobby pages: 0x… holds 64 bytes of slots` (all eight hooks)
- `Main menu: Die Kollektion <version> | 4 vehicles, 2 patches registered (label enabled True, active in hierarchy True)` when the menu first shows

`No hooks installed: Die Kollektion is inactive this session` means no safe place was found: the game runs without the mod. Capture `/proc/<pid>/maps` while it runs, add it to `tests/maps/` and fix `NearBlockPlanner`. Change the planner only with `make check` green over every captured layout.

## Crashes

Player.log ends with `Received signal SIGSEGV` but no native stack. Use the core: `coredumpctl list`, then gdb on the core; find `__restore_rt` on the main thread's stack (Unity's alternate signal stack), read the ucontext RIP at uc+40+16*8, map it to a module and offset (`tools/resolve_crash.py`, `decomp/`). A RIP of garbage after a `call` into a GameAssembly function that starts `ff 25` means a damaged hook slot.

## Build

`dotnet build -c Release` builds and deploys the DLL and each vehicle folder's definition, built meshes and icon into `<game>/BepInEx/plugins/VehicleMods/` (or `-p:DeployDir=<dir>`); `-p:Deploy=false` only compiles. The game folder defaults to Steam's default library; pass `-p:GameDir=<path>` (or set `GameDir` in the environment) for any other. The game must be closed. Each vehicle's `build/` folder is build output (gitignored).
