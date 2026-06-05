# Installation & Deployment Guide

This guide covers (A) running for end users, (B) building the no‑install portable
Windows bundle, and (C) developer setup.

---

## A. End users — run the packaged app (no installation)

1. Obtain **`AVS_Analytics_Portable.zip`** (built per section B).
2. Extract it anywhere (Desktop, a shared drive, a USB stick…).
3. Open the extracted folder and double‑click **`Start_AVS_Analytics.bat`**.
4. A console window appears ("Starting local dashboard…") and your default browser
   opens at **http://localhost:8501**.
5. To stop the app, close the console window.

**No prerequisites.** Python and every dependency are bundled inside the `runtime\`
folder. Nothing is installed into Windows, the registry, or `PATH`.

The bundle layout:

```
AVS_Analytics_Portable\
├── Start_AVS_Analytics.bat     ← double-click this
├── Home.py
├── app\                        ← application code
├── sample_data\
├── .streamlit\                 ← theme + local-only server config
└── runtime\                    ← private Python 3.11 + libraries
```

---

## B. Build the portable bundle (one‑time, needs internet)

Do this once on a **Windows** machine with internet access. The resulting ZIP is fully
offline and can be copied to air‑gapped machines.

```powershell
# from the repository root
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
```

What it does:

1. Downloads the official **embeddable Python 3.11** distribution.
2. Enables `site-packages` and bootstraps `pip`.
3. `pip install -r requirements.txt` into the private `runtime\` folder.
4. Copies the app, sample data, theme config, and launcher.
5. Produces **`dist\AVS_Analytics_Portable.zip`**.

Options:

```powershell
# pin a different Python patch version or port
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -PythonVersion 3.11.9 -Port 8501
```

> **Why this is the only networked step:** downloading the libraries requires the
> internet *once*, at build time. After the ZIP is produced, the app never needs a
> connection again.

### Notes on the bundle
- Approx. size: ~250–400 MB (mostly pandas/numpy/duckdb/plotly + a bundled Chromium used
  only for PDF chart images).
- The bundle is portable across Windows 10/11 x64 machines.
- To customize the port, edit `--server.port` in `Start_AVS_Analytics.bat` and
  `.streamlit/config.toml`.

---

## C. Developer setup (from source)

**Prerequisites:** Python 3.10+ (3.11 recommended).

```bash
# clone, then:
pip install -r requirements.txt
streamlit run Home.py
```

Or use the convenience launchers (they create a local `.venv` automatically):

| Platform | Launcher |
|----------|----------|
| Windows  | `run_local.bat` |
| macOS    | double‑click `Start_AVS_Analytics.command` |
| macOS / Linux | `./run_local.sh` |

### Running tests

```bash
pip install pytest
python -m pytest tests/test_core.py -v      # correctness on the sample dataset
python tests/stress_test.py 500000          # performance at scale
```

### Regenerating screenshots (optional)

Screenshots in `docs/screenshots/` were captured from the live app. To refresh them you
need a headless Chromium (e.g. `playwright install chromium`) and the app running locally.

---

## Network / firewall

The app binds to **`localhost` only** (`server.address = "localhost"`). It is not exposed
to your LAN or the internet. No inbound firewall rule is required; Windows may still prompt
once for loopback access — you can safely allow or ignore it.

## Offline / air‑gapped deployment

Build the ZIP on a connected machine (section B), copy it to the air‑gapped machine, extract,
and run. No connectivity is needed at runtime.
