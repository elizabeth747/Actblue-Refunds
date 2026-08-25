import argparse
import io
import sys

import pandas as pd
from dotenv import load_dotenv

from actblue_refunds.accounts import MissingCredentialsError, load_accounts
from actblue_refunds.client import ActBlueAPIError, ActBlueClient
from actblue_refunds.dashboard import write_dashboard
from actblue_refunds.report import write_report


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Combine ActBlue refund data across multiple accounts.")
    parser.add_argument("--start", required=True, help="Start date, inclusive, YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date, exclusive, YYYY-MM-DD")
    parser.add_argument("--config", default="accounts.yaml", help="Path to accounts config file")
    parser.add_argument("--out", default="refunds_combined.xlsx", help="Output spreadsheet path")
    parser.add_argument(
        "--dashboard-out",
        default=None,
        help="Output HTML dashboard path (default: --out with a .html extension)",
    )
    parser.add_argument("--no-dashboard", action="store_true", help="Skip generating the HTML dashboard")
    return parser.parse_args(argv)


def main(argv=None):
    load_dotenv()
    args = parse_args(argv)

    try:
        accounts = load_accounts(args.config)
    except MissingCredentialsError as e:
        sys.exit(str(e))

    if not accounts:
        sys.exit(f"No accounts configured in {args.config}")

    frames = []
    for account in accounts:
        print(f"Fetching refunds for {account['name']}...")
        client = ActBlueClient(account["client_uuid"], account["client_secret"])
        try:
            csv_text = client.get_refunded_contributions(args.start, args.end)
        except (ActBlueAPIError, TimeoutError) as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            continue

        df = pd.read_csv(io.StringIO(csv_text))
        df.insert(0, "account", account["name"])
        frames.append(df)
        print(f"  {len(df)} refunded contribution(s)")

    if not frames:
        sys.exit("No refund data retrieved for any account.")

    combined = pd.concat(frames, ignore_index=True, sort=False)
    write_report(combined, args.out)
    print(f"\nWrote combined report for {len(frames)} account(s), {len(combined)} refund(s) to {args.out}")

    if not args.no_dashboard:
        dashboard_out = args.dashboard_out or _default_dashboard_path(args.out)
        write_dashboard(combined, dashboard_out, start=args.start, end=args.end)
        print(f"Wrote dashboard to {dashboard_out}")


def _default_dashboard_path(out_path):
    if out_path.lower().endswith(".xlsx"):
        return out_path[: -len(".xlsx")] + ".html"
    return out_path + ".html"


if __name__ == "__main__":
    main()
