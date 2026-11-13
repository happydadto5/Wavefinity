(() => {
  const dialog = document.getElementById('suggestions-dialog');
  const form = document.getElementById('suggestions-form');
  const result = document.getElementById('suggestions-result');
  const status = document.getElementById('suggestions-status');
  const submit = document.getElementById('suggestions-submit');
  let busy = false;
  document.getElementById('suggestions-open').addEventListener('click', () => {
    dialog.showModal();
  });
  const close = () => { if (!busy) dialog.close(); };
  document.getElementById('suggestions-close').addEventListener('click', close);
  document.getElementById('suggestions-done').addEventListener('click', close);
  dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
  dialog.addEventListener('close', () => {
    if (!result.hidden) {
      form.reset();
      form.hidden = false;
      result.hidden = true;
      status.textContent = '';
    }
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || !form.reportValidity()) return;
    busy = true;
    submit.disabled = true;
    status.textContent = '';
    try {
      const data = await api('/api/suggestions', { kind: form.elements.kind.value, title: form.elements.title.value, description: form.elements.description.value });
      await WFFileSystem.writeBlob(null, 'Wavefinity suggestion.txt', new Blob([data.text], { type: 'text/plain;charset=utf-8' }));
      form.hidden = true;
      result.hidden = false;
    } catch (error) {
      status.textContent = error.message || 'Could not create the issue. Please try again later.';
    } finally {
      busy = false;
      submit.disabled = false;
    }
  });
})();
