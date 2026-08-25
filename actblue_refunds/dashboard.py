"""Builds a self-contained HTML dashboard summarizing refunds across accounts.

Produces one static file with no external dependencies (safe to open offline):
stat tiles, a by-client bar chart, a by-month stacked bar chart, and a
searchable/sortable table of every individual refund. Contains donor-level
detail (name, email, employer, etc.) pulled straight from the ActBlue export,
so treat the output file with the same care as the underlying CSV/xlsx.
"""

import json

import pandas as pd

from actblue_refunds.report import detect_columns, find_column, summarize_by_account, summarize_by_month

_MAX_TABLE_ROWS = 5000

# Only refunds from forms whose slug ends in one of these are shown on the
# dashboard - "rtext" is covered by the "text" suffix. Anything else (e.g.
# "dc-web", "my-express", stray tracking slugs) is excluded, not just hidden
# from the filter dropdown.
_ALLOWED_FORM_SUFFIXES = ("text", "email", "ads")

# Same categories, but checked most-specific-first so "rtext" doesn't get
# swallowed by the "text" suffix - used to reduce a form slug down to just
# its category for display (e.g. "chevalier-rtext" -> "rtext").
_FORM_CATEGORIES = ("rtext", "text", "email", "ads")

# Categorical palette, fixed order (never cycled within 8 slots) - see the
# dataviz skill's references/palette.md for how this was validated.
_PALETTE_LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
_PALETTE_DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]

_TABLE_FIELDS = [
    ("Client", None),  # filled in from the literal "account" column
    ("Receipt ID", ["receipt id"]),
    ("Form", ["fundraising page"]),
    ("Refcode", ["reference code"]),
    ("Contribution Date", ["date"]),
    ("Refund Date", ["refund date"]),
    ("Amount", None),  # filled in from the caller's detected amount_col
    ("First Name", ["donor first name"]),
    ("Last Name", ["donor last name"]),
    ("Email", ["donor email"]),
    ("City", ["donor city"]),
    ("State", ["donor state"]),
    ("Employer", ["donor employer"]),
    ("Occupation", ["donor occupation"]),
    ("Committee", ["recipient committee"]),
    ("Card Type", ["card type"]),
]


def _account_order(df):
    seen = []
    for account in df["account"]:
        if account not in seen:
            seen.append(account)
    return seen


def _pick_table_columns(df, amount_col):
    used = set()
    columns = []

    def add(label, col):
        if col and col not in used:
            used.add(col)
            columns.append((label, col))

    for label, patterns in _TABLE_FIELDS:
        if label == "Client":
            add(label, "account" if "account" in df.columns else None)
        elif label == "Amount":
            add(label, amount_col)
        else:
            add(label, find_column(df, patterns))
    return columns


def _form_slug(value):
    return str(value).rstrip("/").rsplit("/", 1)[-1]


def _matches_allowed_form(value):
    if pd.isna(value):
        return False
    return _form_slug(value).lower().endswith(_ALLOWED_FORM_SUFFIXES)


def _form_category(value):
    slug = _form_slug(value).lower()
    for category in _FORM_CATEGORIES:
        if slug.endswith(category):
            return category
    return slug


def _cell_value(value, numeric=False, form=False):
    if pd.isna(value):
        return None
    if numeric:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    value = _form_category(value) if form else str(value)
    return value


