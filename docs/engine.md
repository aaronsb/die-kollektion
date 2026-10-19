# Engine, loader and mesh facts

What we know about *Over the Hill* (Funselektor) as a modding target, and what the plugin and tools rely on. Learned on the native Linux build; Windows is untested.

## Engine

- Unity 6000.0.75f1, IL2CPP (metadata v31), URP. FMOD Studio is the audio middleware only (`StreamingAssets/*.bank`).
- Content ships as Addressables bundles in `over the hill_Data/StreamingAssets/aa/StandaloneLinux64/`. Type trees are present, so UnityPy reads MonoBehaviour fields by name.
  - `cars_assets_all_*.bundle`: vehicle prefabs (`Car_<Codename>`), meshes, textures.
  - `scriptableobjects_assets_all_*.bundle`: car definitions, liveries, upgrade lists, engine tiers, tyre configs, icons.
  - `localization-string-tables-english(en)_*.bundle`: display names and descriptions.
- Official mod support is liveries only (mod.io and `~/My Games/over the hill/LocalLiveries/`). A new vehicle needs a code mod.

## Stock roster (the cars the catalogue has)

| Codename | Display | Bed | Collider length (m) | Wheel radius (m) | Travel (m) |
|---|---|---|---|---|---|
| Mammoth | Das Mammoth | yes | 4.24 | 0.52 | 0.70 |
| RustOx | Das Rust Ox | no | 4.87 | 0.36 | 0.60 |
| Lynx | Das Lynx | no | 3.68 | 0.40 | 0.35 |
| Wombat | Das Wombat | no | 3.88 | 0.43 | 0.55 |
| Marshal | The Marshal | no | 4.38 | 0.52 | 0.70 |
| Baguette | Rancho, catalog-excluded | no | 4.38 | 0.30 | 0.25 |
| Grizzly | Grizzly, catalog-excluded | no | 3.10 | 0.30 | 0.25 |

Hidden car ItemIds: Baguette `2077913603`, Grizzly `2940455280`. The plugin un-hides both (`HiddenCars.cs`).

## The donor: Mammoth

From `Car_Mammoth` local positions:
- Wheel colliders: front z +1.10, rear z −1.43 (wheelbase 2.53 m); x ±0.90 (track 1.80 m).
- `Axles/SuspensionRigidFront` z +1.11, `SuspensionRigidRear` z −1.43: skinned solid-axle meshes.
- Body: `Parts/Mammoth/Mammoth_body_LOD0..3` under one LODGroup. Collision: `Collider/Top`, `Collider/Base` (MeshColliders).
- Centre of mass (0, 0.65, −0.05). Winch points front z 2.12, rear z −2.24.
- Rear lamps: the body has two sets. The upper blocks (y 0.97-1.11) carry the brake/position emitters (`Lights/*PositionBrakelight`, `*BrakingBrakelight`, root y 1.04); the lower round lamps (y 0.69-0.85) are red plus the reverse light (root y 0.80).

Atlas (material `Mammoth`): `Mammoth_masks` is blue where the livery paints and green for glass (red+green is a lamp lens, which the shader keeps lit and snow-free); `Mammoth_skin00` is the default livery; `Mammoth_AO` carries baked shading. UV (0.635, 0.59) is clean painted cab roof, used for repainted parts. Our hand-made parts are flat-coloured from atlas points, so they need no UVs.

The mechanic's truck (`r1_canada` scene bundle, scale 100, offset (0, −0.071, 0.086) onto the Mammoth) shares the Mammoth's UV layout, and its LOD0 matches the Mammoth's LOD0 face for face ahead of the cab.

## Suspension (VPP)

