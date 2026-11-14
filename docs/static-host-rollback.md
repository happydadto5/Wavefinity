# Static host rollback record

Fill this in **before** the old Render Web Service is retired (B15), and keep it. Rolling back means pointing
`wavefinity.org` and `www` at the old Python Web Service again. The service stays in place, unchanged, until
Andrew authorizes retiring it. Its code and settings are described in
[legacy-python-server-hosting.md](legacy-python-server-hosting.md); `render.yaml` and the `Dockerfile` are
unchanged.

## Record to complete at cutover

Read each value from the Render dashboard or the private Help-Code record at that time. Do not guess, and do not
copy DNS record values into this public file.

| Item | Value |
|---|---|
| Old Web Service name | `wavefinity` (per `render.yaml`; confirm in dashboard) |
| Old Web Service hostname (`*.onrender.com`) | `wavefinity.onrender.com` (per the legacy hosting record; confirm in dashboard) |
| Commit the old service was last deployed from (dashboard → Events) | _read from dashboard_ |
| New Static Site name and hostname | `wavefinity-static` / `wavefinity-static.onrender.com` |
| Cutover date and who authorized it | _fill in_ |
| Exact DNS values before the change | _private Help-Code record only_ |

## Rolling back

Do these in order. The old service must be proven working **before** the domain is pointed at it, otherwise
visitors land on a service that is asleep, suspended or running the wrong code.

1. Make the old Web Service ready first. If it was suspended, resume it from its dashboard. Deploy the
   **commit recorded above** using Render's Manual Deploy of that specific commit. Do not use "Deploy latest
   commit": `main` has moved on since the cutover and is not the recorded recovery source. The service's
   auto-deploy is off, so nothing deploys by itself.
2. Open the old service's own `*.onrender.com` address (recorded above) and confirm the app loads and a bin
   previews. A free-plan service can take about a minute to wake. Do not continue until this works.
3. In Render, attach `wavefinity.org` and `www` to the old Web Service again (detach them from the Static Site
   first if Render requires it).
4. In Porkbun, restore the records to the values saved in the private Help-Code record.
5. Wait for DNS and the HTTPS certificate; confirm `wavefinity.org` now shows the old service.

This rollback can only be carried out while the "commit the old service was last deployed from" row above is
filled in and the old Web Service still exists. Until that row is filled, the record is incomplete and the old
service must not be retired.

User files are unaffected either way: they live in each user's own Space folder on their PC, and a hosting or DNS
change neither uploads nor restores them.
