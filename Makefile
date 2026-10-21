# Werkstatt: set up, build, check and deploy Die Kollektion. `make` (or `make start`) says what to do next.
# Every target is safe to rerun. GAME_DIR is found through Steam; pass GAME_DIR="..." if yours is elsewhere.

PY      := .venv/bin/python
WS      := python3 tools/werkstatt.py
GAME_DIR ?= $(shell python3 tools/werkstatt.py game-dir 2>/dev/null)
export GAME_DIR MY_GAMES DEPLOY_DIR FORCE BEPINEX_ARCHIVE PROFILE VERSION DRY_RUN

.DEFAULT_GOAL := start
.PHONY: start help doctor setup bepinex extract build check contact loop pack deploy undeploy update status save-add save-test save-real all release nexus-images blender-addon kollektion

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
	@for v in vehicles/*/vehicle.json; do g=$$($(PY) -I -c 'import json, sys; print(json.load(open(sys.argv[1])).get("generator", ""))' "$$v"); \
		if [ -n "$$g" ]; then echo "generate $$v ($$g)"; $(PY) "$$g" "$$v" || exit 1; fi; done
	@for v in vehicles/*/vehicle.json; do echo "build $$v"; $(PY) tools/build_vehicle.py "$$v" || exit 1; done
	$(PY) tools/trace_icons.py
	$(PY) -I tools/rasterize_icons.py

check: ## Run every gate (holes, slivers, game-update handling, names, catalogue, hook-page placement); fails if any does
	@$(WS) gates

contact: ## Render every vehicle's contact sheet (needs Blender)
	@for d in $$($(PY) -I -c 'import glob, json; print(" ".join(sorted({json.load(open(p))["donor"] for p in glob.glob("vehicles/*/vehicle.json")})))'); do $(PY) tools/composite_atlas.py $$d || exit 1; done
	@for v in vehicles/*/; do $(PY) tools/contact_sheet.py "$${v%/}" || exit 1; done

deploy: check ## Install the mod into the game (game closed). DEPLOY_DIR=<dir> deploys elsewhere to inspect it
	@$(WS) deploy

undeploy: ## Remove exactly the files the last deploy installed (FORCE=1 if you changed them since)
	@$(WS) undeploy

update: ## Deploy this checkout in full, with the gates (the loader rebuilds the plugin by itself after a game update)
	@$(WS) update

status: ## Compare the repo, the build and the game folder
	@$(WS) status

save-add: ## Put the four trucks in your save (game closed; backs the save up first). IDS="..." for some
	@$(WS) save-add $(IDS)

save-test: ## Swap in a test save where every car owns every part, to preview them in the garage (game closed)
	@$(WS) save-test

save-real: ## Put your own save back after save-test (game closed)
	@$(WS) save-real

all: ## Everything after setup: extract, build, check, deploy
	@$(WS) require
	$(MAKE) --no-print-directory extract
	$(MAKE) --no-print-directory build
	$(MAKE) --no-print-directory deploy
	@echo "Done. Next: make start"

# ---------------------------------------------------------------- changing a vehicle, sharing a pack

loop: ## Change one vehicle: build it, run its gates, redo its contact sheet, summarise what changed (V=<vehicle>)
	@$(WS) loop $(V)

pack: ## Build the shareable zip of a pack into dist/ (P=<pack>, default die-kollektion)
	@python3 tools/pack.py build packs/$(or $(P),die-kollektion)

kollektion: ## Build the kollektion app from one source for Linux and Windows into build/kollektion/<linux-x64|win-x64>/
	@for rid in linux-x64 win-x64; do dotnet publish src/kollektion -c Release -r $$rid -nologo -v quiet -o build/kollektion/$$rid || exit 1; done

blender-addon: ## Zip the Blender add-on for Edit > Preferences > Add-ons > Install from Disk (docs/blender_addon.md)
	@python3 tools/werkstatt.py blender-addon

# ---------------------------------------------------------------- publishing (maintainers)

nexus-images: ## Maintainers: render the Nexus page's banner and gallery into docs/nexus/images/ (needs Blender, built vehicles)
	$(PY) tools/nexus_images.py

release: ## Maintainers: tag and publish a release (VERSION=x.y.z; DRY_RUN=1 builds everything but publishes nothing)
	@python3 tools/release.py build $(VERSION) $(if $(filter 1,$(DRY_RUN)),--dry-run)
