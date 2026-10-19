# Changelog

All notable changes to Die Kollektion Werkstatt. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/).

## [0.5.0] - 2026-10-19

The first public release, on GitHub and Nexus Mods. Werkstatt builds the trucks on your machine from your own copy of the game; nothing from the game ships. Native Linux today; Windows support is planned.

### Added
- **The Werkstatt make flow.** `make start` checks the setup and prints one plain next step at a time, from a fresh game install to a deployed mod; `make doctor` lists every check with the install command for your distro; `make bepinex` installs the pinned BepInEx 6 IL2CPP build (be.789, checksum-verified, asks before downloading) and fixes its start script and config; `make all` extracts, builds, checks and deploys; `make undeploy` removes exactly what was installed; `make status` compares repo, build and game folder; `make save-add` puts the trucks in a save after backing it up.
- **Contact sheets.** Each vehicle folder's page on GitHub shows four isometric renders, a rig view of its colliders, wheel colliders and attach points, and the mesh checks (gaps, slivers, culled faces, triangle counts, attach-point checks). `make loop V=<vehicle>` rebuilds one vehicle and summarises what changed.
- **Vehicle folders.** One self-contained folder per vehicle under `vehicles/`, with its manifest (`vehicle.json`, whose `kind` is `novel`, `based` or `patch`), its own meshes, Blender masters and icon.
- **Packs.** `packs/die-kollektion/manifest.json` (strict JSON in the pattern of the game's official livery manifest) and `make pack`, which zips only our own files and refuses anything extracted from the game.
- **The golf-bag canary.** A low-poly golf bag strapped to the roof of The Ding, the first patch on a stock car other than the Mammoth.
- **Review on GitHub.** A Drive report issue form, and pull requests that carry each vehicle's updated contact sheets; `CONTRIBUTING.md` describes the flow.
- `AGENTS.md`, guidance for AI agents helping a person build or tweak vehicles.
- **Releases with the plugin ready-made.** `make release VERSION=x.y.z` (maintainers; `DRY_RUN=1` to rehearse) checks versions and gates, compiles the plugin against the installed game, and publishes `die-kollektion-werkstatt-<version>.zip` (Werkstatt with `prebuilt/`), the pack zip and `SHA256SUMS` on GitHub Releases. With a prebuilt plugin built for the player's game version, `make deploy` installs it instead of compiling, so players need no .NET SDK.
- **CI.** GitHub Actions run every check that needs no game files on each pull request and push (`tools/release.py ci`), and verify each release's tag, versions and assets.

### Fixed
- Rear-section upgrades (tailgate spare, bike rack) sat 18.7 cm inside the bed on the Glyptodon, Megaloceros and Mastodon; they now move with the bed's rear end.
- After the game update of 2026-10-19 the plugin crashed during the logo: the hooks' jump slots could land in memory .NET later overwrites. The plugin now reserves its own block for them as soon as it loads, re-checks it before installing the hooks, and runs the game without the mod rather than crash when no safe block exists. `make check` tests the placement against captured memory layouts.
- The BepInEx download failed with HTTP 403 (the build server refuses Python's default user agent).
