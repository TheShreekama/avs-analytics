"""Debug — everything the app read and decided, laid out to be photographed.

When a report comes up empty on a file nobody but its owner can see, the only
way to find out why is to show, step by step, what was read and what each rule
made of it.  This module computes that from the live context; the Debug page
(:mod:`app.views.debug`) renders it, and :func:`summary_text` writes the same
facts as one plain-text block that can be copied or photographed whole.

Nothing here changes a number: it re-reads the context the reports read.
"""
from __future__ import annotations

import pandas as pd

from . import cleaning, eos_tracker, kpi, metrics, schema, segments
from ..config import FY_START_MONTH

#: The FDO columns every EOS figure leans on, in the order a trace reads them.
KEY_FIELDS = ("tpid", "customer_name", "phase", "tags", "migration_path",
              "factory_offering", "linked_offering", "nomination_status",
              "migration_status", "current_state", "created_date",
              "approval_date", "actual_start_date", "actual_end_date",
              "total_cores", "total_acr", "ww_region")

_DATE_KEYS = {f.key for f in schema.CANONICAL_FIELDS if f.dtype == "date"} \
    if hasattr(schema.CANONICAL_FIELDS[0], "dtype") else set()


def _label(key: str) -> str:
    field = schema.CANONICAL_BY_KEY.get(key)
    return field.label if field is not None else key


def _is_date(key: str) -> bool:
    return key in _DATE_KEYS or key.endswith("_date")


def _sample(values: pd.Series, n: int = 3) -> str:
    seen = [str(v) for v in values.dropna().astype(str).str.strip().unique() if str(v)]
    return " | ".join(v[:40] for v in seen[:n])


# --------------------------------------------------------------------------- #
# What is loaded
# --------------------------------------------------------------------------- #
def loaded(ctx) -> list[tuple[str, str]]:
    """What the app is reading right now — the first thing to rule out."""
    from ..version import build_stamp
    built, fingerprint = build_stamp()
    tracker_read = getattr(ctx, "tracker_report", None) or {}
    order = {None: "detected per column", True: "day first",
             False: "month first"}[tracker_read.get("dayfirst")]
    rows = [
        ("Build", f"{built} · {fingerprint}"),
        ("FDO dataset", "BUNDLED SAMPLE — not your file" if ctx.is_sample
         else ctx.filename),
        ("FDO rows / accounts", f"{len(ctx.fact):,} waves · "
                                f"{ctx.fact['tpid_key'].nunique():,} TPIDs"
         if not ctx.fact.empty else "0"),
        ("Reporting floor", _floor_line(ctx)),
        ("As-of date", f"{pd.Timestamp(ctx.as_of):%d %b %Y}"),
        ("EOS tracking sheet", ctx.tracker_filename if ctx.has_tracker
         else "NOT LOADED"),
    ]
    if ctx.has_tracker:
        overlay = ctx.report.get("tracker") or {}
        rows += [("Sheet rows / accounts",
                  f"{tracker_read.get('rows', 0):,} rows · "
                  f"{tracker_read.get('accounts', 0):,} TPIDs"),
                 ("Sheet TPIDs found in FDO",
                  f"{overlay.get('matched_accounts', 0):,} of "
                  f"{tracker_read.get('accounts', 0):,}"),
                 ("Sheet date order", order)]
        for note in tracker_read.get("files") or []:
            rows.append(("Sheet read from",
                         f"{note['file']}"
                         + (f" · sheet '{note['sheet']}'" if note.get("sheet") else "")
                         + f" · headers on row {note.get('header_row') or '–'}"))
    return rows


def _floor_line(ctx) -> str:
    scope = ctx.report.get("scope") or {}
    if not scope:
        return "–"
    return (f"{scope.get('floor_fy', '')} onwards — dropped "
            f"{scope.get('excluded_rows', 0):,} waves, "
            f"{scope.get('excluded_accounts', 0):,} whole accounts")