def write_dashboard(df, out_path, start=None, end=None):
    amount_col, date_col = detect_columns(df)

    form_col = find_column(df, ["fundraising page"])
    excluded = {"count": 0, "total": None}
    if form_col is not None:
        keep = df[form_col].apply(_matches_allowed_form)
        dropped = df[~keep]
        excluded["count"] = int(len(dropped))
        if amount_col is not None and excluded["count"]:
            excluded["total"] = float(dropped[amount_col].sum())
        df = df[keep]

    accounts = _account_order(df)
    colors = {
        account: {
            "light": _PALETTE_LIGHT[i % len(_PALETTE_LIGHT)],
            "dark": _PALETTE_DARK[i % len(_PALETTE_DARK)],
        }
        for i, account in enumerate(accounts)
    }

    by_account_records = []
    by_month_records = []
    total_refunded = None
    if amount_col is not None:
        by_account = summarize_by_account(df, amount_col)
        by_account_records = [
            {"account": account, "count": int(row.refund_count), "total": float(row.total_refunded)}
            for account, row in by_account.iterrows()
        ]
        total_refunded = float(df[amount_col].sum())

        if date_col is not None:
            by_month = summarize_by_month(df, amount_col, date_col)
            by_month_records = [
                {"month": month, "account": account, "count": int(row.refund_count), "total": float(row.total_refunded)}
                for (month, account), row in by_month.iterrows()
            ]

    table_columns = _pick_table_columns(df, amount_col)
    total_rows = len(df)
    truncated = total_rows > _MAX_TABLE_ROWS
    table_rows = [
        [
            _cell_value(row[col], numeric=(label == "Amount"), form=(label == "Form"))
            for label, col in table_columns
        ]
        for _, row in df.head(_MAX_TABLE_ROWS).iterrows()
    ]

    payload = {
        "range": {"start": start, "end": end},
        "accounts": accounts,
        "colors": colors,
        "totals": {
            "refunded": total_refunded,
            "count": total_rows,
            "accountCount": len(accounts),
        },
        "excludedForms": excluded,
        "byAccount": by_account_records,
        "byMonth": by_month_records,
        "table": {
            "columns": [label for label, _ in table_columns],
            "rows": table_rows,
            "truncated": truncated,
            "totalRows": total_rows,
        },
    }

    html = _TEMPLATE.replace("__DATA__", json.dumps(payload))
    with open(out_path, "w") as f:
        f.write(html)


