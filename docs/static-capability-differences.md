# Browser capabilities and recovery (B13)

B13 exports production components for the browser migration. B14 alone registers
`capabilities.js` in the window local API and `engine/ai_routes.py` in Python,
then assembles the complete static deployment. This package does not claim an
integrated or deployed browser edition.

AI Help retains prompt generation, request IDs, context fingerprints, candidate
proof through the canonical preview and Space-cap rules, repair prompts, manual
paste, Modify Current Bin and Generate as New Bin. Prompt and candidate payloads
share `wavefinity_web_impl/_ai.py` with the historical server entry points.
Browser Space context comes from folder inventory/metadata snapshots, retained
with the prompt session; a claimed Space descriptor alone is not authority.

## Optional browser-direct AI

Connection settings select OpenAI-compatible Chat Completions, Anthropic Messages
or Gemini generateContent. Only Test connection and Ask my AI invoke a provider;
Save and status do not. Requests use HTTPS, CORS, no cookies/referrer, no cache,
and `redirect: error`. Keys appear only in provider authorization headers, never
URLs, prompt messages, reports or stored preferences. Response errors use HTTP
status explanations without echoing untrusted response bodies or credentials.
Provider adapters return the same `{answer}` response shape.

The key lives in document session memory, with a Clear session key control.
Reload, navigation/close and BFCache pagehide clear it and abort pending provider
calls. Connection provider/name/base URL/model are the only saved AI settings;
preference import strips other AI fields. There is no remember-key feature.
Browser scripts, extensions and developer tools may expose a browser-used key.
Use a dedicated limited-billing key where the provider offers one; charges and
revocation belong to the provider account. No Wavefinity-owned key or proxy exists.

The user must confirm their provider permits browser access with their credential.
OpenAI-compatible calls use Bearer authorization; Anthropic uses `x-api-key`,
`anthropic-version` and explicit dangerous-browser-access consent; Gemini uses
`x-goog-api-key` in a header. Custom origins require a separate trust checkbox
bound to the entered endpoint; changing its URL clears that confirmation.
Same-site and Wavefinity domain endpoints are rejected. A custom endpoint also
needs that exact origin explicitly allowed by the deployment CSP; trust does not
bypass CSP, CORS or provider organization policy.

For B14, the default CSP `connect-src` must allow only `'self'`,
`https://api.openai.com`, `https://api.anthropic.com` and
`https://generativelanguage.googleapis.com` (plus any separately approved exact
custom origin). Never use a wildcard HTTPS allowance or add a proxy to bypass a
provider restriction. A browser cannot reliably distinguish CORS, CSP, redirect
and network failures; the UI says so. HTTP errors retain their status, including
credential, access/policy, endpoint/model and quota/billing failures. Manual
copy/paste remains available throughout, including after direct chat fails.

Invoking AI sends the selected prompt and design/Space descriptors to the chosen
provider. Geometry generation, meshes and folder files stay on the PC. Direct
chat does not upload files or mesh data. Copy/paste shares only what the user
chooses to paste into their external chat tool.

Provider protocol references:
[OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create),
[Anthropic browser authentication](https://platform.claude.com/docs/en/manage-claude/authentication),
[Gemini API](https://ai.google.dev/api).

## Other desktop differences

Suggestions become a local text download; no issue is posted and no credentials
are needed. Slicer browsing explains that a browser cannot locate or launch an
executable. Print still prepares its B08 multipart 3MF handoff for the user to open
in Bambu Studio; Export is retained. Show-log explains there is no server log:
Inventory is in the chosen folder and browser diagnostics are in Developer Tools.
Space show-folder remains owned by B09.

## Unsupported browsers and recovery

Startup gates Space routing before opening saved Spaces. New Space and Create
also gate before any creation; persistent-file primitives reject writes when
secure writable directory-handle APIs are absent. Ephemeral previews and Blob
downloads may still work; there is no Space autosave promise. Firefox/Safari
normally lack the required folder picker. Detection checks capabilities, not
browser names. Private modes, permissions and storage policy may restrict even a
supported browser.

Open the same site (`https://wavefinity.org` in production) in Windows desktop
Chrome/Edge and select the original folder. Or use **Space / preferences recovery**
from the Space header, About, or unsupported-browser notice. Export the current
Space or preferences as JSON. Restore a Space export into an empty selected
folder in a supported browser using B09's format, hashes, path checks, identity
rules and rollback. Then Open Space and select that folder. Preferences import
restores validated non-secret settings; reload applies all settings and a new
session key is needed for AI. Recovery does not overwrite a nonempty folder,
silently adopt a Space, or claim handles/browser data transfer between profiles,
browsers or origins. Browser-only records unavailable to this profile cannot be
exported here; use the originating browser or the original folder/export.
