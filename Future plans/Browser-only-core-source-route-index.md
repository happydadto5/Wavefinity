# Wavefinity current source route lookup — migration navigation only

Source ownership baseline from November 12, 2026, reconciled to current `main` at `794691fa72610b94130f3fe1e75de7b6aac775cf` by B01. Source anchors are handler definition lines at that head (lookup hints, not a frozen snapshot of later edits). The machine-readable twin of this table is `web/browser-core/contracts/route-manifest.json`, which also carries each route's input fields, output fields and effects. The **Owner column is authoritative single-owner Bxx**, not a list of contributors. **No test code, test scanners, test execution, or user QA plans.** Before implementing a package, read its named current source functions because ongoing Gridfinity changes can shift code.

`wavefinity_web.py` registers the core Python routes and `organizer_drawer/__init__.py:drawer_routes` adds drawer routes. `organizer_spaces/__init__.py:space_routes` is registered only under `if not HOSTED` in the legacy web server; the final browser app needs those Space operations anyway. The frontend column lists prominent literal call sites, **not every indirect caller**. **Ownership is singular:** a consuming UI package is not a second route owner. For example, **B10 owns all `/api/drawer/*` routes, including its print variants**, while B08 supplies shared print preparation/3MF helpers; **B11 owns all structural/Storage Drawers routes and pegboard hooks**. B09 owns folder/Space operations and `/api/space/warm`; B13 owns the browser-only replacement for the legacy slicer-browse and show-log paths. `route_dispatch.py` is a shared routing integration point owned first by B04 and finally by B14, not a second owner of those route semantics.

