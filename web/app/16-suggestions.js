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
      const response = await fetch('/api/suggestions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ kind: form.elements.kind.value, title: form.elements.title.value, description: form.elements.description.value }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Could not create the issue. Please try again later.');
      const link = document.getElementById('suggestions-link');
      link.href = data.url;
      link.textContent = `#${data.number}`;
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