# --------------------------------------------------------------------------- #
# The EOS funnel
# --------------------------------------------------------------------------- #
def eos_funnel(ctx, window: tuple | None = None) -> pd.DataFrame:
    """Accounts at each step from "in the file" to "in the EOS report"."""
    fact = ctx.fact
    rows: list[tuple[str, int, str]] = []
    if fact.empty:
        return pd.DataFrame(rows, columns=["Step", "Accounts", "What it means"])
    acc = fact.drop_duplicates("tpid_key")
    tagged = segments.generation_by_tpid(fact)
    by_tag = tagged.isin((segments.GEN_1, segments.GEN_2))
    path = fact.groupby("tpid_key")["is_av36_eos"].any()
    scope = ctx.report.get("scope") or {}
    rows.append(("FDO accounts nominated before the floor (dropped)",
                 int(scope.get("excluded_accounts", 0)),
                 f"Every wave dated before {scope.get('floor_fy', 'FY25')}; "
                 "not in any report"))
    rows.append(("FDO accounts kept", len(acc), "Unique TPIDs after the floor"))
    rows.append(("…with an AVS Migration - Gen1/Gen2 tag on any wave",
                 int(by_tag.sum()), "Read from the Tags column"))
    rows.append(("…on an AV36/AV36P/AV52 - EOS path or offering",
                 int(path.sum()), "Read from Primary Migration Path, Factory "
                                  "Offering and Linked Offering"))
    if ctx.has_tracker:
        read = ctx.tracker_report or {}
        overlay = ctx.report.get("tracker") or {}
        tracked = acc[acc[eos_tracker.TRACKED_FLAG].astype(bool)]
        rows.append(("Accounts in the tracking sheet", int(read.get("accounts", 0)),
                     "Unique TPIDs in the sheet"))
        rows.append(("…whose TPID is in the FDO dataset",
                     int(overlay.get("matched_accounts", 0)),
                     "Reported with their FDO waves, ACR and cores"))
        counted = set(fact.loc[segments.eos_population(fact, sheet=True).to_numpy(),
                               "tpid_key"])
        dropped = int((~ctx.tracker["tpid_key"].isin(counted)).sum())
        rows.append(("…not counted as EOS", dropped,
                     "Not in the FDO dataset, or only From AVS / pre-floor waves "
                     "there: no ACR, cores or waves to report"))
        stated = (ctx.tracker["target_generation"]
                  .isin((segments.GEN_1, segments.GEN_2)))
        rows.append(("…with a readable Target SDDC Generation",
                     int(stated.sum()), "Gen1 / Gen2; the rest are EOS with "
                                        "the generation not stated"))
    else:
        gen = acc["generation"].isin((segments.GEN_1, segments.GEN_2))
        rows.append(("Accounts with a generation tag", int(gen.sum()),
                     "What puts an account in EOS scope without a sheet"))
        leaving = acc["is_from_avs"].astype(bool)
        rows.append(("…of those, (From AVS) moves — never EOS",
                     int((gen & leaving).sum()),
                     "Primary Migration Path contains From AVS"))
    eos = segments.population(fact, segments.CAT_EOS_ALL)
    rows.append(("EOS Migrations (All) — accounts", int(eos["tpid_key"].nunique())
                 if not eos.empty else 0, "What the EOS report counts, all time"))
    unclassified = segments.population(fact, segments.CAT_EOS_UNCLASSIFIED)
    rows.append(("EOS by path but no generation (left out)",
                 int(unclassified["tpid_key"].nunique()) if not unclassified.empty else 0,
                 "Listed on Data Inconsistency"))
    if not eos.empty:
        start, end = window or metrics.date_preset_range(ctx.as_of, "This FY",
                                                         FY_START_MONTH)[:2]
        created = pd.to_datetime(eos["created_date"], errors="coerce")
        inside = eos[created.between(start, end)]
        rows.append((f"…with a Nom. Created Date {start:%d %b %Y} – {end:%d %b %Y}",
                     int(inside["tpid_key"].nunique()) if not inside.empty else 0,
                     "What a This-FY report shows; All time shows the line above"))
        no_date = eos[created.isna()]
        rows.append(("…with no readable Nom. Created Date",
                     int(no_date["tpid_key"].nunique()) if not no_date.empty else 0,
                     "Left out of any dated period"))
        waves = kpi.wave_index(eos)
        states = kpi.account_state(eos, waves.last).value_counts()
        rows.append(("EOS accounts by state",
                     int(states.sum()),
                     ", ".join(f"{k} {v}" for k, v in states.items())))
    return pd.DataFrame(rows, columns=["Step", "Accounts", "What it means"])


