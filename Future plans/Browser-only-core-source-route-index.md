# Wavefinity current source route lookup — migration navigation only

Source ownership baseline from November 12, 2026; source locations are a frozen navigation snapshot. The **fourth column is authoritative single-owner Bxx**, not a list of contributors. **No test code, test scanners, test execution, or user QA plans.** Before implementing a package, read its named current source functions because ongoing Gridfinity changes can shift code.

`wavefinity_web.py` registers the core Python routes and `organizer_drawer/__init__.py:drawer_routes` adds drawer routes. `organizer_spaces/__init__.py:space_routes` is registered only under `if not HOSTED` in the legacy web server; the final browser app needs those Space operations anyway. The frontend column lists prominent literal call sites, **not every indirect caller**. **Ownership is singular:** a consuming UI package is not a second route owner. For example, **B10 owns all `/api/drawer/*` routes, including its print variants**, while B08 supplies shared print preparation/3MF helpers; **B11 owns all structural/Storage Drawers routes and pegboard hooks**. B09 owns folder/Space operations and `/api/space/warm`; B13 owns the browser-only replacement for the legacy slicer-browse and show-log paths. `route-dispatch.py` is a shared routing integration point owned first by B04 and finally by B14, not a second owner of those route semantics.

| API path | Existing handler | Main frontend reference(s) | Owner | Disposition |
|---|---|---|---|---|
| `/api/ai/ask` | `ai_ask_payload` · `wavefinity_web.py:3491` | `web/app/02-lifecycle-ai-help.js:916` | B13 | local |
| `/api/ai/candidate` | `ai_candidate_payload` · `wavefinity_web.py:3493` | `web/app/02-lifecycle-ai-help.js:638` | B13 | local |
| `/api/ai/connection` | `ai_connection_payload` · `wavefinity_web.py:3490` | `web/app/02-lifecycle-ai-help.js:879`, `web/app/02-lifecycle-ai-help.js:900` | B13 | local |
| `/api/ai/prompt` | `ai_prompt_payload` · `wavefinity_web.py:3492` | `web/app/02-lifecycle-ai-help.js:604` | B13 | local |
| `/api/ai/repair-prompt` | `ai_repair_prompt_payload` · `wavefinity_web.py:3494` | `web/app/02-lifecycle-ai-help.js:801` | B13 | local |
| `/api/browse-output-folder` | `browse_output_folder_payload` · `wavefinity_web.py:3526` | `web/spaces/07-welcome-folders.js:46` | B09 | local |
| `/api/browse-slicer-path` | `browse_slicer_path_payload` · `wavefinity_web.py:3528` | `web/app/15-generate-dialogs.js:619` | B13 | local |
| `/api/catalog` | `catalog_payload (GET)` · `wavefinity_web.py:3676` | No literal reference in sampled callers | B04 | local |
| `/api/connector` | `connector_save_payload` · `wavefinity_web.py:3511` | `web/app/15-generate-dialogs.js:285`, `web/app/15-generate-dialogs.js:291` | B06 | local |
| `/api/design/division-label-fit` | `division_label_fit_payload` · `wavefinity_web.py:3496` | No literal reference in sampled callers | B04 | local |
| `/api/design/inventory-preview` | `inventory_preview_payload` · `wavefinity_web.py:3495` | No literal reference in sampled callers | B04 | local |
| `/api/design/validate` | `_validate_design_open_guard → validate_design_payload` · `wavefinity_web.py:3489; see function immediately before POST_ROUTES` | `web/app/03-history-utils-catalog.js:162`, `web/app/11-parts-preview-requests.js:45`, `web/spaces/04-metadata-persistence.js:143` | B04 | local |
| `/api/drawer/connectors` | `connectors` · `organizer_drawer/__init__.py:1267` | No literal reference in sampled callers | B10 | local |
| `/api/drawer/design-source/duplicate` | `duplicate_design_source` · `organizer_drawer/__init__.py:1259` | `web/app/03-history-utils-catalog.js:130` | B10 | local |
| `/api/drawer/design-source/save` | `save_design_source` · `organizer_drawer/__init__.py:1257` | `web/spaces/06-inventory-io.js:172`, `web/app/02-lifecycle-ai-help.js:95` | B10 | local |
| `/api/drawer/design-source/status` | `change_design_status` · `organizer_drawer/__init__.py:1260` | `web/app/15-generate-dialogs.js:254`, `web/app/15-generate-dialogs.js:488`, `web/app/15-generate-dialogs.js:516` | B10 | local |
| `/api/drawer/generate-bin` | `generate_hosted_bin` · `organizer_drawer/__init__.py:1258` | `web/spaces/06-inventory-io.js:62` | B10 | local |
| `/api/drawer/load` | `load` · `organizer_drawer/__init__.py:1255` | `web/spaces/06-inventory-io.js:280`, `web/drawer-model.js:1185` | B10 | local |
| `/api/drawer/print-bins` | `print_bins` · `organizer_drawer/__init__.py:1270` | `web/drawer-model.js:1850` | B10 | local |
| `/api/drawer/print-complete` | `print_complete` · `organizer_drawer/__init__.py:1268` | `web/drawer-model.js:1893` | B10 | local |
| `/api/drawer/print-spacers` | `print_spacers_only` · `organizer_drawer/__init__.py:1269` | `web/drawer-model.js:1713` | B10 | local |
| `/api/drawer/report` | `report` · `organizer_drawer/__init__.py:1261` | `web/drawer-model.js:1408` | B10 | local |
| `/api/drawer/save` | `save` · `organizer_drawer/__init__.py:1256` | `web/spaces/06-inventory-io.js:67`, `web/spaces/06-inventory-io.js:166`, `web/spaces/06-inventory-io.js:257` | B10 | local |
| `/api/drawer/save-bins` | `save_bins` · `organizer_drawer/__init__.py:1271` | `web/drawer-model.js:1812` | B10 | local |
| `/api/drawer/spacers` | `spacers` · `organizer_drawer/__init__.py:1264` | No literal reference in sampled callers | B10 | local |
| `/api/drawer/spacers/generate` | `spacers_generate` · `organizer_drawer/__init__.py:1265` | No literal reference in sampled callers | B10 | local |
| `/api/drawer/spacers/refresh` | `spacers_refresh` · `organizer_drawer/__init__.py:1266` | `web/spaces/06-inventory-io.js:168`, `web/drawer-model.js:1574` | B10 | local |
| `/api/drawer/surface-fill` | `surface_fill` · `organizer_drawer/__init__.py:1262` | `web/drawer-model.js:1492` | B10 | local |
| `/api/drawer/surface-fill/create` | `surface_fill_create` · `organizer_drawer/__init__.py:1263` | `web/drawer-model.js:1511` | B10 | local |
| `/api/export/<token>/<filename>` | `token download (GET)` · `wavefinity_web.py:3682` | No literal reference in sampled callers | B06 | retired → local Blob ID |
| `/api/feature/apply` | `apply_feature_payload` · `wavefinity_web.py:3502` | No literal reference in sampled callers | B04 | local |
| `/api/feature/default` | `default_feature_payload` · `wavefinity_web.py:3499` | No literal reference in sampled callers | B04 | local |
| `/api/feature/delete` | `delete_feature_payload` · `wavefinity_web.py:3504` | `web/app/11-parts-preview-requests.js:97` | B04 | local |
| `/api/feature/draft` | `draft_payload` · `wavefinity_web.py:3500` | No literal reference in sampled callers | B04 | local |
| `/api/feature/duplicate` | `duplicate_feature_payload` · `wavefinity_web.py:3503` | No literal reference in sampled callers | B04 | local |
| `/api/feature/fit` | `feature_fit_payload` · `wavefinity_web.py:3501` | `web/app/11-parts-preview-requests.js:845` | B04 | local |
| `/api/folder/inventory` | `set_inventory` · `organizer_spaces/__init__.py:1461` | No literal reference in sampled callers | B09 | local |
| `/api/folder/no-defined-space` | `no_defined_space` · `organizer_spaces/__init__.py:1453` | `web/spaces/08-space-setup.js:313` | B09 | local |
| `/api/folder/use` | `open_folder` · `organizer_spaces/__init__.py:1452` | `web/spaces/07-welcome-folders.js:90`, `web/spaces/07-welcome-folders.js:94` | B09 | local |
| `/api/generate` | `generate_payload` · `wavefinity_web.py:3510` | `web/app/15-generate-dialogs.js:237` | B06 | local |
| `/api/health` | `health_payload (GET)` · `wavefinity_web.py:3673` | `web/app/15-generate-dialogs.js:749` | B03 | local |
| `/api/layout/expand` | `expand_layout_payload` · `wavefinity_web.py:3509` | `web/app/11-parts-preview-requests.js:977`, `web/app/11-parts-preview-requests.js:1057` | B04 | local |
| `/api/layout/mode` | `mode_payload` · `wavefinity_web.py:3508` | `web/app/03-history-utils-catalog.js:858` | B04 | local |
| `/api/nest/photo` | `photo_nest_payload` · `wavefinity_web.py:3506` | No literal reference in sampled callers | B12 | local |
| `/api/nest/retrace` | `nest_retrace_payload` · `wavefinity_web.py:3507` | No literal reference in sampled callers | B12 | local |
| `/api/nest/trace` | `nest_trace_payload` · `wavefinity_web.py:3505` | No literal reference in sampled callers | B12 | local |
| `/api/operation-status` | `operation_status_payload` · `wavefinity_web.py:3556` | `web/app/03-history-utils-catalog.js:466`, `web/app/03-history-utils-catalog.js:499`, `web/app/03-history-utils-catalog.js:508` | B03 | local |
| `/api/pegboard/hooks` | `pegboard_hooks_payload` · `wavefinity_web.py:3498` | No literal reference in sampled callers | B11 | local |
| `/api/pegboard/layouts` | `pegboard_layouts_payload` · `wavefinity_web.py:3497` | `web/drawer-model.js:1149` | B04 | local |
| `/api/preferences` | `preferences_payload` · `wavefinity_web.py:3524` | `web/app/15-generate-dialogs.js:631` | B09 | local |
| `/api/preview` | `preview_payload` · `wavefinity_web.py:3487` | `web/app/11-parts-preview-requests.js:767` | B05 | local |
| `/api/print` | `print_payload` · `wavefinity_web.py:3513` | `web/app/15-generate-dialogs.js:455`, `web/app/15-generate-dialogs.js:467` | B08 | local |
| `/api/sampler` | `sampler_payload` · `wavefinity_web.py:3512` | No literal reference in sampled callers | B06 | local |
| `/api/show-log` | `show_log_payload` · `wavefinity_web.py:3529` | No literal reference in sampled callers | B13 | local |
| `/api/suggestions` | `_post_suggestion` · `wavefinity_web.py:3738` (POST, external request) | Main UI reference must be read in current source; not a core local-geometry route | B13 | local |
| `/api/space/browse-storage-parent` | `browse_space_parent_payload` · `wavefinity_web.py:3527` | `web/spaces/07-welcome-folders.js:377` | B09 | local |
| `/api/space/configure` | `configure_migrate` · `organizer_spaces/__init__.py:1457` | `web/spaces/08-space-setup.js:682` | B09 | local |
| `/api/space/configure-text` | `configure_space_text_payload` · `wavefinity_web.py:3531` | `web/spaces/08-space-setup.js:611` | B09 | local |
| `/api/space/copy` | `copy_space` · `organizer_spaces/__init__.py:1459` | No literal reference in sampled callers | B09 | local |
| `/api/space/copy-name` | `copy_space_name_payload` · `wavefinity_web.py:3533` | No literal reference in sampled callers | B09 | local |
| `/api/space/copy-text` | `copy_space_text_payload` · `wavefinity_web.py:3532` | No literal reference in sampled callers | B09 | local |
| `/api/space/create` | `configure` · `organizer_spaces/__init__.py:1456` | `web/spaces/08-space-setup.js:682` | B09 | local |
| `/api/space/create-text` | `create_space_text_payload` · `wavefinity_web.py:3530` | `web/spaces/08-space-setup.js:611` | B09 | local |
| `/api/space/defaults` | `set_bin_defaults` · `organizer_spaces/__init__.py:1462` | No literal reference in sampled callers | B09 | local |
| `/api/space/delete` | `delete_space` · `organizer_spaces/__init__.py:1460` | No literal reference in sampled callers | B09 | local |
| `/api/space/forget` | `forget` · `organizer_spaces/__init__.py:1466` | No literal reference in sampled callers | B09 | local |
| `/api/space/inspect` | `inspect` · `organizer_spaces/__init__.py:1446` | `web/spaces/07-welcome-folders.js:82`, `web/spaces/07-welcome-folders.js:253`, `web/spaces/08-space-setup.js:343` | B09 | local |
| `/api/space/no-inventory` | `lambda payload: set_inventory({...payload, inventory: False})` · `organizer_spaces/__init__.py:1465` | No literal reference in sampled callers | B09 | local |
| `/api/space/open` | `open_folder` · `organizer_spaces/__init__.py:1464` | No literal reference in sampled callers | B09 | local |
| `/api/space/other-spaces` | `other_spaces_route` · `organizer_spaces/__init__.py:1449` | `web/spaces/07-welcome-folders.js:166` | B09 | local |
| `/api/space/printer-profile` | `printer_profile_route` · `organizer_spaces/__init__.py:1471` | No literal reference in sampled callers | B09 | local |
| `/api/space/resume` | `resume` · `organizer_spaces/__init__.py:1463` | No literal reference in sampled callers | B09 | local |
| `/api/space/show-folder` | `show_folder_payload` · `wavefinity_web.py:3525` | No literal reference in sampled callers | B09 | local |
| `/api/space/startup` | `startup` · `organizer_spaces/__init__.py:1448` | `web/spaces/08-space-setup.js:1132` | B09 | local |
| `/api/space/storage-box-print` | `storage_box_print_payload` · `wavefinity_web.py:3518` | `web/spaces/10-storage-box-structural.js:384` | B11 | local |
| `/api/space/storage-change` | `change_storage` · `organizer_spaces/__init__.py:1470` | `web/spaces/07-welcome-folders.js:445` | B09 | local |
| `/api/space/storage-drawers-mutate` | `storage_drawers_mutate_route` · `organizer_spaces/__init__.py:1472` | `web/spaces/14-drawers-cabinet.js:188` | B11 | local |
| `/api/space/storage-drawers-mutate-text` | `storage_drawers_mutate_text_payload` · `wavefinity_web.py:3523` | `web/spaces/14-drawers-cabinet.js:205` | B11 | local |
| `/api/space/storage-drawers-reset` | `storage_drawers_reset_payload` · `wavefinity_web.py:3522` | `web/spaces/04-metadata-persistence.js:34` | B11 | local |
| `/api/space/storage-drawers-summary` | `storage_drawers_summary_payload` · `wavefinity_web.py:3520` | `web/spaces/14-drawers-cabinet.js:105` | B11 | local |
| `/api/space/storage-drawers-validate` | `storage_drawers_validate_payload` · `wavefinity_web.py:3521` | `web/spaces/04-metadata-persistence.js:30` | B11 | local |
| `/api/space/storage-parent` | `set_storage_parent` · `organizer_spaces/__init__.py:1467` | No literal reference in sampled callers | B09 | local |
| `/api/space/storage-plan` | `storage_plan` · `organizer_spaces/__init__.py:1469` | `web/spaces/07-welcome-folders.js:379` | B09 | local |
| `/api/space/storage-state` | `storage_state` · `organizer_spaces/__init__.py:1468` | `web/spaces/07-welcome-folders.js:356` | B09 | local |
| `/api/space/structural-design` | `structural_design_payload` · `wavefinity_web.py:3514` | `web/spaces/10-storage-box-structural.js:164` | B11 | local |
| `/api/space/structural-generate` | `structural_generate_payload` · `wavefinity_web.py:3515` | `web/spaces/10-storage-box-structural.js:358`, `web/spaces/14-drawers-cabinet.js:490`, `web/spaces/14-drawers-cabinet.js:606` | B11 | local |
| `/api/space/structural-print` | `structural_print_payload` · `wavefinity_web.py:3516` | `web/spaces/10-storage-box-structural.js:307`, `web/spaces/14-drawers-cabinet.js:474` | B11 | local |
| `/api/space/structural-print-combined` | `structural_print_combined_payload` · `wavefinity_web.py:3517` | `web/spaces/14-drawers-cabinet.js:411` | B11 | local |
| `/api/space/surface-print` | `surface_print_payload` · `wavefinity_web.py:3519` | No literal reference in sampled callers | B11 | local |
| `/api/space/update` | `update` · `organizer_spaces/__init__.py:1458` | No literal reference in sampled callers | B09 | local |
| `/api/space/use-untyped` | `use_folder` · `organizer_spaces/__init__.py:1455` | `web/spaces/08-space-setup.js:994`, `web/spaces/08-space-setup.js:997` | B09 | local |
| `/api/space/warm` | `warm_spaces_payload` · `wavefinity_web.py:3488` | No literal reference in sampled callers | B09 | local |

