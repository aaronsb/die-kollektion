#!/usr/bin/env python3
"""The workshop loop, behind the Makefile: change a vehicle, review it on GitHub, drive it, merge it.

Standard library only; it wraps git, the GitHub CLI (gh) and tools/werkstatt.py. Usage:

    python3 tools/workshop.py loop <vehicle>         build one vehicle, run the gates, redo its contact sheet, write CHANGES.md
    python3 tools/workshop.py pr                     push this branch and open or update its pull request
    python3 tools/workshop.py prs                    list open pull requests and the vehicles they change
    python3 tools/workshop.py try <PR>               check out a pull request, build, check and install it
    python3 tools/workshop.py main                   back to main, pull, build, check and install it
    python3 tools/workshop.py sheet <vehicle>        open the vehicle's contact sheet on GitHub
    python3 tools/workshop.py report <vehicle>       open a Drive report, prefilled with the installed build
    python3 tools/workshop.py comment <PR> <text>    comment on a pull request
    python3 tools/workshop.py approve <PR>           merge a pull request you have driven, then do `main`

Environment: NO_BROWSER=1 prints links instead of opening them; DRY_RUN=1 makes `approve` say what it would
do without merging; FORCE=1 lets `approve` merge a pull request whose build you haven't installed. DEPLOY_DIR
installs somewhere other than the game folder (as `make deploy` does).
"""
import json
import os
import subprocess
import sys
import urllib.parse
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import werkstatt as ws  # noqa: E402

ROOT = ws.ROOT
REPO = "aaronsb/die-kollektion"
WEB = f"https://github.com/{REPO}"


# ---------------------------------------------------------------- git, gh and the installed build

def git(*args, check=False):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if check and r.returncode:
        raise SystemExit(f"git {' '.join(args)} failed:\n{r.stderr.strip()}")
    return r.stdout.strip()


