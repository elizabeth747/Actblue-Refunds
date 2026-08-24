"""Sanity check that ActBlue credentials work end-to-end.

Requests a refunded_contributions CSV and confirms a download URL comes
back. Does not download or print the CSV contents (donor PII).
"""

import os
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


_load_dotenv()


def main() -> None:
    client = ActBlueClient()
    end = date.today()
    start = end - timedelta(days=60)

    print(f"Requesting refunded_contributions from {start} to {end}...")
    download_url = client.get_refunded_contributions(
        date_range_start=start.isoformat(),
        date_range_end=end.isoformat(),
    )
    print("Connected to ActBlue successfully.")
    print(f"Download URL (valid ~10 min): {download_url[:60]}...")


if __name__ == "__main__":
    main()
