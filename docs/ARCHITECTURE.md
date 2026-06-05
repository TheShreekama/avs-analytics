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
loader.make_connection             → DuckDB in-memory table `fact`
      │
      ├── analytics.*  (SQL aggregations: count_by, crosstab, timeseries,
      │                 closure/approval rate, Sankey, stage-by-track, fetch_rows)
      ├── metrics.*    (WTD/MTD/QTD/YTD periods, headline KPIs, formatting)
      ├── insights.*   (deterministic rules → Insight cards)
      └── exporter.*   (ReportLab PDF + local Plotly→PNG via kaleido)
      ▼
app/views/*  (11 Streamlit report pages)  ←  app/ui/* (theme, charts, components)
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
| `app/core/insights.py` | Deterministic rule‑based insights |
| `app/core/exporter.py` | Executive PDF assembly |
| `app/ui/theme.py` | CSS, KPI/insight card HTML, headers/banners |
| `app/ui/charts.py` | Plotly chart factory + PNG rendering |
| `app/ui/components.py` | KPI rows, filter sidebar, tables, period KPIs |
| `app/state.py` | Session `DataContext`, cached build steps |
| `app/main.py` | Navigation + sidebar assembly (`run()`) |
| `app/views/*` | The 11 report pages |
| `Home.py` | Entry point (root‑level; keeps `app` importable, avoids `pages/` magic) |

## The canonical schema

The source export carries ~88 columns (many empty or from an unrelated Copilot/Foundry
schema). We map only the fields we report on to stable canonical keys. **Every report
references canonical keys**, so a renamed source column is fixed once in the Column Mapping
screen — never in code. `auto_map` matches headers by exact → normalized → synonym → token
containment, so the standard export and close variants map with zero clicks.

### Key derivations
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

## Packaging

`packaging/build_windows.ps1` assembles a private embeddable‑Python runtime with all wheels
pre‑installed, plus the app, into `AVS_Analytics_Portable.zip`. The launcher
`Start_AVS_Analytics.bat` runs `runtime\python.exe -m streamlit run Home.py` bound to
`localhost` and opens the browser. See [`INSTALL.md`](INSTALL.md).

## Testing

- `tests/test_core.py` — 20 assertions on parsing, derivations, DuckDB queries, metrics and
  insights, validated against the sample.
- `tests/stress_test.py` — synthetic 500k‑row performance check.
- `tests/_page_harness.py` — renders any view under Streamlit's `AppTest` runtime (used to
  smoke‑test all 11 pages for render errors).
