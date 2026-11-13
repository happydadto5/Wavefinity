"""B10 drawer routes. Folder bytes enter/leave as values, never host paths.

B14 owns registry assembly. Canonical text handlers preserve inventory merge,
deletion, grid and generation rules. Batch handlers use request-scoped MEMFS;
their slicer callback packages a plate and cannot launch or mark Printed.
"""
import base64
import copy
import tempfile
import threading
import re
import uuid
from pathlib import Path

from organizer_drawer import drawer_routes, inventory_row_file_names, SPACER_KINDS
from organizer_app import design_from_dict, generate_organizer_files_transactional
from organizer_inventory import (
    INVENTORY_FILENAME, load_inventory, load_inventory_text, design_specs, render_inventory,
)
from organizer_drawer._inventory import _copy_count
from organizer_geometry import build_scope
from organizer_outputs.printer_profile import (
    current_export_profile, normalise_printer_profile, export_printer_profile,
)
from . import build_outputs as outputs
from . import plate_layout
from .print_routes import _read_files


def _name(value):
    if (not isinstance(value, str) or not value or value in (".", "..")
            or any(c in value for c in ('/', '\\', ':', '\x00'))
            or not value.lower().endswith('.3mf')):
        raise ValueError("Inventory files must be direct-child 3MF filenames.")
    return value


def _generator(root, design, row_id=None):
    inventory = load_inventory(root)
    space = (inventory.get('layout') or {}).get('space') or {}
    box, layout, label, name, location, scoop = design_from_dict(design)
    outputs._check_space_height(space, box, layout, label, name, scoop)
    generate_organizer_files_transactional(
        box, layout, root, label, name, location, scoop,
        auto_timestamp=False, keep_log=False,
        pegboard_thickness_mm=space.get('pegboard_thickness_mm', 3.2),
        serial=(row_id or '') if not box.b4b.enabled and re.fullmatch(r'B[0-9]+', row_id or '') else '',
    )
    # Both canonical callers supply an isolated build stage, containing only
    # the inventory snapshot before generation.
    return sorted(root.glob('*.3mf'))


_text_routes = drawer_routes(threading.RLock(), Path('/unused-browser-drawer'),
                             hosted=True, generate_from_design=_generator)
_BATCH = {'/api/drawer/' + name for name in
          ('save-bins', 'print-bins', 'print-spacers', 'print-complete')}


def _check_confirmation(payload):
    receipt = payload.get('print_confirmation')
    if receipt is None:
        return
    if not isinstance(receipt, list) or not receipt or payload.get('opened_in_bambu') is not True:
        raise ValueError('Confirm that you opened this print file in Bambu Studio.')
    current = load_inventory_text(payload.get('inventory_text') or '')
    by_id = {row['id']: row for row in current['bins']}
    specs = design_specs(current['layout'])
    if current['layout'] != payload.get('expected_print_layout'):
        raise ValueError('The layout changed since Print was prepared; nothing was marked Printed.')
    for entry in receipt:
        row = entry['row']
        if by_id.get(row['id']) != row or specs.get(row['id']) != entry.get('design'):
            raise ValueError('Inventory changed since Print was prepared; nothing was marked Printed.')
    allowed = {entry['row']['id'] for entry in receipt}
    if (payload.get('new_bins') or payload.get('delete_ids')
            or not {str(row.get('id')) for row in payload.get('bin_updates', [])} <= allowed):
        raise ValueError('Print confirmation may update only the prepared rows.')


def _confirmed_save(payload):
    _check_confirmation(payload)
    current = load_inventory_text(payload.get('inventory_text') or '')
    specs = design_specs(current['layout'])
    request = dict(payload)
    updates = []
    for update in payload.get('bin_updates', []):
        row_id = str(update.get('id'))
        if row_id in specs:
            saved = _text_routes['/api/drawer/design-source/status']({
                **request, 'row_id': row_id, 'action': 'mark_printed', 'design': specs[row_id],
            })
            request['inventory_text'] = saved['inventory_text']
        else:
            updates.append(update)
    return _text_routes['/api/drawer/save']({**request, 'bin_updates': updates})


