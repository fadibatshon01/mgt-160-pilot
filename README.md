# MGT 160 Pilot

Behavioral economics experiment for UCSD MGT 160. Participants are randomized into one of four conditions (2×2: hyped vs. neutral headline × social proof vs. no social proof), allocate a hypothetical $1,000 portfolio between a guaranteed-8% Safe asset and a fictional ETF (HLXE) with random returns, then see their outcome. Top 3 final portfolio values win Venmo prizes ($20 / $15 / $5). All decisions and metadata are logged to a Google Sheet via a Google Apps Script web app.

## Repo layout

- `apps-script.gs` — Apps Script endpoint code. Paste into Apps Script bound to the Sheet.
- `test.html` — minimal page with one button that POSTs a dummy row to the endpoint. Used to verify the data pipeline before building the experiment UI.
- `index.html` — (Phase 2) the actual experiment.

## Data pipeline

The page POSTs a JSON body as `text/plain;charset=utf-8` to the deployed Apps Script Web App URL. `text/plain` is used deliberately — it counts as a CORS "simple" request and avoids the preflight `OPTIONS` call that Apps Script doesn't handle. The Apps Script `doPost` function reads the raw body from `e.postData.contents`, parses it as JSON, and appends a row to the first sheet of the bound spreadsheet.

## Google Sheet column headers

Paste these into row 1 of the bound Sheet (Sheet ID `19QtzOEEPzBWAlKqUqExDVD4TQXQqm8qz5U1_ZM-OG1k`), in order, left to right:

```
timestamp	condition	headline_type	social_proof	safe_allocation	hlxe_allocation	hlxe_return	final_portfolio	confidence	prior_investor	age	gender	year_in_school	major_area	time_on_page_seconds	time_to_submit_seconds	venmo_handle
```

(The values are tab-separated — copy the line above and paste into cell A1; Sheets will split it across columns.)

The column order in the Sheet **must match** the `COLUMNS` array in `apps-script.gs`. The script writes rows positionally, not by header name.

## Apps Script deployment

1. Open the bound Google Sheet in your browser.
2. **Extensions → Apps Script** — this opens a new Apps Script project bound to the Sheet.
3. Delete the default `Code.gs` content and paste the contents of `apps-script.gs` from this repo.
4. Save (cmd+S). Name the project something like "MGT 160 Pilot Endpoint".
5. Click **Deploy → New deployment**.
6. Click the gear icon next to "Select type" and choose **Web app**.
7. Configure:
   - **Description:** `pilot v1` (or any label)
   - **Execute as:** *Me (your account)*
   - **Who has access:** *Anyone*
8. Click **Deploy**.
9. Google will prompt for permissions on first deploy:
   - Click **Authorize access**, pick your account.
   - You'll see a "Google hasn't verified this app" warning — this is expected for personal Apps Script projects. Click **Advanced**, then **Go to {project name} (unsafe)**.
   - Grant the requested permissions (it needs to read/write the bound spreadsheet).
10. Copy the **Web app URL** that appears (ends in `/exec`). This is `ENDPOINT_URL`.

If you redeploy after editing the script, use **Deploy → Manage deployments → edit (pencil icon) → Version: New version → Deploy** to keep the same URL. Choosing "New deployment" instead generates a fresh URL.

## Pipeline test

1. Paste your deployed Web App URL into `test.html` — replace `PASTE_YOUR_APPS_SCRIPT_WEB_APP_URL_HERE` with the `/exec` URL.
2. Open `test.html` locally (double-click in Finder, or push to GitHub Pages and open).
3. Click **Send Test Row**.
4. You should see "Success — row appended to Sheet." Check the Sheet for a new row with the dummy values.

If you see a CORS error, the most common cause is that the Web App was deployed with "Who has access: Only myself" instead of "Anyone". Re-deploy.

If you see a 401 or "page not found", the URL likely has a typo or the deployment was deleted.

## GitHub Pages deployment

After Phase 2 is built and `index.html` exists:

1. Push to `main` on `https://github.com/fadibatshon01/mgt-160-pilot`.
2. **Settings → Pages → Source:** Deploy from a branch → `main` / root → Save.
3. The site will be live at `https://fadibatshon01.github.io/mgt-160-pilot/` within ~1 minute.
