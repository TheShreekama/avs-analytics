# Windows Setup Guide (copy & paste)

This app runs from source with a normal Python install. **No `.bat`/`.exe`, no
PowerShell download scripts, no bundled browser** — just Python source plus
standard, widely‑whitelisted libraries (pandas, numpy, duckdb, plotly, reportlab,
matplotlib). That keeps it friendly to strict corporate antivirus/EDR policies.

> You do **not** need `run_local.bat` or any launcher script — they were removed.
> You run two short commands yourself (below).

---

## 1. Install Python 3.11 (one time)

Pick **one** option. None require administrator rights — Python installs into your
user profile.

### Option A — official installer (most reliable)
1. Open <https://www.python.org/downloads/windows/> and download **Python 3.11.x**
   (Windows installer, 64‑bit).
2. Run it. On the **first screen**, tick **“Add python.exe to PATH”**, then click
   **“Install Now”**.

### Option B — winget (if your laptop allows it)
Open **PowerShell** (no admin needed) and paste:
```powershell
winget install -e --id Python.Python.3.11 --scope user
```

### Verify
Close and reopen your terminal, then paste:
```powershell
python --version
```
You should see `Python 3.11.x`. If Windows opens the Microsoft Store instead, use
Option A above (the Store stub doesn’t support virtual environments well).

---

## 2. Get the application code

### Option A — download ZIP (no Git needed)
1. On the repository page, click **Code ▸ Download ZIP**.
2. Right‑click the ZIP ▸ **Extract All…** to e.g. `C:\Users\<you>\avs-analytics`.

### Option B — Git (if installed)
```powershell
git clone https://github.com/TheShreekama/avs-analytics.git
```

---

## 3. Install the libraries (one time)

Open **PowerShell** (or Command Prompt), then paste this block. Replace the path on
the first line with where you put the folder.

```powershell
cd "C:\Users\<you>\avs-analytics"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

> **Command Prompt (cmd.exe) instead of PowerShell?** Use this activate line
> instead of the one above:
> ```bat
> .venv\Scripts\activate.bat
> ```

Everything installs into the `.venv` folder **inside the project** — nothing touches
Windows, the registry, or `PATH`. This step needs internet **once**; afterwards the
app runs fully offline.

### Behind a corporate proxy?
If `pip install` fails to reach the internet, set your proxy first (ask IT for the
address), then re‑run the `pip install` line:
```powershell
$env:HTTPS_PROXY = "http://your-proxy:port"
$env:HTTP_PROXY  = "http://your-proxy:port"
pip install -r requirements.txt
```

---

## 4. Run the app

Every time you want to use it, paste these two lines from the project folder:

```powershell
.\.venv\Scripts\Activate.ps1
streamlit run Home.py
```

Then open this address in your browser:

> **http://127.0.0.1:8501**

Use **`http://`** and **`127.0.0.1`** (not `https`, not `localhost`). A bare IP can’t be
force‑upgraded to HTTPS, which avoids the “connection refused” some corporate browsers
cause on local apps. Keep the terminal window open while you use the app; press
**Ctrl+C** (or close the window) to stop it.

---

## 5. Day‑to‑day (after first setup)

```powershell
cd "C:\Users\<you>\avs-analytics"
.\.venv\Scripts\Activate.ps1
streamlit run Home.py
```

To update to a newer version of the code: download/extract the new ZIP (or `git pull`),
then re‑run `pip install -r requirements.txt` once in case dependencies changed.

---

## Why this is antivirus‑friendly

- **No compiled executables** — you run Python source (`streamlit run Home.py`). There is
  no `.exe` to sign or be quarantined.
- **No launcher scripts** — the `.bat`/`.ps1` files were removed; you run plain commands,
  so there’s no script spawning child processes for EDR to flag.
- **No bundled browser** — PDF charts are drawn with **matplotlib**, not a packaged
  Chromium. The interactive dashboard uses Plotly, which is just JavaScript rendered
  inside your own browser.
- **No outbound network at runtime** — the only network is a local web server bound to
  **127.0.0.1** (loopback). Nothing is exposed to the LAN or internet; no telemetry.
- **User‑space only** — Python and the `.venv` live in your profile/project folder; no
  admin rights, no registry changes.

---

## Network / firewall

The server binds to **`127.0.0.1` only** (loopback). It is not reachable from your
network or the internet, so no inbound firewall rule is needed. If Windows Firewall ever
prompts, you can safely **Block** it — loopback still works.

## Troubleshooting

| Symptom | Fix |
|--------|-----|
| `python` opens the Microsoft Store | Install via python.org (step 1, Option A) and re‑open the terminal. |
| `Activate.ps1 cannot be loaded … execution policy` | Run once: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` then re‑run the activate line. (Process scope only; resets when you close the window.) |
| Browser shows `https://…` / “connection refused” | Open **http://127.0.0.1:8501** (http + IP). |
| Browser didn’t open | Open **http://127.0.0.1:8501** manually. |
| `pip install` blocked | Set `HTTPS_PROXY`/`HTTP_PROXY` (step 3) and retry. |
| Port 8501 in use | `streamlit run Home.py --server.port 8600` then open `http://127.0.0.1:8600`. |

---

## Running tests (optional, for developers)

```powershell
pip install pytest
python -m pytest tests/test_core.py tests/test_app.py -v   # correctness + page render
python tests/stress_test.py 500000                          # performance at scale
```
