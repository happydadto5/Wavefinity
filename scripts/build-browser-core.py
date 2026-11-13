#!/usr/bin/env python3
"""Compile the shipping browser engine from this checkout; never import it.

Normal builds are offline. --fetch-vendor restores missing pinned downloads only,
verifying the committed manifest before accepting any bytes. No Emscripten runs.
--refresh-catalog compiles canonical catalog data on a dependency-equipped
maintainer machine; ordinary/static-host builds only read its hashed JSON.
"""
from __future__ import annotations

import argparse
import ast
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / 'web/browser-core'
VENDOR = CORE / 'vendor'
ENGINE = CORE / 'engine'
PINS = {
    'pyodide': '0.28.3', 'numpy': '2.2.5', 'shapely': '2.0.7',
    'geos': '3.12.1', 'networkx': '3.4.2', 'trimesh': '5.0.0',
    'earcut': '3.0.2', 'manifold': '3.5.0',
    'manifold_commit': '541c33bd2ab9b1a72816bdecff90566c0a3ee56c',
    'emscripten': '4.0.10',
}
TRIMESH_SHA = '51ec67d7f9f74b918f2a695da5fd511b9c084e96307648ae83f45b58f13f8009'
PACKAGE_ROOTS = (
    'organizer_app_impl', 'organizer_b4b', 'organizer_base_trim',
    'organizer_drawer', 'organizer_engine', 'organizer_features',
    'organizer_geometry', 'organizer_inserts', 'organizer_inventory',
    'organizer_outputs', 'organizer_spaces', 'organizer_storage',
    'wavefinity_web_impl',
)
ROOT_MODULES = (
    'organizer_app.py', 'photo_nest.py', 'plate_layout.py',
    'space_source.py', 'bambu_handoff.py',
)
# Native replacements are deliberately not installed by this asset compiler.
IMPORT_PACKAGES = {
    'numpy': 'numpy', 'shapely': 'shapely', 'matplotlib': 'matplotlib',
    'PIL': 'pillow', 'cv2': 'opencv-python', 'trimesh': None,
    'manifold3d': None, 'mapbox_earcut': None, 'lib3mf': None,
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8', newline='\n')


def vendor_path(name: str) -> Path:
    relative = PurePosixPath(name)
    if relative.is_absolute() or '..' in relative.parts or '\\' in name:
        raise ValueError(f'Unsafe vendor asset path: {name}')
    return VENDOR.joinpath(*relative.parts)


def vendor_inputs(fetch: bool) -> tuple[dict, dict[str, bytes]]:
    manifest = json.loads((VENDOR / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['pins'] != PINS:
        raise ValueError('Browser runtime pins differ from the B02 contract')
    assets = {}
    for name, entry in manifest['assets'].items():
        path = vendor_path(name)
        if not path.is_file() and fetch and entry.get('url'):
            if not entry['url'].startswith('https://'):
                raise ValueError(f'Non-HTTPS build input: {name}')
            data = urllib.request.urlopen(entry['url'], timeout=120).read()
            if digest(data) != entry['sha256'] or len(data) != entry['bytes']:
                raise ValueError(f'Download integrity mismatch: {name}')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        data = path.read_bytes()
        if digest(data) != entry['sha256'] or len(data) != entry['bytes']:
            raise ValueError(f'Vendor integrity mismatch: {name}')
        assets[name] = data
    lock = json.loads(assets['pyodide/pyodide-lock.json'])
    for name, package in manifest['packages'].items():
        if lock['packages'][name] != package:
            raise ValueError(f'Package differs from pinned Pyodide lock: {name}')
        asset = 'pyodide/' + package['file_name']
        if digest(assets[asset]) != package['sha256']:
            raise ValueError(f'Wheel integrity mismatch: {name}')
        for dependency in package['depends']:
            if dependency not in manifest['packages']:
                raise ValueError(f'Missing local dependency: {name} -> {dependency}')
    for name in ('numpy', 'shapely', 'networkx'):
        if manifest['packages'][name]['version'] != PINS[name]:
            raise ValueError(f'Incorrect browser package version: {name}')
    if digest(assets[manifest['runtime']['trimesh_wheel']]) != TRIMESH_SHA:
        raise ValueError('Trimesh wheel differs from the contract pin')
    if not any(font['member'].endswith('/DejaVuSans-Bold.ttf') for font in manifest['fonts']):
        raise ValueError('The engine requires the bundled DejaVu Sans Bold font')
    for font in manifest['fonts']:
        with zipfile.ZipFile(io.BytesIO(assets['pyodide/' + font['wheel']])) as wheel:
            if digest(wheel.read(font['member'])) != font['sha256']:
                raise ValueError(f'Font integrity mismatch: {font["member"]}')
    return manifest, assets


def source_inputs() -> tuple[dict[str, bytes], dict[str, dict], list[str]]:
    files = [ROOT / name for name in ROOT_MODULES]
    for name in PACKAGE_ROOTS:
        if not (ROOT / name / '__init__.py').is_file():
            raise ValueError(f'Missing canonical package: {name}')
        files.extend(sorted((ROOT / name).rglob('*.py')))
    sources = {path.relative_to(ROOT).as_posix(): path for path in files
               if '__pycache__' not in path.parts}
    for path in sorted(ENGINE.glob('*.py')):
        if not re.fullmatch(r'[a-z_][a-z0-9_]*', path.stem):
            raise ValueError(f'Adapter must have a snake_case module name: {path.name}')
        sources['wf_browser_core/' + path.name] = path
    archive = {}
    hashes = {}
    external = set()
    local = set(PACKAGE_ROOTS) | {Path(name).stem for name in ROOT_MODULES} | {'wf_browser_core'}
    for name, path in sorted(sources.items()):
        # Normalize checkout line endings: the zip is independent of core.autocrlf.
        text = path.read_text(encoding='utf-8-sig')
        data = text.encode('utf-8')
        tree = ast.parse(text, filename=name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                external.update(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                external.add(node.module.split('.')[0])
        archive[name] = data
        hashes[name] = {'source': path.relative_to(ROOT).as_posix(), 'sha256': digest(data), 'bytes': len(data)}
    if 'wf_browser_core/__init__.py' not in archive:
        raise ValueError('Missing browser adapter package __init__.py')
    external -= local | sys.stdlib_module_names | {'js', 'pyodide'}
    unknown = external - IMPORT_PACKAGES.keys()
    if unknown:
        raise ValueError(f'Unaccounted external imports: {sorted(unknown)}')
    # B01 is a shipping input, rather than a reason to import the HTTP server.
    routes = CORE / 'contracts/route-manifest.json'
    archive['wf_browser_core/route_manifest.json'] = routes.read_text(encoding='utf-8-sig').encode('utf-8')
    hashes['wf_browser_core/route_manifest.json'] = {
        'source': routes.relative_to(ROOT).as_posix(),
        'sha256': digest(archive['wf_browser_core/route_manifest.json']),
        'bytes': len(archive['wf_browser_core/route_manifest.json']),
    }
    # B14: the flat final declaration is what route_dispatch.py dispatches from.
    declaration = CORE / 'contracts/route-declaration.json'
    archive['wf_browser_core/route_declaration.json'] = declaration.read_text(encoding='utf-8-sig').encode('utf-8')
    hashes['wf_browser_core/route_declaration.json'] = {
        'source': declaration.relative_to(ROOT).as_posix(),
        'sha256': digest(archive['wf_browser_core/route_declaration.json']),
        'bytes': len(archive['wf_browser_core/route_declaration.json']),
    }
    return archive, hashes, sorted(external)


def catalog_inputs(archive: dict, hashes: dict, refresh: bool) -> dict:
    # Conservatively bind the catalog to all canonical Python inputs. Adapter
    # changes do not invalidate it; any canonical change requires regeneration.
    inputs = {name: entry['sha256'] for name, entry in hashes.items()
              if not name.startswith('wf_browser_core/')}
    source_sha = digest(json.dumps(inputs, sort_keys=True, separators=(',', ':')).encode('utf-8'))
    catalog_path = ENGINE / 'catalog.json'
    manifest_path = ENGINE / 'catalog_manifest.json'
    if refresh:
        # Explicit production asset compilation only. Render's normal build
        # never takes this branch or imports canonical/native geometry.
        sys.path.insert(0, str(ROOT))
        from wavefinity_web_impl._catalog import catalog_payload
        from wavefinity_web_impl._runtime import SERVER_VERSION, API_COMPAT_VERSION
        catalog = catalog_payload(environment={
            'platform': 'browser', 'version': SERVER_VERSION, 'instance': 'browser',
            'api_compat': API_COMPAT_VERSION, 'build': source_sha, 'hosted': True,
            'output': '', 'preferences': {},
            'slicer': {'available': False, 'path': None, 'name': 'Bambu Studio'},
        })
        write_json(catalog_path, catalog)
        write_json(manifest_path, {
            'schema': 'wavefinity-browser-catalog/1',
            'sha256': digest(catalog_path.read_bytes()), 'source_sha256': source_sha,
            'source_hashes': inputs,
        })
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    data = catalog_path.read_bytes()
    if (manifest['schema'] != 'wavefinity-browser-catalog/1'
            or manifest['source_sha256'] != source_sha or manifest['source_hashes'] != inputs
            or manifest['sha256'] != digest(data)):
        raise ValueError('Catalog inputs changed; regenerate shipping assets with --refresh-catalog on a dependency-equipped maintainer machine')
    for path in (catalog_path, manifest_path):
        name = 'wf_browser_core/' + path.name
        data = path.read_bytes()
        archive[name] = data
        hashes[name] = {'source': path.relative_to(ROOT).as_posix(),
                        'sha256': digest(data), 'bytes': len(data)}
    return {key: manifest[key] for key in ('schema', 'sha256', 'source_sha256')}


def build(fetch: bool, refresh_catalog: bool = False) -> None:
    vendor, assets = vendor_inputs(fetch)
    archive, hashes, imports = source_inputs()
    catalog = catalog_inputs(archive, hashes, refresh_catalog)
    for module in imports:
        package = IMPORT_PACKAGES[module]
        if package and package not in vendor['packages']:
            raise ValueError(f'Import has no local wheel: {module}')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for name, data in sorted(archive.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, data, compresslevel=9)
    data = buffer.getvalue()
    ENGINE.mkdir(parents=True, exist_ok=True)
    # Always regenerate; an old source archive is never an input to this build.
    (ENGINE / 'canonical.zip').write_bytes(data)
    sizes = {name: {'bytes': len(value), 'gzip_bytes': len(gzip.compress(value, mtime=0))}
             for name, value in sorted(assets.items())}
    sizes['engine/canonical.zip'] = {'bytes': len(data), 'gzip_bytes': len(gzip.compress(data, mtime=0))}
    # Conservatively includes every vendored file, even bridge sources/licenses.
    raw = sum(item['bytes'] for item in sizes.values())
    compressed = sum(item['gzip_bytes'] for item in sizes.values())
    target = vendor['planning']['compressed_first_load_target_bytes']
    manifest = {
        'schema': 'wavefinity-browser-engine/1',
        'archive': 'canonical.zip', 'sha256': digest(data), 'bytes': len(data),
        'source_hash_mode': 'UTF-8 without BOM, LF line endings', 'sources': hashes,
        'catalog': catalog,
        'vendor_manifest_sha256': digest((VENDOR / 'manifest.json').read_bytes()),
        'external_imports': imports, 'pending_adapters': vendor['pending_adapters'],
        'size_accounting': {'assets': sizes, 'total_bytes': raw,
                            'total_gzip_bytes': compressed, 'planning_target_bytes': target,
                            'within_planning_target': compressed <= target,
                            'scope': 'Entire B02 vendor tree and canonical.zip; excludes future UI/worker assets and manifest JSON. gzip totals are build encoding sizes, not observed network transfer. Hosting compression/traffic allowance is not established here.'},
        'memory_planning': vendor['planning'],
    }
    write_json(ENGINE / 'manifest.json', manifest)
    # Include manifests and unpacked adapter sources in the final on-disk total.
    # The manifest cannot recursively encode its own gzip size.
    complete_files = sorted(path for directory in (VENDOR, ENGINE)
                            for path in directory.rglob('*') if path.is_file())
    complete_raw = sum(path.stat().st_size for path in complete_files)
    complete_gzip = sum(len(gzip.compress(path.read_bytes(), mtime=0)) for path in complete_files)
    print(f'Browser core: {len(hashes)} source files; {len(assets)} pinned vendor assets')
    print(f'Assets: {raw:,} bytes raw; {compressed:,} bytes gzip; target {target:,} bytes')
    print(f'Complete vendor/engine trees including manifests: {complete_raw:,} bytes raw; {complete_gzip:,} bytes gzip')
    print(f'canonical.zip SHA256 {digest(data)}')
    if complete_gzip > target:
        raise ValueError(f'Complete B02 assets exceed the 64 MiB planning target by {complete_gzip-target:,} bytes; no features were dropped')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch-vendor', action='store_true', help='Restore missing HTTPS assets using committed hashes (build-time network only)')
    parser.add_argument('--refresh-catalog', action='store_true', help='Compile canonical catalog JSON using locally installed production dependencies')
    args = parser.parse_args()
    try:
        build(args.fetch_vendor, args.refresh_catalog)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        raise SystemExit(f'Browser core build failed: {error}') from None
