# Browser structural operations (B11)

`web/browser-core/engine/structural_routes.py` exports the Python `ROUTES` map
for structural design/generate/print/print-combined, Storage Box and Surface
combined Print, Storage Drawers summary/validate/reset/mutate/mutate-text, and
pegboard hooks. Space warm remains B09; inventory routes remain B10. B14 owns
registry assembly, worker delivery binding and shipping-bundle regeneration.
The existing shipping builder includes engine Python modules automatically.

Requests are copied before building. The module calls canonical Space design,
cabinet planning/materialization, Base Trim export, ordinary bin generation
and pegboard hook builders in request-scoped MEMFS. It retains the current
printer-profile context and reports build progress through B06 delivery.
Geometry rules are shared, including both Gridfinity pocket pitches, exact
nominal dimensions versus the enlarged external-baseplate cavity, provisional
0.35 mm clearance per side, and the canonical minimum floor builds (including
the Storage Box underside recess). No new physical-fit guarantee is made.

Structural files leave Python as opaque local file handles. Combined Print
also uses B10's inventory-text/file-bytes boundary, regenerates missing bin
files from canonical sources, includes each drawer's connectors, and returns
partial results without Printed promotion if preparation fails. B07 packages
the handoff as an arranged four-member combined plate, preserving registered
multipart geometry. No native slicer process is launched.

The Space UI saves cabinet and Base Trim outputs through their existing
manifest/hash ownership gates and durable rollback journals. Other outputs
use the existing collision-aware file saver. The browser captures the folder,
Space identity, accepted definition, design epoch and inventory text. It
refuses stale applications and conflicting structural/inventory filenames.
Structural saves may succeed before a later inventory/plate save fails;
those files remain in their original folder, while Printed stays unchanged.

Print asks the person to open the named file in Bambu Studio. Only explicit
confirmation updates Printed. Combined Print reuses B10's confirmation receipt
and unchanged inventory/layout checks. The Base Trim joint-fit shortcut leaves
the container's print state unchanged. There is no persistent Prepared state.

This package was reviewed by reading source and diffs. No coder tests, browser
driving or physical-fit verification were performed.
