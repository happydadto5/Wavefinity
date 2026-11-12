// Isolated worker. No production APIs, state, storage, or geometry service calls.
const PYODIDE = 'https://cdn.jsdelivr.net/pyodide/v0.28.3/full/';
const MANIFOLD = 'https://cdn.jsdelivr.net/npm/manifold-3d@3.5.0/';
const EARClIP = 'https://cdn.jsdelivr.net/npm/earcut@3.0.2/+esm';
const TRIMESH = 'https://files.pythonhosted.org/packages/37/82/19a03ba344ecb66ea8caab697b3059e0fbea576420f99945944c479caa78/trimesh-5.0.0-py3-none-any.whl';
const TRIMESH_SHA = '51ec67d7f9f74b918f2a695da5fd511b9c084e96307648ae83f45b58f13f8009';
let py, manifold, reference, loaded = false, loaderReport;
const progress = message => postMessage({type: 'progress', message});
async function bytes(url, expected) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  const data = await response.arrayBuffer();
  if (expected) {
    const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', data)),
      x => x.toString(16).padStart(2, '0')).join('');
    if (hash !== expected) throw new Error(`Integrity mismatch: ${url}`);
  }
  return data;
}
function resources() {
  const entries = performance.getEntriesByType('resource');
  return {
    requests: entries.length,
    known_encoded_bytes: entries.reduce((n, x) => n + x.encodedBodySize, 0),
    byte_sizes_unavailable: entries.filter(x => !x.encodedBodySize).length,
    note: 'Resource Timing can hide cross-origin bytes. Zero is unknown, not free.',
  };
}
async function load() {
  const start = performance.now();
  progress('Loading pinned Python and WebAssembly tools…');
  const refResponse = await fetch('browser-local-poc/reference.json');
  if (!refResponse.ok) throw new Error(`Reference HTTP ${refResponse.status}`);
  reference = await refResponse.json();
  const archive = await bytes('browser-local-poc/canonical.zip', reference.archive_sha256);
  const pyModule = await import(`${PYODIDE}pyodide.mjs`);
  py = await pyModule.loadPyodide({indexURL: PYODIDE});
  progress('Loading NumPy, Shapely and mesh analysis…');
  await py.loadPackage(['numpy', 'shapely', 'networkx']);
  const wheel = await bytes(TRIMESH, TRIMESH_SHA);
  py.unpackArchive(wheel, 'zip', {extractDir: '/poc'});
  py.unpackArchive(archive, 'zip', {extractDir: '/poc'});
  const earcut = (await import(EARClIP)).default;
  self.pocEarcut = (verticesJSON, endsJSON) => {
    const vertices = JSON.parse(verticesJSON), ends = JSON.parse(endsJSON);
    return JSON.stringify(earcut(vertices.flat(), ends.slice(0, -1), 2));
  };
  progress('Checking the browser boolean interface…');
  const factory = (await import(`${MANIFOLD}manifold.js`)).default;
  manifold = await factory({locateFile: name => `${MANIFOLD}${name}`});
  manifold.setup();
  // A Mesh constructor existing is not evidence that Mesh64 exists.
  const probe = new manifold.Mesh({numProp: 3,
    vertProperties: new Float32Array([0.123456789012345, 0, 0]), triVerts: new Uint32Array()});
  const capabilities = {
    release: 'manifold-3d@3.5.0', mesh64_export: typeof manifold.Mesh64,
    mesh_vertex_array: probe.vertProperties.constructor.name,
    input_coordinate: 0.123456789012345, roundtrip_coordinate: probe.vertProperties[0],
    float64_supported: false,
  };
  // This pinned release has no Mesh64 bridge. Never route through Mesh/float32.
  py.globals.set('poc_reference_json', JSON.stringify(reference));
  const bridge = await bytes('browser-local-poc/bridge.py');
  py.runPython(new TextDecoder().decode(bridge));
  loaderReport = {
    baseline_commit: reference.baseline_commit, spec: reference.spec,
    loader_ms: performance.now() - start, loader_resources: resources(),
    runtime: JSON.parse(py.runPython('poc_versions()')),
    manifold: capabilities,
    dependencies: {
      pyodide: '0.28.3', trimesh: '5.0.0', earcut: '3.0.2 (JS number/float64 coordinates)',
      native_manifold3d: 'Not in this Pyodide distribution; no compatible wheel provided.',
      lib3mf: 'Not loaded or required for STL; native library/WASM wrapper needed for future 3MF.',
    },
    poc_success: false,
  };
  loaded = true;
  postMessage({type: 'ready', report: loaderReport});
}
function build(message) {
  if (!loaded) throw new Error('Load tools before Build');
  const start = performance.now(), before = performance.getEntriesByType('resource').length;
  let blocked = 0;
  const original = {fetch: self.fetch, XMLHttpRequest: self.XMLHttpRequest, WebSocket: self.WebSocket};
  const refuse = () => { blocked++; throw new Error('Network forbidden during local geometry calculation'); };
  // Enforce the same rule in both modes. External browser-offline observation is
  // separately recorded by the acceptance runner; this is not a claim of that.
  self.fetch = refuse; self.XMLHttpRequest = refuse; self.WebSocket = refuse;
  try {
    if (JSON.stringify(message.spec) !== JSON.stringify({x: 42, y: 42, z: 28})) {
      throw new Error('Only the pinned 42x42x28 ordinary bin is supported');
    }
    const result = JSON.parse(py.runPython('poc_build()'));
    const report = {...loaderReport, ...result, build_ms: performance.now() - start,
      network_guard: {enabled: true, requested_offline: message.offline, blocked_attempts: blocked,
        resource_entries_added: performance.getEntriesByType('resource').length - before},
      rough_memory: {python_wasm_heap_bytes: py._module?.HEAPU8?.buffer.byteLength ?? null,
        manifold_wasm_heap_bytes: manifold.HEAPU8?.buffer.byteLength ?? null,
        note: 'Allocated linear memory only; excludes JS heap, browser and GPU. Null means unavailable.'},
      next_story: 'Provide a pinned browser float64 Manifold Mesh64 input/output bridge (or a compatible Pyodide manifold3d wheel), then repeat this same ordinary-bin comparison before connectors.'};
    postMessage({type: 'result', id: message.id, report});
  } finally {
    Object.assign(self, original);
  }
}
let queue = Promise.resolve();
self.onmessage = ({data}) => {
  queue = queue.then(() => data.type === 'load' ? load() : build(data)).catch(error => {
    postMessage({type: 'failure', id: data.id,
      report: {poc_success: false, failure: String(error), stack: error.stack}});
  });
};
