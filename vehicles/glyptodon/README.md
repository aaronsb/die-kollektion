# Das Glyptodon

**Kind:** based · **Base:** Mammoth · **Item:** 3000000003

A new vehicle built from the game's Mammoth (Glyptodon family, two-door).

The renders show geometry built from the player's own copy of the Mammoth. This sheet ships pictures and numbers only, no mesh data.

## Isometric

![Isometric views](contact/iso.png)

## Rig

Body in X-ray with each connected piece in its own colour (1175 pieces at LOD0); Collider/Top cyan, Collider/Base orange, wheel colliders green; attach points marked by id (table below; squares are upgrade-slot pivots).

![Rig views](contact/rig.png)

| Id | Point | Category | Position (Unity root, m) | Nearest surface |
|---|---|---|---|---|
| HFL | `Axles/WheelColliders/WheelFL` | hub | (-0.930, +0.448, +1.221) |  |
| HFR | `Axles/WheelColliders/WheelFR` | hub | (+0.930, +0.448, +1.221) |  |
| HRL | `Axles/WheelColliders/WheelRL` | hub | (-0.930, +0.448, -2.029) |  |
| HRR | `Axles/WheelColliders/WheelRR` | hub | (+0.930, +0.448, -2.029) |  |
| COM | `CoM` | com | (+0.000, +0.650, -0.412) |  |
| WF | `Winch/WinchAttachPoints/Front` | winch | (+0.000, +0.850, +2.300) | 2.0 cm |
| WB | `Winch/WinchAttachPoints/Rear` | winch | (+0.000, +0.880, -3.335) | 1.1 cm |
| WL | `Winch/WinchAttachPoints/Left` | winch | (-1.003, +0.634, +0.000) | 13.3 cm |
| WR | `Winch/WinchAttachPoints/Right` | winch | (+1.003, +0.634, +0.000) | 13.3 cm |
| D1 | `WaterDetector/BackCarSubmerged` | water | (+0.000, +2.289, -0.609) |  |
| D2 | `WaterDetector/EngineAirIntakeWaterDetector_1` | water | (+0.000, +1.075, +1.459) |  |
| D3 | `WaterDetector/EngineAirIntakeWaterDetector_2` | water | (+0.000, +1.784, +1.400) |  |
| D4 | `WaterDetector/EngineAirIntakeWaterDetector_3` | water | (+0.000, +2.297, +1.193) |  |
| D5 | `WaterDetector/FrontCarSubmerged` | water | (+0.000, +2.259, +0.970) |  |
| D6 | `WaterDetector/IsTouchingWaterDetector` | water | (+0.000, +0.029, +0.150) |  |
| D7 | `WaterDetector/TiresFullySubmergedWaterDetector` | water | (+0.000, +0.164, +0.150) |  |
| L1 | `Lights/LeftBrakingBrakelight` | light | (-0.885, +1.040, -3.345) | 3.5 cm |
| L2 | `Lights/LeftHeadlight` | light | (-0.700, +0.830, +2.300) | 4.3 cm |
| L3 | `Lights/LeftPositionBrakelight` | light | (-0.885, +1.040, -3.345) | 3.5 cm |
| L4 | `Lights/LeftReverselight` | light | (-0.800, +1.040, -3.345) | 4.8 cm |
| L5 | `Lights/LeftSpotlightFlare` | light | (-0.700, +0.830, +2.300) | 4.3 cm |
| L6 | `Lights/RightBrakingBrakelight` | light | (+0.885, +1.040, -3.345) | 3.5 cm |
| L7 | `Lights/RightHeadlight` | light | (+0.700, +0.830, +2.300) | 4.2 cm |
| L8 | `Lights/RightPositionBrakelight` | light | (+0.885, +1.040, -3.345) | 3.5 cm |
| L9 | `Lights/RightReverselight` | light | (+0.800, +1.040, -3.345) | 4.8 cm |
| L10 | `Lights/RightSpotlightFlare` | light | (+0.700, +0.830, +2.300) | 4.2 cm |
| EX | `Effects/VehicleParticles/ExhaustParticlesManager` | exhaust | (-1.170, +0.690, -1.320) | 1.0 cm |
| SP | `spare (Mammoth_wheel)` | spare | (-0.531, +0.860, -0.350) | 16.5 cm |
| AN | `upgrade slot Antenna (17 options; median pivot)` | slot | (+0.729, +2.967, +1.387) | 53.2 cm |
| BD | `upgrade slot Bed (7 options; median pivot)` | slot | (+0.000, +1.284, -2.618) | 12.5 cm |
| FN | `upgrade slot Fender (28 options; median pivot)` | slot | (+0.000, +0.678, -1.048) | 4.3 cm |
| FS | `upgrade slot Front (13 options; median pivot)` | slot | (+0.000, +0.866, +1.922) | 7.4 cm |
| FB | `upgrade slot Front_Bumper (21 options; median pivot)` | slot | (+0.000, +0.830, +2.174) | 2.4 cm |
| RS | `upgrade slot Rear (20 options; median pivot)` | slot | (+0.000, +1.427, -3.280) | 2.6 cm |
| RB | `upgrade slot Rear_Bumper (20 options; median pivot)` | slot | (+0.000, +1.127, -2.847) | 6.4 cm |
| RC | `upgrade slot Rollcage (1 options; median pivot)` | slot | (+0.000, -0.071, +0.086) | 50.1 cm |
| RF | `upgrade slot Roof (19 options; median pivot)` | slot | (+0.001, +2.199, +0.108) | 11.8 cm |
| RL | `upgrade slot Roof_Bar (17 options; median pivot)` | slot | (+0.000, +2.264, +1.012) | 2.4 cm |
| SD | `upgrade slot Side (26 options; median pivot)` | slot | (-0.006, +1.439, -2.030) | 26.8 cm |
| ST | `upgrade slot Side_Step (4 options; median pivot)` | slot | (+0.000, +0.575, -0.014) | 12.8 cm |
| SN | `upgrade slot Snorkel (2 options; median pivot)` | slot | (-0.729, +1.589, +1.476) | 5.2 cm |
| WN | `upgrade slot Winch (1 options; median pivot)` | slot | (+0.000, +0.829, +1.932) | 10.9 cm |

