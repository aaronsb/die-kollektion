# VehicleMods plugin

The BepInEx 6 IL2CPP plugin ("Die Kollektion") that puts the trucks in the game. It reads `vehicles/*.json` (schema: `VehicleDefinition.cs`) and the OBJ meshes beside them at load.

## Load sequence

1. `Plugin.Load` touches no IL2CPP type. It starts a background thread that sleeps 2 s, then waits for `[AddressablesPreLoader] Addressables finished loading` in Player.log.
2. `DobbyNearPages` moves Dobby's hook slots onto pages of our own, then the thread patches only `GameStateManager.Transition` (`MainThreadEntry`).
3. That hook's first call (main thread, before the main menu) applies every other `[HarmonyPatch]` class independently and registers the cars.
4. `DerivedVehicles` clones the donor `CarInfo`, maps the new prefab addresses back to the donor's prefab, and on spawn reshapes the clone: wheelbase, track, steering, suspension, meshes, colliders, and the spare wheel (`AddSpare`). `HiddenCars` un-hides Rancho and Grizzly. `Catalog` and `LocalizedText` add the names.

## Invariants

- No class injection: no `AddComponent` of plugin types, no managed delegates handed to the game. It crashes the game.
- Patch only from the `GameStateManager.Transition` entry hook.
- Plugin threads catch everything; an escaping exception aborts the game.
- Photon Fusion only spawns prefabs registered at build time, so every vehicle shares its donor's prefab and is reshaped on spawn.

## Hook pages (`DobbyNearPages.cs`)

Dobby keeps each hook's 8-byte jump slot in near pages that can fall inside coreclr's executable reservation; once coreclr commits that memory for JIT code, the next call through a hook jumps into garbage (it crashed the mechanic twice on 2026-10-18). The plugin finds the reservation from `System.Private.CoreLib.dll` and maps four pages at its top, which coreclr fills last. A healthy start logs:

- `Dobby pages: mapped 0x…-0x… in the top of coreclr's executable reservation (…, below <file>)` (or `in a free hole`)
- `Dobby pages: 0x… holds 56 bytes of slots` (all seven hooks)

An `Error … expect a crash` line means the hooks are unprotected: warn the player away from the mechanic.

## Crashes

Player.log ends with `Received signal SIGSEGV` but no native stack. Use the core: `coredumpctl list`, then gdb on the core; find `__restore_rt` on the main thread's stack (Unity's alternate signal stack), read the ucontext RIP at uc+40+16*8, map it to a module and offset (`tools/resolve_crash.py`, `decomp/`). A RIP of garbage after a `call` into a GameAssembly function that starts `ff 25` means a damaged hook slot.

## Build

`dotnet build -c Release` builds and deploys the DLL, `vehicles/*` and icons into `<game>/BepInEx/plugins/VehicleMods/`; `-p:Deploy=false` only compiles. The game folder defaults to Steam's default library; pass `-p:GameDir=<path>` (or set `GameDir` in the environment) for any other. The game must be closed. `plugins/VehicleMods/vehicles/` is build output (gitignored).
