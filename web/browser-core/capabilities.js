// B13 window-side routes. B14 imports this map into the local dispatcher.
import { aiConnection, aiAsk } from './ai-providers.js';

export const BROWSER_NOTICE = 'Spaces and autosave need writable folder handles. In Firefox/Safari or another unsupported browser, use only temporary previews and Blob downloads; reload/close may lose unsaved work. Open this same site in Windows desktop Chrome/Edge and select the original folder, or import a Wavefinity Space/preferences export there. Folder handles and browser data do not transfer automatically between browsers, profiles or origins.';
export const SLICER_NOTICE = 'A browser cannot browse for or launch a slicer executable. Print prepares a 3MF download; open it yourself in Bambu Studio. Export remains available.';
export const LOG_NOTICE = 'There is no Wavefinity server log in the browser edition. Inventory is in your selected Space folder. Browser diagnostics are in Developer Tools; do not share API keys or request headers.';

export function suggestions(payload) {
  const kind = String(payload.kind || ''), title = String(payload.title || '').trim(), description = String(payload.description || '').trim();
  if (!['bug', 'suggestion'].includes(kind) || !title || title.length > 200 || !description || description.length > 8000) throw new Error('Choose a report type, title (up to 200 characters) and description (up to 8,000 characters).');
  return { local: true, text: `${kind}\n${title}\n\n${description}`, message: 'Suggestion prepared locally. Download or copy it; nothing was submitted online.' };
}

export function browseSlicerPath() { return { slicer_path: null, message: SLICER_NOTICE }; }
export function showLog() { return { file: null, message: LOG_NOTICE }; }

export const ROUTES = new Map([
  ['/api/ai/connection', aiConnection],
  ['/api/ai/ask', aiAsk],
  ['/api/suggestions', suggestions],
  ['/api/browse-slicer-path', browseSlicerPath],
  ['/api/show-log', showLog],
]);
