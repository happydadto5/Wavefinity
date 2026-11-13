"""B11 structural operations over request snapshots in Pyodide MEMFS.

Persistent folder identity, owned-output journals and writes stay in B09's
browser storage. B14 registers this ROUTES map and configures B06 delivery.
No slicer process or Printed mutation happens in this module.
"""
import base64
import copy
import tempfile
import uuid
from pathlib import Path

from organizer_app import design_from_dict
from organizer_base_trim import base_trim_from_design, base_trim_summary, generate_base_trim_joint_test_file
from organizer_base_trim.outputs import base_trim_plan, public_plan, export_base_trim
from organizer_b4b import b4b_summary
from organizer_engine import export_object_groups_3mf
from organizer_features.pegboard import make_pegboard_hooks, pegboard_standard, pegboard_hook_count
from organizer_geometry import build_scope
from organizer_inventory import (
    INVENTORY_FILENAME, load_inventory, render_inventory, design_specs,
    storage_drawers_mutate_text, normalise_space_definition,
)
from organizer_outputs.space import structural_kind, structural_design, STORAGE_BOX, BASE_TRIM, STORAGE_DRAWERS
from organizer_outputs.printer_profile import current_export_profile, normalise_printer_profile, export_printer_profile, print_file_fit_issues
from organizer_storage.drawers import normalise_storage_drawers_definition, reset_storage_drawers_definition, storage_drawers_definition_problem
from organizer_storage.drawer_geometry import storage_drawers_summary
from organizer_storage.drawer_outputs import structural_signature, structural_manifest_plan, materialize_storage_drawers
from organizer_drawer import drawer_report, blocking_problem_messages, selected_blocking_problems, blocking_problem_copy
from organizer_drawer._inventory import prepare_inventory_bins, _space_connectors
from wavefinity_web_impl._outputs import (
    storage_drawers_preview_meshes, _storage_box_printer_fit,
    _storage_box_arrangement_issue, _surface_arrangement_issue,
)
from . import build_outputs as outputs, plate_layout
from .drawer_routes import _generator, _name
from .print_routes import _read_files, _emit


def _profile(payload):
    raw = payload.get('printer_profile')
    result = current_export_profile() if raw is None else normalise_printer_profile(raw)
    if raw is not None:
        result['configured'] = payload.get('printer_profile_configured') is True
    return result


def _design(payload, profile):
    space = payload.get('space')
    kind = structural_kind(space)
    if kind == STORAGE_DRAWERS:
        space = normalise_storage_drawers_definition(space)
        reply = {'kind': kind, 'design': None,
                'summary': storage_drawers_summary(space, profile),
                'preview': storage_drawers_preview_meshes(space) if payload.get('include_preview') else None,
                'signature': structural_signature(space), 'printer_profile': profile,
                'orientations': {}}
        if not payload.get('include_preview'):
            plan = structural_manifest_plan(space, Path('/browser-output'), profile)
            reply['orientations'] = {one['key']: one['orientation'] for one in plan['components']}
            reply['expected_components'] = [{'key': one['key'], 'filename': one['filename']} for one in plan['components']]
        return reply
    if kind not in (STORAGE_BOX, BASE_TRIM):
        raise ValueError('This Space type has no structural output.')
    design = structural_design(space, bed_x_mm=profile['x_mm'], bed_y_mm=profile['y_mm'])
    if kind == STORAGE_BOX:
        summary = b4b_summary(design_from_dict(design)[0])
        summary['fits_printer'], summary['first_fit_error'] = _storage_box_printer_fit(summary, profile)
        return {'kind': kind, 'design': design, 'summary': summary}
    plan = base_trim_plan(space, profile)
    return {'kind': kind, 'design': design, 'summary': base_trim_summary(base_trim_from_design(design)),
            'plan': public_plan(plan), 'signature': plan['signature'], 'printer_profile': profile}


def _build(payload, root, profile):
    space = payload.get('space')
    kind = structural_kind(space)
    if kind == STORAGE_DRAWERS:
        result = materialize_storage_drawers(space, root, profile, None)
        return list(result['files']), {'manifest': result['manifest'], 'warnings': result['warnings']}
    if kind == BASE_TRIM:
        if payload.get('joint_test_sample'):
            design = structural_design(space, bed_x_mm=profile['x_mm'], bed_y_mm=profile['y_mm'])
            result = generate_base_trim_joint_test_file(base_trim_from_design(design), root, auto_timestamp=True)
            return sorted(root.glob('*.3mf')), {'result': outputs._safe_result(result, root)}
        result = export_base_trim(space, root, profile, payload.get('space_id'))
        return list(result['files']), {'manifest': result['manifest'], 'plan': result['plan']}
    if kind == STORAGE_BOX:
        design = structural_design(space, bed_x_mm=profile['x_mm'], bed_y_mm=profile['y_mm'])
        timestamp = bool(payload.get('auto_timestamp', payload['route'].endswith('structural-print')))
        result, _extra = outputs._generate({'design': design, 'auto_timestamp': timestamp}, root)
        return sorted(root.glob('*.3mf')), {'result': outputs._safe_result(result, root)}
    raise ValueError('This Space type has no structural output.')


