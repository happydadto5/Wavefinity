# Browser ordinary outputs (B06)

`web/browser-core/engine/build_outputs.py` exports Python `ROUTES` for
`/api/generate`, `/api/connector` and `/api/sampler`. It calls the canonical
builders, preserving Wavefinity's 7 mm waves, both Gridfinity pitches and
profiles, filename segments, connector fits, installed features, Space height
checks and printer-volume checks. No geometry fork or reduced-size whitelist
is introduced. Canonical STL export remains available through `export_mesh`;
the existing ordinary generation routes continue to produce 3MF files.
The Generate caller supplies the current printer profile and saved inventory/
metadata text read from the selected handle after the resume checkpoint. The
entry guard uses those saved records for Space grid ownership; folderless
output does not request inventory logging.

The worker's temporary filesystem is memory, not a server output directory.
All completed files are read before any are emitted; replies contain
`files: [{name, local_file_id}]`. Reports contain basenames rather than
temporary paths. Inventory data is returned for browser-owned persistence;
the engine never logs inventory into its temporary filesystem.

## Worker integration boundary

B14 owns final registration. It must register the module's `ROUTES` in the
Python dispatcher and supply job-scoped file/progress delivery. The module
also exposes `dispatch_output_json(path, payload_json, emit_file, progress)`
as the worker binding for these routes. Pass the worker's existing
`ctx.file(bytes, name, mime)` and `ctx.progress(object)` callbacks. It converts
Python bytes into transferable Uint8Array data with Pyodide FFI, returning a
JSON result or the standard typed error envelope. Each `ctx.file` returns the
worker file ID; B03 remaps those IDs into the main thread's local Blob table.
Failed jobs discard emitted handles. Callbacks are restored after each call.
There is no HTTP fallback, export token or JSON/base64 file transport.
This package does not modify the central dispatcher or wire the final UI.

## 3MF and integrity

`three_mf.py` replaces the ordinary native-export surface only when canonical
export functions run on Emscripten. Native historical exports keep lib3mf.
The browser writer uses ZIP and XML for core mesh resources, component
assemblies, build items/transforms, Application/Title metadata and Bambu's
settings attachment relationship. Existing settings helpers preserve names,
resource IDs, identity matrices, default body slot 1 and lettering slot 2.
Scene instances are transformed before serialization, including sampler
placements. Text/body overlap and accent-body splitting use canonical checks.

Before output is installed, a runtime reader checks ZIP integrity and OPC
members/content types/relationships, object IDs/references, cycles, mesh
arrays and indices, finite transforms, reachable resources, names and Bambu
object/part metadata. Public validators retain object/build/group counts,
watertightness, winding, positive volume, normal versus multipart checks and
file hashes. Group validation also compares actual mesh arrays. Printer fit
reads every transformed build instance through this reader, avoiding native
format dependencies. Unsupported package structures fail closed. This is a
strict reader for the emitted core subset, not a claim of lib3mf conformance
or observed Bambu Studio parity. Combined-plate packaging remains B07 work.

## Saving

`saveGeneratedFiles` claims every local Blob before touching the destination.
Folder writes run in the existing per-folder queue. Foreign bin collisions
require renaming, owned stale names may be replaced, and connectors retain
hash-based skip/Replace/Cancel choices. Original bytes are captured in memory;
a later failure or navigation/design change restores overwritten files and
removes newly created ones. If access fails during rollback, the error names
the files that could not be restored; no success is reported. This is rollback
for handled errors, not crash-atomic multi-file filesystem replacement.

Without a folder, one file downloads directly; multiple files download as one
store-mode UTF-8 ZIP containing the original filenames and bytes. Preparing
the whole archive before its single download avoids unrollbackable partial
sets of browser downloads. A download means browser handoff, not proof of an
OS save or slicer opening. Local handles are released on success, cancellation
and failure. No automated tests, browser runs or slicer checks establish
empirical parity for this package; review is by source and shipping build.
