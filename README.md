# Actblue-Refunds

Pulls refund data from multiple ActBlue entities/committees via ActBlue's
CSV API and combines it into one spreadsheet, so refunds don't have to be
checked account-by-account in the ActBlue dashboard.

## How it works

ActBlue's [CSV API](https://secure.actblue.com/docs) generates reports
asynchronously per entity: this tool requests a `refunded_contributions`
report for each configured account and date range, polls until it's ready,
downloads it, and combines every account's rows into one workbook with:

- **All Refunds** — every row from every account, tagged with an `account` column
- **Summary by Account** — refund count and total per account
- **Summary by Month** — refund count and total per account, per month

It also writes a self-contained HTML **dashboard** (no external dependencies,
safe to open offline) alongside the workbook: stat tiles, a total-refunded-by-client
chart, a refunds-by-month chart stacked by client, and a searchable/sortable table
of every individual refund. It contains the same donor-level detail as the
"All Refunds" sheet (name, email, address, employer, etc.), so handle it with the
same care as the underlying export.

## Setup

1. For each ActBlue entity, generate a Client UUID/Secret pair for the CSV
   API: on that entity's ActBlue dashboard, go to **Settings → CSV API**
   and follow ActBlue's instructions to request access and generate
   credentials. (This is separate from your ActBlue login and from
   webhooks — it's the API used for pulling historical CSV reports.)

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Copy `accounts.example.yaml` to `accounts.yaml` and list every account:

   ```yaml
   accounts:
     - key: campaign_a
       name: "Campaign A for Congress"
     - key: campaign_b
       name: "Campaign B Committee"
   ```

4. Copy `.env.example` to `.env` and fill in each account's credentials,
   named after its `key`:

   ```
   ACTBLUE_CAMPAIGN_A_CLIENT_UUID=...
   ACTBLUE_CAMPAIGN_A_CLIENT_SECRET=...
   ```

   `accounts.yaml` and `.env` are gitignored since `.env` holds secrets —
   don't commit real credentials.

## Usage

```bash
python track_refunds.py --start 2026-01-01 --end 2026-08-24 --out refunds_combined.xlsx
```

- `--start` is inclusive, `--end` is exclusive (both `YYYY-MM-DD`), matching
  ActBlue's API. ActBlue rejects ranges longer than 6 months, so for a longer
  history run this multiple times over shorter windows.
- If an account's report fails to generate, that account is skipped with an
  error printed to stderr, and the report is built from the remaining
  accounts.
- The HTML dashboard is written next to `--out` by default (same path with a
  `.html` extension); override with `--dashboard-out`, or skip it entirely
  with `--no-dashboard`.

## Notes

- ActBlue's exact CSV column names for `refunded_contributions` aren't
  hard-coded here (they aren't publicly guaranteed to be stable); the
  summary sheets auto-detect an amount and a date column by name. If that
  detection fails, the **All Refunds** sheet still has the complete raw
  data, and a **Summary** sheet explains why the roll-ups were skipped.
- CSV generation can take anywhere from a few seconds to a couple of
  minutes depending on the date range and account size; the client polls
  every 2 seconds for up to 5 minutes per account before giving up.

## Tests

```bash
pip install pytest
pytest
```
