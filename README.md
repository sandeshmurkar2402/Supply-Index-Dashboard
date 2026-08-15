# Supply Index Dashboard

A static dashboard for the **Supply_Index_Dashboard** tab of the Supply Index
Google Sheet, covering the three business lines — Group Online, Group Offline,
and 1:1 Sessions — plus 1:1 slot supply, category/leader breakdowns, and page
views. Tabs: Today (default), Yesterday, This Week, This Month, and a custom
date range. Deployed as a static site (e.g. GitHub Pages); no server required
to view it.

## How data flows

1. `scripts/fetch.py` reads the `Supply_Index_Dashboard` sheet via a Google
   service account and writes `data/supply_index.json`.
2. `.github/workflows/update-data.yml` runs `fetch.py` on a schedule (hourly)
   and on manual `workflow_dispatch`, committing the refreshed JSON.
3. `index.html` fetches `data/supply_index.json` on load and on Refresh.
   If a viewer has saved a GitHub fine-grained PAT (via the gear icon —
   `Actions: Read and write` on this repo), Refresh instead triggers the
   workflow directly and waits for it to finish before reloading, so the
   click pulls live data from the sheet rather than waiting for the next
   scheduled sync. The token is stored only in that browser's `localStorage`
   — it is never sent anywhere but the GitHub API, and never committed.

## Local development

```
pip install -r requirements.txt
python scripts/fetch.py      # needs cred1.json (service account key) in this folder — gitignored
python server.py             # serves the dashboard at http://localhost:8080
                              # its /api/refresh endpoint re-runs fetch.py on demand
```

## Deployment setup

1. Create the GitHub repo and push this folder (`cred1.json` is gitignored —
   never commit it).
2. Add a repo secret `GOOGLE_CREDENTIALS`: base64 of the service account JSON —
   `base64 -w0 cred1.json` (Linux/Git Bash) or
   `[Convert]::ToBase64String([IO.File]::ReadAllBytes("cred1.json"))` (PowerShell).
3. Enable GitHub Pages for the repo (serve from the `main` branch root).
4. Update the `GH_REPO` constant near the top of `index.html`'s `<script>`
   if the repo name/owner differs from `sandeshmurkar2402/Supply-Index-Dashboard`.
5. Share the Google Sheet with the service account's `client_email`
   (found in `cred1.json`) as Viewer, if not already shared.
