# Contributing

For maintainers and agents changing this repository. Playing, building and making your own vehicle need none of this; see the [README](README.md) and [AGENTS.md](AGENTS.md).

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
