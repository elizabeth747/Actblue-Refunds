# Setup: ActBlue refund → Meta Ad Report

This wires ActBlue's refund webhook into the "Meta Ad Report" Google Sheet.
When ActBlue reports a refund, a Google Apps Script bound to the sheet looks
up which Facebook ad the original donation came from (via the "Mapping" tab)
and appends a row to a new "Refund Log" tab.

## 1. Add the script to the spreadsheet

1. Open the **Meta Ad Report** spreadsheet.
2. **Extensions > Apps Script**.
3. Delete the placeholder `myFunction() {}` code and paste in the contents
   of [`google-apps-script/Code.gs`](google-apps-script/Code.gs) from this repo.
4. Save the project (give it a name if prompted, e.g. "Refund Webhook").

## 2. Set your webhook secret

Apps Script web apps can't read incoming HTTP headers, so ActBlue's
Username/Password Basic Auth fields can't actually be verified here. Instead
we use a secret token in the URL's query string, which Apps Script *can* read.

1. In `Code.gs`, find `setWebhookToken()` near the bottom and replace
   `'REPLACE_WITH_A_LONG_RANDOM_STRING'` with a long random string of your
   choosing (e.g. generate one with `openssl rand -hex 24` or any password
   generator). Keep it secret - treat it like a password.
2. In the Apps Script editor toolbar, select `setWebhookToken` from the
   function dropdown and click **Run**. Approve the permissions prompt
   (first run only) - this lets the script read/write the spreadsheet.
3. You can revert your edit to the placeholder string afterward if you'd
   rather not leave the real secret sitting in the script source; the value
   is now stored separately in Script Properties either way.

## 3. Deploy as a Web App

1. **Deploy > New deployment**.
2. Type: **Web app**.
3. Execute as: **Me**.
4. Who has access: **Anyone** (required - ActBlue isn't a logged-in Google
   user. The secret token from step 2 is what keeps this from being abused).
5. Click **Deploy**, authorize if prompted, and copy the **Web app URL**.

## 4. Register the webhook in ActBlue

In ActBlue's "Create a New Webhook" form:

- **Webhook event type**: ActBlue Default Refunds
- **Webhook name**: anything, e.g. "Meta Ad Report Refund Log"
- **Endpoint URL**: `<your Web app URL>?token=<the secret from step 2>`
- **Username**: anything (required by the form, not checked by this script)
- **Password**: anything (same as above)

Save it.

## 5. Test it

1. Use ActBlue's **Webhook Simulator** (`/webhook_simulations/new` in your
   ActBlue dashboard) to send a mock refund payload to your endpoint URL.
   Note the data it sends is fake/mock data (e.g. a donor named "Refunded
   Jack") - it's only there to confirm the pipe works end to end, not to
   validate real numbers. Remove that test row from the Refund Log once
   confirmed.
2. Open the **Refund Log** tab (created automatically on first event) in the
   spreadsheet and check the row that shows up. The **Raw Payload** column
   contains the exact JSON ActBlue sent.
3. If **FB Ad Name** shows "NO MATCH FOUND IN MAPPING TAB" or the row's Match
   Status looks off, paste that row's Raw Payload value back to Claude -
   `extractRefundedLineItems_()` in `Code.gs` is built against ActBlue's
   documented payload shape but may need a tweak for edge cases (e.g. a
   refcode stored somewhere unexpected, or a committee name that doesn't
   match the Mapping tab's Account column).

## 6. Optional: backfill past refunds

If you want history for refunds that already happened before this webhook
existed, ActBlue can send those too - request a "backfill" date when you
register the webhook (or contact ActBlue support afterward). Backfills can
arrive as a large burst of requests; the script handles that fine since each
call is a quick, independent spreadsheet append.

## 7. Optional: roll up refunds on the Dashboard tab

Rather than auto-editing your live Dashboard formulas, here's a formula you
can paste yourself into a new "Refunded" column next to the per-ad table,
assuming that table's Ad Name column is `A` and Refund Log's FB Ad Name/Refund
Amount columns are `F`/`G`:

```
=SUMIFS('Refund Log'!G:G, 'Refund Log'!F:F, A2)
```

Adjust the row/column references to match wherever you add it.
