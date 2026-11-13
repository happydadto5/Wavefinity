# Browser Space persistence (B09)

`web/browser-core/space-store.js` and `preferences.js` export JavaScript
`ROUTES` Maps. B14 registers both in the window-side dispatcher; neither map
is imported into Python. B14 continues to own final registry and UI assembly.
The selected home directory is the existing hosted `home` handle, used directly
as the Space storage authority; no OS path or implicit server directory exists.

All B09 Space, folder, picker, preferences, warm and Show Folder routes live in
these maps. Inventory contents and drawer routes remain B10; structural and
cabinet validation remains B11. Slicer selection and Show Log remain B13.
`engine/space_values.py` is an internal, allowlisted worker value adapter,
called through `WFLocalAPI.spaceValues`, not a Python HTTP route map. It reuses
the canonical inventory parser, Space configuration, grid ownership, printer
validation and measured-lift rules. The worker channel does no persistent I/O.

`.wavefinity.json` stays at version 9, with its existing Space ID and checkpoint
fields. Defaults, resume, structural ownership and printer settings keep their
existing shapes. Floor/None, null floor grid, nominal cell field, physical
cavity and null-versus-zero seated lift remain separate values. A copied Space
gets a new ID; restore preserves its ID and rejects a conflicting remembered
folder. Forget removes a shortcut, without deleting Space files.

`WFFileSystem.queueFolderWrite(handle, task)` resolves `isSameEntry` before
queuing, so a restored handle shares its folder's write queue. Transactions
that already hold that queue use `SP._writeMetadataNow`; ordinary callers use
`SP.writeMetadata`. Do not nest a second queued write for the same folder.
The existing checkpoint queue coalesces redundant designs. Space switches flush
outgoing checkpoints and folder writes; checkpoint completions check Space,
folder and design epoch before adopting in-memory state. B10 consumes this
same queue for its file-set transactions and retains its generated-file rollback.

Directory pickers execute before worker initialization so the original user
gesture remains available. Startup checks permission without requesting it;
unavailable access reports a reconnect requirement. No-handle operation never
reports autosave. Show Folder displays the current selected folder in the app.

Space creation/configuration reads and validates before replacing Inventory,
then restores Inventory if metadata cannot be saved. Missing original files
are removed during rollback rather than replaced with empty files. Copy/import
require empty destinations. Explicit storage `move` copies to an empty selected
folder, publishes home/active/recent handles in one IndexedDB transaction, and
retains the original as a reported `leftover`. `switch` selects empty storage;
`use_existing` selects existing storage without copying into it. An interrupted
publication keeps a handle-only recovery record and the original authority.
IndexedDB contains handles, origin preferences and explicit recovery data;
Space files remain in the selected folder.

Copy/import rollback records written file digests and newly created directories.
It removes only matching bytes and empty directories. Unexpected or changed
files remain in an explicitly reported incomplete copy; rollback does not
recursively erase a destination that another application may have changed.

## Explicit backup and recovery API

- `exportSpace(payload)` returns `wavefinity-space/1` JSON containing relative
  filename components, base64 file bytes and SHA-256 digests. It flushes pending
  checkpoints and reads the selected folder under its write queue.
- `importSpace(backup, folder)` validates every digest, path, metadata identity
  and canonical Space definition before writing into an empty selected folder.
  Failed imports remove their partial file set. With no folder argument, it
  stores explicit recovery data and returns `autosave: false`; it does not
  invent a persistent folder. `exportSpace()` can re-export that recovery copy
  when no folder is active. B13 owns the recovery controls that call these APIs.
- `exportPreferences()` / `importPreferences(backup)` use
  `wavefinity-preferences/1`; `/api/preferences` also accepts `action: export`
  or `action: import` with `backup`. Imports validate known settings and merge
  them without importing paths or credentials. UI choices live under `ui` (or
  the supported theme/units/sidebar/last_space_kind keys); printer settings use
  the canonical build-volume keys. Preference writes are serialized and resolve
  only when the IndexedDB transaction commits.

The main app loads these preferences after its catalog. Its printer and
connector controls use this same route authority. On first access, the previous
origin-local printer/connector records migrate only after canonical validation;
the old keys are retired only after the IndexedDB commit. An unreadable printer
record exposes Reset Printer Settings rather than silently becoming configured.

Browser file operations cannot lock out other applications editing a folder.
The application rejects observed destination collisions and preserves original
files on failures it can recover. Runtime interaction and final integrated UI
behavior remain owner-verified; no coder tests or browser driving were used.