# --------------------------------------------------------------------------- #
# The verdict — said in words before any table
# --------------------------------------------------------------------------- #
def _this_fy(ctx) -> tuple:
    return metrics.date_preset_range(ctx.as_of, "This FY", FY_START_MONTH)[:2]


def period_line(ctx, period: tuple | None) -> str:
    """How much of the data the sidebar's reporting period lets through."""
    fact = ctx.fact
    if not period or period[0] is None:
        return "All time — no date filter"
    start, end = pd.Timestamp(period[0]), pd.Timestamp(period[1])
    created = pd.to_datetime(fact["created_date"], errors="coerce") \
        if not fact.empty else pd.Series(dtype="datetime64[ns]")
    inside = created.between(start, end)
    accounts = fact.loc[inside, "tpid_key"].nunique() if not fact.empty else 0
    span = (f"{created.min():%d %b %Y} – {created.max():%d %b %Y}"
            if created.notna().any() else "none readable")
    return (f"{start:%d %b %Y} – {end:%d %b %Y}: {int(inside.sum()):,} of "
            f"{len(fact):,} waves ({accounts:,} accounts) have a Nom. Created Date "
            f"inside it. Your Nom. Created Dates run {span}.")


def verdicts(ctx, last_failure: dict | None = None,
             period: tuple | None = None) -> list[str]:
    """Why the reports show what they show, in plain sentences, worst first."""
    out: list[str] = []
    fact = ctx.fact
    if ctx.is_sample:
        out.append("The BUNDLED SAMPLE is loaded, not your file. Upload again on "
                   "Data & Upload (uploads last only for the browser session).")
    if getattr(ctx, "has_eos_list", False):
        applied = ctx.report.get("eos_list") or {}
        out.append(f"All EOS customers list loaded ({int(applied.get('listed_accounts', 0)):,} "
                   f"TPIDs): AVS → Azure Native keeps {int(applied.get('native_kept', 0)):,} "
                   f"customer(s) and leaves out {int(applied.get('native_excluded', 0)):,} "
                   "not on the list.")
    empty = int(ctx.report.get("empty_rows", 0))
    if empty:
        where = ", ".join(f"{f} ({n:,})" for f, n in
                          (ctx.report.get("empty_rows_by_file") or {}).items())
        out.append(f"{empty:,} of {int(ctx.report.get('n_rows', 0)):,} rows in the "
                   f"FDO file(s) were empty — no TPID, name, wave, offering or status "
                   f"— and are skipped" + (f": {where}." if where else "."))
    for row in files_report(ctx).to_dict("records"):
        if row["Rows kept"] == 0:
            out.append(f"File '{row['File']}' contributed no usable rows — its "
                       "headers are not the ones the other file uses, or it has a "
                       "title above the header row.")
    dupes = int(ctx.report.get("duplicate_task_ids", 0) or 0)
    if dupes:
        out.append(f"{dupes:,} Task IDs appear more than once — if both files are "
                   "exports of the same view, upload only the newer one.")
    if last_failure:
        out.append(f"The last upload FAILED ({last_failure['when']}): "
                   f"{last_failure['file']} at '{last_failure['stage']}' — "
                   f"{last_failure['message']}")
    if fact.empty:
        out.append("No usable FDO rows are loaded.")
        return out
    # Every report: a page is empty either because no row belongs to it, or
    # because none of its rows falls in the reporting period.
    cats = categories(ctx).set_index("Report")["Accounts (all time)"]
    if cats.sum() == 0:
        top = value_report(ctx, "migration_path", 5)
        shown = "; ".join(f"'{v}' ({n})" for v, n in top.itertuples(index=False))
        out.append("NO REPORT HAS ANY ACCOUNT: a row reaches All AVS Migrations when "
                   "its Primary Migration Path / Factory Offering names AVS ('to AVS', "
                   "'AVS Migration' …) and AVS → Azure Native when the path contains "
                   f"'From AVS'. Your most common paths: {shown}.")
    if period and period[0] is not None and not fact.empty:
        start, end = pd.Timestamp(period[0]), pd.Timestamp(period[1])
        created = pd.to_datetime(fact["created_date"], errors="coerce")
        if not created.between(start, end).any():
            out.append(f"NOTHING FALLS IN THE REPORTING PERIOD: the sidebar is set to "
                       f"{start:%d %b %Y} – {end:%d %b %Y} and no row has a Nom. Created "
                       f"Date inside it, so every dated page is empty. Set the sidebar's "
                       f"Date range to All time.")
    tagged = int(segments.generation_by_tpid(fact)
                 .isin((segments.GEN_1, segments.GEN_2)).sum())
    path = int(fact.groupby("tpid_key")["is_av36_eos"].any().sum())
    if not tagged and not path:
        out.append("Your FDO file marks NO account as EOS: no wave's Tags contain "
                   "'AVS Migration - Gen1' or '- Gen2', and no Primary Migration "
                   "Path, Factory Offering or Linked Offering reads 'AV36/AV36P/AV52 "
                   "- EOS'. With this file, EOS accounts can only come from the EOS "
                   "tracking sheet.")
    if not ctx.has_tracker:
        out.append("No EOS tracking sheet is loaded in this session"
                   + (" — so every EOS report is empty." if not tagged else ".")
                   + " Upload it on Data & Upload, section 2 (both uploads are "
                   "needed every time the app starts).")
    else:
        read = ctx.tracker_report or {}
        overlay = ctx.report.get("tracker") or {}
        accounts, matched = int(read.get("accounts", 0)), int(overlay.get("matched_accounts", 0))
        if not accounts:
            out.append("The tracking sheet is loaded but no row has a TPID.")
        elif not matched:
            out.append(f"None of the sheet's {accounts:,} TPIDs is in the FDO "
                       "dataset, so there is no EOS account to report — compare "
                       "the two TPID columns below.")
        elif matched < accounts:
            out.append(f"{matched:,} of the sheet's {accounts:,} TPIDs are in the FDO "
                       f"dataset; the other {accounts - matched:,} are NOT counted as "
                       "EOS (no ACR, cores or waves to report) and are listed on "
                       "Data Inconsistency.")
        if accounts:
            out.append("The sheet is the list of EOS accounts: its TPIDs that the "
                       "FDO dataset holds are reported as EOS, and an account the "
                       "FDO export tags as EOS but the sheet omits is not.")
        if accounts and read.get("no_generation", 0) == accounts:
            out.append("The sheet's Target SDDC Generation could not be read for any "
                       "account (column: "
                       f"{(read.get('mapping') or {}).get('target_generation') or 'NOT FOUND'}"
                       "), so none of them falls in the Gen-1 or Gen-2 blocks.")
    eos = segments.population(fact, segments.CAT_EOS_ALL)
    n_eos = int(eos["tpid_key"].nunique()) if not eos.empty else 0
    if n_eos:
        start, end = _this_fy(ctx)
        created = pd.to_datetime(eos["created_date"], errors="coerce")
        inside = int(eos.loc[created.between(start, end), "tpid_key"].nunique())
        out.append(f"EOS has {n_eos:,} accounts over all time; {inside:,} have a Nom. "
                   f"Created Date in This FY ({start:%d %b %Y} – {end:%d %b %Y}). "
                   "A This-FY report shows only those — choose All time for the rest.")
    else:
        out.append("RESULT: 0 EOS accounts, so every EOS report says 'No nominations "
                   "fall into this report'.")
    return out


