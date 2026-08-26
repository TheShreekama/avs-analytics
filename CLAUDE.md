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
  `segments` (migration category, source/target platform, Gen-1/Gen-2, EOS population),
  `kpi` (requirement-defined metrics in pandas, each returning its source records),
  `mapping`, `metrics` (periods, date presets, KPIs), `analytics` (**all SQL lives here**),
  `insights` (deterministic rules), `exporter` (ReportLab PDF).
- `app/ui/` — `theme`, `charts` (Plotly, interactive/browser), `pdf_charts` (matplotlib,
  PDF static images — no bundled browser), `components` (filter sidebar, date-range
  controls, KPI rows, tables), `drilldown` (selectable charts → underlying records).
- `app/views/` — report pages, plus `category_dashboard` which renders the standard
  five-category dashboard (one entry point per category, wired into `st.navigation`).

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
- **AV36/EOS membership** (`cleaning.is_av36_eos_path`) is checked across `migration_path`,
  `factory_offering` *and* `linked_offering` — real exports carry the marker on the offering
  ("AV36/AV36P/AV52 - EOS"), not the path. SKU markers (av36/av36p/av52, end-of-support)
  match anywhere; short words (eos/egs/eol) must be whole tokens, so "Geospatial" is not a hit.
- **Date parsing** (`cleaning.parse_date_series`) accepts Excel serial numbers ("45855" — an
  unformatted date cell), ISO stamps with or without timezone, month names, and d/m/y triples;
  the day-first vs month-first order is inferred **per column**. Times are dropped (calendar
  days) and a bare year stays unparsed rather than becoming 1 January.
- **`eos_status` waterfall** (`cleaning.derive_eos_status`, first match wins): Completed →
  Cancelled → Blocked → At Risk (deferred) → Delayed (planned-end past & not ended) →
  At Risk (follow-up overdue / waiting) → On Track. **"Risk"** = {At Risk, Delayed, Blocked}.
- **Full offering names.** On AVS → Azure pages, show `migration_path` (e.g. "SQL Server MI
  Migration (From AVS)"), not the short `factory_offering`.
- **Dates.** `metrics.date_preset_range` (This/Last week, This/Last month, Last 3/6 months,
  This/Last FY [July], All time, Custom); default preset "This FY". FY presets span the
  **whole** fiscal year (1 Jul → 30 Jun), not year-to-date; everything is anchored on the
  sidebar as-of date. A range excludes rows whose date is
  NULL unless the sidebar's "Include N with no <date>" box is ticked (`_date.include_null`).

- **Migration categories** (`segments.population`): `all_avs` = target platform is AVS
  (on-prem / VMG / AWS-VMC / AVS-to-AVS / EOS); `avs_native` = `is_from_avs`; the three EOS
  categories = the EOS population split by generation. There is only ever **one dataset**.
  **An account is EOS when ANY of its waves carries an "AVS Migration - Gen1/Gen2" tag**
  (that tag sets both scope and generation); with no tag on any wave, an
  "AV36/AV36P/AV52 - EOS" path/offering is the fallback (`segments.eos_population`) and the
  account lands on the "No generation tag" page.
- **TPID is authoritative** for joins, dedup and counts (`segments.tpid_key`; falls back to
  the account name only when a row has no TPID). The `customer` rollup keys on it — never
  on the account name, which differs between worksheets.
- **Generations** (`segments.classify_generation`, per TPID across ALL waves): the **Tags**
  column alone decides — "AVS Migration - Gen1"/"- Gen2" matched against the cell stripped
  to letters+digits, because tags arrive concatenated ("Qualify and AccelerateAVS
  Migration - Gen1"); Gen-1 wins if both appear. No tag → Unclassified (and not EOS).
  Host SKUs are no longer part of the classification.
- **Metric rules** (`core/kpi.py`, all with `records` for drill-down): new engagements =
  unique TPIDs by **Wave-1** approval date; migration ends = unique TPIDs whose **latest**
  wave is `7 - Completed` (Wave 7 done + Wave 8 open ⇒ not counted), dated by actual end;
  hosts migrated = **sum of Total Cores** over completed records (never a TPID count);
  Cumulative is the final column and runs over the displayed months only.
- **Terminology.** "AV36 EOS" is called **EOS Migration** everywhere in the UI. The
  AVS → Azure Native page labels the Total Cores metric **Cores Migrated**; the AVS
  categories call it **Hosts Migrated** (same column, different noun).
- **Explanations.** Every title carries an ⓘ (`theme.info_mark`, hover text) fed from
  `core/glossary.py` — one place for "what does this number mean", shared by tooltips and
  the Methodology page.
- **Build stamp.** `app/version.py` derives a build time (newest source mtime) and a
  content fingerprint, shown in the sidebar, on Data & Upload and printed to the console
  at startup — the app is distributed by copying a folder, so "am I running the new code"
  needs an answer that does not rely on someone bumping a number.
- **Drill-down.** Charts use a category x-axis and `drilldown.normalize_bucket` so a
  Plotly month label ("2026-06-01") matches the record's period ("2026-06"); summary
  tables are `st.dataframe(on_select=...)` rows that select the same bucket.

## Conventions

- **All SQL is in `app/core/analytics.py`** (DuckDB). Views call helpers; avoid inline SQL
  (a few documented multi-line queries in trend views are the exception). The
  requirement-defined metrics live in `app/core/kpi.py` as pandas — the latest-wave and
  unique-TPID rules read far better there, and each returns the rows behind the number.
- **Date ranges.** A global reporting period lives in the sidebar
  (`components.global_date_controls`); every report can override it with
  `components.report_date_range`, which returns `(start, end, description)`.
- Charts: **Plotly** for the browser (JS, no binary); **matplotlib** for the PDF (headless
  Agg, no bundled Chromium). Value axes are integer-only.
- Server binds **127.0.0.1** (`.streamlit/config.toml`). No `.bat`/`.ps1`/`.exe`; run from
  source. Kept deliberately antivirus/EDR-friendly for locked-down corporate laptops.
- Windows-only: there are no macOS/Linux launchers.
