# Development Context

> **Company / production note:** This file exists only to give an AI coding assistant (or a
> new developer) fast context about the project. It is **not used at runtime** and has no
> effect on the app. It is the **single** context file in this repository — you can safely
> **delete `CLAUDE.md`** before or while using this project in a company environment.

## What this is

A 100% local, offline **Streamlit** dashboard for **AVS (Azure VMware Solution) migration
analytics and executive reporting**. No external APIs, no AI at runtime, no telemetry, no
outbound network. Targets 500k+ rows via in-process DuckDB. Windows-only run instructions.

## Run (Windows)

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run Home.py
:: then open http://127.0.0.1:8501  (http + the 127.0.0.1 IP, not https/localhost)
```

## Test

```bat
.venv\Scripts\python.exe -m pip install pytest
.venv\Scripts\python.exe -m pytest tests\test_core.py tests\test_app.py -v
```

`test_core.py` = engine assertions on the bundled sample; `test_app.py` = renders every page
under Streamlit's AppTest in both counting modes.

## Architecture

`Home.py` (root entry) → `app/main.py:run()` → `st.navigation` over `app/views/*`.

- `app/core/` — `schema` (canonical fields + auto_map), `loader` (ingest + DuckDB),
  `cleaning` (parsing/derivations/DQ), `rollup` (wave dedup → `customer` table),
  `mapping`, `metrics` (periods, date presets, KPIs), `analytics` (**all SQL lives here**),
  `insights` (deterministic rules), `exporter` (ReportLab PDF).
- `app/ui/` — `theme`, `charts` (Plotly, interactive/browser), `pdf_charts` (matplotlib,
  PDF static images — no bundled browser), `components` (filter sidebar, KPI rows, tables).
- `app/views/` — 13 report pages.

## Key domain rules (read before editing reports)

- **Reporting scope.** `is_from_avs = FALSE` → *primary* (AVS Migration Nominations,
  onboarding to AVS). `is_from_avs = TRUE` → *AVS → Azure Native* (offerings whose migration
  path contains "(From AVS)"). From-AVS data appears **only** on `avs_native_status` and
  `avs_to_azure` pages. Scope is enforced centrally in `components.filter_sidebar(scope=...)`
  (which also scopes filter options and counts) and per-section in `exporter.build_report`.
- **Region.** Use `region_geo` (geography only: Americas / EMEA / ASIA) for all region
  groupings/filters/insights. `ww_region` keeps the full "Geo - Segment" value; the segment
  is in `customer_segment`.
- **Wave dedup (`customer` table).** Approval/creation date = Wave-1 (lowest wave number);
  status/region/closure = last wave; category membership = ANY wave; ACR/cores summed.
  Toggle grain with `analytics.use_table("customer" | "fact")` (driven by the sidebar
  counting-mode radio via `state.active_table()`).
- **`eos_status` waterfall** (`cleaning.derive_eos_status`, first match wins): Completed →
  Cancelled → Blocked → At Risk (deferred) → Delayed (planned-end past & not ended) →
  At Risk (follow-up overdue / waiting) → On Track. **"Risk"** = {At Risk, Delayed, Blocked}.
- **Full offering names.** On AVS → Azure pages, show `migration_path` (e.g. "SQL Server MI
  Migration (From AVS)"), not the short `factory_offering`.
- **Dates.** `metrics.date_preset_range` (This/Last week, This/Last month, Last 3/6 months,
  This FY [July], All time, Custom); default preset "All time" — a narrow default emptied
  almost every page; anchored on the sidebar as-of date. A range excludes rows whose date is
  NULL unless the sidebar's "Include N with no <date>" box is ticked (`_date.include_null`).

## Conventions

- **All SQL is in `app/core/analytics.py`** (DuckDB). Views call helpers; avoid inline SQL
  (a few documented multi-line queries in trend views are the exception).
- Charts: **Plotly** for the browser (JS, no binary); **matplotlib** for the PDF (headless
  Agg, no bundled Chromium). Value axes are integer-only.
- Server binds **127.0.0.1** (`.streamlit/config.toml`). No `.bat`/`.ps1`/`.exe`; run from
  source. Kept deliberately antivirus/EDR-friendly for locked-down corporate laptops.
- Windows-only: there are no macOS/Linux launchers.
