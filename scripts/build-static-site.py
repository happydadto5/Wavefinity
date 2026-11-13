#!/usr/bin/env python3
"""Assemble the complete static Wavefinity site into dist/ (B14 production build).

Standard library only. Steps, any failure aborts the build with a non-zero exit:
  1. Route integrity: the flat final route declaration the runtime dispatches from
     (web/browser-core/contracts/route-declaration.json) is compared with the route
     manifest (B01) and the source-route index, and with the declaring module sources.
  2. Regenerate the browser engine bundle (scripts/build-browser-core.py, no network).
  3. Copy the production files into dist/ (proof-of-concept, tests and non-shipping
     material excluded) and check the result is self-contained.

This is shipping compile integrity, not a test. It changes no hosting, DNS or domain.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'web'
CORE = WEB / 'browser-core'
DIST = ROOT / 'dist'
DECLARATION = CORE / 'contracts/route-declaration.json'
MANIFEST = CORE / 'contracts/route-manifest.json'
INDEX = ROOT / 'Future plans/Browser-only-core-source-route-index.md'

RUNTIMES = {'python', 'javascript'}
OWNERS = {'B03', 'B04', 'B05', 'B06', 'B08', 'B09', 'B10', 'B11', 'B12', 'B13'}
BUILTIN_MODULE = 'web/browser-core/local-api.js'   # /api/health, /api/operation-status
# Modules whose route keys come from canonical code they wrap rather than from their own text.
DELEGATES = {'web/browser-core/engine/drawer_routes.py': 'organizer_drawer/__init__.py'}
PATH_RE = re.compile(r'/api/[a-z0-9][a-z0-9/-]*')
INDEX_ROW = re.compile(r'^\| `(/api/[^`]+)` \| (.*?) \| (.*?) \| (B\d\d) \| (\w+) \| (local|retired)\b')


class BuildError(Exception):
    pass


def fail(message: str) -> None:
    raise BuildError(message)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8-sig'))


# ---------------------------------------------------------------- route integrity

def string_literals(path: Path) -> set[str]:
    """String constants of a Python or JavaScript module (template text split at ${})."""
    text = path.read_text(encoding='utf-8-sig')
    if path.suffix == '.py':
        return {node.value for node in ast.walk(ast.parse(text, filename=str(path)))
                if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    found = set()
    for match in re.finditer(r"'((?:[^'\\\n]|\\.)*)'|\"((?:[^\"\\\n]|\\.)*)\"|`((?:[^`\\]|\\.)*)`", text):
        if match.group(3) is not None:
            found.update(part for part in re.split(r'\$\{[^}]*\}', match.group(3)) if part)
        else:
            found.add(match.group(1) if match.group(1) is not None else match.group(2))
    return found


def path_is_spelled(path: str, literals: set[str]) -> bool:
    """A route key is written whole, or as a '/api/x/' prefix plus a separate name literal."""
    if path in literals:
        return True
    return any(prefix.endswith('/') and path.startswith(prefix) and path[len(prefix):] in literals
               for prefix in literals if prefix.startswith('/api/'))


def check_routes() -> dict:
    declaration = load_json(DECLARATION)
    if declaration.get('schema') != 'wavefinity-route-declaration/1':
        fail('Route declaration has an unknown schema.')
    declared: dict[str, dict] = {}
    for row in declaration['routes']:
        path = row.get('path')
        if not isinstance(path, str) or not PATH_RE.fullmatch(path):
            fail(f'Route declaration has an invalid path: {path!r}')
        if path in declared:
            fail(f'Duplicate route in declaration: {path}')
        if row.get('runtime') not in RUNTIMES or row.get('owner') not in OWNERS:
            fail(f'Unknown runtime or owner for declared route {path}')
        module = row.get('module')
        if not isinstance(module, str) or not (ROOT / module).is_file():
            fail(f'Declared module is unavailable for {path}: {module}')
        declared[path] = row

    manifest = load_json(MANIFEST)
    seen: set[str] = set()
    retired: dict[str, dict] = {}
    for row in manifest['routes']:
        path = row['path']
        if path in seen:
            fail(f'Duplicate route in manifest: {path}')
        seen.add(path)
        disposition = row.get('disposition')
        if disposition == 'local':
            wanted = declared.get(path)
            if wanted is None:
                fail(f'Manifest local route is missing from the declaration: {path}')
            for key, field in (('owner', 'owner'), ('runtime', 'runtime'), ('module', 'browser_module')):
                if wanted[key] != row.get(field):
                    fail(f'{path}: declaration {key} {wanted[key]!r} differs from manifest {field} {row.get(field)!r}')
        elif disposition == 'retired':
            if not row.get('replacement'):
                fail(f'Retired route does not name its local replacement: {path}')
            retired[path] = row
        else:
            fail(f'Unclassified route in manifest: {path} ({disposition!r})')
    local_paths = {row['path'] for row in manifest['routes'] if row['disposition'] == 'local'}
    extra = sorted(set(declared) - local_paths)
    if extra:
        fail(f'Declaration has routes the manifest does not list as local: {extra}')
    callable_retired = sorted(set(retired) & set(declared))
    if callable_retired:
        fail(f'Retired routes are callable: {callable_retired}')

    # Source-route index: same set, owners, runtimes and dispositions.
    indexed: dict[str, tuple] = {}
    for line in INDEX.read_text(encoding='utf-8-sig').splitlines():
        match = INDEX_ROW.match(line)
        if match:
            path, handler, _refs, owner, runtime, disposition = match.groups()
            if path in indexed:
                fail(f'Duplicate route in index: {path}')
            indexed[path] = (handler, owner, runtime, disposition)
    if set(indexed) != seen:
        fail(f'Index and manifest disagree. Missing from index: {sorted(seen - set(indexed))}; '
             f'not in manifest: {sorted(set(indexed) - seen)}')
    for path, (handler, owner, runtime, disposition) in indexed.items():
        if path in retired:
            if disposition != 'retired':
                fail(f'Index does not retire {path}')
            continue
        row = declared[path]
        if (owner, runtime, disposition) != (row['owner'], row['runtime'], 'local'):
            fail(f'Index row for {path} contradicts the declaration')
        named = re.search(r'`(web/browser-core/[^`\s·]+)`\s*$', handler.split('·')[-1].strip())
        if named and named.group(1) != row['module']:
            fail(f'Index names {named.group(1)} for {path}; declared module is {row["module"]}')

    # Declaring sources: each module exports ROUTES, spells every route it is declared
    # for, and spells no other route.
    by_module: dict[str, set[str]] = {}
    for path, row in declared.items():
        by_module.setdefault(row['module'], set()).add(path)
    for module, paths in sorted(by_module.items()):
        source = ROOT / module
        literals = string_literals(source)
        if module in DELEGATES:
            literals |= string_literals(ROOT / DELEGATES[module])
        text = source.read_text(encoding='utf-8-sig')
        if module != BUILTIN_MODULE:
            has_routes = (re.search(r'^ROUTES\s*=', text, re.M) if source.suffix == '.py'
                          else re.search(r'^export const ROUTES\b', text, re.M))
            if not has_routes:
                fail(f'{module} does not export ROUTES')
        for path in sorted(paths):
            if not path_is_spelled(path, literals):
                fail(f'{module} does not define declared route {path}')
        # A trailing-slash literal is a key prefix, not a route.
        unexpected = sorted(item for item in literals if PATH_RE.fullmatch(item)
                            and not item.endswith('/') and item not in declared)
        if unexpected:
            fail(f'{module} names routes that are not declared: {unexpected}')
        foreign = sorted(item for item in literals if item in declared and item not in paths)
        if foreign and source.suffix == '.js' and module != BUILTIN_MODULE:
            fail(f'{module} registers routes declared for another module: {foreign}')
    print(f'Routes: {len(declared)} local routes declared once, {len(retired)} retired, '
          f'manifest and index agree.')
    return declaration


# ---------------------------------------------------------------- browser engine

def build_engine() -> None:
    spec = importlib.util.spec_from_file_location('build_browser_core', ROOT / 'scripts/build-browser-core.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.build(fetch=False)


# ---------------------------------------------------------------- dist assembly

POC_NAMES = {'browser-local-poc.html', 'browser-local-poc.js', 'browser-local-poc-worker.js', 'browser-local-poc'}
# Repository-relative web/ paths that are build inputs or superseded, never shipped.
EXCLUDED = {
    'images',                                    # canonical artwork is repository-root images/
    'browser-core/contracts/route-manifest.json',  # packaged in the engine bundle, not fetched
    'browser-core/vendor/manifest.json',
    'browser-core/vendor/manifold64/bridge64.cpp',
    'browser-core/vendor/manifold64/build.sh',
    'browser-core/engine/catalog.json',          # inside canonical.zip
    'browser-core/engine/catalog_manifest.json',
}
EXCLUDED_DIRS = {'__pycache__', 'tests', 'test', 'browser-tests', 'node_modules', '.git'}
SHIPPED_SUFFIXES = {'.html', '.js', '.mjs', '.css', '.json', '.wasm', '.zip', '.whl', '.png',
                    '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.webp', '.woff', '.woff2', '.ttf', '.md', ''}
SECRET = re.compile(r'(^\.env|\.pem$|\.key$|\.pfx$|secret|credential)', re.I)


def excluded(relative: Path) -> bool:
    posix = relative.as_posix()
    if relative.parts[0] in POC_NAMES or any(part in EXCLUDED_DIRS for part in relative.parts):
        return True
    if relative.parts[0] == 'browser-core' and len(relative.parts) == 3 and relative.parts[1] == 'engine' \
            and relative.suffix in {'.py', '.pyc'}:
        return True                              # sources live inside canonical.zip
    return any(posix == item or posix.startswith(item + '/') for item in EXCLUDED)


def copy_file(source: Path, target: Path, written: dict[str, Path]) -> None:
    key = target.relative_to(DIST).as_posix()
    if key in written:
        fail(f'Two inputs map to dist/{key}')
    if SECRET.search(source.name):
        fail(f'Refusing to ship a credential-like file: {source}')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    written[key] = source


def assemble() -> None:
    if DIST.exists():
        if DIST.resolve().parent != ROOT:
            fail('Refusing to clean an unexpected dist location.')
        shutil.rmtree(DIST)
    DIST.mkdir()
    written: dict[str, Path] = {}
    for source in sorted(WEB.rglob('*')):
        if not source.is_file():
            continue
        relative = source.relative_to(WEB)
        if excluded(relative):
            continue
        if source.suffix.lower() not in SHIPPED_SUFFIXES:
            fail(f'Unclassified file type under web/: {relative.as_posix()}')
        copy_file(source, DIST / relative, written)
    images = ROOT / 'images'
    if not images.is_dir():
        fail('Repository-root images/ is missing.')
    for source in sorted(images.rglob('*')):
        if source.is_file():
            copy_file(source, DIST / 'images' / source.relative_to(images), written)
    brochure = ROOT / 'Brochure.md'
    if not brochure.is_file():
        fail('Brochure.md is missing.')
    copy_file(brochure, DIST / 'Brochure.md', written)
    copy_file(brochure, DIST / 'brochure.md', written)
    print(f'dist: {len(written)} files')


REQUIRED = (
    'index.html', 'Brochure.md', 'brochure.md', 'browser-core/worker.js', 'browser-core/local-api.js',
    'browser-core/contracts/route-declaration.json', 'browser-core/engine/canonical.zip',
    'browser-core/engine/manifest.json', 'browser-core/vendor/pyodide/pyodide.mjs',
    'browser-core/vendor/pyodide/pyodide.asm.wasm', 'browser-core/vendor/pyodide/pyodide-lock.json',
    'browser-core/vendor/manifold64/bridge64.mjs', 'browser-core/vendor/manifold64/bridge64.wasm',
    'browser-core/vendor/earcut/earcut.mjs', 'browser-core/vendor/trimesh/trimesh-5.0.0-py3-none-any.whl',
)


def verify_dist() -> None:
    for name in REQUIRED:
        if not (DIST / name).is_file():
            fail(f'dist is missing {name}')
    if (DIST / 'Brochure.md').read_bytes() != (DIST / 'brochure.md').read_bytes():
        fail('Brochure aliases differ.')
    for name in POC_NAMES:
        if (DIST / name).exists():
            fail(f'Proof-of-concept file reached dist: {name}')
    if any('browser-local-poc' in path.as_posix() for path in DIST.rglob('*')):
        fail('Proof-of-concept path reached dist.')
    engine = json.loads((DIST / 'browser-core/engine/manifest.json').read_text(encoding='utf-8'))
    if hashlib.sha256((DIST / 'browser-core/engine/canonical.zip').read_bytes()).hexdigest() != engine['sha256']:
        fail('dist engine bundle does not match its manifest.')
    page = (DIST / 'index.html').read_text(encoding='utf-8')
    for reference in sorted(set(re.findall(r'''(?:src|href)=["'](/[^"'#?]*)''', page))):
        if reference != '/' and not (DIST / reference.lstrip('/')).is_file():
            fail(f'index.html references a file that is not in dist: {reference}')
    declared = {row['module'] for row in load_json(DIST / 'browser-core/contracts/route-declaration.json')['routes']}
    with zipfile.ZipFile(DIST / 'browser-core/engine/canonical.zip') as bundle:
        packaged = set(bundle.namelist())
    for module in sorted(declared):
        if module.endswith('.py'):          # Python modules run from the engine bundle
            if f'wf_browser_core/{Path(module).name}' not in packaged:
                fail(f'Declared module is not in the engine bundle: {module}')
        elif not (DIST / Path(module).relative_to('web')).is_file():
            fail(f'Declared module is not shipped: {module}')
    for name in ('route_declaration.json', 'route_dispatch.py'):
        if f'wf_browser_core/{name}' not in packaged:
            fail(f'Engine bundle lacks {name}')
    for path in DIST.rglob('*'):
        if path.is_file() and path.suffix in {'.py', '.pyc', '.cpp', '.sh'}:
            fail(f'Non-shipping source reached dist: {path.relative_to(DIST).as_posix()}')
    total = sum(path.stat().st_size for path in DIST.rglob('*') if path.is_file())
    biggest = max((path for path in DIST.rglob('*') if path.is_file()), key=lambda path: path.stat().st_size)
    print(f'dist verified: {total:,} bytes; largest file {biggest.relative_to(DIST).as_posix()} '
          f'({biggest.stat().st_size:,} bytes)')


def main() -> int:
    try:
        check_routes()
        build_engine()
        assemble()
        verify_dist()
    except BuildError as error:
        print(f'STATIC BUILD ABORTED: {error}', file=sys.stderr)
        return 1
    print('Static site ready in dist/. Publish directory: dist')
    return 0


if __name__ == '__main__':
    sys.exit(main())
