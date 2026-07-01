# How to Run — Windows Setup (copy & paste)

This app runs from source with a normal Python install on **Windows**. There are **no
`.bat`/`.exe` launchers, no PowerShell scripts, and no bundled browser** — just Python
source plus standard, widely‑whitelisted libraries (pandas, numpy, duckdb, plotly,
reportlab, matplotlib). That keeps it friendly to strict corporate antivirus/EDR policies.

You do it once (Steps 1–3), then just run one command each time (Step 4).

---

## Step 1 — Install Python 3.11 (one time)

1. Open <https://www.python.org/downloads/windows/> and download the latest
   **Python 3.11.x** “Windows installer (64‑bit)”.
2. Run the installer. On the **first screen**, tick **“Add python.exe to PATH”** (important),
   then click **“Install Now”**. No administrator rights are required — it installs into
   your user profile.
3. **Close and reopen** Command Prompt, then check it works:

```bat
python --version
```

You should see `Python 3.11.x`.
*(If Windows opens the Microsoft Store instead, install from python.org above — the Store
stub doesn’t create virtual environments reliably.)*

---

## Step 2 — Get the application files

Put the project folder somewhere in your user profile, e.g.
`C:\Users\<you>\avs-analytics`.

- **Download ZIP:** on the repository page click **Code ▸ Download ZIP**, then right‑click
  the ZIP ▸ **Extract All…**.
- **Or with Git:** `git clone <repository-url>`

---

## Step 3 — Install the libraries (one time)

Open **Command Prompt**, go to the project folder, and run these two lines:

```bat
cd C:\Users\<you>\avs-analytics
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

- The first line creates a private environment (the `.venv` folder) **inside the project** —
  nothing is installed into Windows, the registry, or `PATH`.
- This step needs internet **once**. Afterwards the app runs fully offline.

> **Behind a corporate proxy?** Set it first (ask IT for the address), then re‑run the
> `pip install` line:
> ```bat
> set HTTPS_PROXY=http://your-proxy:port
> set HTTP_PROXY=http://your-proxy:port
> .venv\Scripts\python.exe -m pip install -r requirements.txt
> ```

---

## Step 4 — Run the app (every time)

From the project folder, run **one** command:

```bat
.venv\Scripts\python.exe -m streamlit run Home.py
```

Then open your browser at:

> ## http://127.0.0.1:8501

Use **`http://`** and **`127.0.0.1`** — **not** `https`, **not** `localhost`. (A bare IP
can’t be force‑upgraded to HTTPS, which avoids the “connection refused” some corporate
browsers cause on local apps.)

Keep the Command Prompt window open while you use the app. To stop it, press **Ctrl+C** or
close the window.

> **Note:** there is deliberately no venv “activate” step — calling
> `.venv\Scripts\python.exe` directly is simpler and avoids PowerShell execution‑policy
> errors. You can paste the Step 4 command into either **Command Prompt** or **PowerShell**.

---

## Every day after setup

Open Command Prompt and run just these two lines:

```bat
cd C:\Users\<you>\avs-analytics
.venv\Scripts\python.exe -m streamlit run Home.py
```

To update to a newer version of the code: replace the files (new ZIP or `git pull`), then
run the Step 3 `pip install` line once more in case dependencies changed.

---

## Why this is antivirus‑friendly

- **No compiled executables** — you run Python source; there is no `.exe` to be quarantined.
- **No launcher scripts** — no `.bat`/`.ps1` spawning child processes for EDR to flag.
- **No bundled browser** — PDF charts are drawn with **matplotlib**; the dashboard uses
  Plotly (JavaScript rendered inside your own browser).
- **No outbound network at runtime** — the only network is a local web server bound to
  **127.0.0.1** (loopback). Nothing is exposed to the LAN or internet; no telemetry.
- **User‑space only** — Python and the `.venv` live in your profile/project folder; no admin
  rights, no registry changes.

---

## Network / firewall

The server binds to **`127.0.0.1` only** (loopback), so it is not reachable from your
network or the internet and needs no inbound firewall rule. If Windows Firewall ever
prompts, you can safely **Block** it — loopback still works.

---

## Troubleshooting

| Symptom | Fix |
|--------|-----|
| `'python' is not recognized` | Python isn’t on PATH — re‑run the installer, tick **“Add python.exe to PATH”**, reopen Command Prompt. |
| `python` opens the Microsoft Store | Install from python.org (Step 1) and reopen the terminal. |
| Browser shows `https://…` / “connection refused” | Open **http://127.0.0.1:8501** (http + the IP). |
| Browser didn’t open | Open **http://127.0.0.1:8501** manually. |
| `pip install` blocked | Set `HTTPS_PROXY`/`HTTP_PROXY` (Step 3) and retry. |
| Port 8501 already in use | `.venv\Scripts\python.exe -m streamlit run Home.py --server.port 8600`, then open `http://127.0.0.1:8600`. |

---

## Running tests (optional, for developers)

```bat
.venv\Scripts\python.exe -m pip install pytest
.venv\Scripts\python.exe -m pytest tests\test_core.py tests\test_app.py -v
```