## Analysis

### Attach points

| Id | Check | Result | |
|---|---|---|---|
| HFL | wheel mesh on its collider; tyre clear of the body above the hub (prefab pose) | mesh offset 0.0 cm, clearance +7.2 cm | pass |
| HFR | wheel mesh on its collider; tyre clear of the body above the hub (prefab pose) | mesh offset 0.0 cm, clearance +7.2 cm | pass |
| HRL | wheel mesh on its collider; tyre clear of the body above the hub (prefab pose) | mesh offset 0.0 cm, clearance +12.8 cm | pass |
| HRR | wheel mesh on its collider; tyre clear of the body above the hub (prefab pose) | mesh offset 0.0 cm, clearance +12.8 cm | pass |
| COM | centre of mass between the wheels (inside track and wheelbase, above the ground) | x -0.00, y 0.65, z -0.41 m; -0.08 m from the collider bottom | pass |
| COL | colliders (convex hulls) cover the LOD0 body no worse than the stock donor's: share of vertices over 10 cm outside within 5 points, worst within 10 cm | 12.0% over 10 cm outside, worst 57 cm (stock 9.4%, worst 34 cm) | **FAIL** |
| WF | winch point within 15 cm of a body or axle surface | 2.0 cm | pass |
| WB | winch point within 15 cm of a body or axle surface | 1.1 cm | pass |
| WL | winch point within 15 cm of a body or axle surface | 13.3 cm | pass |
| WR | winch point within 15 cm of a body or axle surface | 13.3 cm | pass |
| L1 | light point within 10 cm of a body or axle surface | 3.5 cm | pass |
| L2 | light point within 10 cm of a body or axle surface | 4.3 cm | pass |
| L3 | light point within 10 cm of a body or axle surface | 3.5 cm | pass |
| L4 | light point within 10 cm of a body or axle surface | 4.8 cm | pass |
| L5 | light point within 10 cm of a body or axle surface | 4.3 cm | pass |
| L6 | light point within 10 cm of a body or axle surface | 3.5 cm | pass |
| L7 | light point within 10 cm of a body or axle surface | 4.2 cm | pass |
| L8 | light point within 10 cm of a body or axle surface | 3.5 cm | pass |
| L9 | light point within 10 cm of a body or axle surface | 4.8 cm | pass |
| L10 | light point within 10 cm of a body or axle surface | 4.2 cm | pass |
| EX | exhaust point within 15 cm of a body or axle surface | 1.0 cm | pass |
| SP | spare point within 23 cm of a body or axle surface | 16.5 cm | pass |
| AN | upgrade-slot pivot no further from the body than on the stock donor (+15 cm) | 53.2 cm (stock 72.9 cm) | pass |
| BD | upgrade-slot pivot no further from the body than on the stock donor (+15 cm) | 12.5 cm (stock 4.1 cm) | pass |
| FN | upgrade-slot pivot no further from the body than on the stock donor (+15 cm) | 4.3 cm (stock 18.1 cm) | pass |
| FS | upgrade-slot pivot no further from the body than on the stock donor (+15 cm) | 7.4 cm (stock 7.4 cm) | pass |
| FB | upgrade-slot pivot no further from the body than on the stock donor (+15 cm) | 2.4 cm (stock 1.5 cm) | pass |
| RS | upgrade-slot pivot no further from the body than on the stock donor (+15 cm) | 2.6 cm (stock 0.8 cm) | pass |
| RB | upgrade-slot pivot no further from the body than on the stock donor (+15 cm) | 6.4 cm (stock 1.6 cm) | pass |
| RC | upgrade-slot pivot no further from the body than on the stock donor (+15 cm) | 50.1 cm (stock 65.2 cm) | pass |
| RF | upgrade-slot pivot no further from the body than on the stock donor (+15 cm) | 11.8 cm (stock 19.5 cm) | pass |
| RL | upgrade-slot pivot no further from the body than on the stock donor (+15 cm) | 2.4 cm (stock 10.6 cm) | pass |
| SD | upgrade-slot pivot no further from the body than on the stock donor (+15 cm) | 26.8 cm (stock 11.8 cm) | pass |
| ST | upgrade-slot pivot no further from the body than on the stock donor (+15 cm) | 12.8 cm (stock 23.0 cm) | pass |
| SN | upgrade-slot pivot no further from the body than on the stock donor (+15 cm) | 5.2 cm (stock 6.2 cm) | pass |
| WN | upgrade-slot pivot no further from the body than on the stock donor (+15 cm) | 10.9 cm (stock 10.9 cm) | pass |

