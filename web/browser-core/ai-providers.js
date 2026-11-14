// Browser-direct BYOK only. No key goes to the worker or persistent storage.
import { loadPreferences, mutatePreferences } from './preferences.js';

export const PROVIDERS = Object.freeze({
  openai: { origin: 'https://api.openai.com', base: 'https://api.openai.com/v1' },
  anthropic: { origin: 'https://api.anthropic.com', base: 'https://api.anthropic.com/v1' },
  gemini: { origin: 'https://generativelanguage.googleapis.com', base: 'https://generativelanguage.googleapis.com/v1beta' },
});
let connection = null;
let revision = 0;
const requests = new Set();
function clearKey() {
  connection = null;
  revision += 1;
  for (const controller of requests) controller.abort();
}
const manual = ' You can still copy the prompt and paste the answer manually.';
const fail = message => Object.assign(new Error(message + manual), { status: 400, kind: 'AI_PROVIDER_ERROR' });

export function providerSettings(raw) {
  const provider = String(raw?.provider || 'openai');
  if (!Object.hasOwn(PROVIDERS, provider)) throw fail('Choose a supported provider adapter.');
  const name = String(raw?.name || '').trim(), model = String(raw?.model || '').trim();
  let url;
  try { url = new URL(String(raw?.url || PROVIDERS[provider].base).trim()); decodeURIComponent(url.pathname); }
  catch (_error) { throw fail('Enter a valid HTTPS endpoint base URL.'); }
  const hostname = url.hostname.toLowerCase().replace(/\.+$/, '');
  if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash ||
      hostname === location.hostname.toLowerCase().replace(/\.+$/, '') || /(^|\.)wavefinity\.org$/i.test(hostname)) {
    throw fail('Use an external provider HTTPS endpoint without credentials, query or fragment. Wavefinity hosts are forbidden.');
  }
  if (!name || name.length > 80 || !model || model.length > 200 || url.href.length > 2048 ||
      /[\x00-\x1f]/.test(name + model) || !/^[a-zA-Z0-9._:/-]+$/.test(model)) {
    throw fail('Enter a connection name and a valid model identifier.');
  }
  return { provider, name, model, url: url.href.replace(/\/$/, '') };
}

function status(settings) {
  return { ...settings, configured: Boolean(connection?.key), has_key: Boolean(connection?.key),
    custom: settings ? new URL(settings.url).origin !== PROVIDERS[settings.provider].origin : false };
}

export async function aiConnection(payload = {}) {
  if (payload.action === 'status') {
    const prefs = await loadPreferences();
    return { ...status(connection || (prefs.ai_provider ? providerSettings(prefs.ai_provider) : null)), mode: prefs.ai_mode || null };
  }
  if (payload.action === 'mode') {
    if (!['manual', 'automatic'].includes(payload.mode)) throw fail('Choose an AI mode.');
    await mutatePreferences(prefs => { prefs.ai_mode = payload.mode; });
    return { mode: payload.mode };
  }
  if (payload.action === 'clear') {
    clearKey();
    return { configured: false, has_key: false };
  }
  if (!['save', 'test'].includes(payload.action)) throw fail('Choose an AI connection action.');
  const settings = providerSettings(payload);
  const key = String(payload.key || '').trim() || (payload.keep_key &&
    connection?.url === settings.url && connection?.provider === settings.provider ? connection.key : '');
  if (!key || key.length > 4096 || /[\x00-\x20\x7f]/.test(key)) throw fail('Enter your provider API key for this session.');
  if (Object.values(settings).some(value => value.includes(key)) || decodeURIComponent(new URL(settings.url).pathname).includes(key)) throw fail('Keep the key only in the API key field.');
  if (payload.browser_access !== true) throw fail('Confirm your provider permits browser access with this credential.');
  const custom = new URL(settings.url).origin !== PROVIDERS[settings.provider].origin;
  if (custom && payload.trust_endpoint !== true) throw fail('Explicitly trust this custom endpoint before sending it a key.');
  const chosen = { ...settings, key };
  if (payload.action === 'test') { await chat(chosen, 'Reply with OK.'); return { ok: true }; }
  // Write only these named non-secret fields. A failed save leaves the old key intact.
  const captured = revision;
  await mutatePreferences(prefs => { prefs.ai_provider = settings; });
  if (captured !== revision) throw fail('The connection was cleared while saving.');
  connection = chosen;
  revision += 1;
  return status(connection);
}

