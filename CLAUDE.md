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

- `app/core/` — `schema` (canonical fields + auto_map), `loader` (ingest, multi-file
  combining, staged failure diagnostics, DuckDB), `nulls` (NA-safe blank/mask helpers),
  `cleaning` (parsing/derivations/DQ), `rollup` (wave dedup → `customer` table),
  `segments` (migration category, source/target platform, Gen-1/Gen-2, EOS population),
  `kpi` (requirement-defined metrics in pandas, each returning its source records),
  `mapping`, `metrics` (periods, date presets, KPIs), `analytics` (**all SQL lives here**),
  `insights` (deterministic rules), `exporter` (ReportLab PDF),
  `html_report` + `html_style` (single-file interactive HTML report).
- `app/ui/` — `theme`, `charts` (Plotly, interactive/browser), `pdf_charts` (matplotlib,
  PDF static images — no bundled browser), `components` (filter sidebar, date-range
  controls, KPI rows, tables), `drilldown` (selectable charts → underlying records).
- `app/views/` — report pages (`data_inconsistency` reviews everything the file
  contradicts itself on; `reports` assembles the PDF from chosen modules, period,
  categories and cover text), plus `category_dashboard` which renders the standard
  six-category dashboard (EOS combined + Gen-1/Gen-2/no-tag, All AVS, AVS → Azure Native) — one entry
  point per category, wired into `st.navigation`.

## Key domain rules (read before editing reports)

- **Reporting scope.** `is_from_avs = FALSE` → *primary* (AVS Migration Nominations,
  onboarding to AVS). `is_from_avs = TRUE` → *AVS → Azure Native* (offerings whose migration
  path contains "(From AVS)"). From-AVS data appears **only** on `avs_native_status` and
  `avs_to_azure` pages. Scope is enforced centrally in `components.filter_sidebar(scope=...)`
  (which also scopes filter options and counts) and per-section in `exporter.build_report`.
- **WW Region.** `region_geo` **is** the cleaned `ww_region` value verbatim (numeric
  prefixes stripped, flagged as DQ) and is labelled **"WW Region"** everywhere — the
  export now carries what the business reports on ("Americas - Enterprise", "Americas
  SME&C", "MS Elevate"), so nothing reduces it to a geography any more. Group, filter
  and label on `region_geo`; `customer_segment` is still reported separately.
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
  sidebar as-of date, which defaults to **today** (never the data's latest date — one
  future-dated row used to drag every window into the wrong fiscal year). A range excludes rows whose date is
  NULL unless the sidebar's "Include N with no <date>" box is ticked (`_date.include_null`).

- **Migration categories** (`segments.population`): `all_avs` = target platform is AVS
  (on-prem / VMG / AWS-VMC / AVS-to-AVS / EOS) **plus every EOS account**, whatever its
  own path says; `avs_native` = `is_from_avs`; the three EOS
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
- **Tag/path consistency** (`segments.eos_consistency`, shown in the sidebar and on Data &
  Upload): accounts tagged Gen-1/Gen-2 with no EOS path on any wave, and waves on the EOS
  path whose account carries no generation tag. Both are legitimate ways into EOS scope —
  the panel just makes the disagreement visible.
- **Explanations.** Every title carries an ⓘ (`theme.info_mark`, hover text) fed from
  `core/glossary.py` — one place for "what does this number mean", shared by tooltips and
  the Methodology page.
- **Build stamp.** `app/version.py` derives a build time (newest source mtime) and a
  content fingerprint, shown in the sidebar, on Data & Upload and printed to the console
  at startup — the app is distributed by copying a folder, so "am I running the new code"
  needs an answer that does not rely on someone bumping a number.
- **Uploads.** A dataset is **one or more files**: `loader.read_files` +
  `combine_raw` stack them on headers matched case/whitespace-insensitively (first
  spelling wins), a column a file lacks is blank for its rows, and every row keeps
  `schema.SOURCE_FILE_COLUMN` → `fact["source_file"]`. `state.build_dataset` is the
  entry point (`build_context` is the one-file shorthand). Every step runs inside
  `loader.ingest_stage(...)`, so a failure arrives as an `IngestError` carrying the
  stage, a plain-English cause, the app frame that raised it and the traceback —
  rendered in full on Data & Upload, never as one line.
- **`pd.NA` has no truth value.** Never write `if not value`, `value in (...)` or
  hand a nullable mask to numpy: an unmapped column makes every value `pd.NA` and
  the whole upload dies with "boolean value of NA is ambiguous". Use
  `nulls.is_blank(value)` (missingness tested first) and `nulls.as_bool_mask(mask)`.
- **EOS monthly matrix** (`kpi.monthly_matrix`, on Status Report → EOS Migrations
  (All)): **Gen1 to Gen1** / **Gen1 to Gen2** blocks — every EOS account comes *from*
  Gen-1 hardware, so the account's own tag names the generation it lands *on*. Rows
  reuse `monthly_unique_tpids` / `monthly_migrations_completed` / `monthly_hosts`;
  *migration start* is **derived** (`kpi.migration_start_dates`: earliest wave whose
  Current State reads On Track/Done → Actual Start, else Planned Start, else Nom.
  Approval); *engagement end* **mirrors migration end** (`MATRIX_ROWS_MIRRORED`) — the
  export has no closure date distinct from the last wave completing, so the two rows
  carry identical values by construction. Columns run from `config.EOS_MATRIX_START_FY` (FY26 =
  Jul 2025) to the as-of month or the latest completion, **every month shown**, each
  fiscal year closing with its own total column. The Trend Analysis "Fiscal years
  side by side" grid likewise lists all twelve months. **The reporting period never
  narrows it**, on the dashboard (which draws it from the unfiltered category) or in
  the HTML report (`build_html_report(..., all_time_where=...)` — the sidebar filters
  with the `_date` key dropped, so a region still binds and a window does not): a
  month with no nominations is itself the number being reported.
- **Two export formats, one report.** `exporter.build_report` (PDF) and
  `html_report.build_html_report` (single-file interactive HTML) take the same
  arguments and select the same populations through the shared public helpers in
  `exporter` (`headline`, `region_status`, `trend_table`, `account_rows`,
  `format_accounts`, `labelled`, `clean`, `REPORTS`) — add a measure in one place,
  not two. The HTML inlines the Plotly bundle, the CSS and its script, so it opens
  offline from an email attachment; that is what makes it ~5 MB.
- **Stage codes on the regional cut.** `kpi.stage_labels` turns "4 - Executing
  Migration" into the axis label **"Stage 4"** plus a key `[("Stage 4", "Executing
  Migration"), …]`; five full status names on one axis leave the plot a sliver.
  `exporter.region_status` returns `(status×region, region×status, legend)` and both
  renderers print the key under the charts.
- **A pie cannot be clicked in Streamlit.** `st.plotly_chart(on_select=...)` returns an
  empty `points` list for pie/donut/sunburst traces whatever the `selection_mode` —
  verified in a browser — so the by-state doughnut is filtered by
  `drilldown.selectable_slices` (chips under the chart) and its summary table, never by
  the slice. Cartesian traces select normally.
- **HTML report specifics.** One header pill (the period); a This-FY KPI row above the
  selected period's row whenever they differ (`_this_fy`, mirroring the dashboard's
  Executive Summary); money axes as `$2M` / `$840k` (`figure(..., currency=True)`);
  `--page-w` plus a **Wide** toggle (remembered in `localStorage`) for the reading width.