## Non-API paths previously supplied by Python

- `/` and HTML/CSS/JS requests resolve beneath `web/`. **Build must copy web contents to dist root**, not to `dist/web`.
- `/images/*` resolves from repository-root `images/`; **copy into `dist/images/`**.
- `/Brochure.md` (also lowercase legacy path `/brochure.md`) resolves from repository-root `Brochure.md`. The static build copies BOTH `dist/Brochure.md` and a byte-identical `dist/brochure.md` alias; no redirect/rule dependency.
- `/api/export/<token>/<filename>` is a server stream of temporary generated files; replace with transferable buffers and local Blobs, not a static URL.
- `/api/catalog` and `/api/health` currently come from server GET handlers. The browser edition serves static/generated catalog and runtime/build identity without a network API.

## Bxx authoritative single-owner resolution

All 92 indexed route rows above have exactly one primary Bxx owner AND explicit disposition: **91 local operations, 1 retired token-download pattern**. At later Andrew GO, compare source registry additions to this table by reading current source, update the index and B01 manifest together. Build-time manifest/registry key comparison uses the updated row set, not the historical numeric 92. If a newly added Gridfinity endpoint exists when the Stories are created, assign it ONE semantic owner and update its row and the static B01 manifest. B04 supplies Python `web/browser-core/engine/route-dispatch.py` and fail-closed `UNSUPPORTED_LOCAL_OPERATION` dispatch. Later packages export their own Python `ROUTES` or JavaScript `ROUTES` (for browser file access/AI connection) without editing central registries. **B14 assembles Python routes into `route-dispatch.py` and JS routes into `local-api.js` once**, without cross-language importing, and emits a single flat route declaration used by normal production shipping. Missing/unknown/retired routes never fall back to HTTP. No parallel central-registry edits. The canonical B01 contract is `web/browser-core/contracts/route-manifest.json`, with path/method/owner/disposition/runtime/module/handler/input/output/effects. B14's production build checks each **local** manifest route matches exactly one actual flat dispatcher registration, each **retired** route matches no callable registration, and the source index has the same dispositions. Do NOT treat this as a test runner, route-scanning script or runtime certification. Ship the manifest to `dist/` only if runtime consumes it. The old root `browser-core/contracts/` path is invalid.

## Route ownership warning

Route lists and caller positions can change while Gridfinity work proceeds. The code in `organizer_spaces/__init__.py`, `organizer_drawer/__init__.py` and `wavefinity_web.py` is the source for current handler details, including side-effect ordering. This is a short lookup index, not a complete request/response schema and not an executable checker. The later coder must retain actual request/response fields by reading the relevant handlers, without creating new testing infrastructure.