- Each corner is an independent `VPFunselektor3DRaycastWheelCollider` (`Axles/WheelColliders/Wheel{FL,FR,RL,RR}`, hub at root y 0.45). `VPVehicleController.axles` only pairs wheels for steering, brakes and drive. There is no anti-roll bar on the Mammoth. The solid axle is visual only: a skinned mesh following the hub bones.
- The per-car values live in `CarInfo.suspensionSetup`; the Mammoth's match its prefab: radius 0.52, travel 0.70, anchor 0.40, spring 40000, damper 7000, preload 0, unsprung mass 55, bump-stop rate 400000, bump travel offset 0.16. Rigidbody mass 3200 kg.
- VPP reads the prefab's wheel-collider fields at `VehicleBase.Spawned`; nothing visible applies `CarInfo.suspensionSetup` to the wheels (the suspension-lift upgrade reads its base travel from it). A definition's `suspension` block therefore sets the wheels in the Spawned prefix and, for a derived car, writes a copy into its CarInfo.
- `suspensionAnchor` is read as a fraction measured up from full extension (Unity's convention); driving bears this out.
- Toggling `VPVehicleController` off and on breaks the vehicle.

## BepInEx

- BepInEx 6.0.0-be.789 IL2CPP linux-x64, extracted into the game folder. Steam launch options: `"./run_werkstatt.sh" %command%`, Werkstatt's launch script, which starts `run_bepinex.sh` with the same arguments.
- **After a game update** a plugin compiled against the old interop hangs the game at start: BepInEx's log stops at `Chainloader initialized` (Steam build 26047935, 2026-10-19; rebuilding against the regenerated interop fixed it). Each deploy records the game's `GameAssembly.so` and `global-metadata.dat` (size, time, sha256), its Steam build and BepInEx's interop hash in `deployed.json`. `run_werkstatt.sh` compares them before each launch (for a deploy made before the record existed: code files newer than BepInEx's last `LogOutput.log` with `Chainloader initialized`); on a difference it moves `plugins/VehicleMods/` to `BepInEx/VehicleMods.aside/` (next to the real `plugins/` when that is a symlink, so the move stays a rename on one filesystem), so that launch runs stock and BepInEx regenerates its interop. After the game exits a separate process rebuilds the DLL (once the interop hash has changed, or BepInEx's log shows it got past `Chainloader initialized` since), copies the aside folder's vehicle files, which were gated at deploy, into `BepInEx/VehicleMods.staging/` with it, and renames that into place. It rebuilds only when the Werkstatt checkout is still at the deployed commit with no uncommitted changes under `plugins/VehicleMods/`; otherwise, and when the build fails, the plugin stays aside, the game runs stock, and the log points at `make update`, which deploys the checkout in full with the gates. After a game update, or without a record, `make deploy` refuses to build until BepInEx has started the game since its code files changed. A launch during a rebuild doesn't wait for it: with the plugin aside it starts stock and tries again after the game exits. One step at a time holds `BepInEx/werkstatt.lock`; the log is `BepInEx/werkstatt-launch.log`, trimmed to its last 256 KB.
- The rebuild runs under `systemd-run --user` where that works, outside the game's process tree: Steam's reaper is a subreaper and waits for every process below it, and dotnet's MSBuild nodes and compiler server outlive a build by about ten minutes, so the build runs with node reuse and shared compilation off. Without systemd it falls back to `setsid`, which stays below the reaper. How Steam shows the game during the rebuild is untested until a real update.
- Known limits: files added by hand to `plugins/VehicleMods/` before a deploy are listed in its `deployed.json` as deployed, so `make undeploy` removes them; files changed or added after it survive a rebuild (it copies the aside folder) and a redeploy (the old folder is kept as `VehicleMods.replaced-<time>`). Steam's Linux runtime container is untested: the launch option wraps Steam's whole command, so the script and the rebuild run on the host, outside any container.
- `UnityLogListening = false` in `BepInEx/config/BepInEx.cfg` is required (see below).

## What crashes this game

- **Class injection.** Il2CppInterop warns `Class::Init signatures have been exhausted, using a substitute!`, and anything that injects a type then segfaults right after `SettingsManager.ParseLaunchOptions`: BepInEx's Unity log listener, `AddComponent<T>()` of a plugin MonoBehaviour, managed delegates handed to the game.
- **Patching in `Load`.** Crashes the render thread during swap-chain setup.
- **Patching from a background thread while the main thread is busy** (a scene change, or `MainThreadScheduler.Update`, which runs every frame).
- **Managed work during swap-chain setup.** Log polling started in `Load` crashed the main thread during `InitializeOrResetSwapChain` in about 4 of 11 launches. The plugin's thread now sleeps 2 s, then polls with one open stream and a reused buffer, and `Load` touches no IL2CPP type.
- **Dobby's near pages inside coreclr's reservation.** See below.

What works: a background thread waits for `[AddressablesPreLoader] Addressables finished loading` in Player.log, patches only `GameStateManager.Transition`, and that hook's first call (main thread, before the main menu) applies the remaining patches and registers the cars. An exception escaping a plugin thread aborts the game, so plugin threads catch everything.

## Hook pages (`DobbyNearPages.cs`)

BepInEx hooks IL2CPP methods with libdobby, which writes `jmp [rip+disp32]` at the hooked function and keeps the 8-byte target slot (and the relocated prologue) in "near" pages within 2 GB (1 GB for code). It maps those pages MAP_FIXED into no-access memory found in /proc/self/maps, which near GameAssembly is coreclr's ~2 GB executable reservation. Once coreclr commits that range for JIT and loader-heap code, the slots hold instruction bytes and the next call through any hook faults (seen as a crash on entering the mechanic).

`DobbyNearPages` works in two steps. At plugin Load (native calls only, no IL2CPP types) it reserves a 4 MB block, PROT_NONE until used, where `NearBlockPlanner` finds room within 1 GB of GameAssembly's code: the top of the largest unmapped gap (claimed with MAP_FIXED_NOREPLACE, so it can never replace a live mapping), else the top of coreclr's executable reservation (the highest no-access run of at least 32 MB in the reservation that starts at `System.Private.CoreLib.dll`, with at most 1 MB of other mappings above it, ending 64 KB below that run's 64 KB-aligned top; coreclr hands the reservation out strictly upward, so its top is committed last). The reservation's top is claimed with MAP_FIXED, replacing coreclr's no-access memory in place. If the claim at Load fails, it is tried again before the hooks. Before the plugin's own hooks (on the entry thread, after the Addressables line or a 60 s timeout) it re-validates the block (still anonymous no-access memory, or it chooses again) and commits its first four pages: one read-write page for jump slots, two read-execute pages for relocated prologues, and one page for the slots moved off Dobby's pages, made read-only once they are written. It then marks Dobby's existing near pages full, hands Dobby the new ones, and moves the live hooks' slots onto the fourth page. If nothing qualifies it installs no hooks at all, so the game runs without the mod instead of crashing.

Dobby's old pages also hold slots no live jump uses: BepInEx hooks `il2cpp_runtime_invoke` to start the chainloader and removes that hook once the chainloader is up, leaving its slot and relocated prologue behind. Those stay where they are. The log's count of slots with "no live jump" also includes any left unmoved because they were damaged or out of reach.

Reading `BepInEx/LogOutput.log` (these messages start `Dobby pages`, apart from the final `No hooks installed` line):
- `reserved at Load: Gap …` or `ReservationTop …`, with the address range and why it was chosen; `using 0x…-0x… of the … block`; one `retiring near page 0x… (slots|code, …)` per Dobby page; `new hooks use 0x… (slots) and 0x… (code), N MB from GameAssembly's code`; one `moved the slot of the hook at <module>+0x…` per live hook, then `moved N live hook slot(s) to 0x…; M slot(s) on Dobby's old pages have no live jump (hooks already undone)`; after the hooks, `0x… holds N bytes of slots` / `of code`. This is a healthy launch.
- `nothing to reserve at Load`, `reserving at Load … failed` or `the block reserved at Load (0x…) was changed since; choosing again`: the Load claim didn't hold and the planner chose again before the hooks. Harmless if a `using` line follows.
- `hook at <module>+0x… has a damaged slot`: a slot was already overwritten before the move; that hook will fault when called. Capture the maps (below).
- `No hooks installed: Die Kollektion is inactive this session`: the game runs stock. The line before it says why: `no safe place for the hooks' jump slots …` (the planner found nothing in reach; capture the maps), `GameAssembly.so not in /proc/self/maps` or `Dobby has no page list` (BepInEx or libdobby changed), or `Dobby pages failed: <exception>` (a fault in the page code itself).

Why near memory can't be avoided: BepInEx be.789 offers `DetourProviderType = Dobby | Funchook` in `BepInEx.cfg`, but the Linux build ships no funchook library, and funchook needs near pages too. libdobby exports `dobby_disable_near_branch_trampoline`, which makes the patch at the hooked function a 14-byte absolute jump with no slot; but five of the first seven hooked prologues (2026-10-19 build) hold a RIP-relative `cmpb $0, disp32(%rip)` within their first 14 bytes (the eighth hook, `StateMainMenu.Update` for the main-menu status line, is unchecked), and Dobby's relocated copy of that instruction needs disp32 reach to GameAssembly's data, so the relocated code still has to sit within 2 GB.

2026-10-19, after a game update (Steam build 26047935): no unmapped gap existed within 2 GB of GameAssembly's code, and the old rule (a no-access run of at least 128 MB ending exactly at the reservation's boundary) failed because three 12 KB mappings sat between coreclr's 744 MB tail and the GPU's `renderD128` mapping. The hooks' slots stayed on Dobby's page at coreclr's committed frontier (0x7FE893D78000), which coreclr overwrote with loader-heap data within seconds; the hook on GameAssembly+0x4DAEF40 then jumped to 0x7FE893D5AA22, a non-executable page (SIGSEGV, SEGV_ACCERR) during the logo. `make check` runs `tools/near-plan` over captured layouts in `tests/maps/` (that one, the layout before the update, and two synthetic controls); add a layout there whenever a launch logs a placement problem (`cat /proc/<pid>/maps`, or from a core: `coredumpctl debug <pid>` with `info proc mappings`, permissions from the core's program headers).

