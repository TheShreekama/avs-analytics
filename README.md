# 📈 AVS Migration Analytics

**A professional, 100% local executive dashboard for Azure VMware Solution (AVS) migration analytics and reporting.**

Upload your AVS nominations export (CSV / XLSX / XLS) and instantly get executive
dashboards, trend analysis, a deterministic insights engine, and a one‑click
executive PDF — all running entirely on your own machine.

![Overview](docs/screenshots/01_overview.png)

---

## 🔒 Privacy & Offline Guarantee (read this first)

This application is **standalone and self‑sufficient. It does not talk to the internet.**

- ❌ **No external APIs** — no REST/cloud backend, no third‑party services.
- ❌ **No AI / no LLM** — the insights engine is 100% deterministic rules.
- ❌ **No telemetry, no tracking, no outbound calls** of any kind.
- ✅ **All processing is local** — your data never leaves the machine.
- ✅ The only "server" is a **local web server bound to `localhost`** that draws the
  dashboard in your browser (this is how every browser app works). It is **not reachable
  from your network or the internet** and exchanges data only between your browser and
  your own computer.

The only time an internet connection is used is **once, by the person building the
package**, to download the Python libraries into the bundle. After that, the bundle is
fully self‑contained and runs in an air‑gapped environment.

> Want to verify? There isn't a single `requests`, `urllib`, `httpx`, `socket`, cloud SDK
> or AI client anywhere in the code. The only third‑party libraries are `streamlit`,
> `pandas`, `numpy`, `duckdb`, `plotly`, and `reportlab` — all local compute.

---

## 🚀 Quick Start

### For end users (Windows — no installation required)

1. Extract `AVS_Analytics_Portable.zip`.
2. Double‑click **`Start_AVS_Analytics.bat`**.
3. Your browser opens at **http://localhost:8501**.

That's it. **No Python, Node, Docker, Java, or database to install** — a private Python
runtime is bundled inside the ZIP.

### For developers / from source

**Windows:** double‑click `run_local.bat`
**macOS:** double‑click `Start_AVS_Analytics.command`
**macOS / Linux (terminal):**

```bash
./run_local.sh
```

These create a self‑contained virtual environment on first run (requires Python 3.10+),
then launch the app and open your browser. Or run it manually:

```bash
pip install -r requirements.txt
streamlit run Home.py
```

---

## 📊 The Reports

| # | Report | What it shows |
|---|--------|---------------|
| 🏠 | **Overview** | Portfolio KPIs, status & regional distribution, delivery health, top insights |
| 1 | **Accounts by Migration Status** | Account/nomination counts by status, regional breakdown, donut + stacked bar + heatmap + drill‑down grid |
| 2 | **Nominations Approved** | Approved This‑Week/Month/Quarter/YTD, daily/weekly/monthly trends, regional & path comparison, approval latency |
| 3 | **Nominations Closed** | Closure velocity, closure rate by region, aging, longest‑open & range‑filtered closed lists |
| 4 | **AV36 EOS Status** | Scoped to **AV36/EOS** nominations (any wave with an AV36/EOS path); derived status taxonomy (On Track / Completed / At Risk / Delayed / Blocked / Cancelled), Region × Status heatmap, aging, risk hotspots |
| 5 | **AVS → Azure Native — Status** | Dedicated home for the **"(From AVS)"** offerings (SQL / OSS DB / Windows / Linux migrations). Status, targets, operational health, records — **shown here only**, never mixed into the primary reports |
| 6 | **Nomination Trends** | Monthly / quarterly / yearly volume, cumulative, peaks/troughs, seasonality |
| 7 | **Approved Trend Analysis** | 1/2/3‑year windows, YoY & MoM, cumulative, growth rates (actuals only — no forecasting) |
| 8 | **AVS → Azure Native — Trends** | Sankey flow, path & target distribution, Started/In‑Progress/Completed, completion & backlog, adoption insights |
| 💡 | **Insights** | Full deterministic insights engine, grouped by category |
| 📄 | **Reports & Export** | Build a comprehensive or module‑specific executive **PDF**; CSV exports |
| 📖 | **Methodology & Logic** | Plain‑language reference for every metric, status, scope and insight rule |

