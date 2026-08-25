import json

import pandas as pd

from actblue_refunds.dashboard import write_dashboard


def _extract_payload(html):
    line = html.split("const DATA = ", 1)[1].split("\n", 1)[0]
    return json.loads(line.rstrip(";"))


def test_write_dashboard_embeds_summary_and_table_data(tmp_path):
    df = pd.DataFrame(
        {
            "account": ["Campaign A", "Campaign A", "Campaign B"],
            "Receipt ID": ["AB1", "AB2", "AB3"],
            "Fundraising Page": [
                "https://secure.actblue.com/page/campaign-a-rtext",
                "https://secure.actblue.com/page/campaign-a-rtext",
                "https://secure.actblue.com/page/campaign-b-email",
            ],
            "Reference Code 2": ["should-not-be-picked", "should-not-be-picked", "should-not-be-picked"],
            "Reference Code": ["fb_ad1", "fb_ad1", "email_1"],
            "Date": ["2026-01-01", "2026-01-15", "2026-02-01"],
            "Refund Amount": [10.0, 5.0, 20.0],
            "Refund Date": ["2026-01-20", "2026-02-01", "2026-02-10"],
            "Donor First Name": ["Alex", "Sam", "Jo"],
            "Donor Email": ["a@example.com", "s@example.com", "j@example.com"],
        }
    )
    out_path = tmp_path / "dashboard.html"

    write_dashboard(df, str(out_path), start="2026-01-01", end="2026-03-01")

    html = out_path.read_text()
    payload = _extract_payload(html)

    assert payload["accounts"] == ["Campaign A", "Campaign B"]
    assert payload["totals"]["refunded"] == 35.0
    assert payload["totals"]["count"] == 3
    assert payload["range"] == {"start": "2026-01-01", "end": "2026-03-01"}

    by_account = {row["account"]: row for row in payload["byAccount"]}
    assert by_account["Campaign A"]["total"] == 15.0
    assert by_account["Campaign B"]["total"] == 20.0

    assert payload["table"]["columns"][:2] == ["Client", "Receipt ID"]
    assert "Contribution Date" in payload["table"]["columns"]
    assert "Refund Date" in payload["table"]["columns"]
    # Contribution date and refund date must resolve to distinct source columns.
    contrib_idx = payload["table"]["columns"].index("Contribution Date")
    refund_idx = payload["table"]["columns"].index("Refund Date")
    assert payload["table"]["rows"][0][contrib_idx] != payload["table"]["rows"][0][refund_idx]
    assert payload["table"]["totalRows"] == 3
    assert payload["table"]["truncated"] is False

    # Form shows just the page slug, not the full URL.
    assert "Form" in payload["table"]["columns"]
    form_idx = payload["table"]["columns"].index("Form")
    assert payload["table"]["rows"][0][form_idx] == "campaign-a-rtext"

    # Refcode must resolve to "Reference Code", not "Reference Code 2".
    assert "Refcode" in payload["table"]["columns"]
    refcode_idx = payload["table"]["columns"].index("Refcode")
    assert payload["table"]["rows"][0][refcode_idx] == "fb_ad1"


def test_write_dashboard_excludes_refunds_from_untracked_forms(tmp_path):
    df = pd.DataFrame(
        {
            "account": ["Campaign A", "Campaign A", "Campaign A", "Campaign A"],
            "Receipt ID": ["AB1", "AB2", "AB3", "AB4"],
            "Fundraising Page": [
                "https://secure.actblue.com/page/campaign-a-rtext",
                "https://secure.actblue.com/page/campaign-a-email",
                "https://secure.actblue.com/page/campaign-a-ads",
                "https://secure.actblue.com/page/dc-web-home",
            ],
            "Refund Amount": [10.0, 20.0, 5.0, 100.0],
        }
    )
    out_path = tmp_path / "dashboard.html"

    write_dashboard(df, str(out_path))

    payload = _extract_payload(out_path.read_text())
    # The "dc-web-home" refund (form doesn't end in text/rtext/email/ads) is dropped.
    assert payload["totals"]["count"] == 3
    assert payload["totals"]["refunded"] == 35.0
    assert payload["excludedForms"] == {"count": 1, "total": 100.0}


def test_write_dashboard_without_amount_column_still_writes_table(tmp_path):
    df = pd.DataFrame({"account": ["Campaign A"], "Notes": ["no numeric data"]})
    out_path = tmp_path / "dashboard.html"

    write_dashboard(df, str(out_path))

    payload = _extract_payload(out_path.read_text())
    assert payload["totals"]["refunded"] is None
    assert payload["byAccount"] == []
    assert payload["table"]["totalRows"] == 1


def test_write_dashboard_assigns_distinct_colors_per_account(tmp_path):
    df = pd.DataFrame(
        {
            "account": ["Campaign A", "Campaign B"],
            "Refund Amount": [1.0, 2.0],
        }
    )
    out_path = tmp_path / "dashboard.html"

    write_dashboard(df, str(out_path))

    payload = _extract_payload(out_path.read_text())
    colors = payload["colors"]
    assert colors["Campaign A"]["light"] != colors["Campaign B"]["light"]
