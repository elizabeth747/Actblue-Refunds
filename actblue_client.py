"""Client for ActBlue's CSV API (contributions, refunds, managed-form data).

Auth: HTTP Basic Auth with a Client UUID / Client Secret pair generated in
the ActBlue Dashboard under Admin -> API Credentials. See
https://secure.actblue.com/docs/csv_api#authentication.

Report generation is async: POST /csvs kicks off the export, then GET
/csvs/{id} is polled until a download_url appears. The download_url is a
presigned S3 link valid for ~10 minutes.
"""

from __future__ import annotations

import os
import time
from typing import Literal

import requests
from requests.auth import HTTPBasicAuth

API_BASE = "https://secure.actblue.com/api/v1"
POLL_INTERVAL_SECONDS = 2

CsvType = Literal["paid_contributions", "refunded_contributions", "managed_form_contributions"]


class ActBlueError(RuntimeError):
    pass


class ActBlueClient:
    def __init__(
        self,
        client_uuid: str | None = None,
        client_secret: str | None = None,
        api_base: str = API_BASE,
    ):
        client_uuid = client_uuid or os.environ.get("ACTBLUE_CLIENT_UUID")
        client_secret = client_secret or os.environ.get("ACTBLUE_CLIENT_SECRET")
        if not client_uuid or not client_secret:
            raise ActBlueError(
                "Missing ActBlue credentials: set ACTBLUE_CLIENT_UUID and "
                "ACTBLUE_CLIENT_SECRET (env vars or .env file)."
            )

        self.api_base = api_base.rstrip("/")
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(client_uuid, client_secret)
        self.session.headers.update({"Accept": "application/json"})

    def request_csv(
        self,
        csv_type: CsvType,
        date_range_start: str,
        date_range_end: str,
    ) -> str:
        """Kick off CSV generation. Returns the report id."""
        response = self.session.post(
            f"{self.api_base}/csvs",
            json={
                "csv_type": csv_type,
                "date_range_start": date_range_start,
                "date_range_end": date_range_end,
            },
        )
        if response.status_code != 202:
            raise ActBlueError(f"Unexpected status requesting CSV: {response.status_code} {response.text}")
        return response.json()["id"]

    def get_csv_status(self, csv_id: str) -> dict:
        response = self.session.get(f"{self.api_base}/csvs/{csv_id}")
        if response.status_code != 200:
            raise ActBlueError(f"Unexpected status polling CSV: {response.status_code} {response.text}")
        return response.json()

    def poll_for_download_url(self, csv_id: str, max_retries: int | None = None) -> str:
        tries = 0
        while max_retries is None or tries < max_retries:
            status = self.get_csv_status(csv_id)
            download_url = status.get("download_url")
            if download_url:
                return download_url
            if status.get("status") not in (None, "in_progress"):
                raise ActBlueError(f"CSV generation failed: {status}")
            time.sleep(POLL_INTERVAL_SECONDS)
            tries += 1
        raise TimeoutError("CSV generation timed out; increase max_retries and try again.")

    def get_refunded_contributions(
        self, date_range_start: str, date_range_end: str, max_retries: int | None = None
    ) -> str:
        """Request refunded contributions for a date range. Returns a presigned
        download URL for the CSV (valid ~10 minutes)."""
        csv_id = self.request_csv("refunded_contributions", date_range_start, date_range_end)
        return self.poll_for_download_url(csv_id, max_retries=max_retries)