def gh(*args, check=True):
    if not ws.which("gh"):
        raise SystemExit("This needs the GitHub CLI (gh). Install it (Arch: sudo pacman -S github-cli), then run `gh auth login`.")
    r = subprocess.run(["gh", *args], cwd=ROOT, capture_output=True, text=True)
    if check and r.returncode:
        raise SystemExit(f"gh {' '.join(args)} failed:\n{(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


def branch():
    return git("rev-parse", "--abbrev-ref", "HEAD")


def uncommitted():
    return git("status", "--porcelain", "--untracked-files=no")


def base_ref():
    """What a branch is compared with: where it left main. On main itself, the last commit."""
    if branch() == "main":
        return "HEAD"
    subprocess.run(["git", "fetch", "--quiet", "origin", "main"], cwd=ROOT, capture_output=True)
    return git("merge-base", "HEAD", "origin/main") or "HEAD"


def contact_at(ref, name):
    r = subprocess.run(["git", "show", f"{ref}:vehicles/{name}/contact/contact.json"], cwd=ROOT,
                       capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 else None


def changes_text(old, new_path):
    """contact_sheet.py's summary of one vehicle's change (it needs the venv's numpy)."""
    py = ws.VENV_PY if os.path.isfile(ws.VENV_PY) else sys.executable
    tmp = os.path.join(ROOT, "vehicles", ".old-contact.json")
    try:
        if old is not None:
            json.dump(old, open(tmp, "w"))
        r = subprocess.run([py, os.path.join(ROOT, "tools", "contact_sheet.py"), "--changes",
                            tmp if old is not None else "-", new_path], cwd=ROOT, capture_output=True, text=True)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    if r.returncode:
        raise SystemExit(f"contact_sheet.py --changes failed:\n{r.stderr.strip()}")
    return r.stdout


def pr_for_branch():
    out = gh("pr", "view", "--json", "number,url,state", check=False)
    try:
        info = json.loads(out)
        return info if info.get("state") == "OPEN" else None
    except ValueError:
        return None


def installed():
    """The deployed.json `make deploy` wrote, or None."""
    folder = ws.deploy_dir_arg([])
    path = os.path.join(folder, "deployed.json") if folder else None
    return json.load(open(path)) if path and os.path.isfile(path) else None


def open_link(url):
    print(url)
    if os.environ.get("NO_BROWSER") != "1":
        webbrowser.open(url)


def make(target, extra_env=None):
    env = dict(os.environ, **(extra_env or {}))
    r = subprocess.run(["make", "--no-print-directory", target], cwd=ROOT, env=env)
    if r.returncode:
        raise SystemExit(f"`make {target}` failed; nothing past it was done.")


def vehicle_arg(args):
    names = [os.path.basename(v) for v in ws.vehicles()]
    if not args or args[0] not in names:
        raise SystemExit(f"Name a vehicle: V=<{'|'.join(names)}>")
    return args[0]


def pr_arg(args):
    if not args or not args[0].isdigit():
        raise SystemExit("Name a pull request: PR=<number> (`make prs` lists them).")
    return args[0]


def refuse_if_running():
    folder = ws.deploy_dir_arg([])
    game = ws.game_dir()
    if game and folder and os.path.realpath(folder).startswith(os.path.realpath(game) + os.sep) and ws.game_running():
        raise SystemExit("The game is running. Quit it first: installing into a running game breaks it.")


def refuse_if_uncommitted():
    if uncommitted():
        raise SystemExit("You have uncommitted changes, and switching branches would carry or lose them:\n"
                         + uncommitted() + "\nCommit them (or `git stash` them), then run this again.")


# ---------------------------------------------------------------- the commands

def cmd_loop(args):
    name = vehicle_arg(args)
    vdir = os.path.join(ROOT, "vehicles", name)
    py = ws.VENV_PY
    generator = os.path.join(ROOT, "tools", f"make_{name}.py")
    steps = ([[py, generator]] if os.path.isfile(generator) else []) + [
        [py, os.path.join(ROOT, "tools", "build_vehicle.py"), os.path.join(vdir, "vehicle.json")],
        [sys.executable, os.path.join(ROOT, "tools", "werkstatt.py"), "gates", name],
        [py, os.path.join(ROOT, "tools", "composite_atlas.py"), "Mammoth"],
        [py, os.path.join(ROOT, "tools", "contact_sheet.py"), vdir],
    ]
    for cmd in steps:
        print("→ " + " ".join(os.path.relpath(c, ROOT) if c.startswith(ROOT) else c for c in cmd), flush=True)
        if subprocess.run(cmd, cwd=ROOT).returncode:
            print("Stopped here. Fix what it reports, then run `make loop V=" + name + "` again.")
            return 1
    base = base_ref()
    text = changes_text(contact_at(base, name), os.path.join(vdir, "contact", "contact.json"))
    out = os.path.join(vdir, "contact", "CHANGES.md")
    open(out, "w").write(f"<!-- Compared with {base[:7]} ({'the last commit' if base == 'HEAD' else 'where this branch left main'}). -->\n" + text)
    print("\n" + text)
    ws.say("Next step:", (
        "You're on main: put the change on a branch before committing it, for example\n"
        "    git switch -c fix/<what-it-fixes>\n" if branch() == "main" else "") +
        f"Look at vehicles/{name}/README.md (the renders and the rig view), commit the vehicle folder, then run\n"
        "    make pr\n"
        "to put it up for review on GitHub.")
    return 0


def cmd_pr(_args):
    b = branch()
    if b == "main":
        raise SystemExit("You're on main. Pull requests come from a branch: `git switch -c fix/<what-it-fixes>`, commit, then `make pr`.")
    if uncommitted():
        print("Note: these changes are not committed, so they are not in the pull request:\n" + uncommitted() + "\n")
    base = base_ref()
    commits = git("log", "--reverse", "--format=%s", f"{base}..HEAD").splitlines()
    if not commits:
        raise SystemExit("This branch has no commits beyond main yet. Commit your change, then run `make pr`.")
    sections = []
    for v in ws.vehicles():
        name = os.path.basename(v)
        old, new = contact_at(base, name), contact_at("HEAD", name)
        if new is None or old == new:
            continue
        path = os.path.join(v, "contact", "contact.json")
        sections.append(changes_text(old, path) + f"\nContact sheet on this branch: {WEB}/tree/{b}/vehicles/{name}\n")
    git("push", "--quiet", "-u", "origin", "HEAD", check=True)
    body = ("## What changed\n\n" + "\n".join(f"- {c}" for c in commits) + "\n\n"
            + ("## Vehicles\n\n" + "\n".join(sections) if sections else "No vehicle's contact sheet changed.\n")
            + "\n## How to test in game\n\n```\nmake try PR=<this number>\n```\n\n"
            "Drive it, then `make report V=<vehicle>` for what you noticed, `make comment PR=<n> MSG=\"...\"` "
            "for a quick note, or `make approve PR=<n>` to merge it.\n\n"
            "<!-- Written by `make pr` (tools/workshop.py); rerun it after new commits to refresh this description. -->\n")
    existing = pr_for_branch()
    if existing:
        gh("pr", "edit", str(existing["number"]), "--body", body)
        url, number = existing["url"], existing["number"]
        print(f"Updated pull request #{number}: {url}")
    else:
        url = gh("pr", "create", "--base", "main", "--head", b, "--title", commits[0], "--body", body)
        number = url.rstrip("/").rsplit("/", 1)[-1]
        print(f"Opened pull request #{number}: {url}")
    ws.say("Next step:", f"Install it and drive it:\n    make try PR={number}")
    return 0


def cmd_prs(_args):
    out = json.loads(gh("pr", "list", "--state", "open", "--json", "number,title,headRefName,files,statusCheckRollup"))
    if not out:
        print("No open pull requests.")
        return 0
    for p in out:
        changed = sorted({f["path"].split("/")[1] for f in p.get("files", [])
                          if f["path"].startswith("vehicles/") and "/contact/" in f["path"]})
        states = [c.get("conclusion") or c.get("state") or c.get("status") for c in p.get("statusCheckRollup") or []]
        checks = "no checks" if not states else ", ".join(f"{states.count(s)} {str(s).lower()}" for s in sorted(set(map(str, states))))
        print(f"#{p['number']:<4} {p['title']}\n      branch {p['headRefName']}; sheets changed: "
              f"{', '.join(changed) or 'none'}; checks: {checks}")
    ws.say("\nNext step:", "Install one and drive it:\n    make try PR=<number>")
    return 0


def cmd_try(args):
    number = pr_arg(args)
    refuse_if_running()
    refuse_if_uncommitted()
    gh("pr", "checkout", number)
    print(f"On the branch of pull request #{number} ({branch()} @ {git('rev-parse', '--short', 'HEAD')}).", flush=True)
    make("build")
    make("deploy", {"WERKSTATT_PR": number})
    ws.say("Next step:", f"Start Over the Hill and drive it. Then either\n"
           f"    make report V=<vehicle>     say what you noticed (opens the Drive report form)\n"
           f"    make approve PR={number}       merge it and go back to main\n"
           f"or `make main` to go back to the known-good build without merging.")
    return 0


def cmd_main(_args):
    refuse_if_running()
    refuse_if_uncommitted()
    git("checkout", "--quiet", "main", check=True)
    r = subprocess.run(["git", "pull", "--ff-only", "--quiet"], cwd=ROOT, capture_output=True, text=True)
    if r.returncode:
        print("Couldn't pull main (offline?); installing the main you have:\n" + r.stderr.strip())
    print(f"On main @ {git('rev-parse', '--short', 'HEAD')}.", flush=True)
    make("build")
    make("deploy", {"WERKSTATT_PR": ""})
    ws.say("Next step:", "The known-good build is installed. Start the game, or `make prs` for changes waiting for review.")
    return 0


def cmd_sheet(args):
    name = vehicle_arg(args)
    b = branch()
    pr = pr_for_branch() if b != "main" else None
    if pr:
        open_link(f"{pr['url']}/files")
    else:
        if not git("ls-remote", "--heads", "origin", b):
            print(f"Branch {b} isn't on GitHub yet; `make pr` pushes it. Showing the local file instead:")
            print(os.path.join(ROOT, "vehicles", name, "README.md"))
            return 0
        open_link(f"{WEB}/tree/{b}/vehicles/{name}")
    return 0


def cmd_report(args):
    name = vehicle_arg(args)
    m = ws.manifest(os.path.join(ROOT, "vehicles", name))
    label = f"{m.get('displayName', 'Das ' + name.title())} (stock car, patched)" if m.get("patch") else m.get("displayName")
    rec = installed()
    if rec:
        build = f"{rec.get('branch', '?')} @ {rec.get('repoCommit', '?')[:7]}" + (f", PR #{rec['pr']}" if rec.get("pr") else "")
    else:
        build = "not installed with `make deploy`"
    query = urllib.parse.urlencode({"template": "drive-report.yml", "title": f"Drive report: {label}",
                                    "labels": f"drive-report,vehicle:{name}", "vehicle": label, "build": build})
    open_link(f"{WEB}/issues/new?{query}")
    return 0


def cmd_comment(args):
    number = pr_arg(args)
    text = " ".join(args[1:]).strip()
    if not text:
        raise SystemExit('Say something: make comment PR=<n> MSG="..."')
    print(gh("pr", "comment", number, "--body", text))
    return 0


def cmd_approve(args):
    number = pr_arg(args)
    info = json.loads(gh("pr", "view", number, "--json", "state,mergeable,title,headRefName,statusCheckRollup,url"))
    if info["state"] != "OPEN":
        raise SystemExit(f"Pull request #{number} is {info['state'].lower()}, not open.")
    if info.get("mergeable") == "CONFLICTING":
        raise SystemExit(f"Pull request #{number} conflicts with main; it needs updating before it can merge.")
    checks = info.get("statusCheckRollup") or []
    failing = [c.get("name") for c in checks if (c.get("conclusion") or c.get("state")) in ("FAILURE", "ERROR", "CANCELLED", "TIMED_OUT")]
    pending = [c.get("name") for c in checks if (c.get("status") or c.get("state")) in ("IN_PROGRESS", "QUEUED", "PENDING")]
    if failing or pending:
        raise SystemExit(f"Checks not passed on #{number}: " + ", ".join(failing + pending))
    rec = installed()
    if (not rec or str(rec.get("pr")) != number) and os.environ.get("FORCE") != "1":
        raise SystemExit(f"The installed build isn't pull request #{number}, so you haven't driven it.\n"
                         f"Drive it first (`make try PR={number}`), or merge anyway with FORCE=1.")
    print(f"#{number} {info['title']}: open, " + ("no checks" if not checks else f"{len(checks)} checks passed")
          + (", installed and driven." if rec and str(rec.get("pr")) == number else ", not driven (FORCE=1)."))
    if os.environ.get("DRY_RUN") == "1":
        print(f"DRY_RUN: would run `gh pr merge {number} --merge --delete-branch`, then `make main`.")
        return 0
    refuse_if_running()
    refuse_if_uncommitted()
    gh("pr", "merge", number, "--merge", "--delete-branch")
    print(f"Merged #{number}.")
    return cmd_main([])


COMMANDS = {"loop": cmd_loop, "pr": cmd_pr, "prs": cmd_prs, "try": cmd_try, "main": cmd_main, "sheet": cmd_sheet,
            "report": cmd_report, "comment": cmd_comment, "approve": cmd_approve}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(2)
    sys.exit(COMMANDS[sys.argv[1]](sys.argv[2:]))
