"""Builds the combined multi-account refund workbook."""

import pandas as pd

_AMOUNT_PATTERNS = ["refund amount", "amount refunded", "amount"]
_DATE_PATTERNS = ["refund date", "date"]


def find_column(df, patterns):
    """Case-insensitive best-effort match of a column name against candidate patterns.

    ActBlue's exact CSV column names aren't hard-coded here since they aren't
    guaranteed to be stable; this keeps the summary sheets working without
    silently mis-mapping data if they change. Tries an exact match for each
    pattern before falling back to substring matches, so e.g. "reference
    code" prefers a column named exactly that over "Reference Code 2".
    """
    lowered = {col.lower(): col for col in df.columns}
    for pattern in patterns:
        if pattern in lowered:
            return lowered[pattern]
    for pattern in patterns:
        for col in df.columns:
            if pattern in col.lower():
                return col
    return None


def detect_columns(df):
    """Returns (amount_col, date_col), either of which may be None if undetected."""
    return find_column(df, _AMOUNT_PATTERNS), find_column(df, _DATE_PATTERNS)


def summarize_by_account(df, amount_col):
    return (
        df.groupby("account")[amount_col]
        .agg(["count", "sum"])
        .rename(columns={"count": "refund_count", "sum": "total_refunded"})
        .sort_values("total_refunded", ascending=False)
    )


def summarize_by_month(df, amount_col, date_col):
    month = pd.to_datetime(df[date_col], errors="coerce").dt.to_period("M").astype(str)
    return (
        df.assign(_month=month)
        .groupby(["_month", "account"])[amount_col]
        .agg(["count", "sum"])
        .rename(columns={"count": "refund_count", "sum": "total_refunded"})
    )


def write_report(df, out_path):
    amount_col, date_col = detect_columns(df)

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="All Refunds", index=False)

        if amount_col is None:
            note = pd.DataFrame(
                {"note": ["Could not auto-detect an amount column for a summary. See 'All Refunds' for raw data."]}
            )
            note.to_excel(writer, sheet_name="Summary", index=False)
            return

        summarize_by_account(df, amount_col).to_excel(writer, sheet_name="Summary by Account")

        if date_col is not None:
            summarize_by_month(df, amount_col, date_col).to_excel(writer, sheet_name="Summary by Month")
