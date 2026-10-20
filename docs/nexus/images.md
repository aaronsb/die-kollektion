# Images for the Nexus page

`make nexus-images` (`tools/nexus_images.py`) renders our vehicles reproducibly, in the contact sheets' look, into `docs/nexus/images/`. Renders of the based trucks and patches show geometry built from the player's own copy of the game; they are pictures, never mesh data. `halogen-headlights-1987x1359.jpg` (in game) and `blender-addon-1920x1080.jpg` (Blender, under Xvfb) are screenshots kept beside them, which the script leaves alone.

## Banner

`images/banner-1300x372.jpg` (1300x372): the four trucks lined up under the title. Upload it as the page banner, not in the gallery.

## Gallery, in upload order

| # | File | Caption |
|---|---|---|
| 1–3 | The maintainer's three in-game screenshots (uploaded directly on Nexus, not kept in the repository) | (as on Nexus) |
| 4 | `images/halogen-headlights-1987x1359.jpg` | Das Megaloceros at dusk with halogen headlights: a warmer, slightly dimmer beam than the stock cars', set per truck in its manifest (in game; since 0.6.0) |
| 5 | `images/megaloceros-1920x1080.jpg` | Das Megaloceros: the square cab as a crew cab, on a long wheelbase |
| 6 | `images/glyptodon-1920x1080.jpg` | Das Glyptodon: the square-cab two-door with a drop-side bed |
| 7 | `images/dingding-1920x1080.jpg` | The canary: a golf bag strapped to The Ding's roof, the first patch on a stock car other than the Mammoth |
| 8 | `images/mastodon-1920x1080.jpg` | Das Mastodon: a round-cab two-door on a stretched chassis |
| 9 | `images/megatherium-1920x1080.jpg` | Das Megatherium: the round-cab crew cab |
| 10 | `images/how-its-built-1920x1080.jpg` | How it's built: the truck beside its rig view, with colliders, wheel colliders and labelled attach points |
| 11 | `images/blender-addon-1920x1080.jpg` | The Werkstatt add-on for Blender: Das Megaloceros in the game's livery, with the bumper winch it shows while it carries the portable winch (since 0.7.0, not yet checked in game). Nudge an item into place, and Save placements writes the truck's placements.json, which the plugin applies in game and in the mechanic's preview |
| 12 | `images/contact-sheet-1920x1080.jpg` | The contact sheet: every vehicle's four isometric corners, rendered the same way so builds compare tile for tile |

Set image 1 (the first in-game screenshot) as the primary image.
