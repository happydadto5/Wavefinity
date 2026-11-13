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
| Old Web Service name | _read from dashboard_ |
| Old Web Service hostname (`*.onrender.com`) | _read from dashboard_ |
| Commit the old service was last deployed from (dashboard → Events) | _read from dashboard_ |
| New Static Site name and hostname | _read from dashboard_ |
| Cutover date and who authorized it | _fill in_ |
| Exact DNS values before the change | _private Help-Code record only_ |

## Rolling back

1. In Render, attach `wavefinity.org` and `www` to the old Web Service again (detach from the Static Site
   first if Render requires it).
2. In Porkbun, restore the records to the values saved in the private Help-Code record.
3. Wait for DNS and the HTTPS certificate; confirm the old service answers.
4. If the old service was suspended, resume it from its dashboard, and redeploy the commit recorded above.

User files are unaffected either way: they live in each user's own Space folder on their PC, and a hosting or DNS
change neither uploads nor restores them.