## Crash forensics

Player.log ends with `Received signal SIGSEGV` but no native stack. Use the core dump: `coredumpctl list`, then gdb on the core; find `__restore_rt` on the main thread's stack (Unity's alternate signal stack), read the ucontext RIP at uc+40+16*8, and map it to a module and offset (`tools/resolve_crash.py`). A RIP of garbage after a `call` into a GameAssembly function that starts `ff 25` means a damaged hook slot.

## Mesh pipeline

1. `tools/export_car_mesh.py <cars bundle> Car_<Donor> extracted/<donor> <node paths...>` extracts donor meshes (MeshFilter, MeshCollider or SkinnedMeshRenderer) to OBJ in car-root metres, x negated (right-handed, opens in Blender). Skinned meshes add `bw` lines (bone indices and weights) and `bp` lines (bind poses). `tools/export_named_mesh.py` exports Mesh assets by name; `tools/export_images.py` exports textures and icons. All of these read the player's own install; `tools/export_game_data.sh` runs them into `extracted/`, which is never committed.
2. `tools/build_vehicle.py vehicles/<name>/vehicle.json` stretches each mesh behind the body cut unless `"stretch": false`, then runs its `ops` (`tools/meshlib.py`): `portalAxle`, `coilSprings`, `relocatePiece`, `removeRegion`, `insertPart`, `removePieces`, `stretchPieces`, `movePieces`, `widenPieces`, `paint` and `addBoxes`. Part files in the definition are relative to the vehicle's folder, except game parts under `extracted/`. Output goes to the vehicle's `build/` folder.
3. `tools/preview_vehicle.sh vehicles/<name>/vehicle.json` builds and renders side, top, rear and three-quarter views in headless Blender into `renders/<codename>.png`.
4. `dotnet build -c Release` in `plugins/VehicleMods` deploys the DLL and, from each vehicle folder, its definition (as `vehicles/<name>.json`), built meshes (`vehicles/<name>/`) and icon (`icons/<Codename>.png`) to `BepInEx/plugins/VehicleMods/`.

## Gotchas

- `pgrep -f "over the hill.x86_64"` also matches the shell running it; check the matches' process names.
- Deploy only with the game closed.
- Stretched faces stretch their texture (fender top, skirt under the bed).
- The game logs occasional `WheelTransformUpdater.UpdateTraxCollider` index errors on several stock cars, with no visible effect.