def _plate(files, root, profile):
    issues = []
    for path in dict.fromkeys(files):
        plate_layout._file_bounds(path)  # B07's package/mesh validation.
        issues.extend(print_file_fit_issues(path, profile))
    if issues:
        raise ValueError('A file does not fit the active printer:\n' + '\n'.join(issues))
    folder = root / 'plate'
    folder.mkdir()
    path = folder / f'Wavefinity Space plate {uuid.uuid4().hex[:12]}.3mf'
    # B07 retains multipart membership and the merged four-member path.
    arranged, issues = plate_layout.combine_for_plate(files, profile, path)
    if issues:
        raise ValueError('The parts do not fit the active printer:\n' + '\n'.join(issues))
    return Path(arranged)


def _handoff(path):
    return {'filename': path.name, 'opened_automatically': False, 'confirmation_required': True}


def _combined(payload, root, profile):
    if not payload.get('space_id'):
        raise ValueError('The Space identity is required before preparing Print.')
    original_text = payload.get('inventory_text') or ''
    (root / INVENTORY_FILENAME).write_text(original_text, encoding='utf-8')
    inventory = load_inventory(root)
    layout, bins = inventory['layout'], inventory['bins']
    space = payload.get('space')
    if (normalise_space_definition(layout.get('space'), allow_legacy=True)
            != normalise_space_definition(space, allow_legacy=True)):
        raise ValueError('The saved Space changed before Print. Reopen the Space and try again.')
    kind = structural_kind(space)
    expected = payload['route']
    if ((expected.endswith('storage-box-print') and kind != STORAGE_BOX)
            or (expected.endswith('surface-print') and kind != BASE_TRIM)
            or (expected.endswith('structural-print-combined') and kind != STORAGE_DRAWERS)):
        raise ValueError('This print action does not match the selected Space.')
    by_id = {row['id']: row for row in bins}
    selected = list(dict.fromkeys(p['bin'] for drawer in layout.get('drawers', [])
                                 for p in drawer.get('placements', [])
                                 if p.get('bin') in by_id and by_id[p['bin']].get('kind') in ('bin', 'b4b')
                                 and by_id[p['bin']].get('status') != 'printed'))
    if kind == STORAGE_DRAWERS:
        blocked = selected_blocking_problems(layout, bins, selected)
        if blocked:
            raise ValueError(blocking_problem_copy(bins, blocked))
    else:
        issue = (_storage_box_arrangement_issue if kind == STORAGE_BOX else _surface_arrangement_issue)(layout['space'], space)
        errors = [issue] if issue else []
        for drawer in layout.get('drawers', []):
            errors.extend(blocking_problem_messages(drawer_report(drawer, bins, layout=layout)))
        if errors:
            raise ValueError('\n'.join(dict.fromkeys(errors)))
    original = {}
    for name, encoded in (payload.get('input_files_base64') or {}).items():
        name = _name(name)
        data = base64.b64decode(encoded, validate=True)
        if not data:
            raise ValueError('An inventory file is empty: ' + name)
        (root / name).write_bytes(data)
        original[name] = data
    structural = root / 'structural'
    structural.mkdir()
    structural_files, extra = _build(payload, structural, profile)
    prepared = prepare_inventory_bins(root, selected, _generator)
    reply = {**extra, 'selected_rows': selected}
    try:
        if prepared['failed']:
            failure = prepared['failed']
            raise ValueError(f"{failure['name']}: {failure['error']}")
        current = prepared['inventory']
        connectors, notes = _space_connectors(root, current['layout'], current['bins'])
        # Refuse incomplete connector generation, as in native combined Print.
        expected_count = sum(drawer_report(d, current['bins'], layout=current['layout'])['connector_total']
                             for d in current['layout'].get('drawers', []))
        if sum(connectors.values()) != expected_count:
            raise ValueError('Space connectors: ' + '; '.join(notes or ['Required connectors could not be made.']))
        files = list(structural_files)
        for row_id in selected:
            files.extend(prepared['files'][row_id])
        for name, count in connectors.items():
            files.extend([root / name] * count)
        plate = _plate(files, root, profile)
        reply.update(handoff=_handoff(plate), files=[p.name for p in files], notes=notes)
        reply['files_base64'] = {plate.name: base64.b64encode(plate.read_bytes()).decode('ascii')}
    except Exception as error:
        reply.update(partial=True, partial_stage='prepare', error=str(error), files=[p.name for p in structural_files])
        reply['files_base64'] = {}
    current = load_inventory(root)
    reply['files_base64'].update({p.name: base64.b64encode(p.read_bytes()).decode('ascii')
                                  for p in root.glob('*.3mf') if original.get(p.name) != p.read_bytes()})
    structural_names = {p.name.casefold() for p in structural_files}
    if structural_names & {p.name.casefold() for p in root.glob('*.3mf')}:
        raise ValueError('Structural and inventory outputs have conflicting filenames. Nothing was applied.')
    existing = {name.casefold() for name in payload.get('available_filenames', [])}
    supplied = {name.casefold() for name in original}
    for name in reply['files_base64']:
        if name.casefold() in existing - supplied:
            raise ValueError(f'{name} already exists and is not a confirmed inventory input. Rename or move it first.')
    reply['structural_files'] = _emit(_read_files(structural_files))
    specs = design_specs(current['layout'])
    reply.update(bins=current['bins'], layout=current['layout'], original_inventory_text=original_text,
                 inventory_text=render_inventory(str(payload.get('inventory_title') or 'Wavefinity'), current['bins'], current['layout']),
                 expected_print_layout=copy.deepcopy(current['layout']),
                 print_confirmation=[{'row': copy.deepcopy(row), 'design': copy.deepcopy(specs.get(row['id']))}
                                     for row in current['bins'] if row['id'] in selected])
    return reply


