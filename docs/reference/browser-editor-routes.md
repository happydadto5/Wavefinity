# Browser catalog and pure editor routes (B04)

The browser engine bundle contains `wf_browser_core.editor_routes.ROUTES` and
`wf_browser_core.route_dispatch`. B14 owns wiring the worker to this Python
dispatcher and adding the later packages' route maps. No JavaScript route
registration is supplied by B04. The integrated browser application is still
being assembled.

The initial map owns catalog, design validation/inventory preview/division label
fit, feature default/draft/fit/apply/duplicate/delete, layout mode/expand, and
pegboard layouts. It calls the canonical payload implementations, preserving
their result shapes, feature order and runtime validation. It does not own
preview, generation, sampler, health, job status, hooks or Storage Drawers routes.

Install the MeshGL64 bridge before importing the dispatcher. `register_routes`
accepts a module's path-to-callable `ROUTES` mapping, skips repeat registration of
that same mapping, and raises `DuplicateLocalRoute` for any collision with another
map. Registration is atomic and rejects retired, undeclared and JavaScript paths
using the bundled route manifest. `dispatch(path, payload)` returns canonical results
or raises the original exception; an unknown path raises
`UnsupportedLocalOperation` (`UNSUPPORTED_LOCAL_OPERATION`, status 404).
`dispatch_json(path, payload_json)` is the worker boundary: it returns a JSON
`{result: ...}` or `{status, error: {kind, message, type}}` envelope. No missing
handler can fall back to HTTP. B14's worker must forward the error status and
exception type/message to B03's transport.

Design editing uses the same extracted entry policy as the desktop server.
B09's folder adapter supplies `inventory_text` and optional `space_id`, plus
`source_inventory_text`, `source_space_id`, `source_row_id` when copying a saved
bin. These are saved folder records, not a request's claimed `space` object.
Optional `space_metadata_text` / `source_space_metadata_text` contain saved
metadata JSON; their identities and grids must agree with inventory. Missing
records fail closed when a Space/source is named. No path is opened, record
rewritten, or Space grid changed by these adapters. Unowned legacy designs retain
the canonical Wavefinity default; current designs carry their explicit grid.
The saved-design module marker guard remains on design validation. All B04
design-edit routes also check canonical source/destination grid compatibility.

The canonical catalog now lives in `wavefinity_web_impl._catalog`, taking an
environment descriptor instead of importing the web server. The server facade
still supplies its real desktop preferences, slicer and build identity. Browser
catalog data is compiled from this function, never from a second table of rules.
Native lib3mf and photo/OpenCV imports are deferred to their own operations;
this does not implement B07 or B12.

`scripts/build-browser-core.py --refresh-catalog` is a production asset build on
a maintainer machine with the production Python dependencies. It writes
`catalog.json`, `catalog_manifest.json`, the source archive and engine manifest.
The catalog manifest binds its bytes to a schema version, SHA-256, and canonical
source hashes. Normal offline/static-host builds read these committed JSON
assets, enforce their provenance, and regenerate the source archive without
importing the engine. Refresh catalog assets whenever canonical Python changes;
adapter-only changes do not invalidate them. This conservative rule may require
refreshing after a change that does not affect the catalog itself.

B14 supplies the same instance/build identity used by local health via
`editor_routes.configure_catalog_identity(instance=..., build=...)`. The catalog
response includes `catalog_version` and `catalog_sha256`; browser runtime and
desktop-only capability flags are generated through the canonical environment
adapter. The worker loads the already-vendored matplotlib package with its
dependencies before importing editor routes: canonical text/label helpers import it, even for
operations that do not build lettering. No native lib3mf/OpenCV module is needed
to import the B04 route map.
