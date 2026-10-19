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

- BepInEx 6.0.0-be.789 IL2CPP linux-x64, extracted into the game folder. Steam launch options: `"./run_bepinex.sh" %command%`.
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

`DobbyNearPages` runs before the entry patch: it finds coreclr's reservation from `System.Private.CoreLib.dll` (walking upward through unnamed memory and `*.dll` images to the first gap or other file mapping), maps four pages at the top of that no-access run (coreclr hands the reservation out strictly upward, so the top is committed last), marks Dobby's existing near pages full, hands Dobby the new ones, and moves the existing hooks' slots onto them. A healthy start logs `Dobby pages: mapped …` and `Dobby pages: 0x… holds 56 bytes of slots` (all seven hooks). An `Error … expect a crash` line means the hooks are unprotected. It is Linux-only and must be a logged no-op elsewhere.

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
