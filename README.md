# MGT 160 Pilot

Behavioral economics pilot for UCSD MGT 160. A single-page web app randomizes participants into a 2×2 (hyped vs. neutral headline × social proof vs. no social proof), captures a $1,000 portfolio allocation between a Treasury bond (5% guaranteed) and a fictional ETF (HLXE, uniform −25% to +25%), reveals a real-money outcome, and logs everything to a Google Sheet via Google Apps Script.

For the full experiment design — research question, manipulations, outcomes, subgroups, participant flow — see [EXPERIMENT.md](EXPERIMENT.md).

## Repo layout

- `index.html` — the participant-facing single-page experiment.
- `apps-script.gs` — Apps Script endpoint code. Two handlers: `doPost` writes a 17-column row to the bound Sheet; `doGet` returns the next block-randomized condition based on current Sheet counts.
- `test.html` — minimal pipeline test page (one button, posts a dummy row). Used to verify the Apps Script write path before touching the experiment UI.
- `EXPERIMENT.md` — experiment design doc (research question, manipulations, flow, deviations from original proposal).
- `README.md` — this file.

## Data pipeline

**Write path (POST):** the participant page POSTs a JSON body as `Content-Type: text/plain;charset=utf-8` to the deployed Apps Script Web App URL. `text/plain` is used deliberately — it counts as a CORS "simple" request and avoids the `OPTIONS` preflight that Apps Script doesn't handle. The script reads the raw body via `e.postData.contents`, parses it, and appends a row.

**Read path (GET):** the page fetches its assigned condition from the same `/exec` URL on the Begin click. The Apps Script `doGet` reads the Sheet's `condition` column, counts entries per cell, and returns the smallest cell (with a uniform random tiebreak). This implements block randomization to keep the 4 cells balanced within ±1 throughout data collection. If the GET fails, the client falls back to local `Math.random()`.

## Google Sheet schema

Sheet ID: `19QtzOEEPzBWAlKqUqExDVD4TQXQqm8qz5U1_ZM-OG1k`. Row 1 must contain these column headers, in this order, left to right (A through Q):

```
timestamp	condition	headline_type	social_proof	safe_allocation	hlxe_allocation	hlxe_return	final_portfolio	confidence	prior_investor	age	gender	year_in_school	major_area	time_on_page_seconds	time_to_submit_seconds	venmo_handle
```

(Values are tab-separated — copy the line above and paste into A1; Sheets splits across columns automatically.)

The column order in the Sheet **must match** the `COLUMNS` array in `apps-script.gs`. The script writes rows positionally, not by header name. The `safe_allocation` field name is preserved for analysis stability even though the user-facing label is now "Treasury bond" rather than "Safe."

## Apps Script deployment

1. Open the bound Sheet.
2. **Extensions → Apps Script** — opens a new project bound to the Sheet.
3. Replace the default `Code.gs` with the contents of [apps-script.gs](apps-script.gs). Save.
4. **Deploy → New deployment.**
5. Type: **Web app**.
6. Configure: **Execute as = Me**, **Who has access = Anyone**.
7. **Deploy**. Authorize when prompted (Advanced → Go to {project} (unsafe) → Allow on first deploy).
8. Copy the `.../exec` Web App URL.
9. Paste it into [index.html](index.html) and [test.html](test.html), replacing the `ENDPOINT_URL` constant.

To redeploy after editing the script, use **Deploy → Manage deployments → pencil icon → Version: New version → Deploy**. This keeps the same `/exec` URL. Choosing "New deployment" instead generates a fresh URL and breaks the live page.

## Pipeline test

1. Open `test.html` in a browser (locally or via the deployed URL).
2. Click **Send Test Row**.
3. Confirm a row appears in the Sheet with the dummy values. Delete the test row before launch.

CORS errors on the test usually mean the deployment was set to "Only myself" instead of "Anyone." Re-deploy to fix.

## Deployment

The participant page is deployed at **https://mgt-160-pilot.vercel.app** (Vercel auto-deploys on every push to `main`).

Alternative: GitHub Pages off the same repo also works (`Settings → Pages → Branch: main / root`). The site would then be at `https://fadibatshon01.github.io/mgt-160-pilot/`.

Send only the production URL to participants; do not share the GitHub repo URL itself, which would let participants read the source and figure out the conditions.

## QA

- `?condition=N` URL parameter (where N ∈ {1,2,3,4}) overrides the server-balanced assignment and forces a specific condition. Used for QA to verify all four conditions render correctly. Should *not* appear in URLs sent to participants.
- Hitting `https://script.google.com/macros/s/.../exec` directly in a browser triggers a `doGet` and returns the current Sheet counts as JSON — useful for monitoring cell balance during data collection.
