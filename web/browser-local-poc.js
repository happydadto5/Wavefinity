const $ = id => document.getElementById(id);
let worker, epoch = 0, sequence = 0, current = 0, report = {}, stlURL;
function clearSTL() {
  if (stlURL) URL.revokeObjectURL(stlURL);
  stlURL = undefined;
  $('stl').hidden = true;
  $('stl').removeAttribute('href');
}
function show() { $('report').textContent = JSON.stringify(report, null, 2); }
function stop() {
  epoch++;
  worker?.terminate(); worker = undefined;
  clearSTL(); report = {}; show();
  $('load').disabled = false;
  for (const id of ['build', 'offline', 'cancel', 'download']) $(id).disabled = true;
}
function build(offline) {
  clearSTL();
  current = ++sequence;
  $('status').textContent = offline ? 'Building with worker network blocked…' : 'Building in browser memory…';
  worker.postMessage({type: 'build', id: current, offline, spec: {x: 42, y: 42, z: 28}});
}
$('load').onclick = () => {
  stop();
  const token = epoch;
  $('load').disabled = true; $('cancel').disabled = false;
  $('status').textContent = 'Loading browser tools…';
  worker = new Worker('browser-local-poc-worker.js', {type: 'module'});
  worker.onerror = event => {
    if (token !== epoch) return;
    report.failure = event.message; report.poc_success = false; show();
    $('status').textContent = 'Loader failed. See report.';
    $('download').disabled = false; $('load').disabled = false;
  };
  worker.onmessage = ({data}) => {
    if (token !== epoch || (data.id !== undefined && data.id !== current)) return;
    if (data.type === 'progress') { $('status').textContent = data.message; return; }
    report = {...report, ...data.report, browser: navigator.userAgent}; show();
    $('download').disabled = false;
    if (data.type === 'ready') {
      $('build').disabled = false; $('offline').disabled = false;
      $('status').textContent = 'Tools loaded. Ready for the ordinary bin.';
    } else if (data.type === 'result') {
      $('status').textContent = report.poc_success ? 'Bin passed all comparisons.' : 'Full bin failed. See exact component below.';
      if (report.poc_success && data.stl) {
        stlURL = URL.createObjectURL(new Blob([data.stl], {type: 'model/stl'}));
        $('stl').href = stlURL; $('stl').hidden = false;
      }
    } else if (data.type === 'failure') {
      $('status').textContent = 'Loader failed. See report.'; $('load').disabled = false;
    }
  };
  worker.postMessage({type: 'load'});
};
$('build').onclick = () => build(false);
$('offline').onclick = () => build(true);
$('cancel').onclick = () => { stop(); $('status').textContent = 'Cancelled. Memory and results cleared.'; };
$('download').onclick = () => {
  const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], {type: 'application/json'}));
  const link = document.createElement('a'); link.href = url; link.download = 'wavefinity-browser-report.json'; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
addEventListener('pagehide', stop);
