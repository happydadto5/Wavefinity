window.WFLocalAPI = (() => {
  let worker, initialization, active = null, epoch = 0;
  const queue = [], jobs = new Map();
  const routes = new Map(); // B14 attaches browser-side route registrations here.
  const instance = crypto.randomUUID();
  const fail = (message, kind, status = 500) => Object.assign(new Error(message), { kind, type: kind, status });
  function startWorker() {
    const current = worker = new Worker('/browser-core/worker.js', { type: 'module' });
    current.onmessage = event => {
      if (worker !== current) return;
      const message = event.data, job = jobs.get(message.job_id);
      if (!job || message.v !== 1 || message.design_epoch !== job.epoch) return;
      if (message.type === 'progress') {
        if (job.operation) job.operation.progress = message.progress;
        return;
      }
      if (message.type === 'file') {
        if (job.stale && job.epoch !== epoch) return;
        job.files.set(message.file_id, WFLocalFiles.put(message.bytes, message.mime));
        return;
      }
      if (message.type !== 'result' && message.type !== 'error') return;
      jobs.delete(job.id); active = null;
      if (job.stale && job.epoch !== epoch) {
        for (const id of job.files.values()) WFLocalFiles.discard(id);
        job.reject(fail('The design changed before this request finished.', 'STALE_DESIGN', 409));
      } else if (message.type === 'error') {
        for (const id of job.files.values()) WFLocalFiles.discard(id);
        const error = fail(message.error?.message || 'Local operation failed.', message.error?.kind || 'LOCAL_RUNTIME_ERROR', message.status);
        if (message.fatal && job.operation) error.operationUnknown = true;
        job.reject(error);
        if (message.fatal || job.path === '__init__') { worker.terminate(); worker = null; initialization = null; }
      } else {
        const used = new Set();
        const replace = value => {
          if (Array.isArray(value)) return value.map(replace);
          if (!value || typeof value !== 'object' || value instanceof ArrayBuffer || ArrayBuffer.isView(value)) return value;
          return Object.fromEntries(Object.entries(value).map(([key, item]) => {
            if (key === 'local_file_id' && job.files.has(item)) { used.add(item); return [key, job.files.get(item)]; }
            return [key, replace(item)];
          }));
        };
        const result = replace(message.result);
        for (const [id, handle] of job.files) if (!used.has(id)) WFLocalFiles.discard(handle);
        job.resolve(result);
      }
      pump();
    };
    current.onerror = () => { if (worker === current) restart(fail('The local worker stopped unexpectedly.', 'LOCAL_WORKER_ERROR')); };
    current.onmessageerror = () => { if (worker === current) restart(fail('The local worker returned an unreadable message.', 'LOCAL_WORKER_ERROR')); };
  }
  function restart(error) {
    worker?.terminate(); worker = null; initialization = null;
    if (active) {
      jobs.delete(active.id);
      for (const id of active.files.values()) WFLocalFiles.discard(id);
      if (active.operation) error.operationUnknown = true;
      active.reject(error); active = null;
    }
    pump();
  }
  function pump() {
    if (active || !queue.length) return;
    if (!worker) startWorker();
    active = queue.shift();
    jobs.set(active.id, active);
    try {
      worker.postMessage({ v: 1, job_id: active.id, path: active.path, payload: active.payload, design_epoch: active.epoch });
    } catch (error) {
      const job = active; active = null; jobs.delete(job.id); job.reject(error); pump();
    }
  }
  function submit(path, payload, { signal, stale = false, operation = null } = {}) {
    if (queue.length >= 32) return Promise.reject(fail('The local job queue is full.', 'LOCAL_QUEUE_FULL', 503));
    return new Promise((resolve, reject) => {
      const job = { id: crypto.randomUUID(), path, payload, epoch, stale, operation, files: new Map(), resolve, reject };
      const abort = () => {
        const error = Object.assign(new Error('Request cancelled.'), { name: 'AbortError' });
        if (active === job) restart(error);
        else { const index = queue.indexOf(job); if (index >= 0) { queue.splice(index, 1); reject(error); } }
      };
      if (signal?.aborted) { reject(Object.assign(new Error('Request cancelled.'), { name: 'AbortError' })); return; }
      signal?.addEventListener('abort', abort, { once: true });
      const finish = fn => value => { signal?.removeEventListener('abort', abort); fn(value); };
      job.resolve = finish(resolve); job.reject = finish(reject);
      queue.push(job); pump();
    });
  }
  function init() {
    if (!initialization) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 60000);
      initialization = submit('__init__', null, { signal: controller.signal })
        .catch(error => { initialization = null; throw error; }).finally(() => clearTimeout(timer));
    }
    return initialization;
  }
  async function request(path, payload, { signal } = {}) {
    if (path === '/api/operation-status') return WFRuntimeStatus.status(payload?.operation_id);
    if (path === '/api/health') {
      const bundle = await init();
      return { ok: true, instance, version: bundle.version, build: bundle.sha256, source_fingerprint: bundle.sha256, runtime: 'browser' };
    }
    const id = payload?.operation_id;
    const signature = JSON.stringify([path, payload]);
    let operation = id && WFRuntimeStatus.get(id);
    if (operation) {
      if (operation.signature !== signature) throw fail('Operation ID already belongs to another request.', 'OPERATION_ID_CONFLICT', 409);
      if (operation.operation_status === 'running') return { operation_id: id, operation_status: 'running' };
      if (operation.operation_status === 'done') return operation.result;
      if (operation.operation_status === 'unknown') throw Object.assign(fail('The earlier operation outcome is unknown.', 'LOCAL_OPERATION_UNKNOWN', 409), { operationUnknown: true });
      throw fail(operation.error, operation.kind, operation.status);
    }
    if (id) operation = WFRuntimeStatus.begin(id, path, signature);
    const execute = async () => {
      await init();
      const handler = routes.get(path);
      return handler ? handler(payload) : submit(path, payload, { signal: id ? null : signal, stale: path === '/api/preview', operation });
    };
    const promise = execute().then(result => {
      if (operation) Object.assign(operation, { operation_status: 'done', result });
      return result;
    }, error => {
      if (operation) Object.assign(operation, { operation_status: error.operationUnknown ? 'unknown' : 'error', error: error.message, kind: error.kind, status: error.status });
      throw error;
    });
    if (!signal) return promise;
    return new Promise((resolve, reject) => {
      const abort = () => reject(Object.assign(new Error('Request timed out.'), { name: 'AbortError' }));
      if (signal.aborted) return abort();
      signal.addEventListener('abort', abort, { once: true });
      promise.then(value => { signal.removeEventListener('abort', abort); resolve(value); }, error => { signal.removeEventListener('abort', abort); reject(error); });
    });
  }
  return { init, request, advanceDesign() { epoch += 1; }, cancel() { restart(fail('Local job cancelled.', 'LOCAL_CANCELLED', 409)); } };
})();