def files_report(ctx) -> pd.DataFrame:
    """Each uploaded FDO file: rows read, rows skipped as empty, rows kept."""
    raw = ctx.raw
    col = schema.SOURCE_FILE_COLUMN
    if raw is None or raw.empty or col not in raw.columns:
        return pd.DataFrame(columns=["File", "Rows read", "Empty rows skipped",
                                     "Rows kept", "Accounts"])
    read = raw[col].astype(str).value_counts()
    empty = ctx.report.get("empty_rows_by_file") or {}
    fact = ctx.fact
    kept = (fact["source_file"].astype(str).value_counts()
            if "source_file" in fact.columns else pd.Series(dtype=int))
    accounts = (fact.groupby(fact["source_file"].astype(str))["tpid_key"].nunique()
                if "source_file" in fact.columns and not fact.empty
                else pd.Series(dtype=int))
    return pd.DataFrame([{
        "File": f, "Rows read": int(n), "Empty rows skipped": int(empty.get(f, 0)),
        "Rows kept": int(kept.get(f, 0)), "Accounts": int(accounts.get(f, 0)),
    } for f, n in read.items()])


def categories(ctx) -> pd.DataFrame:
    """Every report's population: accounts over all time, and in This FY."""
    fact = ctx.fact
    start, end = _this_fy(ctx)
    rows = []
    for cat, label in segments.CATEGORY_LABELS.items():
        pop = segments.population(fact, cat) if not fact.empty else fact
        if pop.empty:
            rows.append({"Report": label, "Accounts (all time)": 0,
                         "Created This FY": 0, "New Engagements This FY": 0})
            continue
        created = pd.to_datetime(pop["created_date"], errors="coerce")
        rows.append({
            "Report": label,
            "Accounts (all time)": int(pop["tpid_key"].nunique()),
            "Created This FY": int(pop.loc[created.between(start, end),
                                           "tpid_key"].nunique()),
            "New Engagements This FY": kpi.new_engagements(pop, start, end).count,
        })
    return pd.DataFrame(rows)


