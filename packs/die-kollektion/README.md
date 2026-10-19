# Die Kollektion (pack)

The example set of vehicle packs for Die Kollektion Werkstatt: four trucks built on the game's Mammoth, a patch for the stock Mammoth itself, and the canary: a golf bag strapped to the roof of The Ding. [`manifest.json`](manifest.json) lists them and puts the trucks in one group, "Die Kollektion".

Each vehicle's folder opens on its contact sheet: four isometric renders, a rig view with colliders and attach points, and the checks.

| In game | Kind | Folder |
|---|---|---|
| Das Glyptodon | new vehicle, based on the Mammoth | [vehicles/glyptodon](../../vehicles/glyptodon) |
| Das Megaloceros | new vehicle, based on the Mammoth | [vehicles/megaloceros](../../vehicles/megaloceros) |
| Das Mastodon | new vehicle, based on the Mammoth and the mechanic's truck | [vehicles/mastodon](../../vehicles/mastodon) |
| Das Megatherium | new vehicle, based on the Mammoth | [vehicles/megatherium](../../vehicles/megatherium) |
| Das Mammoth | patch on the stock car | [vehicles/mammoth](../../vehicles/mammoth) |
| The Ding | patch on the stock car: the canary, a golf bag on the roof | [vehicles/dingding](../../vehicles/dingding) |

## Installing it

The plugin doesn't load pack zips yet; it installs from this repository. From the repository root, run `make start` and do what it says; it ends with the pack installed in your game.

## The zip

`make pack` writes `dist/die-kollektion-<version>.zip`: this manifest, this page, the licences, and each vehicle folder's own files (manifests, models we made, icons we drew, contact sheets). Nothing from the game is in it; the parts the trucks reuse from the Mammoth are extracted from your own copy of the game when you build.
