/**
 * ActBlue refund webhook receiver, bound to the "Meta Ad Report" spreadsheet.
 *
 * Deploy this as a Web App (Deploy > New deployment > Web app). Register the
 * resulting URL as an "ActBlue Default Refunds" webhook - because the webhook
 * event type is chosen at registration, every call this script receives is a
 * refund notification. It looks up which Facebook ad the refunded donation
 * came from (via the "Mapping" tab) and appends one row per refunded line
 * item to the "Refund Log" tab.
 *
 * Payload shape (confirmed against ActBlue's docs example):
 *   {
 *     "contribution": { "orderNumber", "createdAt", "refcodes": { "refcode", "refcodeCustom", "refcode2" }, ... },
 *     "lineitems": [ { "committeeName", "amount", "refundedAt", "lineitemId", ... }, ... ],
 *     "donor": {...},
 *     "form": {...}
 *   }
 * A single order can have multiple line items (e.g. split/joint contributions
 * across committees); only the ones with a non-null "refundedAt" are refunds.
 *
 * Auth note: ActBlue's webhook form sends credentials as HTTP Basic Auth
 * (Username/Password), but Apps Script web apps cannot read incoming HTTP
 * headers - there is no way to verify a Basic Auth header here. Instead,
 * put a long random secret in the Endpoint URL's query string (e.g.
 * ".../exec?token=SECRET") and set that same value via setWebhookToken().
 * The Username/Password fields on ActBlue's form still need something
 * entered (required fields) but are not checked by this script.
 *
 * ActBlue recommends acknowledging receipt (200 response) before doing any
 * heavy processing, since backfills/high-volume periods can send many
 * requests quickly - this script's per-request work is a couple of small
 * spreadsheet reads/appends, which is cheap enough to do inline.
 *
 * Setup instructions: see SETUP.md in this repo.
 */

function doGet(e) {
  // Visiting the deployed URL in a browser sends a GET, not the POST ActBlue
  // sends - this just avoids an "error" page when someone checks the link.
  return ContentService.createTextOutput(
    'ActBlue refund webhook is live. Configure ActBlue to POST refund events to this URL.'
  ).setMimeType(ContentService.MimeType.TEXT);
}

const REFUND_LOG_SHEET = 'Refund Log';
const MAPPING_SHEET = 'Mapping';
const REFUND_LOG_HEADERS = [
  'Received At',
  'Contribution Date',
  'Refunded At',
  'Account (Committee)',
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
    logRow_(
      { contributionDate: '', refundedAt: '', account: '', refcode: '', amount: '', orderNumber: '' },
      'REJECTED: bad or missing token',
      rawBody
    );
    return jsonResponse_({ status: 'unauthorized' });
  }

  try {
    const payload = JSON.parse(rawBody);
    const refunds = extractRefundedLineItems_(payload);

    if (refunds.length === 0) {
      logRow_(
        { contributionDate: (payload.contribution || {}).createdAt || '', refundedAt: '', account: '', refcode: '', amount: '', orderNumber: (payload.contribution || {}).orderNumber || '' },
        'NO LINE ITEM MARKED REFUNDED',
        rawBody
      );
    } else {
      refunds.forEach(function (refund) {
        logRow_(refund, '', rawBody);
      });
    }

    return jsonResponse_({ status: 'ok' });
  } catch (err) {
    logRow_(
      { contributionDate: '', refundedAt: '', account: '', refcode: '', amount: '', orderNumber: '' },
      'ERROR: ' + err.message,
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

/**
 * Returns one entry per refunded line item: { contributionDate, refundedAt,
 * account, refcode, amount, orderNumber }.
 */
function extractRefundedLineItems_(payload) {
  const contribution = payload.contribution || {};
  const refcodes = contribution.refcodes || {};
  const refcode = firstDefined_(refcodes.refcode, refcodes.refcodeCustom, refcodes.refcode2) || '';
  const lineitems = payload.lineitems || [];

  return lineitems
    .filter(function (li) { return !!li.refundedAt; })
    .map(function (li) {
      return {
        contributionDate: contribution.createdAt || '',
        refundedAt: li.refundedAt || '',
        account: li.committeeName || '',
        refcode: refcode,
        amount: li.amount || '',
        orderNumber: contribution.orderNumber || '',
      };
    });
}

function firstDefined_() {
  for (let i = 0; i < arguments.length; i++) {
    const v = arguments[i];
    if (v !== undefined && v !== null && v !== '') return v;
  }
  return null;
}

function logRow_(refund, matchStatusOverride, rawBody) {
  // Multiple ActBlue accounts can point at this same webhook (e.g. several
  // client committees), so concurrent calls are expected - especially during
  // a backfill, which can burst many requests at once. Serialize the
  // read-then-append below so two simultaneous calls can't collide on the
  // same row.
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = getOrCreateRefundLogSheet_(ss);
    const refcode = (refund.refcode || '').toString().trim();
    const fbAdName = lookupAdName_(ss, refcode);

    const matchStatus =
      matchStatusOverride ||
      (fbAdName ? 'MATCHED' : refcode ? 'NO MATCH FOUND IN MAPPING TAB' : 'NO REFCODE ON PAYLOAD');

    sheet.appendRow([
      new Date(),
      refund.contributionDate || '',
      refund.refundedAt || '',
      refund.account || '',
      refcode,
      fbAdName,
      refund.amount || '',
      refund.orderNumber || '',
      matchStatus,
      rawBody,
    ]);
  } finally {
    lock.releaseLock();
  }
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
  if (!refcode) return '';
  const mappingSheet = ss.getSheetByName(MAPPING_SHEET);
  if (!mappingSheet) return '';

  const data = mappingSheet.getDataRange().getValues();
  // Expects header row: Ad Name in FB | Ad Name in Refcode | Account
  for (let i = 1; i < data.length; i++) {
    const fbName = data[i][0];
    const refcodeInSheet = (data[i][1] || '').toString().trim();
    if (refcodeInSheet && refcodeInSheet.toLowerCase() === refcode.toLowerCase()) {
      return fbName;
    }
  }
  return '';
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

/**
 * Optional: paste ActBlue's example refund payload here and run this function
 * from the Apps Script editor to sanity-check extraction logic without
 * needing a live webhook call.
 */
function testWithSamplePayload() {
  const sample = {
    contribution: {
      createdAt: '2019-01-18T20:44:25-05:00',
      orderNumber: 'AB00000000',
      refcodes: { refcode: 'r1', refcode2: 'r2', refcodeCustom: 'r3' },
    },
    lineitems: [
      {
        committeeName: 'LoremIpsum for Congress',
        amount: '25.9',
        refundedAt: '2017-10-03T13:48:26-04:00',
        lineitemId: 99999999,
      },
    ],
  };
  Logger.log(JSON.stringify(extractRefundedLineItems_(sample), null, 2));
}
