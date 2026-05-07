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

function doGet() {
  return jsonResponse({ status: 'ok', message: 'MGT 160 pilot endpoint is live' });
}

function jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
