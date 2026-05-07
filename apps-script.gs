/**
 * MGT 160 Pilot — Apps Script endpoint
 *
 * Receives JSON-encoded participant data from the experiment page
 * and appends a single row to the bound Google Sheet.
 *
 * Deploy as a Web App: Execute as = me, Who has access = Anyone.
 */

const SHEET_ID = '19QtzOEEPzBWAlKqUqExDVD4TQXQqm8qz5U1_ZM-OG1k';

const COLUMNS = [
  'timestamp',
  'condition',
  'headline_type',
  'social_proof',
  'safe_allocation',
  'hlxe_allocation',
  'hlxe_return',
  'final_portfolio',
  'confidence',
  'prior_investor',
  'age',
  'gender',
  'year_in_school',
  'major_area',
  'time_on_page_seconds',
  'time_to_submit_seconds',
  'venmo_handle'
];

function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return jsonResponse({ status: 'error', message: 'No POST body received' });
    }

    const data = JSON.parse(e.postData.contents);

    const sheet = SpreadsheetApp.openById(SHEET_ID).getSheets()[0];

    const row = COLUMNS.map(function (key) {
      if (key === 'timestamp') {
        return data.timestamp || new Date().toISOString();
      }
      return data[key] === undefined ? '' : data[key];
    });

    sheet.appendRow(row);

    return jsonResponse({ status: 'success', row: row });
  } catch (err) {
    return jsonResponse({ status: 'error', message: String(err) });
  }
}

/**
 * GET handler — assigns the next participant's condition (1–4) using
 * block randomization. Reads completed rows in the Sheet, counts how
 * many of each condition have been recorded, and returns the condition
 * with the fewest entries (random tiebreak when several are tied).
 *
 * The client (index.html) calls this on the Begin click and falls back
 * to local Math.random() if the request fails.
 */
function doGet(e) {
  try {
    const sheet = SpreadsheetApp.openById(SHEET_ID).getSheets()[0];
    const lastRow = sheet.getLastRow();

    const counts = { 1: 0, 2: 0, 3: 0, 4: 0 };

    if (lastRow >= 2) {
      const conditionCol = COLUMNS.indexOf('condition') + 1; // 1-indexed
      const values = sheet.getRange(2, conditionCol, lastRow - 1, 1).getValues();
      for (let i = 0; i < values.length; i++) {
        const c = parseInt(values[i][0], 10);
        if (c >= 1 && c <= 4) counts[c] += 1;
      }
    }

    // Find the lowest count.
    let min = Infinity;
    for (const k in counts) if (counts[k] < min) min = counts[k];

    // Candidates = all conditions tied for the lowest count.
    const candidates = [];
    for (const k in counts) if (counts[k] === min) candidates.push(parseInt(k, 10));

    // Random tiebreak.
    const condition = candidates[Math.floor(Math.random() * candidates.length)];

    return jsonResponse({ status: 'ok', condition: condition, counts: counts });
  } catch (err) {
    return jsonResponse({ status: 'error', message: String(err) });
  }
}

function jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
