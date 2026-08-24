"""Pull refunded_contributions from ActBlue and save to a local CSV.

Usage:
    python3 pull_refunds.py [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--out FILE]

ActBlue caps each report request to a 6-month date range, so this chunks
the requested span into 6-month windows, pulls each, and merges them into
a single CSV (one header row).

Defaults to the full available history (2004-01-01, ActBlue's founding)
through tomorrow (the API's end date is exclusive, so this includes today).
"""

import argparse
import csv
import os
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from actblue_client import ActBlueClient


def _load_dotenv(path: Path = Path(__file__).with_name(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, 28)
    return date(year, month, day)


def _six_month_windows(start: date, end: date):
    cursor = start
    while cursor < end:
        window_end = min(_add_months(cursor, 6), end)
        yield cursor, window_end
        cursor = window_end


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2004-01-01")
    parser.add_argument("--end", default=(date.today() + timedelta(days=1)).isoformat())
    parser.add_argument("--out", default="refunded_contributions.csv")
    args = parser.parse_args()

    _load_dotenv()
    client = ActBlueClient()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    out_path = Path(args.out)

    header = None
    total_rows = 0
    windows_with_data = 0

    with out_path.open("w", newline="") as out_f:
        writer = None
        for window_start, window_end in _six_month_windows(start, end):
            print(f"Requesting refunded_contributions from {window_start} to {window_end}...")
            download_url = client.get_refunded_contributions(
                date_range_start=window_start.isoformat(),
                date_range_end=window_end.isoformat(),
            )
            tmp_path, _ = urllib.request.urlretrieve(download_url)
            with open(tmp_path, newline="") as in_f:
                reader = csv.reader(in_f)
                rows = list(reader)
            os.remove(tmp_path)

            if not rows:
                continue
            if header is None:
                header = rows[0]
                writer = csv.writer(out_f)
                writer.writerow(header)
            body = rows[1:]
            if body:
                writer.writerows(body)
                total_rows += len(body)
                windows_with_data += 1

    print(f"Saved {total_rows} refund records ({windows_with_data} non-empty windows) to {out_path}")


if __name__ == "__main__":
    main()
