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
  `statuses` (what a Migration Status *means* — `status_class` — in either vocabulary),
  `eos_tracker` (the manual EOS tracking sheet — read, rolled up per TPID, joined on,
  its status/state written over the export's), `eos_programme` (the EOS Programme
  Tracker report, built once for the page and both exports),
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
  point per category, wired into `st.navigation`; `eos_programme` is the EOS Programme
  Tracker page (Status Report → EOS Programme Tracker).

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
- **Factory Offering and Primary Migration Path are two different columns**, and neither
  stands in for the other. `factory_offering` is **which factory delivers the work** ("AVS
  Migration Nominations", "SQL Migration Nominations") and scopes the AVS pipeline;
  `migration_path` is **what moves where** ("Onprem to AVS", "SQL Server MI Migration (From
  AVS)"), decides `is_from_avs`, and scopes the native pipeline. Both are carried in
  `kpi.DRILLDOWN_COLUMNS` and charted separately in the "By offering, path & target"
  section; label them "Factory Offering" and "Primary Migration Path" respectively.
- **Dates.** `metrics.date_preset_range` (This/Last week, This/Last month, Last 3/6 months,
  This/Last FY [July], All time, Custom); default preset "This FY". FY presets span the
  **whole** fiscal year (1 Jul → 30 Jun), not year-to-date; everything is anchored on the
  sidebar as-of date, which defaults to **today** (never the data's latest date — one
  future-dated row used to drag every window into the wrong fiscal year). A range excludes rows whose date is
  NULL unless the sidebar's "Include N with no <date>" box is ticked (`_date.include_null`).

- **Migration categories** (`segments.population`): `all_avs` = target platform is AVS
  (on-prem / VMG / AWS-VMC / AVS-to-AVS / EOS) **plus every EOS account**, whatever its
  own path says; `avs_native` = `is_from_avs`; `eos_all` = **Gen-1 ∪ Gen-2 only**.
  An EOS-by-path account with no generation tag (`eos_unclassified`) is **excluded from
  every EOS report** — EOS is reported by generation, and an ungenerationed account would
  make the combined total disagree with the sum of its blocks — but it stays in `all_avs`
  and is listed on Data Inconsistency. There is only ever **one dataset**.
  **With the EOS tracking sheet loaded, the sheet IS the list of EOS accounts**
  (`segments.eos_population(fact, sheet=True)` = `eos_tracked` and not From AVS) — **of
  the accounts the FDO dataset holds**: a sheet TPID the export lacks (or holds only From
  AVS / pre-floor waves for) has no ACR, cores or waves, so it is **not counted** and
  nothing is invented for it; it is named on Data & Upload, Data Inconsistency, the Debug
  funnel ("…not counted as EOS") and the Programme Tracker (`Programme.not_in_fdo`,
  `exporter.programme_gap_note`). An export-tagged account the sheet omits is not EOS
  (listed on Data Inconsistency as "Marked EOS in the export, not in the sheet"), and a
  matched sheet account with no generation still counts in `eos_all` (neither Gen block;
  the matrix gains a "Generation not stated" block via `exporter.matrix_blocks`).
  Without a sheet, the rules below decide exactly as before.
  **The manual EOS tracking sheet decides an account's generation wherever it states
  one** (`Target SDDC Generation` = Gen1/Gen2); failing that, **an account is EOS when ANY
  of its waves carries an "AVS Migration - Gen1/Gen2" tag** (that tag sets both scope and
  generation); with no tag on any wave, an "AV36/AV36P/AV52 - EOS" path/offering is the
  fallback (`segments.eos_population`) and the account lands on the "No generation tag"
  page. Each row carries `generation_source` so a reader can see which document answered.
- **All EOS customers list** (third upload on Data & Upload, `app/core/eos_customers.py`,
  columns **TPID** and **Customer**, read like the tracking sheet): when loaded, **AVS →
  Azure Native reports only customers on it** — `eos_customers.apply_to_fact`, run in
  `state._build_fact` after the floor, **drops the From AVS waves of every TPID not on
  the list**, so no page, export or total can count them (nothing else moves: From AVS
  counts nowhere else). `report["eos_list"]` (kept/excluded/not-in-FDO, excluded names)
  feeds Data & Upload's panel, the Debug verdicts and `eos_customers.scope_note(ctx)`,
  printed on the native dashboard, PDF and HTML report. No list → unchanged.
  `ctx.eos_list`, `has_eos_list`, `eos_list_signature` (in the cache key),
  `state.reload_with(eos_list_files=…)`.
- **TPID is authoritative** for joins, dedup and counts (`segments.tpid_key`; falls back to
  the account name only when a row has no TPID). The `customer` rollup keys on it — never
  on the account name, which differs between worksheets.
- **Generations** (`segments.classify_generation`, per TPID across ALL waves): the **Tags**
  column alone decides — "AVS Migration - Gen1"/"- Gen2" matched against the cell stripped
  to letters+digits, because tags arrive concatenated ("Qualify and AccelerateAVS
  Migration - Gen1"); Gen-1 wins if both appear. No tag → Unclassified (and not EOS).
  Host SKUs are no longer part of the classification. **The EOS tracking sheet overrides
  all of it** where it states a `Target SDDC Generation` (`eos_tracker.resolve_generation`,
  applied inside `cleaning.build_fact_frame` *before* scope is decided, because the
  generation is what puts an account in EOS scope).
- **Metric rules** (`core/kpi.py`, all with `records` for drill-down): new engagements =
  unique TPIDs by **Wave-1** approval date, **and** that wave's `Nomination Status =
  "Approved"`. Two halves, and they are separate: **which wave answers is decided by the
  date alone** — Wave-1 whatever its *Migration Status* or *Current State* (a cancelled or
  blocked Wave-1 still dates the engagement), moving on to the next wave **only** when
  Wave-1 has no *Nom. Approval Date* (`kpi.dated_wave`, carried as `WaveIndex.approval`;
  the record returned is the wave the date came from, so a drill-down names it) — and the
  **status is then read from that same wave**. It is deliberately *not* a search for an
  approved wave: an account whose dating wave was declined is not counted at all, rather
  than counted on a later wave's date in a month nobody approved anything in.
  `kpi.monthly_unique_tpids` applies the same two halves, so the trend and the tile count
  one population; migration ends = unique TPIDs classified
  Completed, dated by actual end; hosts migrated = **sum of Total Cores** over completed
  records (never a TPID count, and deliberately wave-level — a completed wave deployed its
  nodes whatever the account's state is now); Cumulative is the final column and runs over
  the displayed months only.
- **Two status vocabularies; rules read `status_class`, never the number.** The FDO export
  numbers 1-4 in flight, 5 Deferred, 6 Cancelled / Archived, 7 Completed; the EOS tracking
  sheet's values carry **no numbers at all** — `Kick-Off Awaited`, `Planning &
  Prerequisites`, `Ready for Migration`, `Executing Migration`, `Sign-off Pending` (all in
  flight), `Completed`, `On Hold`, `Cancelled` — and none is ever read, stored or shown
  (`TrackerStatus.order` is internal, for sorting and "least advanced" only; a sheet stage
  has a blank `migration_status_code`). The two vocabularies overlap, so every row carries
  `status_class` (`statuses.IN_FLIGHT/COMPLETED/DEFERRED/ON_HOLD/CANCELLED/UNKNOWN`) and
  `status_source` ("FDO export"/"EOS tracker"); `kpi.is_completed/in_flight/is_deferred/
  is_on_hold/is_cancelled`, the pipeline, `derive_eos_status` and the rollup all read the
  class. `kpi.stage_labels` labels an export stage "Stage 4" (with a legend) and a sheet
  stage by its own wording ("Executing Migration").
- **The sheet's Migration Status and Current State replace the export's**
  (`eos_tracker.apply_status`, in `build_fact_frame` after the status split): on every wave
  the export still has **open** (class not completed/cancelled), or on the latest wave when
  all are closed — a closed wave keeps its status (and its cores stay migrated). Originals
  kept as `fdo_migration_status`/`fdo_current_state`; a wave the sheet completes with no
  Actual End Date takes the sheet's end date. Values are parsed by **wording**
  (`eos_tracker.parse_status`/`parse_state`, case/punctuation-insensitive; a number — alone
  or in front of the wording — is never read, and "5 - Deferred by Customer" names nothing); unrecognised
  values leave the export answering and are listed on Data & Upload. Several rows per
  TPID: least advanced in-flight stage, then On Hold, Completed, Cancelled; state Blocked >
  On Track > Completed.
- **A tracked account's state is the sheet's** (`kpi.tracker_account_state`, applied at
  the end of `kpi.account_state`): Cancelled (`8.`) → On Hold (`7.`) → Completed (`6.` or
  state Completed) → Blocked (state) → On-Track (state On Track, stage 1-5 or blank) →
  Other. **On Hold** is a new state in `EXCLUDED_STATES` (stopped-accounts section, label
  "On Hold"). `kpi.on_track_wave` returns the latest wave for a sheet-on-track account with
  no export-on-track wave, and drops sheet-stopped ones. `kpi.migrations_completed` dates by
  `kpi.completion_dates` — read from the account's **real latest row** (not the
  column-filled one): its **FDO** Actual End Date (`fdo_actual_end_date`, never the
  sheet's date, never one the sheet filled in), else `kpi.END_DATE_CHAIN` — Planned End →
  Actual Start → Planned Start → Nom. Approval → Nom. Created (`kpi.end_dates`; records
  carry `reported_end_date` + `end_date_source`). That is exactly the matrix's
  *engagement end* (`engagement_end_dates` reuses `completion_date`) and the fallback of
  *migration end*, so the Migrations Completed tile and the engagement-end row always
  reconcile. **Hosts Migrated and ACR Claimed** (and their trends / the matrix hosts
  row) date each wave the same way (`kpi._with_end_dates`) — but only a **completed**
  wave falls back; any other wave counts on its own FDO Actual End Date or not at all.
- **Total ACR leaves out blocked waves** (`kpi.account_acr`: Current State contains
  "Blocked"): account rows, Top 10, by-state, reconciliation, the Programme Tracker and
  the `customer` rollup (`_acr_counted`). The stopped-accounts section's **ACR held up**
  is the exception — every wave (`kpi.held_up_acr`).
- **From AVS is read from the Primary Migration Path only** (`kpi.mentions_from_avs`,
  `cleaning.migration_direction`); platform classification reads the offerings with any
  "From AVS" stripped (`cleaning._without_from_avs`). It never counts in All AVS or EOS.
  Pipeline condition 4 excludes `On Hold` and `Cancelled` too
  (`kpi.PIPELINE_EXCLUDED_STATUSES`).
- **Account state** (`kpi.account_state`, read across **all** of an account's waves, first
  match wins): **On-Track** = ANY wave where `Nomination Status = "Approved"` **and** the
  status is in flight (1-4) **and** Current State is exactly `On Track`
  (`kpi.is_on_track_wave`; matched through `_state_key`, so "On-Track" is the same state,
  while **an unapproved nomination and a blank Current State are not on track — there is no
  fallback**);
  **Completed** = latest wave `7 - Completed` AND
  no wave on track; then **Blocked** (latest wave's **FDO** Current State written and not
  On Track / Done / Waiting action on follow up date — `kpi.is_fdo_blocked`, ahead of
  the Migration Status) → Cancelled → On Hold → Deferred → Other from the latest wave. So
  "latest wave completed + earlier wave on track" is **On-Track**, not Completed. Every
  account resolves to exactly one state, so `by_state` (the reported cut) and
  `excluded_accounts` (`EXCLUDED_STATES`) partition the population — nothing double-counted,
  nothing lost. `on_track_by_stage` groups by the stage of the **on-track wave itself**.
- **Programme summary** (opens the EOS report, before the executive summary — dashboard
  EOS (All) page, PDF and HTML;
  `exporter.programme_summary` → `ProgrammeSummary`, text via `summary_sentence` /
  `summary_lines` / `summary_note`): "To date, X customers are participating in
  factory-driven migrations: Y completed, Z in progress, U in planning, B blocked." —
  **four buckets, a flat list, nothing else** — + Gen1→Gen1 / Gen1→Gen2 / Gen1→Azure
  Native lines in the same shape.
  **Read from the FDO export alone** (`kpi.programme_status`, via
  `kpi.fdo_migration_status` / `kpi.fdo_current_state` = `fdo_migration_status` /
  `fdo_current_state`, the export's values before the sheet writes over them): **the
  EOS tracking sheet plays no part**, unlike every other EOS figure (a stakeholder
  decision). Per account, first match: **Completed** = latest wave **7** and no wave
  still at a stage; **Blocked** = latest wave's Current State is **written and not one
  of `kpi.NON_BLOCKING_STATES`** (On Track, Done, Waiting action on follow up date —
  `kpi.is_fdo_blocked`; a blank/"Unknown" Current State blocks nothing, the Migration
  Status decides); **In progress** = any wave at **4**; **In planning** = any wave at
  **1**, 2 or 3; **everyone else is Blocked too** (latest wave 5/6 whatever its
  Current State, or no Migration Status) — so the four always add up to the customers.
  **"Include blocked accounts"** (ticked by default) — unticked, the Blocked bucket
  leaves every number and line (`SummaryTotals.show_blocked=False` drops "N blocked"
  from the sentence): `programme_summary` works `programme_status` out once per motion
  and `ProgrammeSummary.reading(False)` (`excluding_blocked`) is the same frames
  filtered.
  **In the HTML every number is clickable** (`summary_sentence(…, num=…)` /
  `summary_lines(…, num=…, tag=…)` render numbers through a callback;
  `ProgrammeSummary.rows` — one row per customer per line, `_buckets` like
  `gen1:blocked|eos:total|…|eos-nb:total` (the lean reading's scopes carry
  `exporter.NO_BLOCKED`), `_left_out` marking the Blocked rows the lean reading drops —
  feeds the "Customers behind these numbers" panel, columns `exporter.SUMMARY_COLUMNS`:
  FDO Migration Status, FDO Current State (latest wave) and **Status Summary**). The four
  readings (native × blocked) are all written out and shown by CSS sibling rules on
  `.sum-toggle` / `.sum-blk-toggle`; rows carry `data-left-out` and the table
  `data-lean-toggle`, so the unticked box hides them (CSS) and `apply()` counts them out;
  `input[data-resets]` clears a pick when a box changes. Azure Native =
  `avs_native` accounts whose first `cleaning.nomination_date` ≥ 1 Jul 2025
  (`kpi.nominated_since`, `exporter.summary_native_start` = `EOS_MATRIX_START_FY`).
  **Every line carries its own split** (`ProgrammeSummary.gen1_split` / `gen2_split` /
  `no_generation_split` / `native_split`, same rule; the EOS lines' splits add up to the
  sentence).
  A customer on an EOS line *and* the Azure Native line is counted once in the total;
  `ProgrammeSummary.overlap` / `exporter.summary_overlap_note` says so whenever the
  lines add up to more than the total.
  The **Gen1 → Azure Native line is shown only when the box is ticked**
  (`summary_lines(s, include_native)`), and then with `exporter.NATIVE_CAVEAT` (moving
  to Azure Native is often modernisation, not an EOS exit).
  "Include Azure Native customers" adds them (unique TPIDs) to every total — each customer
  classified within its own motion, EOS bucket winning (`exporter._totals`): a
  `st.checkbox` on the page (beside "Include blocked accounts") and a CSS-only
  `.sum-toggle` in the HTML (always unticked — a reader's choice, never a generation
  option). The PDF prints the EOS reading, the one leaving the blocked customers out, and
  the with-native one underneath. All time, never the period.
- **Status Summary comes from the blocked wave** (`kpi.status_summary_by_account`): for
  an account whose latest wave is blocked (`kpi.fdo_blocked_accounts`), its latest
  `kpi.is_fdo_blocked` wave with a Status Summary written — that note says *why* — else
  (and for every other account) its latest written one. Used by the summary's customers
  panel and the blocked-accounts rows (`kpi.blocked_accounts`).
- **Copy and CSV on every HTML table** (`html_report._table_tools`, written by `_table`, or
  into the search row by `_accounts_panel` / `_accounts_body` / `_rows_panel` /
  `_searchable_table` with `actions=False`): Copy puts the **rows as shown** (search,
  chart pick, sort, the blocked box) on the clipboard as TSV + HTML through a `copy`
  event (`navigator.clipboard` fallback); CSV saves a UTF-8 (BOM) file via a Blob,
  named from the section and panel title, formula-looking cells prefixed `'`. No
  network, so it works offline. "Status Summary" cells (`_NOTE_COLUMNS`) stay **one
  line in a wide column** (`td.note-cell`, ellipsis, the whole note in `title` and in
  Copy/CSV), so every row is the same height.
- **Report periods in the exports** (`exporter.period_population`, `report_views`): both
  renderers build every report from `all_time_where` (filters minus the period). Dated
  headline tiles and trends read the **whole** category windowed by their own dates (as
  the dashboards do), so a wave is never cut before latest-wave/state rules run (cutting
  first used to make an account with a newer open wave look Completed). The pipeline,
  regional, generation, insights and stopped-account sections read
  `period_population` — accounts with a wave whose Nom. Created Date is in the period,
  **all** their waves kept. **The HTML report carries a period switch** at the top of the
  side panel: **Current FY** and **Reporting Period** (the Reports page's period, "All
  dates in the dataset" when none) — one view when they are the same window; it opens
  on the Reporting Period (`exporter.report_views`, keys `fy` / `sel`). Period-bound sections are written once per view inside
  `<div class="pv" data-pv=…>` via `html_report._period_view`, which sets `_ID_PREFIX`
  so every `_slug` id is view-prefixed (`all-optx-eos`, `fy-kpis-eos`); CSS on
  `<body data-period>` hides the others with no script. The programme summary, matrix,
  fiscal-year view and top accounts are written once and never change. The matrix
  table's first column is sticky (`_table(..., sticky_first=True)`).
- **Latest wave** (`kpi._last_of`): column-wise `GroupBy.last()` (a blank cell takes the
  account's most recent answer) **except** `_STATUS_COLUMNS`, taken whole from the real
  latest row — else a sheet stage (no code) borrowed an earlier wave's code ("Stage 7 =
  Executing Migration").
- **Where every account sits** (`exporter.reconciliation`, under the pipeline on every
  dashboard and in both exports): each account state, its account count and ACR, and
  **where that state is reported** — On-Track and Completed are charted, everything else is
  in the stopped-accounts section. Rows sum to the report's own account count, because
  `account_state` puts each account in exactly one. It exists because "the chart shows 32 of
  my 36 accounts, where are the other four?" is a fair question a report should answer
  itself.
- **Accounts by generation and state** (`exporter.generation_status`, EOS reports only):
  generation down the side plus an **`ALL_EOS_ROW`** total on top, state across the top —
  On-Track, Completed and Blocked first, then any other state present — so every row totals
  the accounts it covers and the grid reconciles with New Engagements over all time. A
  heatmap cell opens its own accounts (`_by_generation_state`, mode `y-x`), and because an
  account belongs to **two** cells (its generation's and the total row's) its
  `data-bucket` carries both, pipe-separated; `inBucket` in the report's script matches any
  of them. Careful in `_generations`: the per-generation wave index is `sub_waves`, because
  shadowing the report's `waves` silently dropped a whole row from the grid.
- **Blocked, deferred & cancelled accounts** (`kpi.blocked_accounts` + `wave_profile`,
  assembled by `exporter.blocked_tables`, titled `exporter.BLOCKED_TITLE`): **every**
  account whose `account_state` is in `EXCLUDED_STATES` — so this section and `by_state`
  (On-Track + Completed) partition the population and the report reconciles. The breakdown
  is **why** (`kpi.blocked_state_label`, first match wins): the **FDO Current State
  wherever it blocks** (`kpi.is_fdo_blocked`; a `kpi.BLOCKED_STATES` value in its
  canonical spelling — a deferred account whose state reads "Blocked - Customer" is
  shown as "Blocked - Customer"), then `6 - Cancelled / Archived` → "Cancelled /
  Archived", sheet On Hold, `5 - Deferred By Customer` → "Deferred By Customer", then the
  Current State as reported (the sheet's for a tracked account), "Not approved", "Not
  stated", else the cell's own wording. A section of its
  own on every dashboard and in both exports, never mixed into the On-Track/Completed
  metrics, with the export's **Status Summary** on every row
  (`kpi.BLOCKED_DRILLDOWN_COLUMNS`, a shorter column list so the reason is not twenty
  columns to the right). **New Engagements is the one deliberate exception** to the
  separation: intake is a historical fact and counts every approved nomination.
- **Forward-looking metrics** (`kpi.eligible_pipeline_waves`): a wave is eligible when all
  **four** hold, judged per wave —
  (1) `Factory Offering = "AVS Migration Nominations"` **or** `Primary Migration Path`
  contains `"From AVS"` (`kpi.in_pipeline_scope`: the offering scopes the AVS motions, the
  path scopes AVS → Azure Native, and the union serves both because neither population
  holds the other's waves);
  (2) `Nomination Status = "Approved"` (`kpi.is_nomination_approved` — the column, not
  `is_approved`, which also accepts a stray approval date);
  (3) `Current State = "On Track"` and nothing else;
  (4) `Migration Status NOT IN ("5 - Deferred By Customer", "6 - Cancelled / Archived",
  "On Hold", "Cancelled")`. Condition (1) is **per report** (`kpi.in_pipeline_scope(fact,
  motion)`, `exporter.pipeline_motion(category)`): AVS and EOS (`MOTION_AVS`) = the offering
  **and no "From AVS" in the path** (`kpi.mentions_from_avs`); AVS → Azure
  Native (`MOTION_NATIVE`) = the path contains "From AVS" (the path only — never an
  offering name). **From AVS counts in AVS → Azure
  Native and nowhere else**; `nodes_planned` (EOS only) always reads `MOTION_AVS`.
  `acr_pipeline` sums Total ACR over them (every report); `nodes_planned` sums Total Cores
  (**EOS reports only**, `exporter.shows_nodes_planned`). Note the rule excludes 5 and 6
  only — a completed wave is kept out by condition 3, since a finished wave reads *Done*,
  not *On Track*.
  **Both are read over the whole dataset, never the reporting period**: work nominated
  before the window is still work still to do. Both renderers take `all_time_where` (the
  sidebar filters with the `_date` key dropped — the same clause the EOS matrix uses) and
  pass that population to `exporter.headline(..., all_time=…)`; every other filter still
  binds, so a region-filtered report reports that region's pipeline. The dashboards need no
  such argument — they read the whole category already.
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
- **Two documents, uploaded separately.** The **FDO Dataset** is the nominations export;
  the **manual EOS tracking sheet** is the programme's own spreadsheet, keyed on **TPID and
  nothing else**. The sheet is *joined* onto the dataset (`eos_tracker.apply_to_fact`),
  never stacked with it — stacking would put rows with no offering, wave or ACR into every
  count. Every other detail (PM, SA, region, offering, ACR, waves) is looked up in the FDO
  dataset by TPID; a sheet TPID the dataset does not hold is reported as unmatched on Data
  & Upload and Data Inconsistency and is **not** counted in any report, the EOS
  Programme Tracker included (see Migration categories). `state.build_dataset(files,
  tracker_files=…)`; overlay columns arrive prefixed `eos_` plus `eos_tracked` and
  `generation_source`, and the `customer` rollup carries them. With no sheet loaded every
  EOS figure is exactly what it was before the sheet existed — that is the test.
- **Reading the sheet** (`eos_tracker.read_tracker_files`, used by `state._read_tracker`):
  the header row is the first of 30 with a TPID header (a title above is fine); in a
  workbook the first sheet with one. TPIDs join as digits (`segments.normalise_tpid`, used
  by `tpid_key` too: `12,039,532` = `12039532.0` = `12039532`). `build_tracker(...,
  dayfirst=)` — Data & Upload's "Dates in the tracking sheet are written" radio
  (`state.tracker_date_order`, session key; folded into the fact cache key, never into
  `ctx.tracker_signature`, which the upload page compares). `report["date_checks"]` holds
  each date column's raw→parsed sample and unparsed values; Data & Upload renders them.
- **`parse_date_series` never raises on a cell**: month-year ("Feb-26") is the 1st; the
  generic fallback only takes values naming day, month **and** year (a 4-digit year, or
  three parts — "13 May 26"), so "1/2" stays blank rather than getting this year; anything
  outside 1900-2200 is NaT (`cleaning._bounded` — "0001-02-03" used to crash the whole
  upload with a pandas AssertionError). Two-digit-year formats are listed explicitly; a
  change here must parse everything the previous version did (compare old vs new on a
  format matrix before committing).
- **Debug page** (`views/debug.py` over `core/diagnostics.py`, Data → Debug): built for a
  user who cannot share the file — one copyable/photographable text block
  (`diagnostics.summary_text`): what is loaded (a loud warning when it is the **bundled
  sample**: uploads live only for the browser session, so a refresh/restart silently
  reverts), the EOS funnel from file to report, every key FDO column with dates written →
  read, the sheet's mapping/dates/unrecognised values, and a per-TPID `trace` giving each
  decision with its reason. `fact["raw_row"]` (position in the combined upload) is what lets
  a trace show a cell as written; `report["scope"]["excluded_tpids"]` names accounts the
  FY25 floor dropped. The sidebar also warns whenever the sample is active.
  `diagnostics.verdicts` leads the page and the text block with the cause in words (sample
  loaded, empty rows skipped, a file contributing nothing, duplicate Task IDs, the last
  failed upload — `state.LAST_FAILURE_KEY`, set by `data_upload._failure_panel` — no EOS
  marker in the FDO file, no/unmatched sheet, period vs all-time); it also lists every
  report's account counts and the top Primary Migration Path / Factory Offering values.
  Two verdicts cover "every page is empty": no report can place any row (paths/offerings
  name neither AVS nor From AVS), and the sidebar period (`components.global_range`,
  passed in by the page) holding none of the rows' Nom. Created Dates
  (`diagnostics.period_line`). `state.set_context` drops any custom date range when a
  different dataset loads — a range picked inside the old file's span can exclude every
  row of the new one.
- **Empty rows are skipped** (`cleaning.build_fact_frame` step 0): a row whose every mapped
  identity column (`_IDENTITY_KEYS`: TPID, name, task, account, wave, offering, path,
  nomination/migration status) is blank is dropped and counted in `report["empty_rows"]`
  / `["empty_rows_by_file"]` — real exports carry hundreds of formatted-but-empty rows,
  which used to become one bogus no-TPID account.
- **EOS Programme Tracker** (`eos_programme.build` → `Programme`): the **sheet itself**, one
  row per TPID the FDO holds (`in_fdo`: a non-From-AVS wave after the floor — the same
  accounts the EOS reports count); the rest go to `Programme.not_in_fdo`, named under the
  tiles and never counted. Name/WW Region/PM/ACR (non From-AVS waves) looked up by TPID. Tiles, by status × gen, by state × gen, status × state,
  SDDC progress, monthly starts/ends, ageing buckets, completed durations, region × status,
  needs attention (Blocked or On Hold), all accounts. Ignores the period and filters.
  Rendered by `views/eos_programme.py`, `exporter._programme_section` and
  `html_report._programme`, placed after the EOS report when
  `exporter.shows_programme(ctx, specs, sections)` (`ReportSections.programme`, default on).
  An empty EOS report states `exporter.tracker_scope_note(ctx)` — e.g. that none of the
  sheet's TPIDs matched the FDO dataset.
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
  reuse `monthly_unique_tpids` / `monthly_hosts`; *migration start* and *migration end*
  take the **EOS tracking sheet's** `Migration Start Date` / `Actual Migration End Date`
  for every account it covers and fall back to the export for the rest
  (`kpi.migration_start_dates`: the earliest wave that actually got going — Current
  State On Track/Done — read from **that wave alone** (`_first_of`), its Actual Start,
  else Planned Start, else Nom. Approval; `kpi.migration_end_dates`: the
  account's latest wave completing, by its Actual End Date). Only the matrix reads them —
  `monthly_migrations_completed`, which the trends and tiles use, is untouched.
  *Engagement end* is **always the export's** (`kpi.engagement_end_dates`): account state
  Completed (the All AVS rule), dated by the latest wave's **Actual End Date** as the export
  records it (`fdo_actual_end_date`, saved by `apply_status` before the sheet fills any
  blank in) — never the sheet's Actual Migration End Date, which dates *migration end*.
  With no sheet the two rows are identical. Blocks come from `exporter.matrix_blocks`
  (+ `matrix_block_rows`, `matrix_block_note`): Gen1→Gen1, Gen1→Gen2, "Generation not
  stated" when present, and last **"All EOS migrations"** (`ALL_EOS_BLOCK`, the blocks
  added together, each TPID once). **In the HTML report every non-zero matrix cell is
  clickable** (`_table(..., cell_drill=panel_id)` writes `data-cell="Measure · Sep-25"`;
  the script's matrix-cell handler filters the block's `_accounts_panel` of
  `kpi.matrix_records` — the very rows each count was made from, bucketed to their month
  and their FY-total column). The explanatory text is one function,
  `exporter.matrix_note`, used by the page, the PDF and the HTML. User-facing text says
  **"FDO export"**, never a bare "the export". Columns run from `config.EOS_MATRIX_START_FY` (FY26 =
  Jul 2025) to the **as-of month**, and every row is counted **up to the as-of date**
  (`kpi._matrix_sources(…, as_of)`, shared by `monthly_matrix` and `matrix_records`) — a
  date after it is not counted, so a tile over Jul 2025 → as-of equals the matrix
  total. Hosts Migrated / ACR Claimed **dedupe Task IDs before windowing**, the order
  the trends use. Custom-range date pickers accept **any date** (`components.PICKER_MIN`
  / `PICKER_MAX`), never just the file's span. **Every month shown**, each
  fiscal year closing with its own total column. The Trend Analysis "Fiscal years
  side by side" grid likewise lists all twelve months. **The reporting period never
  narrows it**, on the dashboard (which draws it from the unfiltered category) or in
  the HTML report (`build_html_report(..., all_time_where=...)` — the sidebar filters
  with the `_date` key dropped, so a region still binds and a window does not): a
  month with no nominations is itself the number being reported.
- **Two export formats, one report.** `exporter.build_report` (PDF) and
  `html_report.build_html_report` (single-file interactive HTML) take the same
  arguments and carry **the same sections in the same order**: summary (over a This-FY row
  whenever the period is something else), EOS programme matrix, trends month by month,
  fiscal years side by side, top accounts by ACR, pipeline, offering cut, regional cut,
  generations, insights, blocked accounts last. They select the same populations through
  the shared public helpers in `exporter` (`headline`, `trends`, `fiscal_year_split`,
  `top_accounts`, `this_fiscal_year`, `unit_noun`, `region_status`, `trend_table`,
  `account_rows`, `format_accounts`, `labelled`, `clean`, `REPORTS`) — add a measure in
  one place, not two, and `test_both_reports_carry_the_same_sections` fails if one drifts.
  The PDF keeps a Part 2 the HTML has no need for: the regional matrix, pipeline counts and
  account records, which a printed page cannot open on demand. The HTML inlines the Plotly
  bundle, the CSS and its script, so it opens offline from an email attachment; that is
  what makes it ~5 MB.
- **Every trend, twice.** `exporter.trends` builds the four monthly measures once for both
  renderers; `exporter.fiscal_year_split` re-cuts each one as one series per fiscal year
  over a shared Jul → Jun axis (`pc.fy_lines_png` in print, `charts.fy_lines` on screen),
  with the month × FY grid beneath it. **The fiscal-year view is read over the whole
  dataset**, never the reporting period — a year-on-year comparison cut to one month has
  nothing to compare — so both renderers pass it the `all_time` population.
- **Top 10 accounts by ACR** (`kpi.top_accounts_by_acr`, `kpi.TOP_ACCOUNTS`): the two broad
  motions only (`exporter.TOP_ACCOUNT_REPORTS` = All AVS, AVS → Azure Native — the EOS
  report's question is which generation, not which account). ACR is summed across **every
  wave**, accounts with none are left out, and the bar is labelled `Customer (TPID)` so no
  two bars can be the same account. All time, never the window. On the dashboards, the ACR
  Trend page and both exports.
- **Stage codes on the regional cut.** `kpi.stage_labels` turns "4 - Executing
  Migration" into the axis label **"Stage 4"** plus a key `[("Stage 4", "Executing
  Migration"), …]`; five full status names on one axis leave the plot a sliver.
  `exporter.region_status` returns `(status×region, region×status, legend)` and both
  renderers print the key under the chart. **The regional cut draws one chart — the
  heatmap.** The stacked bar carried the same numbers; the pivot survives only as the
  PDF drill-down's matrix, and the dashboard's selection moved to a region × stage
  summary table (a heatmap cell cannot be clicked in Streamlit).
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
  Bucket strings are computed in Python so the browser only compares strings — a row that
  belongs to several points carries them pipe-separated and `inBucket` matches any; the
  search box and the chart selection go through one filter so neither undoes the other. Neither
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
- **Money is formatted by column, in one place.** `metrics.MONEY_COLUMNS` /
  `metrics.format_money_frame` decide which columns are money and render them;
  `components.format_money` (dashboards, `fmt_currency`) and `html_report._accounts_frame`
  (exported tables, `fmt_compact_currency`) both defer to it, so no table is the one place
  showing a raw `2400000`. A column already formatted is left alone rather than written
  twice, and Total Cores is rendered as a whole number — a node count reading "36.0" is the
  float leaking.
- **Money reads in K/M everywhere, tooltips included.** `metrics.fmt_compact_currency`
  ($12.5K / $125K / $1.25M) is computed in Python and carried on the trace as
  `customdata`, because Plotly's own SI format writes a lowercase "k" and no symbol —
  pass `currency=True` to `charts.trend_chart` / `bar` / `donut` / `fy_lines` (the factory
  writes the hover, `html_report._Builder.figure` the axis; omitting it on the factory
  leaves an axis reading $1.2M above a tooltip reading 1,250,000).
- **Opt-in sections.** The blocked-accounts block and the methodology in the HTML report
  are `_optional_card`s: a real checkbox plus `.opt-toggle:not(:checked) ~ .opt-body
  { display: none }`, so each is hidden from the first paint with **no script having run** —
  which is what makes it work in a file opened offline. The script only re-measures
  Plotly on reveal (a chart laid out hidden is zero wide). Default unticked, and the
  methodology carries no `doc.anchor`, so it stays out of the contents list.
- **Which sections a report carries** is `exporter.ReportSections(blocked=True,
  insights=False, programme=True, methodology=False)` — the defaults the Reports page
  offers — passed to `build_report` and `build_html_report` alike. **The Methodology &
  logic section is opt-in** (Reports page checkbox, off by default) in both formats; when
  included, the HTML keeps it behind the reader's own "Show methodology & logic" box. Inclusion (build time) and visibility (the reader's checkbox)
  are separate questions.
- **The This-FY row** (`html_report._this_fy`) sits above the selected period's row
  whenever the two differ, mirroring the dashboards — **including over "All time"**, which
  resolves to no window at all: reading "no window" as "nothing to compare against" is what
  used to drop the row from the report while the dashboard still showed it.
- **REQUIREMENT — the methodology on screen must state the logic the code actually
  applies.** Not the intended rule, not a simplification, not an example: the rule as
  implemented. A number a reader cannot reconcile against its stated definition is worse
  than an undocumented one, because they will trust it. So when a metric changes, its
  entry in `glossary.REPORT_METHODOLOGY` changes **in the same commit**, and a test binds
  the two wherever it can (`..._the_pipeline_rule_is_documented_exactly_as_implemented`
  drives its assertions off `kpi.PIPELINE_OFFERING` / `kpi.PIPELINE_EXCLUDED_STATUSES`, so
  editing the code without the words fails the build). Where a stakeholder's description
  of a rule differs from the code, **ask** — do not document the description, and do not
  silently change the code to fit it.
- **Each report states its own methodology: one titled entry per figure, as steps.**
  `glossary.REPORT_METHODOLOGY` is the single source rendered by the PDF, the HTML report
  and the Methodology page (which leads with it), so one figure cannot be documented three
  ways. It is `(heading, items)` where an item is a context paragraph or a
  `glossary.Definition(title, body)` — **43 of them, ~205 bullets**, titled with the name
  the reports actually label the figure by (*New Engagements*, *ACR Pipeline*, *Aging
  (days)*), so a reader holding a number can look it up. `body` is **short bullets, one
  step each**, in the order the code applies them, closing with `Unit: …` on a counted
  figure — never paragraphs and never formulas: a reader checking a number wants the steps,
  and a rule they must decode is one they end up trusting instead of checking.
  **Bold means "this is in the spreadsheet"** — a column name exactly as the file heads it
  (`**Nom. Approval Date**`) or a value exactly as that column holds it
  (`**7 - Completed**`). That convention is the whole point: it is what lets a reader open
  the export and find the same cell. Keep it; do not bold for emphasis.
  Five tests hold the line: `..._is_plain_english_not_formulas` (no `COUNT(`, `SUM(`,
  `IF`/`ELSE`, arrows), `..._is_a_list_of_steps_not_a_wall_of_prose` (2–10 bullets, ≤45
  words each, rendered as real `<li>`s),
  `..._every_headline_figure_is_defined_under_the_name_it_is_shown_by`,
  `..._a_definition_names_the_columns_it_is_read_from` (every entry names a real `schema`
  header, bar five listed derived ones), and
  `..._the_pipeline_rule_is_documented_exactly_as_implemented`.
  **The Methodology page carries no second copy**: it renders this constant first and then
  only what is about the *application* (counting modes, navigation, date presets, uploads,
  drill-down, exports) rather than how a figure is worked out.
- **A generated report names neither the app nor the file it read.** No `Source:` line, no
  dataset on the cover, no app name in the PDF furniture or the HTML footer; the default
  title is `exporter.DEFAULT_TITLE` ("Migration Programme Report").
- **Readable headers in the HTML report.** `html_report._label` maps canonical keys to
  their schema labels, so an account table heads its columns "Customer Name", not
  `customer_name`. The dashboards already did this through `components.column_label`.
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
