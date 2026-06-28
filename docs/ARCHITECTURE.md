# Architecture

## Goals & constraints

- **Local‑first / offline:** no external APIs, no AI, no telemetry, no outbound calls.
- **Runnable by a non‑technical user:** double‑click launcher, no runtimes to install.
- **Executive quality:** clean, branded dashboards and a leadership‑ready PDF.
- **Scale:** responsive at 500k+ rows / 100+ columns.
- **Maintainable:** single language (Python), declarative schema, small focused modules.

## Why Streamlit (not React + FastAPI)

A local single‑user analytics tool benefits most from the simplest robust stack. Streamlit
gives one Python runtime, one process, one port — which makes the "extract‑and‑double‑click"
packaging tractable and the codebase easy to maintain. There is **no REST API and no
separate backend service**; the only network surface is a `localhost`‑bound web server that
renders the UI in the browser (unavoidable for any browser app, and fully on‑device).

DuckDB provides the analytical horsepower so Streamlit only has to render.

## Data flow

```
upload (CSV/XLSX/XLS)
      │  loader.read_raw            → all-string DataFrame (we control every parse)
      ▼
mapping.resolve_mapping            → canonical_key → source_header (auto + saved)
      │
      ▼
cleaning.build_fact_frame          → tidy "fact" frame + cleaning report
      │   • dates (MM-DD-YYYY + fallbacks)
      │   • currency (strips $/commas incl. Indian grouping; rejects dates)
      │   • WW Region normalization (strip numeric prefixes)
      │   • coded status split  "7 - Completed" → (7, "Completed")
      │   • migration_direction + azure_target
      │   • eos_status (vectorised np.select)
      │   • is_approved / is_closed / is_open, aging, cycle time
      │   • per-row data-quality flags
      ▼
rollup.build_customer_rollup       → one row per customer (dedup across waves)
      │   • membership (AV36 EOS / AVS→Azure) = ANY wave matches
      │   • approval date = Wave-1; status/closure = last wave
      │
loader.make_connection             → DuckDB tables `fact` (waves) + `customer` (dedup)
      │     a global toggle picks which table reports query (analytics.use_table)
      │     a reporting *scope* (analytics.apply_scope) keeps "(From AVS)" offerings
      │     out of every primary report (enforced once in the filter sidebar)
      │
      ├── analytics.*  (SQL aggregations: count_by, crosstab, timeseries,
      │                 closure/approval rate, Sankey, stage-by-track, fetch_rows)
      ├── metrics.*    (WTD/MTD/QTD/YTD periods, date-range presets, KPIs, formatting)
      ├── insights.*   (deterministic rules → Insight cards)
      └── exporter.*   (ReportLab PDF + matplotlib static charts — no bundled browser)
      ▼
app/views/*  (13 Streamlit report pages)  ←  app/ui/* (theme, charts, components)
```

## Module map

| Module | Responsibility |
|--------|----------------|
| `app/config.py` | Palette, status colours, paths, constants |
| `app/core/schema.py` | Canonical field catalogue + fuzzy `auto_map` |
| `app/core/loader.py` | File ingest (CSV/XLSX/XLS) → raw frame; DuckDB connection |
| `app/core/cleaning.py` | All parsing, normalization & derived columns; DQ flags |
| `app/core/mapping.py` | Mapping resolution, persistence, coverage |
| `app/core/metrics.py` | Period maths + KPI bundle + formatters |
| `app/core/analytics.py` | DuckDB query helpers (the only place SQL lives) |
| `app/core/rollup.py` | Customer‑level rollup (wave deduplication) |
| `app/core/insights.py` | Deterministic rule‑based insights |
| `app/core/exporter.py` | Section‑based executive PDF assembly |
| `app/ui/theme.py` | CSS, KPI/insight card HTML, headers/banners |
| `app/ui/charts.py` | Plotly chart factory + PNG rendering |
| `app/ui/components.py` | KPI rows, filter sidebar, tables, period KPIs |
| `app/state.py` | Session `DataContext`, cached build steps |
| `app/main.py` | Navigation + sidebar assembly (`run()`) |
| `app/views/*` | The 13 report pages |
| `Home.py` | Entry point (root‑level; keeps `app` importable, avoids `pages/` magic) |

## The canonical schema

The source export carries ~88 columns (many empty or from an unrelated Copilot/Foundry
schema). We map only the fields we report on to stable canonical keys. **Every report
references canonical keys**, so a renamed source column is fixed once in the Column Mapping
screen — never in code. `auto_map` matches headers by exact → normalized → synonym → token
containment, so the standard export and close variants map with zero clicks.

### Key derivations
- **Reporting scope:** `is_from_avs` splits the data — primary reports show AVS Migration
  Nominations (`is_from_avs = FALSE`); the two AVS → Azure Native pages show the
  `"(From AVS)"` offerings (`is_from_avs = TRUE`). Nothing crosses over.
- **Region (geography):** `region_geo` = the part of WW Region before the first " - "
  (Americas / EMEA / ASIA); the segment stays in Customer Segment.
- **Migration direction:** `"… (From AVS)"` → *AVS → Azure Native*; `to AVS` / `EGS` /
  `AV36` / `ODAA` → *Onboard to AVS*.
- **Azure‑native target:** path → destination service (e.g. *SQL Server MI Migration* →
  *Azure SQL Managed Instance*).
- **EOS status:** unified from Current State + Milestone Status + Migration Status code +
  planned‑end vs as‑of, priority Completed → Cancelled → Blocked → At Risk → Delayed →
  At Risk → On Track.
- **Approval/closure:** approval date or status; closure from code 7 / Done / Completed /
  actual end date.

## Performance

- The expensive cleaning build runs **once per upload** and is cached
  (`st.cache_data`); the DuckDB connection is cached as a resource.
- All report aggregations are **SQL over the columnar `fact` table** — sub‑20 ms even at
  500k rows (see `tests/stress_test.py`).
- The EOS derivation is vectorised (`np.select`), keeping the 500k build at ~8 s.

Measured (500k rows × 100 cols, in‑container): build ≈ 8 s, DuckDB ingest ≈ 7 s, every
report query < 20 ms.

## Data quality

Cleaning records a per‑row flag list and an aggregate report. Detected issues in the real
sample include numeric‑prefixed WW Region values, a column‑shifted row (a date in Total ACR,
a currency in Total Cores), and an invalid Customer Segment. These surface in the
**Insights** page and the data‑quality banner rather than silently corrupting metrics.

## Deployment (corporate‑friendly)

The app runs from source — **no compiled launcher, no `.bat`/`.ps1` scripts, and no bundled
browser binary** — which keeps it easy on strict antivirus/EDR policies. You install Python
3.11, create a `.venv`, `pip install -r requirements.txt`, and `streamlit run Home.py`; the
server binds to `127.0.0.1` (loopback) and you open `http://127.0.0.1:8501`. PDF charts are
rendered with matplotlib (not kaleido/Chromium). Full copy‑paste Windows instructions are in
[`INSTALL.md`](INSTALL.md).

## Testing

- `tests/test_core.py` — assertions on parsing, derivations, region geography, reporting
  scope, date‑range presets, DuckDB queries, metrics and insights, validated against the sample.
- `tests/test_app.py` — renders every page (both counting modes) under Streamlit's `AppTest`
  runtime via `tests/_page_harness.py` and asserts no render errors.
- `tests/stress_test.py` — synthetic 500k‑row performance check.