| API path | Existing handler | Main frontend reference(s) | Owner | Runtime | Disposition |
|---|---|---|---|---|---|
| `/api/ai/ask` | `ai_ask_payload` · `wavefinity_web.py:3206` | `web/app/02-lifecycle-ai-help.js:916` | B13 | javascript | local |
| `/api/ai/candidate` | `ai_candidate_payload` · `wavefinity_web.py:3255` | `web/app/02-lifecycle-ai-help.js:638` | B13 | python | local |
| `/api/ai/connection` | `ai_connection_payload` · `wavefinity_web.py:3158` | `web/app/02-lifecycle-ai-help.js:879`, `web/app/02-lifecycle-ai-help.js:900` | B13 | javascript | local |
| `/api/ai/prompt` | `ai_prompt_payload` · `wavefinity_web.py:3218` | `web/app/02-lifecycle-ai-help.js:604` | B13 | python | local |
| `/api/ai/repair-prompt` | `ai_repair_prompt_payload` · `wavefinity_web_impl/_ai.py:646` | `web/app/02-lifecycle-ai-help.js:801` | B13 | python | local |
| `/api/browse-output-folder` | `browse_output_folder_payload` · `wavefinity_web.py:1297` | `web/spaces/07-welcome-folders.js:46` | B09 | javascript | local |
| `/api/browse-slicer-path` | `browse_slicer_path_payload` (POST; also GET) · `wavefinity_web.py:1239` | `web/app/15-generate-dialogs.js:619` | B13 | javascript | local |
| `/api/catalog` | `catalog_payload (GET)` · `wavefinity_web.py:733` | `web/app.js:7` | B04 | python | local |
| `/api/connector` | `connector_save_payload` · `wavefinity_web.py:2075` | `web/app/15-generate-dialogs.js:285`, `web/app/15-generate-dialogs.js:291` | B06 | python | local |
| `/api/design/division-label-fit` | `division_label_fit_payload` · `wavefinity_web.py:1928` | `web/app/08-draft-fields-render.js:1026` | B04 | python | local |
| `/api/design/inventory-preview` | `inventory_preview_payload` · `wavefinity_web_impl/_designs/_layout.py:327` | No literal reference in current callers | B04 | python | local |
| `/api/design/validate` | `_validate_design_open_guard -> validate_design_payload (wavefinity_web_impl/_designs/_preview.py)` · `wavefinity_web.py:3497` | `web/app/02-lifecycle-ai-help.js:214`, `web/app/03-history-utils-catalog.js:172`, `web/app/07-kind-pickers-bore-math.js:301` (+3 more) | B04 | python | local |
| `/api/drawer/connectors` | `connectors` · `organizer_drawer/__init__.py:1234` | No literal reference in current callers | B10 | python | local |
| `/api/drawer/design-source/duplicate` | `duplicate_design_source` · `organizer_drawer/__init__.py:528` | `web/app/03-history-utils-catalog.js:140`, `web/drawer-model.js:1406`, `web/drawer-panel.js:684` | B10 | python | local |
| `/api/drawer/design-source/save` | `save_design_source` · `organizer_drawer/__init__.py:479` | `web/app/02-lifecycle-ai-help.js:95`, `web/drawer-view.js:1374`, `web/spaces/06-inventory-io.js:172` | B10 | python | local |
| `/api/drawer/design-source/status` | `change_design_status` · `organizer_drawer/__init__.py:539` | `web/app/15-generate-dialogs.js:254`, `web/app/15-generate-dialogs.js:488`, `web/app/15-generate-dialogs.js:516` (+2 more) | B10 | python | local |
| `/api/drawer/generate-bin` | `generate_hosted_bin` · `organizer_drawer/__init__.py:500` | `web/spaces/06-inventory-io.js:62` | B10 | python | local |
| `/api/drawer/load` | `load` · `organizer_drawer/__init__.py:439` | `web/app/06-form-sync-controls.js:166`, `web/drawer-model.js:1205`, `web/spaces/06-inventory-io.js:280` | B10 | python | local |
| `/api/drawer/print-bins` | `print_bins` · `organizer_drawer/__init__.py:1030` | `web/drawer-model.js:1898` | B10 | python | local |
| `/api/drawer/print-complete` | `print_complete` · `organizer_drawer/__init__.py:1048` | `web/drawer-model.js:1941` | B10 | python | local |
| `/api/drawer/print-spacers` | `print_spacers_only` · `organizer_drawer/__init__.py:981` | `web/drawer-model.js:1761` | B10 | python | local |
| `/api/drawer/report` | `report` · `organizer_drawer/__init__.py:565` | `web/drawer-model.js:1455` | B10 | python | local |
| `/api/drawer/save` | `save` · `organizer_drawer/__init__.py:459` | `web/drawer-model.js:1282`, `web/drawer-model.js:1296`, `web/drawer-model.js:1356` (+3 more) | B10 | python | local |
| `/api/drawer/save-bins` | `save_bins` · `organizer_drawer/__init__.py:1222` | `web/drawer-model.js:1860` | B10 | python | local |
| `/api/drawer/spacers` | `spacers` · `organizer_drawer/__init__.py:630` | `web/drawer-panel.js:1154` | B10 | python | local |
| `/api/drawer/spacers/generate` | `spacers_generate` · `organizer_drawer/__init__.py:648` | No literal reference in current callers | B10 | python | local |
| `/api/drawer/spacers/refresh` | `spacers_refresh` · `organizer_drawer/__init__.py:772` | `web/drawer-model.js:1622`, `web/spaces/06-inventory-io.js:168` | B10 | python | local |
| `/api/drawer/surface-fill` | `surface_fill` · `organizer_drawer/__init__.py:572` | `web/drawer-model.js:1540` | B10 | python | local |
| `/api/drawer/surface-fill/create` | `surface_fill_create` · `organizer_drawer/__init__.py:580` | `web/drawer-model.js:1559` | B10 | python | local |
| `/api/export/<token>/<filename>` | `token download (GET)` · `wavefinity_web.py:do_GET` | `web/app/15-generate-dialogs.js:670`, `web/app/15-generate-dialogs.js:704`, `web/app/15-generate-dialogs.js:734` (+3 more) | B06 | none | retired → local Blob ID |
| `/api/feature/apply` | `apply_feature_payload` · `wavefinity_web_impl/_designs/_features.py:297` | `web/app/06-form-sync-controls.js:295`, `web/app/07-kind-pickers-bore-math.js:525`, `web/app/10-draft-update-commit.js:848` (+2 more) | B04 | python | local |
| `/api/feature/default` | `default_feature_payload` · `wavefinity_web_impl/_designs/_features.py:67` | `web/app/07-kind-pickers-bore-math.js:489` | B04 | python | local |
| `/api/feature/delete` | `delete_feature_payload` · `wavefinity_web_impl/_designs/_features.py:500` | `web/app/11-parts-preview-requests.js:97` | B04 | python | local |
| `/api/feature/draft` | `draft_payload` · `wavefinity_web_impl/_designs/_features.py:185` | `web/app/10-draft-update-commit.js:675`, `web/app/10-draft-update-commit.js:897` | B04 | python | local |
| `/api/feature/duplicate` | `duplicate_feature_payload` · `wavefinity_web_impl/_designs/_features.py:428` | `web/app/09-draft-sizing-helpers.js:543` | B04 | python | local |
| `/api/feature/fit` | `feature_fit_payload` · `wavefinity_web_impl/_designs/_features.py:270` | `web/app/11-parts-preview-requests.js:846` | B04 | python | local |
| `/api/folder/inventory` | `set_inventory` · `organizer_spaces/__init__.py:964` | No literal reference in current callers | B09 | javascript | local |
| `/api/folder/no-defined-space` | `no_defined_space` · `organizer_spaces/__init__.py:1074` | `web/spaces/08-space-setup.js:313` | B09 | javascript | local |
| `/api/folder/use` | `open_folder` · `organizer_spaces/__init__.py:1067` | `web/spaces/07-welcome-folders.js:94` | B09 | javascript | local |
| `/api/generate` | `generate_payload` · `wavefinity_web.py:1734` | `web/app/15-generate-dialogs.js:237` | B06 | python | local |
| `/api/health` | `health_payload (GET)` · `wavefinity_web.py:547` | `web/app/15-generate-dialogs.js:749` | B03 | javascript | local |
| `/api/layout/expand` | `expand_layout_payload` · `wavefinity_web_impl/_designs/_layout.py:43` | `web/app/07-kind-pickers-bore-math.js:407`, `web/app/09-draft-sizing-helpers.js:127`, `web/app/11-parts-preview-requests.js:978` (+1 more) | B04 | python | local |
| `/api/layout/mode` | `mode_payload` · `wavefinity_web_impl/_designs/_features.py:527` | `web/app/03-history-utils-catalog.js:876` | B04 | python | local |
| `/api/nest/photo` | `photo_nest_payload` · `wavefinity_web_impl/_nest.py:371` | `web/app/09-draft-sizing-helpers.js:780` | B12 | python | local |
| `/api/nest/retrace` | `nest_retrace_payload` · `wavefinity_web_impl/_nest.py:350` | `web/app/09-draft-sizing-helpers.js:597` | B12 | python | local |
| `/api/nest/trace` | `nest_trace_payload` · `wavefinity_web.py:699` | `web/app/09-draft-sizing-helpers.js:706` | B12 | python | local |
| `/api/operation-status` | `operation_status_payload` · `wavefinity_web_impl/_runtime.py:349` | `web/app/03-history-utils-catalog.js:480`, `web/app/03-history-utils-catalog.js:522` | B03 | javascript | local |
| `/api/pegboard/hooks` | `pegboard_hooks_payload` · `wavefinity_web.py:2160` | `web/spaces/12-space-info.js:261` | B11 | python | local |
| `/api/pegboard/layouts` | `pegboard_layouts_payload` · `wavefinity_web_impl/_designs/_layout.py:350` | `web/drawer-model.js:1169` | B04 | python | local |
| `/api/preferences` | `preferences_payload` · `wavefinity_web.py:1191` | `web/app/05-surface-trim-form.js:320`, `web/app/06-form-sync-controls.js:119`, `web/app/15-generate-dialogs.js:631` | B09 | javascript | local |
| `/api/preview` | `preview_payload` · `wavefinity_web.py:1401` | `web/app/11-parts-preview-requests.js:768`, `web/structural-design.js:397` | B05 | python | local |
| `/api/print` | `print_payload` · `wavefinity_web.py:2208` | `web/app/15-generate-dialogs.js:467` | B08 | python | local |
| `/api/sampler` | `sampler_payload` · `wavefinity_web.py:2099` | No literal reference in current callers | B06 | python | local |
| `/api/show-log` | `show_log_payload` · `wavefinity_web.py:1388` | No literal reference in current callers | B13 | javascript | local |
| `/api/space/browse-storage-parent` | `browse_space_parent_payload` · `wavefinity_web.py:1333` | `web/spaces/07-welcome-folders.js:377` | B09 | javascript | local |
| `/api/space/configure` | `configure_migrate` · `organizer_spaces/__init__.py:847` | `web/spaces/08-space-setup.js:682` | B09 | javascript | local |
| `/api/space/configure-text` | `configure_space_text_payload` · `wavefinity_web_impl/_designs/_layout.py:412` | `web/spaces/08-space-setup.js:611`, `web/spaces/12-space-info.js:453` | B09 | javascript | local |
| `/api/space/copy` | `copy_space` · `organizer_spaces/__init__.py:1151` | `web/spaces/12-space-info.js:195`, `web/spaces/12-space-info.js:290` (dynamic `/api/space/${action}`) | B09 | javascript | local |
| `/api/space/copy-name` | `copy_space_name_payload` · `wavefinity_web_impl/_designs/_layout.py:388` | `web/spaces/12-space-info.js:105` | B09 | javascript | local |
| `/api/space/copy-text` | `copy_space_text_payload` · `wavefinity_web_impl/_designs/_layout.py:397` | `web/spaces/12-space-info.js:177` | B09 | javascript | local |
| `/api/space/create` | `configure` · `organizer_spaces/__init__.py:759` | `web/spaces/08-space-setup.js:682` | B09 | javascript | local |
| `/api/space/create-text` | `create_space_text_payload` · `wavefinity_web_impl/_designs/_layout.py:364` | `web/spaces/08-space-setup.js:611` | B09 | javascript | local |
| `/api/space/defaults` | `set_bin_defaults` · `organizer_spaces/__init__.py:994` | `web/spaces/05-space-memory.js:553` | B09 | javascript | local |
| `/api/space/delete` | `delete_space` · `organizer_spaces/__init__.py:1202` | `web/spaces/12-space-info.js:195`, `web/spaces/12-space-info.js:303` (dynamic `/api/space/${action}`) | B09 | javascript | local |
| `/api/space/forget` | `forget` · `organizer_spaces/__init__.py:1103` | `web/spaces/09-event-wiring.js:134` | B09 | javascript | local |
| `/api/space/inspect` | `inspect` · `organizer_spaces/__init__.py:732` | `web/spaces/07-welcome-folders.js:82`, `web/spaces/07-welcome-folders.js:253`, `web/spaces/08-space-setup.js:343` (+1 more) | B09 | javascript | local |
| `/api/space/no-inventory` | `lambda payload: set_inventory({**payload, 'inventory': False})` · `organizer_spaces/__init__.py:1465` | No literal reference in current callers | B09 | javascript | local |
| `/api/space/open` | `open_folder` · `organizer_spaces/__init__.py:1067` | No literal reference in current callers | B09 | javascript | local |
| `/api/space/other-spaces` | `other_spaces_route` · `organizer_spaces/__init__.py:726` | `web/spaces/07-welcome-folders.js:166` | B09 | javascript | local |
| `/api/space/printer-profile` | `printer_profile_route` · `organizer_spaces/__init__.py:1385` | `web/spaces/13-printer-profiles.js:14`, `web/spaces/13-printer-profiles.js:19`, `web/spaces/13-printer-profiles.js:38` (+1 more) | B09 | javascript | local |
| `/api/space/resume` | `resume` · `organizer_spaces/__init__.py:1033` | `web/spaces/05-space-memory.js:430` | B09 | javascript | local |
| `/api/space/show-folder` | `show_folder_payload` · `wavefinity_web.py:1272` | `web/spaces/12-space-info.js:88` | B09 | javascript | local |
| `/api/space/startup` | `startup` · `organizer_spaces/__init__.py:669` | `web/spaces/08-space-setup.js:1132` | B09 | javascript | local |
| `/api/space/storage-box-print` | `storage_box_print_payload` · `wavefinity_web.py:3004` | `web/spaces/10-storage-box-structural.js:384` | B11 | python | local |
| `/api/space/storage-change` | `change_storage` · `organizer_spaces/__init__.py:1316` | `web/spaces/07-welcome-folders.js:445` | B09 | javascript | local |
| `/api/space/storage-drawers-mutate` | `storage_drawers_mutate_route` · `organizer_spaces/__init__.py:1405` | `web/spaces/14-drawers-cabinet.js:189` | B11 | python | local |
| `/api/space/storage-drawers-mutate-text` | `storage_drawers_mutate_text_payload` · `wavefinity_web_impl/_outputs.py:242` | `web/spaces/14-drawers-cabinet.js:206` | B11 | python | local |
| `/api/space/storage-drawers-reset` | `storage_drawers_reset_payload` · `wavefinity_web_impl/_outputs.py:316` | `web/spaces/04-metadata-persistence.js:34` | B11 | python | local |
| `/api/space/storage-drawers-summary` | `storage_drawers_summary_payload` · `wavefinity_web.py:2423` | `web/spaces/14-drawers-cabinet.js:106`, `web/structural-design.js:188` | B11 | python | local |
| `/api/space/storage-drawers-validate` | `storage_drawers_validate_payload` · `wavefinity_web_impl/_outputs.py:310` | `web/spaces/04-metadata-persistence.js:30` | B11 | python | local |
| `/api/space/storage-parent` | `set_storage_parent` · `organizer_spaces/__init__.py:1215` | No literal reference in current callers | B09 | javascript | local |
| `/api/space/storage-plan` | `storage_plan` · `organizer_spaces/__init__.py:1242` | `web/spaces/07-welcome-folders.js:379` | B09 | javascript | local |
| `/api/space/storage-state` | `storage_state` · `organizer_spaces/__init__.py:1238` | `web/spaces/07-welcome-folders.js:356` | B09 | javascript | local |
| `/api/space/structural-design` | `structural_design_payload` · `wavefinity_web.py:2535` | `web/spaces/10-storage-box-structural.js:164`, `web/spaces/11-base-trim.js:156`, `web/structural-design.js:387` (+1 more) | B11 | python | local |
| `/api/space/structural-generate` | `structural_generate_payload` · `wavefinity_web.py:2604` | `web/spaces/10-storage-box-structural.js:358`, `web/spaces/11-base-trim.js:195`, `web/spaces/11-base-trim.js:306` (+2 more) | B11 | python | local |
| `/api/space/structural-print` | `structural_print_payload` · `wavefinity_web.py:2733` | `web/spaces/10-storage-box-structural.js:307`, `web/spaces/14-drawers-cabinet.js:475` | B11 | python | local |
| `/api/space/structural-print-combined` | `structural_print_combined_payload` · `wavefinity_web.py:2620` | `web/spaces/14-drawers-cabinet.js:412` | B11 | python | local |
| `/api/space/surface-print` | `surface_print_payload` · `wavefinity_web.py:3014` | `web/spaces/11-base-trim.js:347` | B11 | python | local |
| `/api/space/update` | `update` · `organizer_spaces/__init__.py:908` | `web/spaces/12-space-info.js:488` | B09 | javascript | local |
| `/api/space/use-untyped` | `use_folder` · `organizer_spaces/__init__.py:735` | `web/spaces/08-space-setup.js:997` | B09 | javascript | local |
| `/api/space/warm` | `warm_spaces_payload` · `wavefinity_web.py:1473` | `web/workspace.js:871` | B09 | javascript | local |
| `/api/suggestions` | `_post_suggestion` · `wavefinity_web.py:3780` | `web/app/16-suggestions.js:30` (direct `fetch()`, not `api()`) | B13 | javascript | local |