def value_report(ctx, key: str, n: int = 10) -> pd.DataFrame:
    """The most common values of one FDO column, as read."""
    fact = ctx.fact
    if fact.empty or key not in fact.columns:
        return pd.DataFrame()
    counts = (fact[key].astype("string").fillna("(blank)").value_counts().head(n))
    return pd.DataFrame({_label(key): [str(v)[:70] for v in counts.index],
                         "Rows": counts.to_numpy()})


# --------------------------------------------------------------------------- #
# Columns as read
# --------------------------------------------------------------------------- #
def column_report(ctx) -> pd.DataFrame:
    """Each key FDO field: the column it was read from, how full it is, and —
    for a date — how many cells were understood, with examples of the rest."""
    raw, mapping = ctx.raw, ctx.mapping or {}
    out = []
    for key in KEY_FIELDS:
        src = mapping.get(key)
        row = {"Field": _label(key), "Your column": src or "— NOT MAPPED —",
               "Filled": "", "Examples as written": "", "Read as": ""}
        if src and src in raw.columns:
            values = raw[src].astype("string").str.strip().replace({"": pd.NA})
            row["Filled"] = f"{int(values.notna().sum()):,} of {len(values):,}"
            row["Examples as written"] = _sample(values)
            if _is_date(key):
                parsed = cleaning.parse_date_series(raw[src])
                failed = values.notna() & parsed.isna()
                example = values[values.notna() & parsed.notna()].head(1)
                shown = (f"{example.iloc[0]} → {parsed[example.index[0]]:%d %b %Y}"
                         if len(example) else "")
                row["Read as"] = (f"{int((values.notna() & parsed.notna()).sum()):,} "
                                  f"dates read; {int(failed.sum()):,} not"
                                  + (f" (e.g. {_sample(values[failed], 2)})"
                                     if failed.any() else "")
                                  + (f" · {shown}" if shown else ""))
        out.append(row)
    return pd.DataFrame(out)


def tag_report(ctx, n: int = 8) -> pd.DataFrame:
    """The most common Tags values, and the generation each one reads as."""
    fact = ctx.fact
    if fact.empty or "tags" not in fact.columns:
        return pd.DataFrame()
    counts = (fact["tags"].astype("string").fillna("(blank)").value_counts()
              .head(n))
    return pd.DataFrame({
        "Tags value": [v[:80] for v in counts.index],
        "Rows": counts.to_numpy(),
        "Reads as": [segments.generation_from_tags([v]) or "no generation"
                     for v in counts.index],
    })