_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Refunds Dashboard</title>
<style>
  :root {
    color-scheme: light;
    --surface-1: #fcfcfb;
    --page: #f9f9f7;
    --text-primary: #0b0b0b;
    --text-secondary: #52514e;
    --text-muted: #898781;
    --grid: #e1e0d9;
    --baseline: #c3c2b7;
    --border: rgba(11,11,11,0.10);
    --hover-wash: rgba(11,11,11,0.04);
  }
  @media (prefers-color-scheme: dark) {
    :root {
      color-scheme: dark;
      --surface-1: #1a1a19;
      --page: #0d0d0d;
      --text-primary: #ffffff;
      --text-secondary: #c3c2b7;
      --text-muted: #898781;
      --grid: #2c2c2a;
      --baseline: #383835;
      --border: rgba(255,255,255,0.10);
      --hover-wash: rgba(255,255,255,0.06);
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--page);
    color: var(--text-primary);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  .wrap { max-width: 1180px; margin: 0 auto; padding: 32px 24px 64px; }
  h1 { font-size: 22px; font-weight: 600; margin: 0 0 4px; }
  .subtitle { color: var(--text-secondary); font-size: 14px; margin: 0 0 28px; }
  .card {
    background: var(--surface-1);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
  }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 14px; margin-bottom: 20px; }
  .stat-label { font-size: 13px; color: var(--text-secondary); margin: 0 0 6px; }
  .stat-value { font-size: 28px; font-weight: 600; }
  .charts { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 20px; }
  @media (max-width: 860px) { .charts { grid-template-columns: 1fr; } }
  .chart-title { font-size: 14px; font-weight: 600; margin: 0 0 4px; }
  .chart-note { font-size: 12px; color: var(--text-muted); margin: 0 0 16px; }
  .bar-row { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
  .bar-label {
    width: 38%; flex: 0 0 38%; font-size: 13px; color: var(--text-secondary);
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .bar-track { flex: 1; position: relative; height: 18px; }
  .bar-fill {
    position: absolute; left: 0; top: 0; height: 100%;
    border-radius: 0 4px 4px 0; min-width: 2px;
  }
  .bar-value { font-size: 12px; color: var(--text-secondary); margin-left: 8px; white-space: nowrap; font-variant-numeric: tabular-nums; }
  .month-chart { display: flex; align-items: flex-end; gap: 10px; height: 200px; padding-top: 24px; border-bottom: 1px solid var(--baseline); }
  .month-col { flex: 1; display: flex; flex-direction: column-reverse; align-items: stretch; height: 100%; min-width: 4px; }
  .month-seg { border-radius: 0; margin-bottom: 2px; }
  .month-seg:last-child { margin-bottom: 0; }
  .month-seg:first-child { border-radius: 4px 4px 0 0; }
  .month-axis { display: flex; gap: 10px; margin-top: 6px; }
  .month-axis span { flex: 1; text-align: center; font-size: 11px; color: var(--text-muted); min-width: 4px; }
  .legend { display: flex; flex-wrap: wrap; gap: 14px; margin: 14px 0 0; }
  .legend-item { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-secondary); }
  .legend-swatch { width: 10px; height: 10px; border-radius: 2px; }
  .tooltip {
    position: fixed; pointer-events: none; background: var(--text-primary); color: var(--page);
    font-size: 12px; padding: 6px 9px; border-radius: 6px; opacity: 0; transform: translate(-50%, -100%);
    transition: opacity 0.08s; z-index: 10; white-space: nowrap;
  }
  .tooltip.visible { opacity: 0.95; }
  .controls { display: flex; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; }
  .controls input, .controls select {
    background: var(--page); color: var(--text-primary); border: 1px solid var(--border);
    border-radius: 8px; padding: 8px 10px; font-size: 13px; font-family: inherit;
  }
  .controls input { flex: 1; min-width: 200px; }
  .table-note { font-size: 12px; color: var(--text-muted); margin: 0 0 10px; }
  .table-scroll { overflow-x: auto; border: 1px solid var(--border); border-radius: 8px; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  thead th {
    position: sticky; top: 0; background: var(--surface-1); text-align: left; padding: 9px 12px;
    font-weight: 600; color: var(--text-secondary); border-bottom: 1px solid var(--border);
    white-space: nowrap; cursor: pointer; user-select: none;
  }
  thead th:hover { color: var(--text-primary); }
  thead th .arrow { color: var(--text-muted); margin-left: 4px; }
  tbody td { padding: 8px 12px; border-bottom: 1px solid var(--grid); white-space: nowrap; }
  tbody tr:hover { background: var(--hover-wash); }
  .empty-note { padding: 20px; text-align: center; color: var(--text-muted); font-size: 13px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Refunds Dashboard</h1>
  <p class="subtitle" id="subtitle"></p>
  <p class="chart-note" id="excludedNote"></p>

  <div class="stats" id="stats"></div>

  <div class="charts">
    <div class="card">
      <p class="chart-title">Total refunded by client</p>
      <p class="chart-note" id="byAccountNote"></p>
      <div id="byAccountChart"></div>
    </div>
    <div class="card">
      <p class="chart-title">Refunds by month</p>
      <p class="chart-note">Stacked by client</p>
      <div id="byMonthChart"></div>
      <div class="legend" id="byMonthLegend"></div>
    </div>
  </div>

  <div class="card">
    <p class="chart-title">All refunds</p>
    <p class="table-note" id="tableNote"></p>
    <div class="controls">
      <input type="text" id="search" placeholder="Search name, email, employer...">
      <select id="clientFilter"></select>
      <select id="formFilter"></select>
    </div>
    <div class="table-scroll">
      <table id="table">
        <thead><tr id="tableHead"></tr></thead>
        <tbody id="tableBody"></tbody>
      </table>
    </div>
  </div>
</div>
<div class="tooltip" id="tooltip"></div>

<script>
const DATA = __DATA__;
const dark = () => window.matchMedia("(prefers-color-scheme: dark)").matches;
const fmtMoney = (n) => "$" + n.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
const fmtInt = (n) => n.toLocaleString();

const tooltip = document.getElementById("tooltip");
function showTooltip(evt, text) {
  tooltip.textContent = text;
  tooltip.style.left = evt.clientX + "px";
  tooltip.style.top = (evt.clientY - 10) + "px";
  tooltip.classList.add("visible");
}
function hideTooltip() { tooltip.classList.remove("visible"); }

function renderSubtitle() {
  const r = DATA.range;
  const range = (r && r.start && r.end) ? ` &middot; ${r.start} to ${r.end}` : "";
  document.getElementById("subtitle").innerHTML =
    `${DATA.totals.accountCount} client${DATA.totals.accountCount === 1 ? "" : "s"}${range}`;

  const excluded = DATA.excludedForms;
  const note = document.getElementById("excludedNote");
  if (excluded && excluded.count > 0) {
    const totalPart = excluded.total != null ? `, ${fmtMoney(excluded.total)}` : "";
    note.textContent = `${fmtInt(excluded.count)} refund${excluded.count === 1 ? "" : "s"}${totalPart} excluded — form isn't text/rtext/email/ads.`;
  } else {
    note.textContent = "";
  }
}

function renderStats() {
  const stats = [
    ["Total refunded", DATA.totals.refunded != null ? fmtMoney(DATA.totals.refunded) : "—"],
    ["Total refunds", fmtInt(DATA.totals.count)],
    ["Clients", fmtInt(DATA.totals.accountCount)],
  ];
  document.getElementById("stats").innerHTML = stats.map(([label, value]) => `
    <div class="card">
      <p class="stat-label">${label}</p>
      <p class="stat-value">${value}</p>
    </div>
  `).join("");
}

function renderByAccountChart() {
  const el = document.getElementById("byAccountChart");
  const note = document.getElementById("byAccountNote");
  if (!DATA.byAccount.length) {
    note.textContent = "No amount column detected in the source data.";
    return;
  }
  note.textContent = "";
  const max = Math.max(...DATA.byAccount.map(r => r.total));
  const mode = dark() ? "dark" : "light";
  el.innerHTML = DATA.byAccount.map(r => {
    const pct = max > 0 ? Math.max((r.total / max) * 100, 1) : 0;
    const color = DATA.colors[r.account][mode];
    return `
      <div class="bar-row" data-account="${r.account}" data-count="${r.count}" data-total="${r.total}">
        <div class="bar-label" title="${r.account}">${r.account}</div>
        <div class="bar-track"><div class="bar-fill" style="width:${pct}%;background:${color}"></div></div>
        <div class="bar-value">${fmtMoney(r.total)}</div>
      </div>
    `;
  }).join("");
  el.querySelectorAll(".bar-row").forEach(row => {
    row.addEventListener("mousemove", evt => {
      showTooltip(evt, `${row.dataset.account}: ${fmtMoney(+row.dataset.total)} (${row.dataset.count} refund${row.dataset.count === "1" ? "" : "s"})`);
    });
    row.addEventListener("mouseleave", hideTooltip);
  });
}

function renderByMonthChart() {
  const el = document.getElementById("byMonthChart");
  const axis = document.createElement("div");
  axis.className = "month-axis";
  const legendEl = document.getElementById("byMonthLegend");
  if (!DATA.byMonth.length) {
    el.innerHTML = '<p class="empty-note">No monthly breakdown available.</p>';
    legendEl.innerHTML = "";
    return;
  }
  const months = [...new Set(DATA.byMonth.map(r => r.month))].sort();
  const totalsByMonth = {};
  months.forEach(m => totalsByMonth[m] = 0);
  DATA.byMonth.forEach(r => totalsByMonth[r.month] += r.total);
  const max = Math.max(...Object.values(totalsByMonth), 1);
  const mode = dark() ? "dark" : "light";

  el.innerHTML = "";
  const chart = document.createElement("div");
  chart.className = "month-chart";
  months.forEach(month => {
    const col = document.createElement("div");
    col.className = "month-col";
    const segs = DATA.byMonth.filter(r => r.month === month);
    segs.forEach(seg => {
      const div = document.createElement("div");
      div.className = "month-seg";
      const heightPct = max > 0 ? (seg.total / max) * 100 : 0;
      div.style.height = heightPct + "%";
      div.style.background = DATA.colors[seg.account][mode];
      div.addEventListener("mousemove", evt => {
        showTooltip(evt, `${seg.account} – ${month}: ${fmtMoney(seg.total)} (${seg.count} refund${seg.count === 1 ? "" : "s"})`);
      });
      div.addEventListener("mouseleave", hideTooltip);
      col.appendChild(div);
    });
    chart.appendChild(col);
  });
  el.appendChild(chart);

  months.forEach(m => {
    const span = document.createElement("span");
    span.textContent = m;
    axis.appendChild(span);
  });
  el.appendChild(axis);

  if (DATA.accounts.length > 1) {
    legendEl.innerHTML = DATA.accounts.map(a => `
      <div class="legend-item">
        <span class="legend-swatch" style="background:${DATA.colors[a][mode]}"></span>${a}
      </div>
    `).join("");
  } else {
    legendEl.innerHTML = "";
  }
}

function renderTable() {
  const note = document.getElementById("tableNote");
  const t = DATA.table;
  note.textContent = t.truncated
    ? `Showing first ${fmtInt(t.rows.length)} of ${fmtInt(t.totalRows)} refunds. Narrow the date range to see the rest. Contains donor-level detail — handle accordingly.`
    : `${fmtInt(t.totalRows)} refund${t.totalRows === 1 ? "" : "s"}. Contains donor-level detail — handle accordingly.`;

  const head = document.getElementById("tableHead");
  head.innerHTML = t.columns.map((c, i) => `<th data-col="${i}">${c}<span class="arrow"></span></th>`).join("");

  const clientIdx = t.columns.indexOf("Client");
  const clientFilter = document.getElementById("clientFilter");
  clientFilter.innerHTML = '<option value="">All clients</option>' +
    DATA.accounts.map(a => `<option value="${escapeHtml(a)}">${escapeHtml(a)}</option>`).join("");

  const formIdx = t.columns.indexOf("Form");
  const formFilter = document.getElementById("formFilter");
  if (formIdx >= 0) {
    const forms = [...new Set(t.rows.map(r => r[formIdx]).filter(v => v != null))].sort();
    formFilter.innerHTML = '<option value="">All forms</option>' +
      forms.map(f => `<option value="${escapeHtml(f)}">${escapeHtml(f)}</option>`).join("");
  } else {
    formFilter.style.display = "none";
  }

  let sortCol = -1, sortDir = 1;
  let rows = t.rows.slice();

  function applyFilters() {
    const q = document.getElementById("search").value.trim().toLowerCase();
    const client = clientFilter.value;
    const form = formIdx >= 0 ? formFilter.value : "";
    let filtered = t.rows;
    if (client) filtered = filtered.filter(r => r[clientIdx] === client);
    if (form) filtered = filtered.filter(r => r[formIdx] === form);
    if (q) filtered = filtered.filter(r => r.some(cell => cell != null && String(cell).toLowerCase().includes(q)));
    rows = filtered;
    if (sortCol >= 0) applySort(false);
    else renderRows();
  }

  function applySort(toggle) {
    if (toggle) sortDir = (sortCol === applySort.lastCol) ? -sortDir : 1;
    applySort.lastCol = sortCol;
    const numeric = t.columns[sortCol] === "Amount";
    rows.sort((a, b) => {
      const av = a[sortCol], bv = b[sortCol];
      if (av == null) return 1;
      if (bv == null) return -1;
      if (numeric) return (av - bv) * sortDir;
      return String(av).localeCompare(String(bv)) * sortDir;
    });
    renderRows();
    head.querySelectorAll("th").forEach(th => th.querySelector(".arrow").textContent = "");
    head.querySelector(`th[data-col="${sortCol}"] .arrow`).textContent = sortDir === 1 ? "↑" : "↓";
  }

  function renderRows() {
    const body = document.getElementById("tableBody");
    if (!rows.length) {
      body.innerHTML = `<tr><td colspan="${t.columns.length}" class="empty-note">No matching refunds.</td></tr>`;
      return;
    }
    body.innerHTML = rows.map(r => `<tr>${r.map((cell, i) =>
      `<td>${cell == null ? "" : (t.columns[i] === "Amount" ? fmtMoney(cell) : escapeHtml(String(cell)))}</td>`
    ).join("")}</tr>`).join("");
  }

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  }

  head.querySelectorAll("th").forEach(th => {
    th.addEventListener("click", () => {
      sortCol = +th.dataset.col;
      applySort(true);
    });
  });
  document.getElementById("search").addEventListener("input", applyFilters);
  clientFilter.addEventListener("change", applyFilters);

  renderRows();
}

function renderAll() {
  renderSubtitle();
  renderStats();
  renderByAccountChart();
  renderByMonthChart();
}
renderAll();
renderTable();
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  renderByAccountChart();
  renderByMonthChart();
});
</script>
</body>
</html>
"""
