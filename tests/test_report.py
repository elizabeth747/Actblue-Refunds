import pandas as pd

from actblue_refunds.report import find_column, write_report


def test_find_column_matches_case_insensitively():
    df = pd.DataFrame(columns=["Order Number", "Refund Amount", "Refund Date"])
    assert find_column(df, ["refund amount", "amount"]) == "Refund Amount"
    assert find_column(df, ["refund date", "date"]) == "Refund Date"


def test_find_column_prefers_exact_match_over_substring():
    df = pd.DataFrame(columns=["Reference Code 2", "Reference Code"])
    assert find_column(df, ["reference code"]) == "Reference Code"


def test_find_column_returns_none_when_no_match():
    df = pd.DataFrame(columns=["Order Number"])
    assert find_column(df, ["amount"]) is None


def test_write_report_builds_summary_sheets(tmp_path):
    df = pd.DataFrame(
        {
            "account": ["Campaign A", "Campaign A", "Campaign B"],
            "Refund Amount": [10.0, 5.0, 20.0],
            "Refund Date": ["2026-01-15", "2026-02-01", "2026-01-20"],
        }
    )
    out_path = tmp_path / "combined.xlsx"

    write_report(df, str(out_path))

    sheets = pd.read_excel(out_path, sheet_name=None)
    assert set(sheets) == {"All Refunds", "Summary by Account", "Summary by Month"}
    by_account = sheets["Summary by Account"].set_index("account")
    assert by_account.loc["Campaign A", "total_refunded"] == 15.0
    assert by_account.loc["Campaign B", "total_refunded"] == 20.0


def test_write_report_without_amount_column_writes_note(tmp_path):
    df = pd.DataFrame({"account": ["Campaign A"], "Notes": ["no numeric data"]})
    out_path = tmp_path / "combined.xlsx"

    write_report(df, str(out_path))

    sheets = pd.read_excel(out_path, sheet_name=None)
    assert set(sheets) == {"All Refunds", "Summary"}