Every report has **Region / Status / path filters** and a **date‑range preset**
(This/Last week, This/Last month, Last 3/6 months, This FY, All time, Custom — default
**Last week**), plus an adjustable **"as‑of" date** that anchors the presets and all
This‑Week/Month/Quarter/YTD windows.

### Reporting scope (AVS‑centric)

The dashboard's primary focus is **AVS Migration Nominations** (onboarding *to* AVS).
Offerings whose migration path is **"(From AVS)"** — i.e. migrating *away* from AVS to an
Azure‑native service — are a different motion and are **quarantined to their own two pages**
(*AVS → Azure Native — Status* and *— Trends*). They never appear in any other status or
trend report, so the primary numbers stay clean. **Region** is shown as geography only
(Americas / EMEA / ASIA); the segment lives in **Customer Segment**.

---

## 🧠 Insights Engine (deterministic — no AI)

Rules derived directly from the data, including:

- Highest / lowest approval‑rate region
- Fastest‑closing region & overall closure rate
- Approval velocity (median created→approved latency, slowest region)
- Oldest open nomination
- Most common migration status
- Fastest‑growing migration path (period‑over‑period)
- Top Azure‑native destination & completion rate
- EOS risk hotspots
- ACR concentration
- **Data‑quality issues** (contaminated values, dirty regions, invalid segments, bad dates…)

---

## 🔁 Counting modes & wave deduplication

A customer often has **multiple waves** (Wave‑1, Wave‑2 …). Counting every wave would
double‑count the customer, so the app supports two counting modes via a **global toggle**
in the sidebar:

- **Customer (deduplicated)** — *default*. Each customer counts **once**. Following the
  agreed rules:
  - **Category membership = any wave.** A customer is an **AV36 EOS** nomination if *any*
    of its waves has an AV36/EOS migration path; likewise **AVS → Azure Native** if any
    wave is a from‑AVS path.
  - **Approval date = Wave‑1** (the first/lowest‑numbered wave).
  - **Status = last wave.** If the last wave is done/completed the account is **closed**;
    otherwise it takes the last wave's operational/EOS status.
- **Nomination (wave‑level)** — every wave/row counts (raw detail).

This applies across all reports, so headline numbers reflect real accounts rather than
inflated wave counts. The sidebar shows both totals (e.g. *Waves: 1,240 · Accounts: 815*).

## 📄 Reports & PDF Export

The **Reports** page produces a leadership‑ready PDF. Choose a **comprehensive** report
(all modules) or **select specific modules** (Overview, Approved, Closed, AV36 EOS, Trends,
AVS→Azure, Insights, Tables). Every PDF includes a cover, executive summary, KPI grid,
charts, ranked insights and a generation timestamp. Charts are rendered locally (bundled
Chromium via `kaleido`) — no internet needed. CSV exports of the cleaned data and insights
are available too.

---

## 🗂️ Data & Column Mapping

The app understands the standard AVS nominations export schema out of the box and
**auto‑maps columns** on upload. If your file uses different headers:

- Open **Data & Upload** to load a file and inspect a per‑column fill/quality profile.
- Open **Column Mapping** to map your headers to the analytics fields, then **save the
  mapping** for reuse on future files.

Supported uploads: **CSV, XLSX, XLS**. First row must be headers.

### What the app derives from your data
- **Migration direction** — *Onboard to AVS* vs *AVS → Azure Native* (from the migration path).
- **Azure‑native target** — e.g. *SQL Server MI Migration (From AVS)* → *Azure SQL Managed Instance*.
- **EOS / operational status** — unified from Current State + Milestone Status + Migration
  Status code + planned‑end vs as‑of date.
