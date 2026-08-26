/**
 * ActBlue refund webhook receiver, bound to the "Meta Ad Report" spreadsheet.
 *
 * Deploy this as a Web App (Deploy > New deployment > Web app). ActBlue POSTs
 * refund events to the resulting URL; this script looks up which Facebook ad
 * the refunded donation came from (via the "Mapping" tab) and appends a row
 * to the "Refund Log" tab.
 *
 * Setup instructions: see SETUP.md in this repo.
 */

const REFUND_LOG_SHEET = 'Refund Log';
const MAPPING_SHEET = 'Mapping';
const REFUND_LOG_HEADERS = [
  'Received At',
  'Refund/Contribution Date',
  'Account',
  'Refcode',
  'FB Ad Name',
  'Refund Amount',
  'Order Number',
  'Match Status',
  'Raw Payload',
];

function doPost(e) {
  const rawBody = (e && e.postData) ? e.postData.contents : '';

  if (!isAuthorized_(e)) {
    logRefund_(
      { refcode: '', amount: '', orderNumber: '', contributionDate: '', matchStatus: 'REJECTED: bad or missing token' },
      rawBody
    );
    return jsonResponse_({ status: 'unauthorized' });
  }

  try {
    const payload = parsePayload_(rawBody);
    const refund = extractRefundFields_(payload);
    logRefund_(refund, rawBody);
    return jsonResponse_({ status: 'ok' });
  } catch (err) {
    logRefund_(
      { refcode: '', amount: '', orderNumber: '', contributionDate: '', matchStatus: 'ERROR: ' + err.message },
      rawBody
    );
    return jsonResponse_({ status: 'logged_with_error' });
  }
}

function isAuthorized_(e) {
  const expected = PropertiesService.getScriptProperties().getProperty('WEBHOOK_TOKEN');
  const provided = e && e.parameter && e.parameter.token;
  return !!expected && !!provided && expected === provided;
}

function parsePayload_(rawBody) {
  if (!rawBody) return {};
  try {
    return JSON.parse(rawBody);
  } catch (jsonErr) {
    // Not JSON. ActBlue's classic API can deliver XML - if that's what you're
    // seeing in the Raw Payload column, tell Claude and it'll add an XML
    // parser here instead of this fallback.
    return { __raw: rawBody };
  }
}

/**
 * TODO: this is a best-guess mapping of common ActBlue payload shapes.
 * Confirm it against a real refund payload (check the "Raw Payload" column
 * in the Refund Log after your first test webhook) and adjust the field
 * paths below to match exactly what ActBlue actually sends.
 */
function extractRefundFields_(payload) {
  const contribution = payload.contribution || payload;
  const refcodes = contribution.refcodes || {};

  const refcode = firstDefined_(refcodes.refcode, contribution.refcode, payload.refcode);
  const amount = firstDefined_(
    contribution.refund && contribution.refund.amount,
    contribution.amount,
    payload.amount
  );
  const orderNumber = firstDefined_(contribution.orderNumber, payload.orderNumber);
  const contributionDate = firstDefined_(
    contribution.refundedAt,
    contribution.createdAt,
    payload.date
  );

  return {
    refcode: refcode || '',
    amount: amount || '',
    orderNumber: orderNumber || '',
    contributionDate: contributionDate || '',
  };
}

function firstDefined_() {
  for (let i = 0; i < arguments.length; i++) {
    const v = arguments[i];
    if (v !== undefined && v !== null && v !== '') return v;
  }
  return null;
}

function logRefund_(refund, rawBody) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = getOrCreateRefundLogSheet_(ss);
  const refcode = (refund.refcode || '').toString().trim();
  const match = lookupAdName_(ss, refcode);

  const matchStatus =
    refund.matchStatus ||
    (match.fbAdName ? 'MATCHED' : refcode ? 'NO MATCH FOUND IN MAPPING TAB' : 'NO REFCODE ON PAYLOAD');

  sheet.appendRow([
    new Date(),
    refund.contributionDate || '',
    match.account || '',
    refcode,
    match.fbAdName || '',
    refund.amount || '',
    refund.orderNumber || '',
    matchStatus,
    rawBody,
  ]);
}

function getOrCreateRefundLogSheet_(ss) {
  let sheet = ss.getSheetByName(REFUND_LOG_SHEET);
  if (!sheet) {
    sheet = ss.insertSheet(REFUND_LOG_SHEET);
    sheet.appendRow(REFUND_LOG_HEADERS);
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function lookupAdName_(ss, refcode) {
  if (!refcode) return { fbAdName: '', account: '' };
  const mappingSheet = ss.getSheetByName(MAPPING_SHEET);
  if (!mappingSheet) return { fbAdName: '', account: '' };

  const data = mappingSheet.getDataRange().getValues();
  // Expects header row: Ad Name in FB | Ad Name in Refcode | Account
  for (let i = 1; i < data.length; i++) {
    const fbName = data[i][0];
    const refcodeInSheet = (data[i][1] || '').toString().trim();
    const account = data[i][2];
    if (refcodeInSheet && refcodeInSheet.toLowerCase() === refcode.toLowerCase()) {
      return { fbAdName: fbName, account: account };
    }
  }
  return { fbAdName: '', account: '' };
}

function jsonResponse_(obj) {
  // Apps Script web apps always answer HTTP 200; the outcome is in the body.
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

/**
 * Run this once manually from the Apps Script editor (pick this function from
 * the dropdown, click Run) after replacing the placeholder below with your
 * own long random string. Do not hardcode the real token anywhere else.
 */
function setWebhookToken() {
  const token = 'REPLACE_WITH_A_LONG_RANDOM_STRING';
  PropertiesService.getScriptProperties().setProperty('WEBHOOK_TOKEN', token);
}