def _batch(path, payload):
    raw = payload.get('printer_profile')
    profile = current_export_profile() if raw is None else normalise_printer_profile(raw)
    if raw is not None:
        profile['configured'] = payload.get('printer_profile_configured') is True
    with tempfile.TemporaryDirectory(prefix='wf-drawer-') as directory:
        root = Path(directory)
        (root / INVENTORY_FILENAME).write_text(payload.get('inventory_text') or '', encoding='utf-8')
        if path.endswith('print-spacers'):
            rows = {row['id']: row for row in load_inventory(root)['bins']}
            for row_id, count in (payload.get('selection') or {}).items():
                row = rows.get(str(row_id))
                if row is None or row.get('kind') not in SPACER_KINDS:
                    raise ValueError('No printable spacer ' + str(row_id))
                _copy_count(row, count)
        original = {}
        for name, encoded in (payload.get('input_files_base64') or {}).items():
            name = _name(name)
            data = base64.b64decode(encoded, validate=True)
            if not data:
                raise ValueError('An inventory file is empty: ' + name)
            (root / name).write_bytes(data)
            original[name] = data
        handoff = {}
        launched = []

        def package_plate(_slicer, files):
            if not files:
                raise ValueError('There is nothing to print.')
            plate = root / 'plate' / f'Wavefinity drawer plate {uuid.uuid4().hex[:12]}.3mf'
            plate.parent.mkdir(exist_ok=True)
            arranged, issues = plate_layout.combine_for_plate(files, profile, plate)
            if issues:
                raise ValueError('The parts do not fit the active printer:\n' + '\n'.join(issues))
            name, data = _read_files([Path(arranged)])[0]
            handoff.update(filename=name, opened_automatically=False, confirmation_required=True)
            handoff['base64'] = base64.b64encode(data).decode('ascii')
            launched.extend(Path(p).name for p in files)
            return arranged

        routes = drawer_routes(threading.RLock(), root,
                               launch_slicer=package_plate,
                               generate_from_design=_generator,
                               printer_profile_for=lambda _: profile, prepare_print_only=True)
        with export_printer_profile(profile), build_scope(preview=False, listener=outputs._progress):
            try:
                result = routes[path]({**payload, 'output': str(root)})
            except Exception as error:
                # Native batch code can raise after recording earlier rows.
                # Those successful files must survive the temporary directory,
                # just as they survive a later failure in the native folder.
                changed = ((root / INVENTORY_FILENAME).read_text(encoding='utf-8')
                           != (payload.get('inventory_text') or ''))
                changed = changed or any(original.get(p.name) != p.read_bytes() for p in root.glob('*.3mf'))
                if not changed:
                    raise
                result = {'partial': True, 'partial_stage': 'prepare', 'error': str(error), 'notes': []}
        inventory = load_inventory(root)
        result = outputs._safe_result(result, root)
        result.update(bins=inventory['bins'], layout=inventory['layout'],
                      inventory_text=render_inventory(str(payload.get('inventory_title') or 'Wavefinity'),
                                                      inventory['bins'], inventory['layout']))
        result.pop('file', None)
        result['files_base64'] = {
            p.name: base64.b64encode(p.read_bytes()).decode('ascii')
            for p in root.glob('*.3mf') if original.get(p.name) != p.read_bytes()
        }
        if handoff and not result.get('partial'):
            result['files_base64'][handoff['filename']] = handoff.pop('base64')
            result['handoff'] = handoff
            if path.endswith('print-spacers'):
                ids = [str(key) for key, count in (payload.get('selection') or {}).items() if int(count) > 0]
            else:
                ids = result.pop('print_row_ids', [])
            specs = design_specs(inventory['layout'])
            result['print_confirmation'] = [
                {'row': copy.deepcopy(row), 'design': copy.deepcopy(specs.get(row['id']))}
                for row in inventory['bins'] if row['id'] in ids
            ]
            result['expected_print_layout'] = copy.deepcopy(inventory['layout'])
            result['files'] = launched
        return result


def _handler(path):
    def handle(payload):
        if path in _BATCH:
            return _batch(path, payload)
        if path == '/api/drawer/save':
            if payload.get('print_confirmation') is not None:
                return _confirmed_save(payload)
        raw = payload.get('printer_profile')
        profile = current_export_profile() if raw is None else normalise_printer_profile(raw)
        if raw is not None:
            profile['configured'] = payload.get('printer_profile_configured') is True
        with export_printer_profile(profile):
            result = _text_routes[path](payload)
        if path == '/api/drawer/load' and 'available_filenames' in payload:
            names = set()
            selected = None
            if payload.get('input_route') in _BATCH:
                if payload['input_route'].endswith('print-complete'):
                    selected = {str(p.get('bin')) for drawer in (result.get('layout') or {}).get('drawers', [])
                                for p in drawer.get('placements', [])}
                    selected -= {row['id'] for row in result['bins'] if row.get('status') == 'printed'}
                    selected &= {row['id'] for row in result['bins']
                                 if row.get('kind') in ('bin', 'b4b', *SPACER_KINDS)}
                else:
                    selected = {str(key) for key in (payload.get('input_selection') or [])}
            for row in result['bins']:
                if selected is not None and row['id'] not in selected:
                    continue
                try:
                    names.update(inventory_row_file_names(payload['available_filenames'], row))
                except ValueError:
                    # Missing/ambiguous sets are left to native batch preflight:
                    # editable bins regenerate, unresolvable spacers are named.
                    pass
            result['input_file_names'] = sorted(names)
        return result
    return handle


ROUTES = {path: _handler(path) for path in _text_routes}