def tpid_join(ctx, n: int = 6) -> pd.DataFrame:
    """TPIDs from each side, raw and as matched — the join, made visible."""
    if not ctx.has_tracker:
        return pd.DataFrame()
    sheet = ctx.tracker[["tpid", "tpid_key"]].head(n)
    fdo_keys = set(ctx.fact["tpid_key"]) if not ctx.fact.empty else set()
    fdo_col = (ctx.mapping or {}).get("tpid")
    fdo_raw = (ctx.raw[fdo_col].astype("string").dropna().drop_duplicates().head(n)
               if fdo_col and fdo_col in ctx.raw.columns else pd.Series(dtype="string"))
    rows = []
    for i in range(max(len(sheet), len(fdo_raw))):
        rows.append({
            "Sheet TPID as written": sheet["tpid"].iloc[i] if i < len(sheet) else "",
            "Matched as": sheet["tpid_key"].iloc[i] if i < len(sheet) else "",
            "In FDO?": ("yes" if sheet["tpid_key"].iloc[i] in fdo_keys else "NO")
            if i < len(sheet) else "",
            "FDO TPID as written": fdo_raw.iloc[i] if i < len(fdo_raw) else "",
            "FDO matched as": (segments.normalise_tpid(fdo_raw.iloc[[i]]).iloc[0]
                               if i < len(fdo_raw) else ""),
        })
    return pd.DataFrame(rows).astype(str).replace({"<NA>": ""})


# --------------------------------------------------------------------------- #
# One account, end to end
# --------------------------------------------------------------------------- #
_TRACE_COLUMNS = (("phase", "Wave"), ("tags", "Tags"),
                  ("migration_path", "Primary Migration Path"),
                  ("factory_offering", "Factory Offering"),
                  ("nomination_status", "Nomination Status"),
                  ("fdo_migration_status", "Migration Status (FDO)"),
                  ("migration_status", "Migration Status (used)"),
                  ("fdo_current_state", "Current State (FDO)"),
                  ("current_state", "Current State (used)"),
                  ("status_source", "Status from"))
_TRACE_DATES = ("created_date", "approval_date", "actual_end_date")


