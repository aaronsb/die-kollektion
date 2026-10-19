# Contributing

For maintainers and agents changing this repository. Playing, building and making your own vehicle need none of this; see the [README](README.md) and [AGENTS.md](AGENTS.md).

## Ways to help

- **Drive and report.** Play with the trucks and patches and tell us what feels or looks wrong: a [Drive report](https://github.com/aaronsb/die-kollektion/issues/new?template=drive-report.yml) for a vehicle, a [bug report](https://github.com/aaronsb/die-kollektion/issues/new?template=bug-report.yml) for anything that breaks.
- **Ask for a vehicle.** A [vehicle request](https://github.com/aaronsb/die-kollektion/issues/new?template=vehicle-request.yml) says what you'd like and whether you'd build it yourself.
- **Build a vehicle.** Each vehicle is one portable folder under `vehicles/<name>/`: its `vehicle.json`, its own meshes and Blender files, its icon, and its contact sheet. Copy the closest existing one, follow [AGENTS.md](AGENTS.md) (or point your agent at it), and open a pull request. Show it off in [Discussions](https://github.com/aaronsb/die-kollektion/discussions/categories/show-and-tell).
- **Test on Windows** once Windows support lands; it's planned, and the label `windows` will collect the work.
- **Answer questions** in [Discussions](https://github.com/aaronsb/die-kollektion/discussions/categories/q-a).

Everything here is shared under GPL-3.0-or-later (code) and CC BY-SA 4.0 (art); by contributing you agree your work is shared the same way. Contribute only geometry, textures and references you made yourself or have the right to share; nothing extracted from the game.

## A change, start to finish

1. **Branch:** `git switch -c fix/<what-it-fixes>` (or `feat/`, `refactor/`, `docs/`).
2. **Change and check:** make the change, then `make loop V=<vehicle>` for each vehicle it touches. That rebuilds the vehicle, runs its gates, regenerates its contact sheet (`vehicles/<name>/README.md`, `contact/`) and writes `contact/CHANGES.md`, the summary of what moved compared with where the branch left main.
3. **Commit by path** (`git add <paths>`, `git commit -- <paths>`), including the updated contact sheets. Never `git add -A` or `git commit -a`.
4. **Pull request:** push and open it with `gh pr create`. Paste each changed vehicle's `CHANGES.md` into the description and say what to look for.
5. **Review:** the reviewer reads the pull request on GitHub: the diff, and the contact-sheet images before and after (GitHub's file view shows them side by side). Driving it first is optional.
6. **Merge:** a regular merge (`gh pr merge <n> --merge`), not a squash or rebase, so the branch's history stays.

## Driving a branch (optional)

With the game closed:

```sh
gh pr checkout <n> && make all        # or: git switch <branch> && make all
```

Back to the known-good build:

```sh
git switch main && git pull && make all
```

`make status` shows which branch and commit is installed. Feedback goes in a pull-request comment, or in a Drive report (the issue form on GitHub) for anything that isn't about one change.
