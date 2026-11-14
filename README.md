---
title: Wavefinity
emoji: 🌊
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# Wavefinity — modular 3D-printable organizers

Wavefinity is a browser-only application with a Python geometry engine for designing and exporting **wavy, interlocking bins**, connectors, dividers, fitted holders and related organizer components. The live static edition runs the geometry/export engine in the browser and provides 2D/3D previews; the CLI and legacy local web service use the same engine. The principal footprint grid is **7 mm**. Designs can include configurable walls, bases, lids, stacking, lettering and fitted inserts. Detailed product behavior and numerical constraints live in the references below, not in this introductory page.

## User workflow

- **Design a bin:** set dimensions, wall/base, interior parts, labels and optional lid/stacking, then preview and save or generate a print file.
- **Organize a Space:** manage bins in a Drawer, Storage Box, Storage Drawers, Surface or Pegboard workflow, with placement, inventory and Space-specific structural parts. Consult the UI reference for each mode and any current Gridfinity options.
- **Print/export:** the Python engine produces 3MF/STL output; assembly/fit requirements and the difference between preview and verified prints are documented in the geometry reference.

The **Side connector** joins two bins at a seam; separate 3-Way/4-Way Corner connectors support suitable equal-height bins. Connector fit depends on the associated bin wall. A Storage Box case and Surface Base Trim are structural outputs of their Spaces, not ordinary Designer bins.

## Live edition and local legacy server

Use the browser-only edition at [www.wavefinity.org](https://www.wavefinity.org). It runs geometry locally in the browser and stores user files on the user's PC.

### Start the legacy server locally

Normal Windows launch: double-click `Launch_Organizer_UI.bat`. The launcher checks GitHub and safely updates the checkout before starting the local service, normally at **http://127.0.0.1:8765**. The Python geometry engine stays local; opening the browser does not move geometry computation to the browser.

**Do not use `Launch_Wavefinity_Clean.bat` casually:** it deliberately wipes application-generated data before relaunching. For server startup, generated output, persistence and recovery details, see [CLI, code and operations](docs/reference/cli-code-and-operations.md).

## Documentation map — open only what the task needs

| Need | Reference |
| --- | --- |
| UI controls, Space types, inventory, layouts, dividers and labels | [UI and Spaces](docs/reference/ui-spaces.md) |
| Feature settings, data ownership and browser API/service | [Features and browser service](docs/reference/features-and-service.md) |
| Geometry, holders, waves, clearances, connectors, text and options | [Geometry and options](docs/reference/geometry-and-options.md) |
| Command-line usage, repository code map, runtime/startup behavior | [CLI, code and operations](docs/reference/cli-code-and-operations.md) |
| Settled numbers, rejected approaches, traps and dated development evidence | [Design decisions and history](docs/reference/design-notes.md) |
| User-facing feature inventory | [features.md](features.md) |
| Outside-AI design option catalog | [ai-features.md](ai-features.md) |
| Agent/Story workflow, owner testing policy, browser audit rules | [AGENTS.md](AGENTS.md) |

Detailed documentation is organized by topic to keep the introduction short. AI working instructions are maintained separately in [AGENTS.md](AGENTS.md).

**Feature & AI docs rule:** When an option is added, changed or removed, the same change updates [features.md](features.md), [ai-features.md](ai-features.md), and the embedded AI Design prompt in [wavefinity_web_impl/_ai.py](wavefinity_web_impl/_ai.py) (including its capability manifest), refreshes the browser catalog snapshot (`web/browser-core/engine/catalog.json`), and passes one check: the manifest never offers an option the answer validator (`_ai_semantic_violation`) rejects. The implementation/catalog owns exact schemas and numerical validation limits.

## Migration references

The browser-only migration design is recorded in the [execution specification](Future%20plans/Browser-only-migration-execution-spec.md); supporting contracts and route maps live in `Future plans/`. The [legacy hosting record](docs/legacy-python-server-hosting.md) documents recovery of the retired Python Web Service.