def trace(ctx, tpid: str) -> dict:
    """Everything about one TPID: its rows as written and as read, the sheet's
    row, and every decision taken on it — with the reason for each."""
    key = segments.normalise_tpid(pd.Series([str(tpid)])).iloc[0]
    out: dict = {"key": key, "verdicts": [], "waves": pd.DataFrame(),
                 "sheet": pd.DataFrame()}
    if pd.isna(key):
        out["verdicts"].append("That is not a TPID the app can read.")
        return out
    fact = ctx.fact
    rows = fact[fact["tpid_key"] == key] if not fact.empty else fact
    scope = ctx.report.get("scope") or {}
    raw_col = (ctx.mapping or {}).get("tpid")
    in_raw = (segments.normalise_tpid(ctx.raw[raw_col]).eq(key).sum()
              if raw_col and raw_col in ctx.raw.columns else 0)
    v = out["verdicts"]

    if rows.empty:
        if key in set(scope.get("excluded_tpids") or []):
            v.append(f"In the FDO file ({int(in_raw)} rows) but every wave was "
                     f"nominated before the {scope.get('floor_fy')} reporting "
                     f"floor, so it was dropped before anything was counted.")
        elif in_raw:
            v.append(f"In the FDO file ({int(in_raw)} rows) but not in the data "
                     "the reports read — see the floor line above.")
        else:
            v.append("NOT in the FDO dataset at all.")
        if ctx.has_tracker and key in set(ctx.tracker["tpid_key"]):
            v.append("It is in the tracking sheet, but NOT counted as an EOS "
                     "account: with no FDO wave there is no ACR, cores or waves "
                     "to report.")
    else:
        v.append(f"In the FDO dataset: {len(rows)} wave(s).")
        waves = pd.DataFrame({label: rows[col].astype("string") if col in rows.columns
                              else "" for col, label in _TRACE_COLUMNS})
        if "raw_row" in rows.columns and not ctx.raw.empty:
            for key_ in _TRACE_DATES:
                src = (ctx.mapping or {}).get(key_)
                written = (ctx.raw[src].iloc[rows["raw_row"].astype(int)].astype("string")
                           .to_numpy() if src and src in ctx.raw.columns
                           else [""] * len(rows))
                read = pd.to_datetime(rows[key_], errors="coerce").dt.strftime("%d %b %Y")
                waves[f"{_label(key_)} (written → read)"] = [
                    f"{w if pd.notna(w) else ''} → {r if pd.notna(r) else 'BLANK'}"
                    for w, r in zip(written, read)]
        out["waves"] = waves.fillna("")

        first = rows.iloc[0]
        tag_gen = segments.generation_from_tags(rows["tags"].tolist()) \
            if "tags" in rows.columns else None
        v.append(f"Gen tag in the FDO Tags: {tag_gen or 'none'}.")
        v.append(f"EOS path/offering marker: "
                 f"{'yes' if bool(rows['is_av36_eos'].any()) else 'no'}.")
        v.append(f"Generation used: {first['generation']} "
                 f"(decided by {first.get(eos_tracker.GENERATION_SOURCE, '–')}).")
        if bool(rows["is_from_avs"].any()):
            v.append("Has a (From AVS) wave — those waves are reported under AVS → "
                     "Azure Native only.")
        cats = [label for cat, label in segments.CATEGORY_LABELS.items()
                if not segments.population(rows, cat).empty]
        v.append("Appears in: " + (", ".join(cats) if cats else "no report"))
        lasts = kpi.latest_wave(rows)
        state = kpi.account_state(rows, lasts).iloc[0]
        stated = kpi.tracker_account_state(lasts).iloc[0]
        v.append(f"Account state: {state} ("
                 + ("from the tracking sheet" if pd.notna(stated)
                    else "from the FDO waves") + ").")
        created = pd.to_datetime(rows["created_date"], errors="coerce").min()
        start, end = metrics.date_preset_range(ctx.as_of, "This FY", FY_START_MONTH)[:2]
        if pd.isna(created):
            v.append("No readable Nom. Created Date — left out of every dated "
                     "period; shows under All time only.")
        else:
            inside = start <= created <= end
            v.append(f"Earliest Nom. Created Date {created:%d %b %Y} — "
                     + ("inside" if inside else "OUTSIDE")
                     + f" This FY ({start:%d %b %Y} – {end:%d %b %Y}).")

    if ctx.has_tracker:
        sheet = ctx.tracker[ctx.tracker["tpid_key"] == key]
        if sheet.empty:
            v.append("Not in the EOS tracking sheet.")
        else:
            row = sheet.iloc[0]
            v.append(f"In the tracking sheet: generation "
                     f"{row.get('target_generation') or 'not readable'}, status "
                     f"{row.get('migration_status') or 'not readable'} "
                     f"(written: {row.get('status_raw') or 'blank'}), state "
                     f"{row.get('current_state') or 'not readable'} "
                     f"(written: {row.get('state_raw') or 'blank'}).")
            out["sheet"] = pd.DataFrame([{
                "TPID": row["tpid"],
                "Target SDDC Generation": row.get("target_generation") or "",
                "Migration Status (written)": row.get("status_raw") or "",
                "Migration Status (read)": row.get("migration_status") or "",
                "Current State (written)": row.get("state_raw") or "",
                "Current State (read)": row.get("current_state") or "",
                "Start (written → read)": _written_read(
                    row.get("migration_start_date_raw"), row.get("migration_start_date")),
                "End (written → read)": _written_read(
                    row.get("migration_end_date_raw"), row.get("migration_end_date")),
            }]).astype(str).replace({"<NA>": "", "nan": "", "None": ""})
    return out