- **Every chart in the HTML report filters its own accounts.** `_drillable` pairs a figure
  with an `_accounts_panel`: rows are written once carrying `data-bucket`, the figure
  carries `data-drill`/`data-drill-mode`, and the report's script listens to
  **`plotly_click`** — Plotly's own event, which works in a plain browser even for pies —
  and shows only matching rows. Modes: `x` (month/category), `label` (pie), `y`
  (horizontal bar), `trace-x` (stacked bar: trace = region, x = stage), `y-x` (heatmap).
  Bucket strings are computed in Python so the browser only compares strings; the search
  box and the chart selection go through one filter so neither undoes the other. Neither
  the "Supporting detail" block nor the closing "Account records" table survives — with
  every chart carrying its own rows, both were the same accounts once more (and most of
  the file's weight).
- **The headline tiles are the selector for one accounts panel.** `_kpi_tiles(tiles,
  group=...)` marks each tile `role="button"` + `data-tile`; `_tile_accounts` writes one
  accordion holding a hidden pane per metric, and the script shows the pane whose tile is
  pressed, updating the summary's name and count. Five panels would be five clicks to
  compare two numbers. They are separate panes rather than one filtered table **because
  the metrics do not share a grain** — engagements are Wave-1 rows per TPID, hosts are
  completed *wave* records — so merging them would have to pretend they do.
- **Nodes vs Cores.** `html_report._unit_noun`: the AVS motions deploy **Nodes**, only
  `(From AVS)` moves **Cores**. One noun per report, used by the tiles and the trend
  titles so the two cannot disagree.
- **Drill-down.** Charts use a category x-axis and `drilldown.normalize_bucket` so a
  Plotly month label ("2026-06-01") matches the record's period ("2026-06"); summary
  tables are `st.dataframe(on_select=...)` rows that select the same bucket.

## Conventions

- **All SQL is in `app/core/analytics.py`** (DuckDB). Views call helpers; avoid inline SQL
  (a few documented multi-line queries in trend views are the exception). The
  requirement-defined metrics live in `app/core/kpi.py` as pandas — the latest-wave and
  unique-TPID rules read far better there, and each returns the rows behind the number.
- **Date ranges.** A global reporting period lives in the sidebar
  (`components.global_date_controls`); every report renders its own control **on the page**
  via `components.page_date_filter` (which defaults to "Global range" and returns a `_date`
  filter for `build_where`). There is no second date widget in the sidebar — one period,
  one place to change it.
- Charts: **Plotly** for the browser (JS, no binary); **matplotlib** for the PDF (headless
  Agg, no bundled Chromium). Value axes are integer-only.
- Server binds **127.0.0.1** (`.streamlit/config.toml`). No `.bat`/`.ps1`/`.exe`; run from
  source. Kept deliberately antivirus/EDR-friendly for locked-down corporate laptops.
- Windows-only: there are no macOS/Linux launchers.
