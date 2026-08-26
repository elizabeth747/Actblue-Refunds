"""Tracks which refunds have already been seen, to support new-refund notifications.

This module only detects and describes new refunds - it doesn't send anything
itself (there's no email/SMTP capability in the CLI tool). track_refunds.py
writes the result to a JSON file that the calling agent (or any other
automation) reads to decide whether to notify someone.
"""

import json
import os

import pandas as pd

from actblue_refunds.dashboard import _form_category, _matches_allowed_form
from actblue_refunds.report import find_column


def _refund_id_col(df):
    return find_column(df, ["refund id"])


def load_seen_ids(state_path):
    """Returns None if no state file exists yet (first run), else a set of ids."""
    if not os.path.exists(state_path):
        return None
    with open(state_path) as f:
        return set(json.load(f))


def save_seen_ids(state_path, ids):
    with open(state_path, "w") as f:
        json.dump(sorted(ids), f)


def find_new_refunds(df, state_path):
    """Returns (new_df, bootstrapped); updates the state file as a side effect.

    On the first run (no state file yet), every current refund is recorded as
    seen but none are reported as new - there's nothing to notify about
    retroactively for refunds that already existed before tracking started.
    """
    id_col = _refund_id_col(df)
    if id_col is None:
        return df.iloc[0:0], False

    ids = df[id_col].dropna().astype(str)
    current_ids = set(ids)
    previous_ids = load_seen_ids(state_path)
    bootstrapped = previous_ids is None

    if bootstrapped:
        new_df = df.iloc[0:0]
    else:
        new_ids = current_ids - previous_ids
        new_df = df[ids.isin(new_ids)]

    save_seen_ids(state_path, current_ids | (previous_ids or set()))
    return new_df, bootstrapped


def summarize_new_refunds(new_df, amount_col):
    """Describes new refunds as plain dicts, restricted to the same tracked
    form categories (text/rtext/email/ads) the dashboard shows - a refund
    from an untracked form isn't on the dashboard, so it shouldn't trigger
    a notification either.
    """
    if not len(new_df) or amount_col is None:
        return []

    form_col = find_column(new_df, ["fundraising page"])
    date_col = find_column(new_df, ["refund date"])
    first_name_col = find_column(new_df, ["donor first name"])
    last_name_col = find_column(new_df, ["donor last name"])

    if form_col is not None:
        new_df = new_df[new_df[form_col].apply(_matches_allowed_form)]

    summaries = []
    for _, row in new_df.iterrows():
        summaries.append(
            {
                "account": row.get("account"),
                "amount": float(row[amount_col]) if pd.notna(row.get(amount_col)) else None,
                "refund_date": str(row[date_col]) if date_col and pd.notna(row.get(date_col)) else None,
                "form": _form_category(row[form_col]) if form_col and pd.notna(row.get(form_col)) else None,
                "donor_first_name": row.get(first_name_col) if first_name_col else None,
                "donor_last_name": row.get(last_name_col) if last_name_col else None,
            }
        )
    return summaries