- **Approval / closure / aging** flags and cycle times.
- **Cleaned values** — currency (incl. Indian "1,92,000" grouping), dates (MM‑DD‑YYYY),
  region normalization (strips numeric prefixes like "1800 Americas - Enterprise").

---

## ⚙️ Architecture

```
Browser (localhost:8501)
        │  (local only)
        ▼
Streamlit UI  ──►  app/views/*   (11 report pages, st.navigation)
        │
        ▼
app/core/   loader → cleaning → DuckDB fact table
            ├─ analytics  (DuckDB SQL aggregations, filters, trends, Sankey)
            ├─ metrics    (WTD/MTD/QTD/YTD, KPIs)
            ├─ insights   (deterministic rules)
            └─ exporter   (ReportLab PDF + local chart images)
```

- **DuckDB** runs all aggregations in‑process for speed at the 500k‑row / 100‑column target.
- **Caching** (`st.cache_data` / `st.cache_resource`) keeps page switches instant.
- Pure‑Python, single runtime — easy to package and maintain.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for details.

---

## 📦 Building the portable Windows bundle

On any Windows machine with internet access (one‑time):

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
```

This downloads embeddable Python, installs the dependencies into a private `runtime\`
folder, copies the app, and produces **`dist\AVS_Analytics_Portable.zip`**. Ship that ZIP.

See [`docs/INSTALL.md`](docs/INSTALL.md) for full packaging & deployment instructions.

---

## 🏎️ Performance

- Target: **500k+ rows, 100+ columns.**
- DuckDB columnar aggregation + cached cleaning keep reports responsive.
- Large files: the cleaned "fact" table is built once per upload and reused across reports.

---

## 📁 Project Structure

```
avs-analytics/
├── Home.py                     # Streamlit entry point (run this)
├── run_local.sh / .bat         # developer launchers (venv)
├── Start_AVS_Analytics.command # macOS launcher
├── requirements.txt
├── app/
│   ├── main.py                 # navigation + sidebar assembly
│   ├── config.py               # palette, paths, constants
│   ├── core/                   # schema, loader, cleaning, mapping,
│   │                           #   metrics, analytics, insights, exporter
│   ├── ui/                     # theme, charts, components
│   └── views/                  # the 11 report pages
├── sample_data/avs_raw_data.csv
├── packaging/
│   ├── Start_AVS_Analytics.bat # user launcher (ships in the bundle)
│   └── build_windows.ps1       # builds the portable ZIP
├── tests/                      # core + app smoke tests
└── docs/                       # INSTALL, ARCHITECTURE, screenshots
```

---

## 🆘 Troubleshooting

- **"Connection refused" / the tab shows `https://localhost:8501`** → your browser
  force‑upgraded the local address to HTTPS, which a local app cannot serve. Open
  **`http://127.0.0.1:8501`** instead — a bare IP is never upgraded or HSTS‑pinned. The
  Windows launchers already bind to and open `127.0.0.1` for this reason.
- **Browser didn't open** → manually visit **http://127.0.0.1:8501**.
- **First run looks stuck** → on a corporate laptop, antivirus may scan every package
  during the one‑time install; give it a few minutes. The launcher waits for the server to
  answer before opening the browser.
- **`pip install` fails behind a proxy** → set `HTTPS_PROXY` / `HTTP_PROXY` (ask IT for the
  address) and re‑run, e.g. `set HTTPS_PROXY=http://your-proxy:port`.
- **Port already in use** → set a different port: `AVS_PORT=8600 ./run_local.sh` (or edit the launcher).
- **"Page not found" on deep links** → use the sidebar navigation; the home page is at `/`.
- **Required fields unmapped after upload** → open **Column Mapping** and map the fields marked •.

---

## 📜 License & Notes

Internal analytics tool. Bundled third‑party libraries retain their respective licenses.
No data is collected or transmitted by this application.
