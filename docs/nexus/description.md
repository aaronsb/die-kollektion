# Nexus description, by section

The text for each section of the Nexus "Description" form, ready to paste. `description.bbcode` holds the same content as one BBCode page for the older editor.

## Description

Die Kollektion Werkstatt is a vehicle mod system for Over the Hill, and Die Kollektion is the first set of vehicles built with it: four trucks and two patches on stock cars.

New trucks go on sale at the merchant like any other vehicle. Each one runs on a stock vehicle reshaped as it spawns (wheelbase, track, suspension, steering, tyres) and carries its own body, cab, frame and bed. Patches change a stock car in place.

It started as "better trucks in the game" and grew into the system those trucks needed. Everything is built on your machine from your own copy of the game, so this download contains no game files.

Home: https://github.com/aaronsb/die-kollektion (source, issues, and every vehicle's contact sheet). Latest release: https://github.com/aaronsb/die-kollektion/releases/latest. This page mirrors each release.

## Installation instructions

1. Install Over the Hill in Steam, start it once, get past the intro, and quit.
2. Download the file from this page and unzip it anywhere.
3. Open a terminal in the unzipped folder and run `make start`.
4. Do the one step it prints, then run `make start` again. Repeat until it says everything is ready. It walks you through:
   - installing a few programs (it prints the exact command for Arch, Debian/Ubuntu or Fedora);
   - `make setup`;
   - `make bepinex`, which downloads the pinned BepInEx build from the official build server after asking, checks it and installs it;
   - setting the Steam launch option it shows you (Library → right-click Over the Hill → Properties → General → Launch Options);
   - starting the game once and quitting;
   - `make all`, which copies the parts it needs from your game, builds the trucks, checks them and installs the mod.
5. Start the game. The trucks are at the merchant. Optional, with the game closed: `make save-add` puts all four in your garage.

Fastest: open the folder with an AI coding agent that reads AGENTS.md (Claude Code, for example) and say "set me up". It runs `make start` step by step and tells you when to click something in Steam.

Uninstall: `make undeploy` removes exactly the files the install put in the game folder. To remove BepInEx as well, clear the Steam launch option and delete `BepInEx/`, `dotnet/`, `libdoorstop.so`, `run_bepinex.sh`, `.doorstop_version` and `changelog.txt` from the game folder.

Back up `~/My Games/over the hill/Saves/` before you start. A save that holds one of these trucks keeps listing it after the mod is removed.

After a game update: close the game and run `make all` again.

## Main features

- **Four trucks:**
  - Das Glyptodon: a square-cab two-door on a long wheelbase, with a ribbed steel drop-side bed, portal axles and coil springs.
  - Das Megaloceros: the square cab as a crew cab, on a longer wheelbase, with storage boxes and a spare wheel.
  - Das Mastodon: a round-cab two-door on a stretched chassis, with portal axles, coil springs and a ribbed steel bed.
  - Das Megatherium: a round-cab crew cab on the same long chassis.
- **Two patches on stock cars:**
  - The Mammoth gets portal axles, coil springs, a side-exit exhaust and a tighter turning circle.
  - The Ding gets a golf bag strapped to its roof: the canary that proves any stock car can be modded.
- **A workshop, not just a mod.** One command (`make start`) sets everything up; `make all` rebuilds and installs; `make undeploy` removes exactly what was installed.
- **Contact sheets.** Every vehicle's folder on GitHub opens as its contact sheet: four isometric renders, a rig view of its colliders and attach points, and the results of the mesh checks.
- **Built for modders.** Vehicles are portable folders with a JSON manifest; changes arrive as pull requests with before-and-after contact sheets. The design for packs, a cross-platform CLI and a Blender add-on is in the repository.
- **Durable.** The plugin reserves its own memory for its hooks as it loads, and runs the game without the mod rather than crash if it can't.
- **Made with AI, agent-friendly on purpose.** AGENTS.md tells an AI agent how to help, whether you want it to just make things work or to coach you while you keep creative control.

## Requirements

- Over the Hill on Steam, the native Linux build. Windows support is planned (a cross-platform CLI and a Windows plugin build are in the design), not ready yet.
- A Linux machine with `make`, Python 3 (with venv), `rsvg-convert` and `potrace`. `make start` prints the install command for your distribution.
- BepInEx 6 IL2CPP, build be.789: installed for you by `make bepinex`, not bundled.
- About 1 GB of free space.
- Optional: the .NET SDK, needed only to build from source or when the game has updated since this release; Blender 5, needed only for contact sheets and editing models.

Known limits: Linux only today; multiplayer with these trucks is untested; the trucks are built on your machine from your own game files, which takes about a minute.

## Shout outs

- Funselektor Labs, for Over the Hill. This mod includes none of the game's files, art or code; its manifests follow the format of Funselektor's official livery modding guide so liveries stay compatible.
- The BepInEx team, for BepInEx 6 with Il2CppInterop, HarmonyX and Dobby.
- The makers of UnityPy, Pillow, NumPy, SciPy, Blender, the .NET SDK, librsvg, potrace and Noto Sans.
- r/overthehillgame, for the enthusiasm and the vehicle wish list.
- Built by aaronsb with AI (Claude). Truck details come from years of driving and wrenching on the real ones.

Code GPL-3.0-or-later, art CC BY-SA 4.0. Not affiliated with Funselektor or with any vehicle manufacturer.
