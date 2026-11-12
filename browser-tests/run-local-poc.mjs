// Story 2979's bounded acceptance exercise. Uses installed Chrome/Edge only.
// No npm packages, browser downloads, installations, or production API calls.
import {spawn} from 'node:child_process';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import path from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';

const [kind = 'chrome', base = 'http://127.0.0.1:8879'] = process.argv.slice(2);
if (!['chrome', 'edge'].includes(kind)) throw new Error('Choose chrome or edge');
const executable = kind === 'chrome'
  ? 'C:/Program Files/Google/Chrome/Application/chrome.exe'
  : 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const output = path.resolve('local-temp/story-2979');
const profile = path.join(output, `${kind}-${Date.now()}`);
await mkdir(profile, {recursive: true});
const child = spawn(executable, ['--headless=new', '--no-first-run', '--no-default-browser-check',
  '--disable-background-networking', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'],
  {stdio: 'ignore', windowsHide: true});
let socket;
try {
  let port;
  for (let i = 0; i < 100; i++) {
    try { port = (await readFile(path.join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]; break; }
    catch { await delay(100); }
  }
  if (!port) throw new Error('Installed browser did not expose its private debugging port');
  const version = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
  socket = new WebSocket(version.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  let next = 0;
  const pending = new Map(), sessions = new Set(), requests = new Map(), errors = [];
  function send(method, params = {}, sessionId) {
    return new Promise((resolve, reject) => {
      const id = ++next; pending.set(id, {resolve, reject});
      socket.send(JSON.stringify({id, method, params, ...(sessionId ? {sessionId} : {})}));
    });
  }
  socket.onmessage = ({data}) => {
    const event = JSON.parse(data);
    if (event.id) {
      const waiter = pending.get(event.id); pending.delete(event.id);
      if (event.error) waiter?.reject(new Error(JSON.stringify(event.error))); else waiter?.resolve(event.result);
      return;
    }
    const key = `${event.sessionId}:${event.params?.requestId}`;
    if (event.method === 'Network.requestWillBeSent') requests.set(key,
      {url: event.params.request.url, method: event.params.request.method, encoded_bytes: 0});
    if (event.method === 'Network.loadingFinished' && requests.has(key))
      requests.get(key).encoded_bytes = event.params.encodedDataLength;
    if (event.method === 'Network.responseReceived' && requests.has(key))
      requests.get(key).status = event.params.response.status;
    if (event.method === 'Runtime.exceptionThrown') errors.push(event.params.exceptionDetails);
    if (event.method === 'Target.attachedToTarget') {
      const session = event.params.sessionId; sessions.add(session);
      (async () => {
        await send('Network.enable', {}, session);
        await send('Network.setCacheDisabled', {cacheDisabled: true}, session);
        await send('Runtime.enable', {}, session);
        await send('Runtime.runIfWaitingForDebugger', {}, session);
      })().catch(error => errors.push(String(error)));
    }
  };
  const {targetId} = await send('Target.createTarget', {url: 'about:blank'});
  const {sessionId} = await send('Target.attachToTarget', {targetId, flatten: true});
  sessions.add(sessionId);
  await send('Page.enable', {}, sessionId);
  await send('Network.enable', {}, sessionId);
  await send('Network.setCacheDisabled', {cacheDisabled: true}, sessionId);
  await send('Target.setAutoAttach', {autoAttach: true, waitForDebuggerOnStart: true, flatten: true}, sessionId);
  const evaluate = async expression => {
    const result = await send('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true}, sessionId);
    if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  await send('Page.navigate', {url: `${base}/browser-local-poc.html`}, sessionId);
  async function waitFor(expression, timeout = 180000) {
    const started = Date.now(); let lastStatus;
    while (Date.now() - started < timeout) {
      const status = await evaluate("document.getElementById('status')?.textContent");
      if (status !== lastStatus) { console.log(`${kind}: ${status}`); lastStatus = status; }
      if (await evaluate(expression)) return;
      await delay(300);
    }
    throw new Error(`Timed out: ${lastStatus}`);
  }
  await waitFor("typeof document.getElementById('load')?.onclick === 'function'");
  await evaluate("document.getElementById('load').click()");
  await waitFor("!document.getElementById('build').disabled || document.getElementById('status').textContent.includes('failed')");
  const loaded = await evaluate("!document.getElementById('build').disabled");
  const snapshot = () => evaluate("({status: document.getElementById('status').textContent, report: JSON.parse(document.getElementById('report').textContent || '{}'), stl_visible: !document.getElementById('stl').hidden})");
  const coldRequests = Array.from(requests.values());
  let online, offline, noNetwork;
  if (loaded) {
    await evaluate("document.getElementById('build').click()");
    await waitFor("document.getElementById('status').textContent.includes('failed') || document.getElementById('status').textContent.includes('passed')");
    online = await snapshot();
    await send('Network.emulateNetworkConditions',
      {offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0}, sessionId);
    // Worker targets do not implement emulateNetworkConditions. Block all
    // worker/page URLs at the browser network layer as well as page offline.
    for (const session of sessions) await send('Network.setBlockedURLs', {urls: ['*']}, session);
    const requestCount = requests.size;
    await evaluate("document.getElementById('offline').click()");
    await waitFor("document.getElementById('status').textContent.includes('failed') || document.getElementById('status').textContent.includes('passed')");
    offline = await snapshot();
    noNetwork = {page_offline: true, all_target_urls_blocked: true,
      new_requests: requests.size - requestCount};
  } else online = await snapshot();
  const evidence = {browser: version.Browser, user_agent: version['User-Agent'],
    cold_loader_requests: coldRequests, cold_loader_encoded_bytes: coldRequests.reduce((n, r) => n + r.encoded_bytes, 0),
    online, offline, no_network_after_load: noNetwork, runtime_errors: errors,
    production_api_requests: Array.from(requests.values()).filter(r => new URL(r.url).pathname.startsWith('/api/'))};
  await writeFile(path.join(output, `${kind}-result.json`), JSON.stringify(evidence, null, 2));
  console.log(JSON.stringify({browser: evidence.browser, loader_bytes: evidence.cold_loader_encoded_bytes,
    loaded, online: online.status, offline: offline?.status, noNetwork, errors: errors.length,
    failure: online.report.failure, partial_geometry: online.report.partial_geometry}));
  await send('Browser.close');
} finally {
  socket?.close();
  if (child.exitCode === null) child.kill();
}
