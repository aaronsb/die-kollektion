# Werkstatt: set up, build, check and deploy Die Kollektion. `make` (or `make start`) says what to do next.
# Every target is safe to rerun. GAME_DIR is found through Steam; pass GAME_DIR="..." if yours is elsewhere.

PY      := .venv/bin/python
WS      := python3 tools/werkstatt.py
GAME_DIR ?= $(shell python3 tools/werkstatt.py game-dir 2>/dev/null)
RV      := python3 tools/workshop.py
export GAME_DIR MY_GAMES DEPLOY_DIR FORCE BEPINEX_ARCHIVE PROFILE NO_BROWSER DRY_RUN

.DEFAULT_GOAL := start
.PHONY: start help doctor setup bepinex extract build check contact deploy undeploy status save-add all \
        loop pr prs try main sheet report comment approve pack

start: ## The next setup step, in plain words. Run it again after each step.
	@$(WS) start

help: ## List the targets
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  make %-10s %s\n", $$1, $$2}'

doctor: ## Every check at once: what is missing and how to get it on this system
	@$(WS) doctor

setup: ## Create .venv/ and install the Python packages the tools use
	python3 -m venv .venv
	$(PY) -m pip install --quiet --upgrade pip
	$(PY) -m pip install --quiet -r requirements.txt
	@echo "Python packages installed. Next: make start"

bepinex: ## Install BepInEx (pinned, checksum-verified; asks before downloading) and set its config
	@$(WS) bepinex

extract: ## Copy the game parts the build needs from your install into extracted/ (never shared)
	@$(WS) require
	tools/export_game_data.sh "$(GAME_DIR)"

build: ## Build every vehicle's meshes and icons from vehicles/
	$(PY) tools/make_glyptodon.py
	$(PY) tools/make_megaloceros.py
	@for v in vehicles/*/vehicle.json; do echo "build $$v"; $(PY) tools/build_vehicle.py "$$v" || exit 1; done
	$(PY) tools/trace_icons.py
	$(PY) -I tools/rasterize_icons.py

check: ## Run every gate (holes, slivers, names, catalogue); fails if any does
	@$(WS) gates

contact: ## Render every vehicle's contact sheet (needs Blender)
	$(PY) tools/composite_atlas.py Mammoth
	@for v in vehicles/*/; do $(PY) tools/contact_sheet.py "$${v%/}" || exit 1; done

deploy: check ## Install the mod into the game (game closed). DEPLOY_DIR=<dir> deploys elsewhere to inspect it
	@$(WS) preflight-deploy
	cd plugins/VehicleMods && dotnet build -c Release -nologo -v minimal -p:GameDir="$(GAME_DIR)" $(if $(DEPLOY_DIR),-p:DeployDir="$(abspath $(DEPLOY_DIR))")
	@$(WS) record-deploy

undeploy: ## Remove exactly the files the last deploy installed (FORCE=1 if you changed them since)
	@$(WS) undeploy

status: ## Compare the repo, the build and the game folder
	@$(WS) status

save-add: ## Put the four trucks in your save (game closed; backs the save up first). IDS="..." for some
	@$(WS) save-add $(IDS)

all: ## Everything after setup: extract, build, check, deploy
	@$(WS) require
	$(MAKE) --no-print-directory extract
	$(MAKE) --no-print-directory build
	$(MAKE) --no-print-directory deploy
	@echo "Done. Next: make start"

# ---------------------------------------------------------------- the workshop loop: change, review, drive, merge

loop: ## Change one vehicle: build it, run its gates, redo its contact sheet, summarise what changed (V=<vehicle>)
	@$(RV) loop $(V)

pr: ## Push this branch and open or update its pull request, with every changed vehicle's summary
	@$(RV) pr

prs: ## List open pull requests: branch, which vehicles' sheets changed, checks
	@$(RV) prs

try: ## Install a pull request to drive it: check out, build, check, deploy (PR=<number>; game closed)
	@$(RV) try $(PR)

main: ## Back to the known-good build: main, pulled, built, checked and installed (game closed)
	@$(RV) main

sheet: ## Open a vehicle's contact sheet on GitHub for this branch, or the pull request's files (V=<vehicle>)
	@$(RV) sheet $(V)

report: ## Open a Drive report for a vehicle, prefilled with the installed build (V=<vehicle>)
	@$(RV) report $(V)

comment: ## Comment on a pull request from the terminal (PR=<number> MSG="...")
	@$(RV) comment $(PR) "$(MSG)"

approve: ## Merge a pull request you have driven, then go back to main (PR=<number>; DRY_RUN=1 to only check)
	@$(RV) approve $(PR)

pack: ## Build the shareable zip of a pack into dist/ (P=<pack>, default die-kollektion)
	@python3 tools/pack.py build packs/$(or $(P),die-kollektion)