async function chat(chosen, prompt) {
  if (typeof prompt !== 'string' || !prompt.trim() || prompt.length > 1_000_000) throw fail('Generate a prompt first (maximum 1,000,000 characters).');
  if (prompt.includes(chosen.key)) throw fail('Remove the API key from the prompt.');
  const headers = { 'Content-Type': 'application/json' };
  let url, body;
  if (chosen.provider === 'anthropic') {
    url = chosen.url + '/messages';
    Object.assign(headers, { 'x-api-key': chosen.key, 'anthropic-version': '2023-06-01',
      'anthropic-dangerous-direct-browser-access': 'true' });
    body = { model: chosen.model, max_tokens: 8192, messages: [{ role: 'user', content: prompt }] };
  } else if (chosen.provider === 'gemini') {
    url = chosen.url + '/models/' + encodeURIComponent(chosen.model.replace(/^models\//, '')) + ':generateContent';
    headers['x-goog-api-key'] = chosen.key;
    body = { contents: [{ role: 'user', parts: [{ text: prompt }] }] };
  } else {
    url = chosen.url + '/chat/completions';
    headers.Authorization = 'Bearer ' + chosen.key;
    body = { model: chosen.model, messages: [{ role: 'user', content: prompt }] };
  }
  const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 55000);
  requests.add(controller);
  try {
    let response;
    try {
      response = await fetch(url, { method: 'POST', headers, body: JSON.stringify(body),
        mode: 'cors', credentials: 'omit', redirect: 'error', referrerPolicy: 'no-referrer',
        cache: 'no-store', signal: controller.signal });
    } catch (_error) {
      throw fail(controller.signal.aborted ? 'The provider request timed out.' :
        'The browser could not reach the provider: CORS, organization policy, CSP, a blocked redirect or a network failure may be responsible. The browser does not disclose which.');
    }
    if (!response.ok) {
      await response.body?.cancel();
      const reason = { 400: 'Request or model rejected', 401: 'Credential rejected', 403: 'Access or organization policy refused',
        404: 'Endpoint or model not found', 429: 'Provider quota, billing or rate limit reached' }[response.status] || 'Provider request failed';
      // Never surface provider bodies/statusText: either may echo credentials.
      throw fail(`${reason} (HTTP ${response.status}).`);
    }
    const reader = response.body.getReader(), chunks = [];
    let size = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 4 * 1024 * 1024) { await reader.cancel(); throw fail('The provider response exceeded 4 MB.'); }
      chunks.push(value);
    }
    let data;
    try { data = JSON.parse(await new Blob(chunks).text()); }
    catch (_error) { throw fail('The provider returned invalid JSON.'); }
    const answer = chosen.provider === 'anthropic' ? data.content?.filter(p => p.type === 'text').map(p => p.text).join('\n') :
      chosen.provider === 'gemini' ? data.candidates?.[0]?.content?.parts?.map(p => p.text || '').join('\n') : data.choices?.[0]?.message?.content;
    if (typeof answer !== 'string' || !answer.trim()) throw fail('The provider returned no text (it may have refused the request).');
    return { answer: answer.split(chosen.key).join('[credential removed]') };
  } catch (error) {
    if (error?.kind === 'AI_PROVIDER_ERROR') throw error;
    throw fail(controller.signal.aborted ? 'The provider request timed out.' : 'The provider response could not be read.');
  } finally { clearTimeout(timer); requests.delete(controller); }
}

export async function aiAsk(payload) {
  if (!connection?.key) throw fail('Configure your own provider key for this session first.');
  const captured = revision;
  const result = await chat(connection, payload.prompt);
  if (captured !== revision) throw fail('The AI connection changed while waiting.');
  return result;
}

// BFCache can retain JS memory; leaving the document clears it as well.
window.addEventListener('pagehide', clearKey);
