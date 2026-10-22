# Licences

Copyright © 2026 Aaron Bockelie.

| What | Where | Licence |
|---|---|---|
| Code: the plugin, `kollektion` and Kollektion.Core, tools, build scripts and the Blender add-on | `plugins/`, `src/`, `tools/`, `blender/`, and any other source file | GNU GPL 3.0 or later ([`LICENSE`](LICENSE)) |
| Art: cab models and their meshes, generated parts, icons, vehicle definitions and pack content | `vehicles/` | Creative Commons Attribution-ShareAlike 4.0 International ([`LICENSES/CC-BY-SA-4.0.txt`](LICENSES/CC-BY-SA-4.0.txt)) |
| Documentation | `docs/`, `README.md`, `AGENTS.md`, `CLAUDE.md` files | CC BY-SA 4.0 |

You may use, change and share all of it, commercially too, as long as what you distribute carries its complete source under the same licence (GPL for code) or the same terms (CC BY-SA for art), with attribution.

## Third-party code

`kollektion` bundles AssetsTools.NET (MIT, with lz4net under BSD-2-Clause and the public-domain LZMA SDK) and the .NET runtime (MIT); parts of Kollektion.Core are ports of Pillow (MIT-CMU), UnityPy (MIT) and Pillow's BCn decoder (CC0). [`THIRD-PARTY-NOTICES.txt`](THIRD-PARTY-NOTICES.txt) lists each, with its licence text in [`LICENSES/`](LICENSES/).

## Packs are data

A pack (a vehicle definition, its meshes, textures and icons, and any other content the plugin loads) is data the plugin reads, not a derivative work of the plugin. Authors of their own packs license them as they choose. Packs made from our art (the cab models, our icons, our definitions) are adaptations of it and fall under CC BY-SA 4.0.

## No game assets

This repository contains no files from *Over the Hill*. Meshes, textures and icons from the game are extracted on your own machine from your own install (`tools/export_game_data.sh`) and are never committed or distributed. *Over the Hill* and its assets belong to Funselektor; this project is not affiliated with or endorsed by them.

## Real vehicle names

Real manufacturer and model names appear only in the catalogue (each definition's `listing` block and the README table generated from it), to say which real vehicle a fictional one is modelled on. They are trademarks of their owners, used descriptively; this project is not affiliated with or endorsed by any manufacturer.