def _written_read(written, read) -> str:
    w = "" if written is None or pd.isna(written) else str(written)
    r = "BLANK" if read is None or pd.isna(read) else f"{pd.Timestamp(read):%d %b %Y}"
    return f"{w} → {r}"


def example_tpids(ctx, n: int = 8) -> list[str]:
    """TPIDs worth tracing: tracked accounts first, then tagged ones."""
    picks: list[str] = []
    if ctx.has_tracker:
        picks += [str(t) for t in ctx.tracker["tpid"].head(n)]
    if not ctx.fact.empty:
        tagged = ctx.fact[ctx.fact["generation"].isin((segments.GEN_1, segments.GEN_2))]
        picks += [str(t) for t in tagged["tpid"].drop_duplicates().head(n)]
    return list(dict.fromkeys(picks))[:n]


# --------------------------------------------------------------------------- #
# One block to copy or photograph
# --------------------------------------------------------------------------- #
def summary_text(ctx, funnel: pd.DataFrame | None = None,
                 columns: pd.DataFrame | None = None,
                 traced: dict | None = None,
                 last_failure: dict | None = None,
                 period: tuple | None = None) -> str:
    """The whole diagnosis as plain text, short enough for one screen."""
    lines = ["== VERDICT =="]
    lines += [f"* {v}" for v in verdicts(ctx, last_failure, period)]
    lines.append("== LOADED ==")
    lines += [f"{k}: {val}" for k, val in loaded(ctx)]
    lines.append(f"Sidebar reporting period: {period_line(ctx, period)}")
    files = files_report(ctx)
    if not files.empty:
        lines.append("== FDO FILES (read / empty skipped / kept / accounts) ==")
        lines += [f"{r['File']}: {r['Rows read']:,} / {r['Empty rows skipped']:,} / "
                  f"{r['Rows kept']:,} / {r['Accounts']:,}"
                  for r in files.to_dict("records")]
    lines.append("== REPORTS (accounts all time / created This FY / new engagements This FY) ==")
    lines += [f"{r['Report']}: {r['Accounts (all time)']:,} / {r['Created This FY']:,} / "
              f"{r['New Engagements This FY']:,}" for r in categories(ctx).to_dict("records")]
    for key in ("migration_path", "factory_offering"):
        values = value_report(ctx, key, 8)
        if not values.empty:
            lines.append(f"== TOP {_label(key).upper()} VALUES ==")
            lines += [f"{n:>6,}  {v}" for v, n in values.itertuples(index=False)]
    funnel = eos_funnel(ctx) if funnel is None else funnel
    lines.append("== EOS FUNNEL ==")
    for step, count, note in funnel.itertuples(index=False):
        tail = f"  [{note}]" if step == "EOS accounts by state" else ""
        lines.append(f"{count:>7,}  {step}{tail}")
    columns = column_report(ctx) if columns is None else columns
    lines.append("== FDO COLUMNS ==")
    for r in columns.to_dict("records"):
        extra = f" | {r['Read as']}" if r["Read as"] else ""
        lines.append(f"{r['Field']}: {r['Your column']} | {r['Filled']}{extra}")
    if ctx.has_tracker:
        read = ctx.tracker_report or {}
        lines.append("== SHEET COLUMNS ==")
        for f in eos_tracker.TRACKER_FIELDS:
            lines.append(f"{f.label}: {(read.get('mapping') or {}).get(f.key) or 'NOT FOUND'}")
        for key, c in (read.get("date_checks") or {}).items():
            lines.append(f"{c['label']}: {c['parsed']} of {c['filled']} read"
                         + (f"; not read: {', '.join(c['unparsed'][:4])}"
                            if c["unparsed"] else ""))
        if read.get("unrecognised_status"):
            lines.append("Status not recognised: "
                         + ", ".join(read["unrecognised_status"][:6]))
        if read.get("unrecognised_state"):
            lines.append("State not recognised: "
                         + ", ".join(read["unrecognised_state"][:6]))
    if traced:
        lines.append(f"== TRACE {traced.get('key')} ==")
        lines += traced.get("verdicts", [])
    return "\n".join(lines)