### Mesh gaps and culled faces

`tools/check_holes.py` per body LOD: a culled patch is where the nearest surface is a back face the game doesn't draw; a gap is an enclosed hole with no surface. Fails at 25 cm² culled or 20 cm² gap.

![Gaps and culled faces, LOD0](contact/gaps.png)

| LOD | Triangles | Open edges | Culled patches (largest) | Gaps (largest) | |
|---|---|---|---|---|---|
| 0 | 11018 | 309 | 4 (5.8 cm²) | 31 (14 cm²) | pass |
| 1 | 9246 | 306 | 1 (2 cm²) | 36 (14.8 cm²) | pass |
| 2 | 7055 | 225 | 15 (5.8 cm²) | 40 (15 cm²) | pass |
| 3 | 6609 | 189 | 11 (5.5 cm²) | 48 (16.5 cm²) | pass |

| Gap (LOD0) | Area | At (OBJ, m) | Region |
|---|---|---|---|
| G1 | 14 cm² | (+0.999, +1.350, +1.627) | body left |
| G2 | 4.5 cm² | (+0.804, +0.599, -0.276) | lower left |
| G3 | 4.5 cm² | (+0.804, +0.599, -0.383) | lower left |
| G4 | 4 cm² | (+0.940, +0.415, +0.452) | lower left |
| G5 | 3.5 cm² | (+0.833, +0.910, +2.093) | lower left |
| G6 | 3.5 cm² | (+1.124, +0.858, -1.461) | lower left |
| G7 | 3.5 cm² | (-0.639, +0.752, -1.399) | lower right |
| G8 | 3.5 cm² | (-0.833, +0.910, +2.093) | lower right |
| G9 | 3.5 cm² | (-0.978, +2.316, +1.061) | greenhouse right |
| G10 | 3.5 cm² | (-0.906, +2.231, +1.232) | greenhouse right |
| G11 | 3.5 cm² | (+0.308, +1.457, +2.073) | body left |
| G12 | 3.2 cm² | (+0.813, +0.613, +0.025) | lower left |
| G13 | 3.2 cm² | (+0.997, +1.347, +1.724) | body left |
| G14 | 3.2 cm² | (+1.047, +0.894, -1.443) | lower left |
| G15 | 3 cm² | (+0.997, +1.346, +1.673) | body left |
| G16 | 3 cm² | (-0.945, +0.421, +0.450) | lower right |
| G17 | 2.8 cm² | (-0.754, +1.112, -3.275) | lower right |
| G18 | 2.8 cm² | (+0.313, +1.380, +2.106) | body left |
| G19 | 2.5 cm² | (+1.121, +0.689, +0.558) | lower left |
| G20 | 2.5 cm² | (+0.758, +1.116, -3.280) | lower left |
| G21 | 2.5 cm² | (+0.803, +0.597, -0.506) | lower left |
| G22 | 2.5 cm² | (-0.878, +2.374, +1.198) | roof |
| G23 | 2.2 cm² | (-1.101, +2.276, +1.049) | greenhouse right |
| G24 | 2.2 cm² | (+0.974, +0.945, +0.421) | lower left |
| G25 | 2.2 cm² | (-0.990, +0.618, +0.482) | lower right |
| G26 | 2.2 cm² | (+1.101, +2.276, +1.049) | greenhouse left |
| G27 | 2.2 cm² | (+0.371, +1.437, +2.086) | body left |
| G28 | 2.2 cm² | (+0.638, +1.382, +2.098) | body left |
| G29 | 2 cm² | (+1.130, +1.142, -2.448) | lower left |
| G30 | 2 cm² | (-1.130, +1.142, -2.448) | lower right |
| G31 | 2 cm² | (+0.253, +1.426, +2.057) | body centre |

