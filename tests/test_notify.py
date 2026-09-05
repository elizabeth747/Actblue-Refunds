import pandas as pd

from actblue_refunds.notify import find_new_refunds, summarize_new_refunds


def _df(rows):
    return pd.DataFrame(rows)


def test_first_run_bootstraps_without_reporting_anything_new(tmp_path):
    state_path = tmp_path / "state.json"
    df = _df(
        [
            {"account": "Campaign A", "Refund ID": "1", "Refund Amount": 10.0},
            {"account": "Campaign A", "Refund ID": "2", "Refund Amount": 20.0},
        ]
    )

    new_df, bootstrapped = find_new_refunds(df, str(state_path))

    assert bootstrapped is True
    assert len(new_df) == 0
    assert state_path.exists()


def test_second_run_reports_only_ids_not_seen_before(tmp_path):
    state_path = tmp_path / "state.json"
    first = _df(
        [
            {"account": "Campaign A", "Refund ID": "1", "Refund Amount": 10.0},
            {"account": "Campaign A", "Refund ID": "2", "Refund Amount": 20.0},
        ]
    )
    find_new_refunds(first, str(state_path))

    second = _df(
        [
            {"account": "Campaign A", "Refund ID": "1", "Refund Amount": 10.0},
            {"account": "Campaign A", "Refund ID": "2", "Refund Amount": 20.0},
            {"account": "Campaign A", "Refund ID": "3", "Refund Amount": 30.0},
        ]
    )
    new_df, bootstrapped = find_new_refunds(second, str(state_path))

    assert bootstrapped is False
    assert list(new_df["Refund ID"]) == ["3"]


def test_third_run_does_not_re_report_already_seen_refunds(tmp_path):
    state_path = tmp_path / "state.json"
    find_new_refunds(_df([{"account": "A", "Refund ID": "1", "Refund Amount": 1.0}]), str(state_path))
    find_new_refunds(
        _df(
            [
                {"account": "A", "Refund ID": "1", "Refund Amount": 1.0},
                {"account": "A", "Refund ID": "2", "Refund Amount": 2.0},
            ]
        ),
        str(state_path),
    )

    new_df, bootstrapped = find_new_refunds(
        _df(
            [
                {"account": "A", "Refund ID": "1", "Refund Amount": 1.0},
                {"account": "A", "Refund ID": "2", "Refund Amount": 2.0},
            ]
        ),
        str(state_path),
    )

    assert bootstrapped is False
    assert len(new_df) == 0


def test_summarize_new_refunds_excludes_untracked_forms():
    df = _df(
        [
            {
                "account": "Campaign A",
                "Refund Amount": 10.0,
                "Refund Date": "2026-08-20",
                "Fundraising Page": "https://secure.actblue.com/page/campaign-a-rtext",
                "Donor First Name": "Alex",
                "Donor Last Name": "Smith",
            },
            {
                "account": "Campaign A",
                "Refund Amount": 25.0,
                "Refund Date": "2026-08-21",
                "Fundraising Page": "https://secure.actblue.com/page/dc-web-home",
                "Donor First Name": "Jo",
                "Donor Last Name": "Lee",
            },
        ]
    )

    summaries = summarize_new_refunds(df, "Refund Amount")

    assert len(summaries) == 1
    assert summaries[0]["account"] == "Campaign A"
    assert summaries[0]["amount"] == 10.0
    assert summaries[0]["form"] == "rtext"
    assert summaries[0]["donor_first_name"] == "Alex"


def test_summarize_new_refunds_returns_empty_for_no_new_rows():
    df = pd.DataFrame(columns=["account", "Refund Amount"])
    assert summarize_new_refunds(df, "Refund Amount") == []
