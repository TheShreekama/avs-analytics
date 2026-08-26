"""Metric rules from the requirements document, verified on a purpose-built file.

The fixture is written as a raw export (source headers, string values) and pushed
through the real mapping → cleaning → classification pipeline, so these tests
cover what the app actually does with a file, not a hand-built fact frame.

Run with:  python -m pytest tests/test_requirements.py -v
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import cleaning, kpi, mapping, rollup, segments  # noqa: E402

# Wave rows: (TPID, name, task, wave, sku, status, approved, actual_end, cores, acr, path)
_ROWS = [
    # A: two waves, latest completed in Jul 2026 -> a completed migration.  Gen-1 (AV36P).
    ("100", "Alpha", "1", "Wave 1", "AV36",  "7 - Completed", "01-10-2026", "02-15-2026", "10", "$100,000", "AV36/AV36P/AV52 - EOS"),
    ("100", "Alpha", "2", "Wave 2", "AV36P", "7 - Completed", "03-01-2026", "07-15-2026", "14", "$50,000",  "AV36/AV36P/AV52 - EOS"),
    # B: Wave 7 completed but Wave 8 still running -> NOT a completed migration.  Gen-1.
    ("200", "Bravo", "3", "Wave 7", "AV52", "7 - Completed",              "01-20-2026", "07-20-2026", "20", "$200,000", "AV36/AV36P/AV52 - EOS"),
    ("200", "Bravo", "4", "Wave 8", "AV52", "4 - Migration In Progress",  "02-20-2026", "",           "8",  "$10,000",  "AV36/AV36P/AV52 - EOS"),
    # C: single wave, only AV64 across every wave -> Gen-2, completed in Aug 2026.
    ("300", "Charlie", "5", "Wave 1", "AV64", "7 - Completed", "02-01-2026", "08-10-2026", "16", "$300,000", "AV64 - EOS"),
    ("300", "Charlie", "6", "Wave 2", "",     "7 - Completed", "02-05-2026", "08-11-2026", "4",  "$5,000",   "AV64 - EOS"),
    # D: EOS marker but blank SKUs everywhere -> Unclassified.
    ("400", "Delta", "7", "Wave 1", "", "2 - Executing Pre-Requisites", "03-15-2026", "", "12", "$80,000", "AV36/AV36P/AV52 - EOS"),
    # E: on-premises onboarding, not EOS -> All AVS Migrations only.
    ("500", "Echo", "8", "Wave 1", "AV64", "4 - Migration In Progress", "04-01-2026", "", "32", "$400,000", "Onprem to AVS"),
    # F: away from AVS -> AVS to Azure Native only.
    ("600", "Foxtrot", "9", "Wave 1", "", "7 - Completed", "05-01-2026", "07-01-2026", "6", "$60,000", "SQL Server MI Migration (From AVS)"),
]

_HEADERS = {
    "tpid": "TPID", "customer_name": "Customer Name", "task_id": "Task ID",
    "phase": "Phase", "avs_sku": "AVS SKU Type", "migration_status": "Migration Status",
    "approval_date": "Nom. Approval Date", "actual_end_date": "Actual End Date",
    "total_cores": "Total Cores", "total_acr": "Total ACR",
    "migration_path": "Primary Migration Path",
}


@pytest.fixture(scope="module")
def fact():
    raw = pd.DataFrame(
        [dict(zip(_HEADERS.values(), row)) for row in _ROWS])
    raw["Factory Offering"] = "AVS Migration Nominations"
    raw["WW Region"] = "Americas - Enterprise"
    raw["Nomination Status"] = "Approved"
    raw["Nom. Created Date"] = raw["Nom. Approval Date"]
    mp = mapping.resolve_mapping(list(raw.columns))
    built, _report = cleaning.build_fact_frame(raw, mp, pd.Timestamp("2026-09-01"))
    return built


def _tpids(records):
    return sorted(records["tpid"].astype(str).unique())


# --------------------------------------------------------------------------- #
# Section 6 — classification
# --------------------------------------------------------------------------- #
def test_generation_is_decided_per_tpid_across_all_waves(fact):
    gen = dict(zip(fact["tpid"].astype(str), fact["generation"]))
    assert gen["100"] == segments.GEN_1          # AV36 + AV36P
    assert gen["200"] == segments.GEN_1          # AV52
    assert gen["300"] == segments.GEN_2          # AV64 only; a blank wave does not disqualify
    assert gen["400"] == segments.GEN_UNCLASSIFIED   # blank SKUs everywhere


def test_gen1_wins_over_gen2_when_both_present():
    assert segments.classify_generation(["AV64", "AV36P"]) == segments.GEN_1
    assert segments.classify_generation(["AV64", "AV64 Node"]) == segments.GEN_2
    assert segments.classify_generation(["", None]) == segments.GEN_UNCLASSIFIED
    assert segments.classify_generation(["AV72"]) == segments.GEN_UNCLASSIFIED


def test_categories_select_the_right_population(fact):
    eos1 = segments.population(fact, segments.CAT_EOS_GEN1)
    eos2 = segments.population(fact, segments.CAT_EOS_GEN2)
    unclassified = segments.population(fact, segments.CAT_EOS_UNCLASSIFIED)
    all_avs = segments.population(fact, segments.CAT_ALL_AVS)
    native = segments.population(fact, segments.CAT_AVS_NATIVE)

    assert _tpids(eos1) == ["100", "200"]
    assert _tpids(eos2) == ["300"]
    assert _tpids(unclassified) == ["400"]
    assert "500" in _tpids(all_avs)              # on-premises onboarding targets AVS
    assert "600" not in _tpids(all_avs)          # away from AVS
    assert _tpids(native) == ["600"]


def test_eos_worksheet_overrides_marker_membership(fact):
    df = fact.copy()
    df["is_eos_population"] = segments.apply_eos_population(df, {"500"})
    assert _tpids(segments.population(df, segments.CAT_EOS_GEN2)) == ["500"]
    assert segments.population(df, segments.CAT_EOS_GEN1).empty


def test_tpid_is_the_matching_key_not_the_account_name(fact):
    df = fact.copy()
    df["customer_name"] = "Same Name Different Systems"
    keys = segments.tpid_key(df)
    assert keys.nunique() == df["tpid"].nunique()


# --------------------------------------------------------------------------- #
# Section 3 / 7 — metric rules
# --------------------------------------------------------------------------- #
def test_new_engagements_counts_unique_tpids_on_wave1_approval(fact):
    eos = segments.population(fact, segments.CAT_EOS_GEN1)
    # Wave-1 approvals: A 10 Jan, B 20 Jan.  A's Wave-2 approval (Mar) must not count.
    m = kpi.new_engagements(eos, "2026-01-01", "2026-01-31")
    assert m.count == 2
    assert _tpids(m.records) == ["100", "200"]
    assert kpi.new_engagements(eos, "2026-03-01", "2026-03-31").count == 0


def test_migration_ends_requires_the_latest_wave_to_be_completed(fact):
    eos = segments.population(fact, segments.CAT_EOS_GEN1)
    m = kpi.migration_ends(eos, "2026-07-01", "2026-07-31")
    # A's last wave completed in July; B has Wave 8 outstanding, so B never counts.
    assert _tpids(m.records) == ["100"]
    assert kpi.migration_ends(eos, None, None).count == 1


def test_hosts_migrated_sums_cores_and_is_not_a_tpid_count(fact):
    eos2 = segments.population(fact, segments.CAT_EOS_GEN2)
    m = kpi.hosts_migrated(eos2, "2026-08-01", "2026-08-31")
    assert m.value == 20            # 16 + 4 across both completed waves of one TPID
    assert m.unit == "hosts"
    assert len(m.records) == 2      # record-level, deliberately not deduplicated to one TPID


def test_hosts_migrated_counts_each_source_record_once(fact):
    eos2 = segments.population(fact, segments.CAT_EOS_GEN2)
    doubled = pd.concat([eos2, eos2], ignore_index=True)
    assert kpi.hosts_migrated(doubled, None, None).value == \
        kpi.hosts_migrated(eos2, None, None).value


def test_nominations_approved_follows_the_selected_window(fact):
    all_avs = segments.population(fact, segments.CAT_ALL_AVS)
    # Jan–Feb: A wave 1, B waves 7 and 8, C waves 1 and 2 — five nomination records.
    assert kpi.nominations_approved(all_avs, "2026-01-01", "2026-02-28").count == 5
    assert kpi.nominations_approved(all_avs, "2026-04-01", "2026-04-30").count == 1


# --------------------------------------------------------------------------- #
# Sections 3.4 / 3.5 / 8 — trends and the cumulative column
# --------------------------------------------------------------------------- #
def test_monthly_tpid_trend_counts_each_tpid_once(fact):
    eos = segments.population(fact, segments.CAT_EOS_GEN1)
    table, _rows = kpi.monthly_unique_tpids(eos, "approval_date")
    assert list(table["period"]) == ["2026-01"]
    assert int(table.loc[0, "Nominations"]) == 2


def test_cumulative_is_the_final_column_and_runs_over_displayed_months(fact):
    table, _rows = kpi.monthly_hosts(segments.population(fact, segments.CAT_ALL_AVS))
    assert list(table.columns)[-1] == "Cumulative"
    assert list(table["Cumulative"]) == list(table["Hosts"].cumsum())


def test_monthly_acr_attributes_each_tpid_once(fact):
    eos = segments.population(fact, segments.CAT_EOS_GEN1)
    table, _rows = kpi.monthly_acr(eos, "approval_date")
    # A: 100k + 50k, B: 200k + 10k — every wave's ACR, counted in one month per TPID.
    assert table["ACR"].sum() == 360_000


# --------------------------------------------------------------------------- #
# Section 3.6 / 3.7 — pipeline
# --------------------------------------------------------------------------- #
def test_state_and_stage_use_the_latest_wave(fact):
    eos = segments.population(fact, segments.CAT_EOS_GEN1)
    states, _rows = kpi.by_state(eos)
    counts = dict(zip(states["category"], states["count"]))
    assert counts.get(kpi.STATE_CLOSED) == 1        # A
    assert counts.get(kpi.STATE_ON_TRACK) == 1      # B, still executing on Wave 8

    stages, stage_rows = kpi.on_track_by_stage(eos)
    assert list(stages["category"]) == ["Migration In Progress"]
    assert int(stages.loc[0, "count"]) == 1
    assert float(stages.loc[0, "acr"]) == 10_000    # B's latest wave


def test_rollup_deduplicates_on_tpid(fact):
    customer = rollup.build_customer_rollup(fact, pd.Timestamp("2026-09-01"))
    assert len(customer) == fact["tpid"].nunique()
    assert set(customer["generation"]) == {segments.GEN_1, segments.GEN_2,
                                           segments.GEN_UNCLASSIFIED}
