window.WFRuntimeStatus = (() => {
  const operations = new Map();
  return {
    get(id) { return operations.get(id); },
    begin(id, path, signature) {
      const entry = { operation_id: id, operation_status: 'running', path, signature };
      operations.set(id, entry);
      return entry;
    },
    status(id) {
      const entry = operations.get(id);
      if (!entry) return { operation_id: id, operation_status: 'unknown' };
      const { path, signature, promise, ...publicStatus } = entry;
      return publicStatus;
    },
  };
})();