| Culled patch (LOD0), along z | Area | Triangles | Region |
|---|---|---|---|
| -3.31..-3.31 m | 5.8 cm² | 1 | body centre |
| -3.31..-0.03 m | 4.2 cm² | 1 | body right |
| -3.31..-0.03 m | 4.2 cm² | 1 | body left |
| -0.00..+0.15 m | 4 cm² | 1 | body right |

### Slivers and triangles

Slivers (faces over 1.5 m long with under 0.01 m² area): `body_LOD0.obj` 8, `body_LOD1.obj` 8.

| Mesh | Triangles | Source |
|---|---|---|
| body_LOD0 | 11018 | built |
| body_LOD1 | 9246 | built |
| body_LOD2 | 7055 | built |
| body_LOD3 | 6609 | built |
| axle_front_LOD0 | 4076 | built |
| axle_rear_LOD0 | 4076 | built |
| collider_top | 20 | built |
| collider_base | 24 | built |

## Facts

| Length | Width | Height | Wheelbase | Track | Ground clearance |
|---|---|---|---|---|---|
| 5.63 m | 2.71 m | 2.59 m | 3.25 m | 1.86 m | 0.43 m |

Height and ground clearance are in the prefab pose (wheels at their modelled hub height, tyres on the ground); suspension sag at rest is not modelled.

| Chassis | Value |
|---|---|
| wheelbase | `3.25` |
| track | `1.86` |
| maxSteerAngle | `37.8` |
| wheel | `{"radius": 0.52, "width": 0.4, "y": 0.45}` |
| tyre | `{"radius": 0.545, "width": 0.352}` |
| suspension | `{"travel": 0.4, "anchor": 0.725, "springRate": 18300, "damperRate": 4500, "preloadDistance": 0.1, "bumpTravelOffset": 0.03}` |
| bodyCut | `[[0.0, -0.62], [1.05, -0.865], [1.21, -1.45]]` |

Generated by Die Kollektion Werkstatt, tools/contact_sheet.py (prototype of `kollektion contact`) from [`contact/contact.json`](contact/contact.json). The real vehicle this one is modelled on is listed in the catalogue in the [main README](../../README.md).