## Non-API paths previously supplied by Python

- `/` and HTML/CSS/JS requests resolve beneath `web/`. **Build must copy web contents to dist root**, not to `dist/web`.
- `/images/*` resolves from repository-root `images/`; **copy into `dist/images/`**.
- `/Brochure.md` (also lowercase legacy path `/brochure.md`) resolves from repository-root `Brochure.md`. The static build copies BOTH `dist/Brochure.md` and a byte-identical `dist/brochure.md` alias; no redirect/rule dependency.
- `/api/export/<token>/<filename>` is a server stream of temporary generated files; replace with transferable buffers and local Blobs, not a static URL.
- `/api/catalog` and `/api/health` currently come from server GET handlers. The browser edition serves static/generated catalog and runtime/build identity without a network API.

## Bxx authoritative single-owner resolution

All 92 indexed route rows above have exactly one primary Bxx owner AND explicit disposition: **91 local operations, 1 retired token-download pattern**. B01 reconciliation at `794691f`: the source registries (`POST_ROUTES` in `wavefinity_web.py`, `drawer_routes`, `space_routes`, the `do_GET` handlers and `_post_suggestion`) define exactly these 92 paths; the completed Gridfinity work changed behavior inside existing routes and added no new route path. `/api/browse-slicer-path` is also answered as an HTTP GET with an empty payload (no UI caller); it stays one row (POST) owned by B13. `/api/space/copy` and `/api/space/delete` are reached only through the dynamic `/api/space/${action}` call in `web/spaces/12-space-info.js`. The Runtime column is the browser-edition runtime: B03 health/operation-status, all B09 routes and the B13 provider/capability routes (`/api/ai/connection`, `/api/ai/ask`, `/api/suggestions`, `/api/browse-slicer-path`, `/api/show-log`) are JavaScript; every other local route is Python. At later Andrew GO, compare source registry additions to this table by reading current source, update the index and B01 manifest together. Build-time manifest/registry key comparison uses the updated row set, not the historical numeric 92. If a newly added Gridfinity endpoint exists when the Stories are created, assign it ONE semantic owner and update its row and the static B01 manifest. B04 supplies Python `web/browser-core/engine/route_dispatch.py` and fail-closed `UNSUPPORTED_LOCAL_OPERATION` dispatch. Later packages export their own Python `ROUTES` or JavaScript `ROUTES` (for browser file access/AI connection) without editing central registries. **B14 assembles Python routes into `route_dispatch.py` and JS routes into `local-api.js` once**, without cross-language importing, and emits a single flat route declaration used by normal production shipping. Missing/unknown/retired routes never fall back to HTTP. No parallel central-registry edits. The canonical B01 contract is `web/browser-core/contracts/route-manifest.json`, with path/method/owner/disposition/runtime/module/handler/input/output/effects. B14's production build checks each **local** manifest route matches exactly one actual flat dispatcher registration, each **retired** route matches no callable registration, and the source index has the same dispositions. Do NOT treat this as a test runner, route-scanning script or runtime certification. Ship the manifest to `dist/` only if runtime consumes it. The old root `browser-core/contracts/` path is invalid.

## Route ownership warning

Route lists and caller positions can change while Gridfinity work proceeds. The code in `organizer_spaces/__init__.py`, `organizer_drawer/__init__.py` and `wavefinity_web.py` is the source for current handler details, including side-effect ordering. This is a short lookup index, not a complete request/response schema and not an executable checker. The later coder must retain actual request/response fields by reading the relevant handlers, without creating new testing infrastructure.
