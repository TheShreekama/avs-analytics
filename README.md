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
- ✅ The only "server" is a **local web server bound to `127.0.0.1`** (loopback) that draws
  the dashboard in your browser (this is how every browser app works). It is **not reachable
  from your network or the internet** and exchanges data only between your browser and
  your own computer.

The only time an internet connection is used is **once, when you install the Python
libraries** (`pip install`). After that, the app runs fully offline / air‑gapped.

> Want to verify? There isn't a single `requests`, `urllib`, `httpx`, `socket`, cloud SDK
> or AI client anywhere in the code. The only third‑party libraries are `streamlit`,
> `pandas`, `numpy`, `duckdb`, `plotly`, `reportlab` and `matplotlib` — all local compute,
> **no bundled browser/Chromium** and no compiled launcher.

---

## 🚀 Quick Start (Windows)

Install Python once, then run **one command** whenever you want the app. There are **no
`.bat`/`.exe` launchers and no scripts** — which keeps it friendly to strict corporate
antivirus/EDR.

**1. Install Python 3.11 (one time).** Download it from
[python.org](https://www.python.org/downloads/windows/); on the first installer screen tick
**“Add python.exe to PATH”**, then click **Install Now** (no admin rights needed).

**2. Set up the app (one time).** Open **Command Prompt**, `cd` into the project folder, and run:

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**3. Run the app (every time).** From the same folder:

```bat
.venv\Scripts\python.exe -m streamlit run Home.py
```

**4. Open your browser** at **http://127.0.0.1:8501**
(use `http://` and `127.0.0.1` — **not** `https`, **not** `localhost`).

Keep the terminal window open while using the app; close it or press **Ctrl+C** to stop.
No activation step, no admin, no registry changes. Full walk‑through with proxy tips and
troubleshooting: **[`docs/INSTALL.md`](docs/INSTALL.md)**.

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
| 6 | **Trend Analysis → Nomination Trends** | Unique TPIDs nominated per month, in every migration category |
| 7 | **Trend Analysis → ACR Trend** | ACR claimed per month, by each wave's Actual End Date, in every category |
| 8 | **Trend Analysis → Nodes Deployed** | Total Cores completed per month, across the AVS motions |
| 9 | **Trend Analysis → Cores Migrated** | The same measure for AVS → Azure Native, under the noun that motion uses |
| 10 | **Trend Analysis → Migrations Completed** | Unique TPIDs whose latest wave completed, per month, in every category |
| 💡 | **Insights** | Full deterministic insights engine, grouped by category |
| 📄 | **Reports & Export** | A two‑part management **PDF** — three executive reports plus their drill‑downs, with contents, bookmarks and cross‑links; CSV exports |
| 📖 | **Methodology & Logic** | Plain‑language reference for every metric, status, scope and insight rule |

Every report has **Region / Status / path filters** and a **date‑range preset**
(This/Last week, This/Last month, Last 3/6 months, This FY, All time, Custom — default
**All time**, so every report opens on the whole dataset), plus an adjustable **"as‑of" date** that anchors the presets and all
This‑Week/Month/Quarter/YTD windows.

### Reporting floor (FY25 onwards)

The dashboard reports from **FY25** (1 Jul 2024) onwards. Waves nominated earlier are
dropped **as the file is read** — before the customer rollup and before the SQL tables
are registered — so no chart, table, total, insight, CSV or PDF can include them, and
**"All time" means FY25 onwards** everywhere. A wave belongs to the fiscal year of its
nomination date (approval date, else creation date); a wave carrying neither cannot be
shown to be out of scope, so it stays. Every page reports how much was excluded.
Configurable via `AVS_REPORTING_FLOOR_FY`.

### Reporting scope (AVS‑centric)

The dashboard's primary focus is **AVS Migration Nominations** (onboarding *to* AVS).
Offerings whose migration path is **"(From AVS)"** — i.e. migrating *away* from AVS to an
Azure‑native service — are a different motion and are **reported on their own**
(*Migration Analytics → AVS → Azure Native*, its Status report, and its own section of
each Trend Analysis page). They never get mixed into another category's numbers, so the
primary figures stay clean. **Region** is shown as geography only
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
charts, ranked insights and a generation timestamp. Charts are rendered locally with
**matplotlib** (no bundled browser) — no internet needed. CSV exports of the cleaned data
and insights are available too.

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
Streamlit UI  ──►  app/views/*   (13 report pages, st.navigation)
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

## 🏢 Corporate / locked‑down laptops

This app is deliberately easy on antivirus/EDR policies:

- **No compiled executables and no launcher scripts** (`.bat`/`.ps1`) — you run plain
  Python source (`streamlit run Home.py`).
- **No bundled browser/Chromium** — PDF charts use matplotlib; the dashboard uses Plotly
  inside your own browser.
- **User‑space only** — Python + the `.venv` live in your profile; no admin, no registry.
- **Loopback only** — the server binds to `127.0.0.1`; nothing is exposed to the network.

See **[`docs/INSTALL.md`](docs/INSTALL.md)** for the full copy‑paste Windows setup, proxy
tips, and troubleshooting.

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
├── requirements.txt
├── app/
│   ├── main.py                 # navigation + sidebar assembly
│   ├── config.py               # palette, paths, scope & date-preset constants
│   ├── core/                   # schema, loader, cleaning, rollup, mapping,
│   │                           #   metrics, analytics, insights, exporter
│   ├── ui/                     # theme, charts (Plotly), pdf_charts (matplotlib), components
│   └── views/                  # the 13 report pages
├── sample_data/avs_raw_data.csv
├── tests/                      # core + app smoke tests
└── docs/                       # INSTALL (Windows setup), ARCHITECTURE, screenshots
```

---

## 🆘 Troubleshooting

- **`python` is not recognized** → Python isn't on PATH. Re‑run the installer and tick
  **“Add python.exe to PATH”**, then open a new Command Prompt.
- **`python` opens the Microsoft Store** → install from
  [python.org](https://www.python.org/downloads/windows/) instead, then reopen the terminal.
- **"Connection refused" / the tab shows `https://…`** → your browser force‑upgraded the
  address to HTTPS, which a local app cannot serve. Open **`http://127.0.0.1:8501`**
  (with `http://` and the `127.0.0.1` IP) — a bare IP is never upgraded or HSTS‑pinned.
- **Browser didn't open** → open **http://127.0.0.1:8501** manually.
- **First run looks slow** → on a corporate laptop, antivirus may scan every package during
  the one‑time `pip install`; give it a few minutes.
- **`pip install` fails behind a proxy** → set the proxy, then re‑run the install command:
  `set HTTPS_PROXY=http://your-proxy:port` (ask IT for the address).
- **Port 8501 already in use** → `.venv\Scripts\python.exe -m streamlit run Home.py --server.port 8600`
  then open `http://127.0.0.1:8600`.
- **Required fields unmapped after upload** → open **Column Mapping** and map the fields marked •.

---

## 📜 License & Notes

Internal analytics tool. Bundled third‑party libraries retain their respective licenses.
No data is collected or transmitted by this application.
