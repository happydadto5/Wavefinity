const base = new URL('./', self.location.href);
let py, manifold, identity;
const limit = 1536 * 1024 * 1024;
const local = path => new URL(path, base).href;
function capacity() {
  // The manifold bridge factory (vendor/manifold64/bridge64.mjs) returns only
  // locateFile/calledRun/Solid/make; its wasm memory (HEAPU8) is not exposed to JS,
  // so it cannot be measured here. The guard is therefore scoped to the heaps that
  // are readable: Pyodide's always, and the bridge's only if a build exposes it.
  const pythonBytes = py?._module?.HEAPU8?.buffer.byteLength;
  if (!pythonBytes) throw new Error('Cannot determine WebAssembly heap capacity.');
  const meshBytes = manifold?.HEAPU8?.buffer?.byteLength || 0;
  if (pythonBytes + meshBytes > limit) throw new Error('Local geometry memory limit exceeded.');
}
async function initialize() {
  const response = await fetch(local('engine/manifest.json'));
  if (!response.ok) throw new Error('Browser engine manifest unavailable.');
  identity = await response.json();
  const archiveResponse = await fetch(local('engine/canonical.zip'));
  if (!archiveResponse.ok) throw new Error('Browser engine bundle unavailable.');
  const archive = await archiveResponse.arrayBuffer();
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', archive)), b => b.toString(16).padStart(2, '0')).join('');
  if (digest !== identity.sha256) throw new Error('Browser engine bundle integrity check failed.');
  const { loadPyodide } = await import(local('vendor/pyodide/pyodide.mjs'));
  py = await loadPyodide({ indexURL: local('vendor/pyodide/') });
  // Canonical editor/text helpers import matplotlib; all wheels are vendored.
  await py.loadPackage(['numpy', 'shapely', 'networkx', 'matplotlib', 'opencv-python', 'pillow']);
  const wheel = await fetch(local('vendor/trimesh/trimesh-5.0.0-py3-none-any.whl'));
  if (!wheel.ok) throw new Error('Browser mesh package unavailable.');
  py.unpackArchive(await wheel.arrayBuffer(), 'zip', { extractDir: '/wavefinity' });
  py.unpackArchive(archive, 'zip', { extractDir: '/wavefinity' });
  const earcut = (await import(local('vendor/earcut/earcut.mjs'))).default;
  const factory = (await import(local('vendor/manifold64/bridge64.mjs'))).default;
  manifold = await factory({ locateFile: name => local(`vendor/manifold64/${name}`) });
  self.wfMakeSolid = (vertices, faces) => manifold.make(new Float64Array(JSON.parse(vertices)), new Uint32Array(JSON.parse(faces)));
  self.wfReadMesh = solid => { const mesh = solid.mesh(); return JSON.stringify({ vertices: Array.from(mesh.vertices), faces: Array.from(mesh.faces) }); };
  self.wfEarcut = (vertices, ends) => JSON.stringify(earcut(JSON.parse(vertices).flat(), JSON.parse(ends).slice(0, -1), 2));
  self.wfCapacity = capacity;
  capacity();
  py.runPython("import sys\nsys.path.insert(0, '/wavefinity')\nfrom js import wfMakeSolid, wfReadMesh, wfEarcut, wfCapacity\nfrom wf_browser_core.manifold_bridge import install\ninstall(wfMakeSolid, wfReadMesh, wfEarcut, wfCapacity)");
  return { sha256: identity.sha256, runtime: 'browser', version: '0.28.3' };
}
const ready = initialize();
// B14: every Python route is dispatched through wf_browser_core.route_dispatch
// (the flat declaration); an unknown path fails closed there and is never HTTP.
let dispatchRoute;
const unsupported = { kind: 'UNSUPPORTED_LOCAL_OPERATION', message: 'This feature is unavailable in the browser edition.' };
self.onmessage = async ({ data: job }) => {
  if (!job || job.v !== 1 || typeof job.job_id !== 'string') return;
  const send = (type, extra = {}, transfer = []) => postMessage({ v: 1, job_id: job.job_id, design_epoch: job.design_epoch, type, ...extra }, transfer);
  try {
    const bundle = await ready;
    if (job.path === '__init__') { send('result', { result: bundle }); return; }
    if (job.path === '__space_values__') {
      capacity();
      py.globals.set('_wf_space_operation', job.payload.operation);
      py.globals.set('_wf_space_payload', JSON.stringify(job.payload.payload));
      try {
        const reply = JSON.parse(py.runPython("from wf_browser_core.space_values import compute_json\ncompute_json(_wf_space_operation, _wf_space_payload)"));
        capacity();
        send(reply.error ? 'error' : 'result', reply);
      } finally {
        py.globals.delete('_wf_space_operation');
        py.globals.delete('_wf_space_payload');
      }
      return;
    }
    if (typeof job.path !== 'string' || !job.path.startsWith('/api/')) { send('error', { error: unsupported, status: 404 }); return; }
    dispatchRoute ??= py.runPython("from wf_browser_core.route_dispatch import dispatch_worker_json\ndispatch_worker_json");
    capacity();
    const file = (bytes, name, mime) => {
      const buffer = bytes instanceof ArrayBuffer ? bytes : bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
      const file_id = crypto.randomUUID();
      send('file', { file_id, name, mime, bytes: buffer }, [buffer]);
      return file_id;
    };
    const reply = JSON.parse(dispatchRoute(job.path, JSON.stringify(job.payload ?? {}), file, progress => send('progress', { progress })));
    capacity();
    if (reply.error) {
      send('error', { error: reply.error, status: reply.status || 500, fatal: /memory|allocation|heap capacity/i.test(String(reply.error.message || '')) });
      return;
    }
    const result = reply.result;
    const transfers = new Set();
    const collect = value => {
      if (value instanceof ArrayBuffer) transfers.add(value);
      else if (ArrayBuffer.isView(value)) transfers.add(value.buffer);
      else if (value && typeof value === 'object') Object.values(value).forEach(collect);
    };
    collect(result);
    send('result', { result }, [...transfers]);
  } catch (error) {
    const message = String(error?.message || error);
    const fatal = /memory|allocation|heap capacity/i.test(message);
    send('error', { status: 500, fatal, error: { kind: 'LOCAL_RUNTIME_ERROR', message } });
  }
};
