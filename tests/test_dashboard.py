import json

import pandas as pd

from actblue_refunds.dashboard import _circular_distance, _extension_hues, _FIXED_HUES, _form_category, write_dashboard


def test_form_category_prefers_rtext_over_text():
    assert _form_category("https://secure.actblue.com/page/chevalier-rtext") == "rtext"
    assert _form_category("https://secure.actblue.com/page/chevalier-text") == "text"
    assert _form_category("dcrowley-email") == "email"
    assert _form_category("some-page-ads") == "ads"


def test_form_filter_dropdown_is_wired_to_a_change_listener(tmp_path):
    # Regression test: the formFilter <select> was rendered but never
    # attached to applyFilters, so choosing an option did nothing.
    df = pd.DataFrame(
        {
            "account": ["Campaign A"],
            "Fundraising Page": ["https://secure.actblue.com/page/campaign-a-email"],
            "Refund Amount": [10.0],
        }
    )
    out_path = tmp_path / "dashboard.html"

    write_dashboard(df, str(out_path))

    html = out_path.read_text()
    assert 'formFilter.addEventListener("change", applyFilters)' in html
    assert 'monthFilter.addEventListener("change", applyFilters)' in html


def test_table_defaults_to_sorting_by_most_recent_refund(tmp_path):
    df = pd.DataFrame(
        {
            "account": ["Campaign A"],
            "Refund Amount": [10.0],
            "Refund Date": ["2026-01-20"],
        }
    )
    out_path = tmp_path / "dashboard.html"

    write_dashboard(df, str(out_path))

    html = out_path.read_text()
    assert "sortCol = refundDateIdx;" in html
    assert "sortDir = -1;" in html


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

    assert payload["table"]["columns"][:3] == ["Client", "Amount", "Refund Date"]
    assert "Receipt ID" not in payload["table"]["columns"]
    assert "Contribution Date" in payload["table"]["columns"]
    assert "Refund Date" in payload["table"]["columns"]
    # Contribution date and refund date must resolve to distinct source columns.
    contrib_idx = payload["table"]["columns"].index("Contribution Date")
    refund_idx = payload["table"]["columns"].index("Refund Date")
    assert payload["table"]["rows"][0][contrib_idx] != payload["table"]["rows"][0][refund_idx]
    assert payload["table"]["totalRows"] == 3
    assert payload["table"]["truncated"] is False

    # Form shows just the category (rtext/text/email/ads), not the full slug or URL.
    assert "Form" in payload["table"]["columns"]
    form_idx = payload["table"]["columns"].index("Form")
    assert payload["table"]["rows"][0][form_idx] == "rtext"
    assert payload["table"]["rows"][2][form_idx] == "email"

    # Refcode must resolve to "Reference Code", not "Reference Code 2".
    assert "Refcode" in payload["table"]["columns"]
    refcode_idx = payload["table"]["columns"].index("Refcode")
    assert payload["table"]["rows"][0][refcode_idx] == "fb_ad1"

    # Refunds by form: two rtext refunds ($10 + $5) and one email ($20).
    by_form = {row["category"]: row for row in payload["byForm"]}
    assert by_form["rtext"] == {"category": "rtext", "count": 2, "total": 15.0}
    assert by_form["email"] == {"category": "email", "count": 1, "total": 20.0}
    assert payload["formColors"]["rtext"]["light"] != payload["formColors"]["email"]["light"]


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

    # Surviving rows show just the category, e.g. "rtext" not "campaign-a-rtext".
    form_idx = payload["table"]["columns"].index("Form")
    forms = [row[form_idx] for row in payload["table"]["rows"]]
    assert forms == ["rtext", "email", "ads"]


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


def test_write_dashboard_assigns_unique_colors_past_eight_accounts(tmp_path):
    # Regression test: colors used to cycle mod 8, so a 9th account silently
    # reused the 1st account's color.
    accounts = [f"Campaign {i}" for i in range(10)]
    df = pd.DataFrame({"account": accounts, "Refund Amount": [1.0] * 10})
    out_path = tmp_path / "dashboard.html"

    write_dashboard(df, str(out_path))

    payload = _extract_payload(out_path.read_text())
    light_colors = [payload["colors"][a]["light"] for a in accounts]
    dark_colors = [payload["colors"][a]["dark"] for a in accounts]
    assert len(set(light_colors)) == len(accounts)
    assert len(set(dark_colors)) == len(accounts)


def test_extension_hues_stay_far_from_the_fixed_eight():
    # Regression test: the 3rd generated hue used to land at 15 degrees,
    # nearly on top of the fixed palette's orange (17 degrees) - golden-angle
    # stepping only spaced extension hues from each other, not from the
    # fixed 8. Every extension hue must clear a real margin from all of them.
    # (Margins shrink as more get packed onto one wheel - 15 degrees is a
    # reasonable bar for a client roster in the dozens, not a guarantee that
    # holds for an unbounded count.)
    hues = _extension_hues(8)
    for hue in hues:
        assert min(_circular_distance(hue, fixed) for fixed in _FIXED_HUES) >= 15