def _output(payload, profile):
    if outputs._emit_file is None:
        raise RuntimeError('Local output file delivery is not configured.')
    with tempfile.TemporaryDirectory(prefix='wf-structural-') as directory:
        root = Path(directory)
        if payload['route'] in _COMBINED:
            return _combined(payload, root, profile)
        files, reply = _build(payload, root, profile)
        if not files:
            raise RuntimeError('No structural files were generated.')
        reply['files'] = _emit(_read_files(files))
        if payload['route'].endswith('structural-print'):
            try:
                plate = _plate(files, root, profile)
                reply.update(print_file=_emit(_read_files([plate]))[0], handoff=_handoff(plate))
            except Exception as error:
                reply.update(partial=True, partial_stage='preflight', error=str(error))
        return reply


def _hooks(payload):
    def build(snapshot, root):
        if not snapshot.get('standard'):
            raise ValueError('Choose a Pegboard standard (standard or skadis).')
        standard = pegboard_standard(snapshot['standard']).id
        count = pegboard_hook_count(snapshot.get('count'))
        target = root / f'Pegboard hooks - {standard} x{count}.3mf'
        hooks = make_pegboard_hooks(standard, count, thickness_mm=snapshot.get('thickness_mm', 3.2))
        export_object_groups_3mf([(name, [(name, mesh)]) for name, mesh in hooks], target)
        return {'pegboard_hooks': {'output': target.name, 'count': count, 'standard': standard}}, {}
    return outputs._run(payload, build)


def _handler(path):
    def handle(payload):
        payload = copy.deepcopy(payload)
        profile = _profile(payload)
        payload['route'] = path
        with export_printer_profile(profile), build_scope(preview=False, listener=outputs._progress) as timings:
            if path.endswith('structural-design'):
                reply = _design(payload, profile)
            elif path.endswith('storage-drawers-summary'):
                reply = storage_drawers_summary(payload.get('space'), profile)
            elif path.endswith('storage-drawers-validate'):
                reply = {'space': normalise_storage_drawers_definition(payload.get('space'))}
            elif path.endswith('storage-drawers-reset'):
                reply = {'space': reset_storage_drawers_definition(payload.get('space')),
                         'message': storage_drawers_definition_problem(payload.get('space')) or ''}
            elif path.endswith(('storage-drawers-mutate', 'storage-drawers-mutate-text')):
                reply = storage_drawers_mutate_text(payload.get('inventory_text') or '',
                    title=str(payload.get('inventory_title') or 'Wavefinity'),
                    operation=str(payload.get('operation') or ''), drawer_id=payload.get('drawer_id'), proposed=payload.get('space'))
            elif path == '/api/pegboard/hooks':
                reply = _hooks(payload)
            else:
                reply = _output(payload, profile)
            reply['build_timings_ms'] = timings.report()
            return reply
    return handle


_COMBINED = {'/api/space/' + name for name in ('structural-print-combined', 'storage-box-print', 'surface-print')}
ROUTES = {path: _handler(path) for path in [
    *('/api/space/' + name for name in ('structural-design', 'structural-generate', 'structural-print',
        'structural-print-combined', 'storage-box-print', 'surface-print', 'storage-drawers-summary',
        'storage-drawers-validate', 'storage-drawers-reset', 'storage-drawers-mutate', 'storage-drawers-mutate-text')),
    '/api/pegboard/hooks',
]}
