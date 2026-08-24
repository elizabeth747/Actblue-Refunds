# Actblue-Refunds

Tools for pulling refund data from ActBlue's CSV API.

## Setup

```
pip install -r requirements.txt
cp .env.example .env   # fill in ACTBLUE_CLIENT_UUID / ACTBLUE_CLIENT_SECRET
```

Credentials come from the ActBlue Dashboard: Admin -> API Credentials.

## Usage

```python
from actblue_client import ActBlueClient

client = ActBlueClient()
download_url = client.get_refunded_contributions(
    date_range_start="2026-01-01",
    date_range_end="2026-02-01",
)
```

`download_url` is a presigned link (valid ~10 minutes) to the generated CSV.

Run `python test_connection.py` to verify credentials are working — it requests
a refunded_contributions report for the last 60 days and confirms a download
URL comes back, without downloading or printing any contribution data.
