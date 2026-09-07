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

from app.config import DIR_OTHER  # noqa: E402
from app.core import (cleaning, kpi, loader, mapping, metrics, nulls, rollup,  # noqa: E402
                      schema, segments)

# Wave rows: (TPID, name, task, wave, sku, status, approved, actual_end, cores, acr, path)
_ROWS = [
    # A: two waves, latest completed in Jul 2026 -> a completed migration.  Gen-1 (AV36P).
    ("100", "Alpha", "1", "Wave 1", "AV36",  "7 - Completed", "01-10-2026", "02-15-2026", "10", "$100,000", "AV36/AV36P/AV52 - EOS"),
    ("100", "Alpha", "2", "Wave 2", "AV36P", "7 - Completed", "03-01-2026", "07-15-2026", "14", "$50,000",  "AV36/AV36P/AV52 - EOS"),
    # B: Wave 7 completed but Wave 8 still running -> NOT a completed migration.  Gen-1.
    ("200", "Bravo", "3", "Wave 7", "AV52", "7 - Completed",              "01-20-2026", "07-20-2026", "20", "$200,000", "AV36/AV36P/AV52 - EOS"),
    ("200", "Bravo", "4", "Wave 8", "AV52", "4 - Migration In Progress",  "02-20-2026", "",           "8",  "$10,000",  "AV36/AV36P/AV52 - EOS"),
    # C: tagged Gen2 -> Gen-2, completed in Aug 2026.  The migration path reads the
    # same as every other EOS row: the tag, not the path, distinguishes generations.
    ("300", "Charlie", "5", "Wave 1", "AV64", "7 - Completed", "02-01-2026", "08-10-2026", "16", "$300,000", "AV36/AV36P/AV52 - EOS"),
    ("300", "Charlie", "6", "Wave 2", "",     "7 - Completed", "02-05-2026", "08-11-2026", "4",  "$5,000",   "AV36/AV36P/AV52 - EOS"),
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


# "Current State" is what decides On-Track.  Written with the real vocabulary of
# the export, including the states that are emphatically *not* on track.
_CURRENT_STATE = {
    "1": "Done", "2": "Done",                 # A — both waves finished
    "3": "Done", "4": "On Track",             # B — Wave 8 still running, on track
    "5": "Done", "6": "Done",                 # C — finished
    "7": "Blocked - Customer",                # D — blocked, so NOT on track
    "8": "Waiting action on follow up date",  # E — waiting, so NOT on track
    "9": "Done",                              # F
}


# The Tags column is what puts an account in EOS scope and fixes its generation.
# Written the way the real export writes them: several tags glued together.
_TAGS = {
    "100": "Qualify and AccelerateAVS Migration - Gen1",
    "200": "Qualify and AccelerateFCS On Hold Reach OutAVS Migration - Gen1",
    "300": "InternalAVS Migration - Gen2",
    "400": "None of the above",            # EOS offering, but no generation tag
    "500": "None of the above",
    "600": "None of the above",
}


@pytest.fixture(scope="module")
def raw_frame():
    raw = pd.DataFrame([dict(zip(_HEADERS.values(), row)) for row in _ROWS])
    raw["Factory Offering"] = "AVS Migration Nominations"
    raw["WW Region"] = "Americas - Enterprise"
    raw["Nomination Status"] = "Approved"
    raw["Nom. Created Date"] = raw["Nom. Approval Date"]
    raw["Tags"] = raw["TPID"].map(_TAGS)
    raw["Current State"] = raw["Task ID"].map(_CURRENT_STATE)
    return raw


@pytest.fixture(scope="module")
def fact(raw_frame):
    mp = mapping.resolve_mapping(list(raw_frame.columns))
    built, _report = cleaning.build_fact_frame(raw_frame, mp, pd.Timestamp("2026-09-01"))
    return built


def _tpids(records):
    return sorted(records["tpid"].astype(str).unique())


# --------------------------------------------------------------------------- #
# Section 6 — classification
# --------------------------------------------------------------------------- #
def test_generation_is_decided_per_tpid_across_all_waves(fact):
    gen = dict(zip(fact["tpid"].astype(str), fact["generation"]))
    assert gen["100"] == segments.GEN_1          # tagged Gen1 on a wave
    assert gen["200"] == segments.GEN_1          # tag buried mid-string
    assert gen["300"] == segments.GEN_2          # tagged Gen2
    assert gen["400"] == segments.GEN_UNCLASSIFIED   # no generation tag anywhere


def test_gen1_wins_over_gen2_when_both_present():
    assert segments.classify_generation(
        ["InternalAVS Migration - Gen2", "AVS Migration - Gen1"]) == segments.GEN_1
    assert segments.classify_generation(["InternalAVS Migration - Gen2"]) == segments.GEN_2
    assert segments.classify_generation(["", None]) == segments.GEN_UNCLASSIFIED
    # SKU values alone never classify an account — only the tag does.
    assert segments.classify_generation(["AV36P"]) == segments.GEN_UNCLASSIFIED


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


def test_one_tagged_wave_makes_the_whole_account_eos(fact):
    """The generation tag defines EOS scope, per account, from a single wave."""
    membership = segments.eos_population(fact)
    # 100/200/300 by tag; 400 through the EOS migration-path fallback.
    assert sorted(fact.loc[membership, "tpid"].astype(str).unique()) == \
        ["100", "200", "300", "400"]
    # Every wave of a qualifying account is in scope, not just the tagged one.
    assert int(membership[fact["tpid"].astype(str) == "100"].sum()) == 2
    # 500 has neither a generation tag nor an EOS offering.
    assert not membership[fact["tpid"].astype(str) == "500"].any()


def test_eos_path_is_the_fallback_when_no_wave_is_tagged(fact):
    """No Gen1/Gen2 tag anywhere -> the "AV36/AV36P/AV52 - EOS" path decides."""
    untagged = segments.population(fact, segments.CAT_EOS_UNCLASSIFIED)
    assert _tpids(untagged) == ["400"]
    # It is in the EOS population, but carries no generation.
    assert set(untagged["generation"]) == {segments.GEN_UNCLASSIFIED}
    assert untagged["is_eos_population"].all()


def test_the_same_eos_path_carries_either_generation(raw_frame):
    """AV36/AV36P/AV52 - EOS is shared: only the tag separates Gen-1 from Gen-2."""
    df = raw_frame.copy()
    df["Primary Migration Path"] = "AV36/AV36P/AV52 - EOS"
    mp = mapping.resolve_mapping(list(df.columns))
    built, _ = cleaning.build_fact_frame(df, mp, pd.Timestamp("2026-09-01"))
    by_tpid = built.drop_duplicates("tpid_key").set_index(built.drop_duplicates(
        "tpid_key")["tpid"].astype(str))["generation"]
    assert by_tpid["100"] == segments.GEN_1          # Gen1-tagged, on that path
    assert by_tpid["300"] == segments.GEN_2          # Gen2-tagged, same path
    assert by_tpid["400"] == segments.GEN_UNCLASSIFIED   # untagged, same path
    # All three are EOS accounts; the tag only decides which page they land on.
    assert segments.eos_population(built).all()


def test_a_tag_brings_an_account_in_without_an_eos_path(raw_frame):
    """The tag alone is enough — the offering need not read as EOS."""
    df = raw_frame.copy()
    df["Primary Migration Path"] = "Onprem to AVS"          # no EOS marker anywhere
    df.loc[df["TPID"] == "500", "Tags"] = "InternalAVS Migration - Gen2"
    mp = mapping.resolve_mapping(list(df.columns))
    built, _ = cleaning.build_fact_frame(df, mp, pd.Timestamp("2026-09-01"))
    gen2 = segments.population(built, segments.CAT_EOS_GEN2)
    assert "500" in gen2["tpid"].astype(str).tolist()
    assert segments.population(built, segments.CAT_EOS_UNCLASSIFIED).empty


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


def test_migrations_completed_requires_the_latest_wave_to_be_completed(fact):
    eos = segments.population(fact, segments.CAT_EOS_GEN1)
    m = kpi.migrations_completed(eos, "2026-07-01", "2026-07-31")
    # A's last wave completed in July; B has Wave 8 outstanding, so B never counts.
    assert _tpids(m.records) == ["100"]
    assert kpi.migrations_completed(eos, None, None).count == 1


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


def test_the_dropped_nominations_approved_metric_is_gone(fact):
    """Removed from the executive summary, and with it the metric behind it."""
    assert not hasattr(kpi, "nominations_approved")


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


def test_acr_claimed_sums_the_waves_that_ended_in_the_window(fact):
    eos = segments.population(fact, segments.CAT_EOS_GEN1)
    # Waves with an Actual End Date: A/W1 Feb $100k, A/W2 Jul $50k, B/W7 Jul $200k.
    # B/W8 never ended, so its $10k is not claimed by anything.
    assert kpi.acr_claimed(eos, None, None).value == 350_000
    july = kpi.acr_claimed(eos, "2026-07-01", "2026-07-31")
    assert july.value == 250_000                 # two waves, two different accounts
    assert len(july.records) == 2
    assert kpi.acr_claimed(eos, "2026-09-01", "2026-09-30").value == 0


def test_monthly_acr_claimed_splits_by_the_month_each_wave_ended(fact):
    eos = segments.population(fact, segments.CAT_EOS_GEN1)
    table, _rows = kpi.monthly_acr_claimed(eos)
    assert list(table["period"]) == ["2026-02", "2026-07"]
    assert list(table["ACR Claimed"]) == [100_000, 250_000]
    assert list(table.columns)[-1] == "Cumulative"
    assert table["ACR Claimed"].sum() == kpi.acr_claimed(eos, None, None).value


# --------------------------------------------------------------------------- #
# Section 3.6 / 3.7 — pipeline
# --------------------------------------------------------------------------- #
def test_state_and_stage_use_the_latest_wave(fact):
    eos = segments.population(fact, segments.CAT_EOS_GEN1)
    states, _rows = kpi.by_state(eos)
    counts = dict(zip(states["category"], states["count"]))
    assert counts.get(kpi.STATE_COMPLETED) == 1    # A
    assert counts.get(kpi.STATE_ON_TRACK) == 1      # B, still executing on Wave 8

    stages, stage_rows = kpi.on_track_by_stage(eos)
    assert list(stages["category"]) == ["Migration In Progress"]
    assert int(stages.loc[0, "count"]) == 1
    assert float(stages.loc[0, "acr"]) == 10_000    # B's latest wave


def test_on_track_reads_current_state_not_merely_unfinished(fact):
    all_avs = segments.population(fact, segments.CAT_ALL_AVS)
    # B's Wave 8 says "On Track".  D is "Blocked - Customer" and E is "Waiting
    # action on follow up date" — both unfinished, neither on track.
    assert _tpids(kpi.on_track_accounts(all_avs).records) == ["200"]


def test_state_chart_reports_only_on_track_and_completed(fact):
    all_avs = segments.population(fact, segments.CAT_ALL_AVS)
    states, rows = kpi.by_state(all_avs)
    assert set(states["category"]) <= set(kpi.REPORTED_STATES)
    counts = dict(zip(states["category"], states["count"]))
    assert counts[kpi.STATE_COMPLETED] == 2         # A and C
    assert counts[kpi.STATE_ON_TRACK] == 1          # B
    assert "400" not in set(rows["tpid"])           # blocked is not a reported state
    # Every state is still available on request, for anyone who needs the rest.
    everything, _ = kpi.by_state(all_avs, only=None)
    assert everything["count"].sum() == all_avs["tpid_key"].nunique()


def test_rollup_deduplicates_on_tpid(fact):
    customer = rollup.build_customer_rollup(fact, pd.Timestamp("2026-09-01"))
    assert len(customer) == fact["tpid"].nunique()
    assert set(customer["generation"]) == {segments.GEN_1, segments.GEN_2,
                                           segments.GEN_UNCLASSIFIED}


# --------------------------------------------------------------------------- #
# Generation from the Tags column
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("tag,expected", [
    ("Qualify and AccelerateAVS Migration - Gen1", segments.GEN_1),
    ("InternalAVS Migration - Gen2", segments.GEN_2),
    # Tags are concatenated with no separator, and the marker can sit mid-string.
    ("Qualify and AccelerateFCS On Hold Reach OutAVS Migration - Gen1", segments.GEN_1),
    ("Something elseAVS Migration - Gen2Another tag", segments.GEN_2),
    ("AVS Migration – Gen2", segments.GEN_2),        # en dash
    ("AVS Migration-Gen1", segments.GEN_1),          # no spaces
    ("AVS Migration Gen2", segments.GEN_2),          # no dash at all
    ("None of the above", None),
    ("", None),
])
def test_generation_from_tags(tag, expected):
    assert segments.generation_from_tags([tag]) == expected


def test_only_the_tag_classifies_an_account():
    assert segments.classify_generation(["AVS Migration - Gen1"]) == segments.GEN_1
    assert segments.classify_generation(["AVS Migration - Gen2"]) == segments.GEN_2
    assert segments.classify_generation(["None of the above"]) == segments.GEN_UNCLASSIFIED


def test_generation_uses_tags_when_skus_are_blank(raw_frame):
    """The real export carries blank SKUs and the generation in Tags."""
    df = raw_frame.copy()
    df["AVS SKU Type"] = ""
    df["Tags"] = ["Qualify and AccelerateAVS Migration - Gen1"] * 4 + \
                 ["InternalAVS Migration - Gen2"] * 2 + ["None of the above"] * 3
    mp = mapping.resolve_mapping(list(df.columns))
    built, _ = cleaning.build_fact_frame(df, mp, pd.Timestamp("2026-09-01"))
    gen = dict(zip(built["tpid"].astype(str), built["generation"]))
    assert gen["100"] == segments.GEN_1
    assert gen["300"] == segments.GEN_2
    assert gen["400"] == segments.GEN_UNCLASSIFIED


def test_eos_categories_need_no_side_worksheet(fact):
    """There is one dataset: nothing in the pipeline asks for an EOS worksheet."""
    assert not hasattr(segments, "apply_eos_population")
    assert not hasattr(segments, "eos_tpids_from_worksheet")
    assert segments.eos_population(fact).any()


def test_glossary_explains_every_headline_metric():
    from app.core import glossary
    for text in (glossary.NEW_ENGAGEMENTS, glossary.MIGRATIONS_COMPLETED,
                 glossary.HOSTS_MIGRATED, glossary.ON_TRACK_ACCOUNTS,
                 glossary.ACR_CLAIMED, glossary.GENERATION_RULE):
        assert len(text) > 80                      # a real explanation, not a label
    assert "Tags" in glossary.GENERATION_RULE
    assert "latest wave" in glossary.MIGRATIONS_COMPLETED
    assert "Current State" in glossary.ON_TRACK_ACCOUNTS
    assert "ACTUAL END DATE" in glossary.ACR_CLAIMED
    assert set(glossary.CATEGORY_HELP) == set(segments.CATEGORY_LABELS)


# --------------------------------------------------------------------------- #
# Data consistency: generation tag vs. EOS migration path
# --------------------------------------------------------------------------- #
def test_eos_consistency_reports_both_mismatches(raw_frame):
    df = raw_frame.copy()
    # 500 keeps its "Onprem to AVS" path but gains a Gen-2 tag -> tagged, no EOS
    # path.  400 already sits on the EOS path with no tag -> path, no tag.
    df.loc[df["TPID"] == "500", "Tags"] = "InternalAVS Migration - Gen2"
    mp = mapping.resolve_mapping(list(df.columns))
    built, _ = cleaning.build_fact_frame(df, mp, pd.Timestamp("2026-09-01"))

    issues = segments.eos_consistency(built)
    assert _tpids(issues["tagged_without_eos_path"]) == ["500"]
    assert _tpids(issues["eos_path_without_tag"]) == ["400"]
    # Wave-level on the path side: every offending wave is listed.
    assert len(issues["eos_path_without_tag"]) == \
        int((built["tpid"].astype(str) == "400").sum())


def test_a_clean_file_reports_no_inconsistency(raw_frame):
    df = raw_frame.copy()
    df["Primary Migration Path"] = "AV36/AV36P/AV52 - EOS"
    df["Tags"] = "Qualify and AccelerateAVS Migration - Gen1"
    mp = mapping.resolve_mapping(list(df.columns))
    built, _ = cleaning.build_fact_frame(df, mp, pd.Timestamp("2026-09-01"))
    issues = segments.eos_consistency(built)
    assert all(frame.empty for frame in issues.values())


def test_every_eos_account_is_also_an_all_avs_migration(fact):
    """EOS accounts roll up into All AVS Migrations, whatever their own path says."""
    eos = fact[fact["is_eos_population"].astype(bool) & ~fact["is_from_avs"].astype(bool)]
    all_avs = segments.population(fact, segments.CAT_ALL_AVS)
    assert set(_tpids(eos)) <= set(_tpids(all_avs))


def test_from_avs_stays_out_of_every_other_category_even_when_tagged(raw_frame):
    """AVS → Azure Native is reported on its own page and nowhere else.

    A "(From AVS)" nomination is leaving AVS. Counting it under All AVS
    Migrations (onboarding TO AVS) or EOS Migration (refreshing ageing AVS
    hosts) would put it in the wrong story — so not even a Gen-1 tag pulls it in.
    """
    df = raw_frame.copy()
    df.loc[df["TPID"] == "600", "Tags"] = "AVS Migration - Gen1"   # a (From AVS) path
    mp = mapping.resolve_mapping(list(df.columns))
    built, _ = cleaning.build_fact_frame(df, mp, pd.Timestamp("2026-09-01"))
    assert _tpids(segments.population(built, segments.CAT_AVS_NATIVE)) == ["600"]
    for category in (segments.CAT_ALL_AVS, segments.CAT_EOS_ALL,
                     segments.CAT_EOS_GEN1, segments.CAT_EOS_GEN2):
        assert "600" not in _tpids(segments.population(built, category)), category
    # ...and it is not counted into the EOS population at all.
    assert not built.loc[built["tpid"] == "600", "is_eos_population"].any()


def test_combined_eos_tab_is_the_union_of_its_generations(fact):
    """The EOS Migration tab holds Gen-1, Gen-2 and the untagged EOS accounts."""
    combined = segments.population(fact, segments.CAT_EOS_ALL)
    gen1 = segments.population(fact, segments.CAT_EOS_GEN1)
    gen2 = segments.population(fact, segments.CAT_EOS_GEN2)
    untagged = segments.population(fact, segments.CAT_EOS_UNCLASSIFIED)

    assert _tpids(combined) == ["100", "200", "300", "400"]
    assert set(_tpids(gen1)) | set(_tpids(gen2)) | set(_tpids(untagged)) == \
        set(_tpids(combined))
    # The parts do not overlap, so the combined count is their sum.
    assert len(gen1) + len(gen2) + len(untagged) == len(combined)
    assert combined["is_eos_population"].all()


# --------------------------------------------------------------------------- #
# Presentation rules that apply everywhere
# --------------------------------------------------------------------------- #
def test_every_table_renders_money_as_currency():
    """ACR is $1.2M / $840.0K wherever it appears — no caller can forget it."""
    from app.ui.components import format_money
    frame = pd.DataFrame({"total_acr": [1_200_000, 840_000, 500, None],
                          "acr": [2_000_000.0, 0.0, 1.0, 3.0],
                          "total_cores": [10, 20, 30, 40],
                          "customer_name": ["A", "B", "C", "D"]})
    out = format_money(frame)
    assert list(out["total_acr"]) == ["$1.20M", "$840.0K", "$500", "—"]
    assert out.loc[0, "acr"] == "$2.00M"
    assert list(out["total_cores"]) == [10, 20, 30, 40]   # counts stay numeric
    assert list(out["customer_name"]) == ["A", "B", "C", "D"]
    assert list(frame["total_acr"])[0] == 1_200_000       # the source is untouched


def test_money_formatting_leaves_already_formatted_columns_alone():
    """A table that formatted its own ACR is not double-formatted."""
    from app.ui.components import format_money
    frame = pd.DataFrame({"ACR": ["$1.20M", "$840.0K"]})
    assert list(format_money(frame)["ACR"]) == ["$1.20M", "$840.0K"]


# --------------------------------------------------------------------------- #
# Fiscal-year split — the "All time" view of every trend
# --------------------------------------------------------------------------- #
def test_fiscal_year_label_names_the_year_the_fy_ends_in():
    from app.core.metrics import fiscal_month_order, fiscal_year_label
    assert fiscal_year_label("2026-07-01") == "FY27"     # first day of FY27
    assert fiscal_year_label("2027-06-30") == "FY27"     # last day of FY27
    assert fiscal_year_label("2026-06-30") == "FY26"
    assert fiscal_month_order()[0] == "Jul"
    assert fiscal_month_order()[-1] == "Jun"
    assert len(fiscal_month_order()) == 12


def test_split_by_fiscal_year_keeps_every_month_and_its_total(fact):
    all_avs = segments.population(fact, segments.CAT_ALL_AVS)
    table, rows = kpi.monthly_unique_tpids(all_avs, "approval_date")
    split = kpi.split_by_fiscal_year(table, "Nominations")
    assert split["Nominations"].sum() == table["Nominations"].sum()
    assert len(split) == len(table)
    # Every month lands in the fiscal year that contains it, Jul→Jun: January
    # 2026 belongs to FY26 (Jul 2025 → Jun 2026), where A and B were approved.
    assert dict(zip(split["bucket"], split["Nominations"]))["FY26 Jan"] == 2
    # Cumulative is deliberately absent: it would run across unrelated years.
    assert "Cumulative" not in split.columns


def test_fy_chart_buckets_resolve_to_records(fact):
    """A click on "FY26 Sep" must find the rows behind that point."""
    all_avs = segments.population(fact, segments.CAT_ALL_AVS)
    table, rows = kpi.monthly_unique_tpids(all_avs, "approval_date")
    split = kpi.split_by_fiscal_year(table, "Nominations")
    labelled = kpi.label_fiscal_year(rows, "approval_date")
    assert set(split["bucket"]) <= set(labelled["bucket"])
    for bucket in split["bucket"]:
        assert not labelled[labelled["bucket"] == bucket].empty


def test_charts_never_emit_a_title_without_text():
    """Regression: `title=None` serialises as {} and Plotly.js draws "undefined"."""
    import json

    from app.ui import charts
    df = pd.DataFrame({"category": ["A", "B"], "count": [3, 4]})
    figs = [charts.bar(df, "category", "count"),
            charts.donut(df, "category", "count"),
            charts.line(df, "category", "count"),
            charts.bar(df, "category", "count", title="Named")]
    for fig in figs:
        title = json.loads(fig.to_json())["layout"].get("title")
        assert title is not None and "text" in title, \
            f"title {title!r} would render as undefined"


# --------------------------------------------------------------------------- #
# Ownership columns and the in-flight On-Track rule
# --------------------------------------------------------------------------- #
def test_drilldowns_name_who_owns_the_account(fact):
    """Every record table says which SA and Factory PM to go and talk to."""
    frame = kpi.drilldown_frame(kpi.latest_wave(fact))
    assert "solution_architect" in frame.columns
    assert "assigned_pm" in frame.columns


def test_on_track_requires_an_in_flight_migration_status(raw_frame):
    """Only statuses 1-4 are in flight; 5/6/7 can never be On-Track.

    B's Wave 8 says "On Track" in Current State. Deferring it must take it out
    of On-Track even though that text is untouched.
    """
    df = raw_frame.copy()
    on_track_before = _on_track_tpids(df)
    assert "200" in on_track_before

    df.loc[df["Task ID"] == "4", "Migration Status"] = "5 - Deferred by Customer"
    assert "200" not in _on_track_tpids(df)

    # ...and each of the four in-flight statuses does keep it on track.
    for status in ("1 - Validating Commitment & Initial Scope",
                   "2 - Executing Pre-Requisites",
                   "3 - Finalize Scope",
                   "4 - Executing Migration"):
        df.loc[df["Task ID"] == "4", "Migration Status"] = status
        assert "200" in _on_track_tpids(df), status


def _on_track_tpids(raw: pd.DataFrame) -> list[str]:
    mp = mapping.resolve_mapping(list(raw.columns))
    built, _ = cleaning.build_fact_frame(raw, mp, pd.Timestamp("2026-09-01"))
    pop = segments.population(built, segments.CAT_ALL_AVS)
    return _tpids(kpi.on_track_accounts(pop).records)


def test_in_flight_is_exactly_statuses_one_to_four():
    df = pd.DataFrame({"migration_status_code": [1, 2, 3, 4, 5, 6, 7, None]})
    assert list(kpi.in_flight(df)) == [True, True, True, True,
                                       False, False, False, False]


# --------------------------------------------------------------------------- #
# Partial uploads — nothing may raise on a missing column
# --------------------------------------------------------------------------- #
# A file that carries only some of the schema used to crash the upload with
# "boolean value of NA is ambiguous": the derived classifications tested
# ``not value`` before they tested for missingness, and pd.NA has no truth value.
_PARTIAL_FILES = {
    "ids only": "TPID,Account Name\n1001,Acme\n1002,Globex\n",
    "no migration path": ("TPID,Account Name,WW Region,Phase,Nomination Status,"
                          "Nom. Created Date\n"
                          "1001,Acme,1800 Americas - Enterprise,Wave 1,Approved,2025-08-01\n"
                          "1002,Globex,,,,\n"),
    "everything blank": ("TPID,Account Name,Primary Migration Path,Tags,Total Cores,"
                         "Total ACR,Actual End Date\n"
                         "1001,Acme,,,,,\n1002,Globex,   ,  ,  ,  ,  \n"),
    "region strips to nothing": ("TPID,Account Name,WW Region\n"
                                 "1001,Acme,1800 Americas - Enterprise\n"
                                 "1002,Globex,1800\n"),
}


@pytest.mark.parametrize("label", sorted(_PARTIAL_FILES))
def test_a_partial_file_still_ingests(label):
    raw = loader.read_raw(f"{label}.csv", _PARTIAL_FILES[label].encode())
    mp = mapping.resolve_mapping(list(raw.columns))
    built, _report = cleaning.build_fact_frame(raw, mp, pd.Timestamp("2026-09-01"))
    assert len(built) == 2
    assert built["migration_direction"].notna().all()


def test_blank_checks_never_evaluate_a_missing_value():
    for value in (pd.NA, None, float("nan"), pd.NaT, "", "   ", "N/A"):
        assert nulls.is_blank(value) is True
    for value in ("Onprem to AVS", 0, 0.0, False):
        assert nulls.is_blank(value) is False
    # The classifier that used to raise, on the value that used to raise.
    assert cleaning.migration_direction(pd.NA) == DIR_OTHER


def test_a_nullable_mask_becomes_a_plain_bool_mask():
    mask = pd.Series([True, False, pd.NA], dtype="boolean")
    out = nulls.as_bool_mask(mask)
    assert out.dtype == bool
    assert list(out) == [True, False, False]        # unknown means "did not match"


# --------------------------------------------------------------------------- #
# Ingest diagnostics — a failure has to say where and why
# --------------------------------------------------------------------------- #
def test_a_failed_stage_reports_stage_origin_and_cause():
    raw = pd.DataFrame({"Empty": ["", ""], "TPID": ["1", "2"]}, dtype="string")
    with pytest.raises(loader.IngestError) as caught:
        with loader.ingest_stage("clean", "avs_export.xlsx", raw,
                                 {"tpid": "TPID", "migration_path": None}):
            cleaning.migration_direction_missing_column()   # AttributeError
    failure = caught.value.failure
    assert failure.stage == "clean"
    assert failure.filename == "avs_export.xlsx"
    assert failure.exc_type == "AttributeError"
    assert failure.detail["Rows"] == "2"
    assert "Empty" in failure.detail["Empty columns"]
    assert "migration_path" in failure.detail["Unmapped fields"]
    assert "Traceback" in failure.traceback
    assert "avs_export.xlsx" in failure.as_text()


def test_a_known_error_message_carries_a_plain_english_cause():
    assert "unmapped" in loader.explain("boolean value of NA is ambiguous")
    assert "header row" in loader.explain("No columns to parse from file")
    assert loader.explain("something nobody has seen before") == ""


def test_the_origin_names_app_code_not_the_stage_wrapper():
    with pytest.raises(loader.IngestError) as caught:
        with loader.ingest_stage("clean", "f.csv"):
            cleaning.parse_date_series(None)             # raises inside app code
    assert caught.value.failure.origin.startswith("app/core/cleaning.py:")


# --------------------------------------------------------------------------- #
# Multi-file datasets
# --------------------------------------------------------------------------- #
def test_files_are_stacked_on_their_shared_headers():
    avs = pd.DataFrame({"TPID": ["1"], "Account Name": ["Acme"],
                        "Primary Migration Path": ["Onprem to AVS"]}, dtype="string")
    native = pd.DataFrame({"tpid ": ["2"], "Account Name": ["Globex"],
                           "Total ACR": ["500"]}, dtype="string")
    combined, manifest = loader.combine_raw([("avs.csv", avs), ("native.xlsx", native)])

    # "tpid " matched "TPID" — headers are matched case- and space-insensitively,
    # keeping the spelling of the file that introduced the column.
    assert list(combined["TPID"]) == ["1", "2"]
    # A column one file does not have is blank for its rows, never NaN.
    assert combined.loc[0, "Total ACR"] == ""
    assert list(combined[schema.SOURCE_FILE_COLUMN]) == ["avs.csv", "native.xlsx"]
    assert list(manifest["file"]) == ["avs.csv", "native.xlsx"]
    assert int(manifest.loc[1, "shared_columns"]) == 2      # TPID + Account Name


def test_every_row_remembers_the_file_it_came_from():
    avs = ("TPID,Account Name,Primary Migration Path,Tags\n"
           "1001,Acme,Onprem to AVS,AVS Migration - Gen1\n").encode()
    native = ("TPID,Account Name,Primary Migration Path\n"
              "2002,Globex,SQL Server MI Migration (From AVS)\n").encode()
    raw, _manifest = loader.read_files([("avs.csv", avs), ("native.csv", native)])
    mp = mapping.resolve_mapping(list(raw.columns))
    built, _report = cleaning.build_fact_frame(raw, mp, pd.Timestamp("2026-09-01"))

    by_tpid = dict(zip(built["tpid"].astype(str), built["source_file"]))
    assert by_tpid["1001"] == "avs.csv"
    assert by_tpid["2002"] == "native.csv"
    # The two files still classify independently — combining is not merging.
    assert set(built.loc[built["tpid"] == "2002", "is_from_avs"]) == {True}
    assert set(built.loc[built["tpid"] == "1001", "is_from_avs"]) == {False}


def test_a_single_file_dataset_is_unchanged_but_labelled():
    frame = pd.DataFrame({"TPID": ["1"]}, dtype="string")
    combined, manifest = loader.combine_raw([("one.csv", frame)])
    assert list(combined.columns) == ["TPID", schema.SOURCE_FILE_COLUMN]
    assert len(manifest) == 1
    assert loader.dataset_label([("one.csv", b"")]) == "one.csv"
    assert loader.dataset_label([("a.csv", b""), ("b.csv", b"")]).startswith("2 files:")


# --------------------------------------------------------------------------- #
# The EOS monthly programme matrix
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def matrix_fact():
    """Three Gen-1 accounts and one Gen-2, with known months and core counts.

    The start dates are written to exercise each rung of the migration-start
    fallback: an actual start, a planned start, an approval date, and an account
    that never started at all.
    """
    # (tpid, name, task, wave, gen, status, approved, actual start, planned
    #  start, actual end, cores, current state)
    rows = [
        # Gen-1 Acme: approved Jul-25, actually started Sep-25, completed Nov-25.
        ("1001", "Acme", "a1", "Wave 1", "Gen1", "7 - Completed", "2025-07-08",
         "2025-09-03", "", "2025-11-14", "36", "Done"),
        # Gen-1 Beta: approved Sep-25, no actual start — planned Oct-25.  Wave 1
        # completed Nov-25 (72 cores) but Wave 2 is still running, so Beta is
        # NOT a completed migration.
        ("1002", "Beta", "b1", "Wave 1", "Gen1", "7 - Completed", "2025-09-02",
         "", "2025-10-01", "2025-11-20", "72", "Done"),
        ("1002", "Beta", "b2", "Wave 2", "Gen1", "4 - Migration In Progress",
         "2025-12-01", "", "", "", "", "On Track"),
        # Gen-1 Delta: approved Oct-25 and blocked — never started.
        ("1003", "Delta", "d1", "Wave 1", "Gen1", "2 - Executing Pre-Requisites",
         "2025-10-05", "", "", "", "", "Blocked - Customer"),
        # Gen-2 Gamma: approved Aug-25, no start dates at all, completed Feb-26.
        ("2001", "Gamma", "g1", "Wave 1", "Gen2", "7 - Completed", "2025-08-11",
         "", "", "2026-02-03", "52", "Done"),
    ]
    raw = pd.DataFrame([{
        "TPID": t, "Customer Name": n, "Task ID": k, "Phase": w,
        "Tags": f"Qualify and AccelerateAVS Migration - {g}",
        "Migration Status": s, "Nom. Approval Date": a, "Nom. Created Date": a,
        "Actual Start Date": ast, "Planned Start Date": pst,
        "Actual End Date": e, "Total Cores": c, "Current State": cs,
        "Primary Migration Path": "AV36/AV36P/AV52 - EOS",
        "WW Region": "Americas - Enterprise",
    } for t, n, k, w, g, s, a, ast, pst, e, c, cs in rows]).astype("string")
    mp = mapping.resolve_mapping(list(raw.columns))
    built, _report = cleaning.build_fact_frame(raw, mp, pd.Timestamp("2026-03-01"))
    return built


def _matrix(fact_frame, generation, end="2026-03-01"):
    block = fact_frame[fact_frame["generation"] == generation]
    months = kpi.month_span(pd.Timestamp("2025-07-01"), pd.Timestamp(end))
    grid = kpi.monthly_matrix(block, months)
    return grid.set_index("Measure")


def test_matrix_shows_every_month_including_the_empty_ones(matrix_fact):
    grid = _matrix(matrix_fact, segments.GEN_1)
    assert list(grid.columns) == ["Jul-25", "Aug-25", "Sep-25", "Oct-25", "Nov-25",
                                  "Dec-25", "Jan-26", "Feb-26", "Mar-26", "FY26 Total"]
    # Dec-25 has nothing in it and is still a column, reading zero.
    assert grid.loc["Total number of new engagement", "Dec-25"] == "0"


def test_each_fiscal_year_closes_with_its_own_total_column(matrix_fact):
    grid = _matrix(matrix_fact, segments.GEN_1, end="2026-09-01")
    columns = list(grid.columns)
    # FY26 (Jul-25 → Jun-26) closes right after Jun-26, before FY27 opens.
    assert columns[columns.index("Jun-26") + 1] == "FY26 Total"
    assert columns[columns.index("FY26 Total") + 1] == "Jul-26"
    assert columns[-1] == "FY27 Total"
    # Totals are the year's months summed: three Gen-1 accounts, all in FY26.
    assert grid.loc["Total number of new engagement", "FY26 Total"] == "3"
    assert grid.loc["Number of hosts migrated", "FY26 Total"] == "108"
    assert grid.loc["Total number of new engagement", "FY27 Total"] == "0"


def test_matrix_counts_match_the_documented_metric_rules(matrix_fact):
    gen1 = _matrix(matrix_fact, segments.GEN_1)
    # New engagements: unique TPIDs in the month of their Wave-1 approval date.
    assert gen1.loc["Total number of new engagement", "Jul-25"] == "1"
    assert gen1.loc["Total number of new engagement", "Sep-25"] == "1"
    # Migration ends: only Acme — Beta's latest wave is still in progress.
    assert gen1.loc["Total number of migration end", "Nov-25"] == "1"
    # Hosts: Total Cores summed over every completed record, so 36 + 72.
    assert gen1.loc["Number of hosts migrated", "Nov-25"] == "108"

    gen2 = _matrix(matrix_fact, segments.GEN_2)
    assert gen2.loc["Total number of new engagement", "Aug-25"] == "1"
    assert gen2.loc["Total number of migration end", "Feb-26"] == "1"
    assert gen2.loc["Number of hosts migrated", "Feb-26"] == "52"


def test_migration_start_walks_the_fallback_chain(matrix_fact):
    starts = kpi.migration_start_dates(matrix_fact)
    by_tpid = {t: (d, src) for t, d, src in zip(
        starts["tpid"].astype(str), starts["migration_start_date"],
        starts["start_date_source"])}

    # Acme has an actual start; Beta's earliest started wave has only a planned
    # one; Gamma has neither, so it falls back to the approval date.
    assert by_tpid["1001"] == (pd.Timestamp("2025-09-03"), "Actual Start Date")
    assert by_tpid["1002"] == (pd.Timestamp("2025-10-01"), "Planned Start Date")
    assert by_tpid["2001"] == (pd.Timestamp("2025-08-11"), "Nom. Approval Date")
    # Delta is blocked — no wave reads On Track or Done, so it never started.
    assert "1003" not in by_tpid


def test_migration_start_reads_the_earliest_started_wave_not_the_first_wave():
    """Wave 1 sat blocked; the migration started with Wave 2."""
    raw = pd.DataFrame([{
        "TPID": "900", "Customer Name": "Late", "Task ID": t, "Phase": w,
        "Tags": "AVS Migration - Gen1", "Migration Status": "4 - Migration In Progress",
        "Nom. Approval Date": "2025-07-01", "Nom. Created Date": "2025-07-01",
        "Actual Start Date": ast, "Current State": cs,
        "Primary Migration Path": "AV36/AV36P/AV52 - EOS",
    } for t, w, ast, cs in [("w1", "Wave 1", "2025-07-05", "Blocked - Customer"),
                            ("w2", "Wave 2", "2025-11-09", "On Track"),
                            ("w3", "Wave 3", "2026-01-04", "On Track")]]).astype("string")
    mp = mapping.resolve_mapping(list(raw.columns))
    built, _report = cleaning.build_fact_frame(raw, mp, pd.Timestamp("2026-03-01"))
    starts = kpi.migration_start_dates(built)
    # Not Wave 1's 2025-07-05: that wave never started.  Not Wave 3's either.
    assert list(starts["migration_start_date"]) == [pd.Timestamp("2025-11-09")]


def test_matrix_counts_migration_starts_in_their_own_month(matrix_fact):
    gen1 = _matrix(matrix_fact, segments.GEN_1)
    assert gen1.loc["Total number of migration start", "Sep-25"] == "1"   # Acme
    assert gen1.loc["Total number of migration start", "Oct-25"] == "1"   # Beta
    assert gen1.loc["Total number of migration start", "FY26 Total"] == "2"
    gen2 = _matrix(matrix_fact, segments.GEN_2)
    assert gen2.loc["Total number of migration start", "Aug-25"] == "1"   # Gamma


def test_engagement_end_mirrors_migration_end(matrix_fact):
    """The export has no engagement-closure date, so the row repeats migration end.

    An account whose latest wave has completed is the closest the data comes to
    an engagement that ended, so the two rows carry the same values by
    construction rather than by coincidence.
    """
    grid = _matrix(matrix_fact, segments.GEN_1)
    assert (list(grid.loc["Total number of engagement end"])
            == list(grid.loc["Total number of migration end"]))
    assert grid.loc["Total number of engagement end", "Nov-25"] == "1"
    # Every row now carries numbers, and they keep their reported order.
    assert not kpi.MATRIX_ROWS_UNAVAILABLE
    assert list(grid.index) == list(kpi.MATRIX_ROWS)


def test_matrix_runs_past_the_as_of_date_to_reach_a_future_completion(matrix_fact):
    gen2 = matrix_fact[matrix_fact["generation"] == segments.GEN_2]
    # As-of Sep-25, but Gamma completes in Feb-26: the span has to reach it.
    months = kpi.matrix_month_span(gen2, pd.Timestamp("2025-07-01"),
                                   pd.Timestamp("2025-09-15"))
    assert str(months[0]) == "2025-07" and str(months[-1]) == "2026-02"


def test_an_empty_generation_still_renders_the_whole_grid(matrix_fact):
    empty = matrix_fact[matrix_fact["generation"] == segments.GEN_UNCLASSIFIED]
    assert empty.empty
    grid = _matrix(matrix_fact, segments.GEN_UNCLASSIFIED)
    assert list(grid.columns)[-1] == "FY26 Total"
    assert grid.loc["Number of hosts migrated", "Nov-25"] == "0"


def test_the_fiscal_year_grid_lists_all_twelve_months():
    """A month with no data keeps its row, so the grid lines up with the chart."""
    from app.core import metrics as metrics_mod
    from app.views import trend_analysis

    split = pd.DataFrame({"fy_month": ["Aug", "Nov", "Aug"],
                          "fy": ["FY25", "FY25", "FY26"],
                          "Nominations": [3, 5, 2]})
    order = metrics_mod.fiscal_month_order(7)
    grid = trend_analysis._fy_grid(split, trend_analysis._BY_KEY["nominations"], order)

    assert list(grid["Month"]) == order + ["Total"]
    row = grid.set_index("Month")
    assert row.loc["Jul", "FY25"] == "0"       # empty month, still a row
    assert row.loc["Aug", "FY26"] == "2"
    assert row.loc["Total", "FY25"] == "8"


# --------------------------------------------------------------------------- #
# The single-file interactive HTML report
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def html_ctx(matrix_fact):
    """A minimal DataContext over the matrix fixture, enough to render a report."""
    from app import state as state_mod
    from app.core import loader as loader_mod, rollup as rollup_mod

    report = {"as_of": pd.Timestamp("2026-03-01"), "dq": {}, "dq_rows": 0,
              "n_rows": len(matrix_fact), "unmapped": [], "parse": {},
              "scope": {"floor_fy": "FY25"}}
    customer = rollup_mod.build_customer_rollup(matrix_fact, report["as_of"])
    return state_mod.DataContext(
        filename="matrix.csv", signature="sig", raw=pd.DataFrame(), mapping={},
        fact=matrix_fact, customer=customer, report=report,
        as_of=report["as_of"],
        con=loader_mod.make_connection(matrix_fact, customer))


@pytest.fixture(scope="module")
def html_doc(html_ctx):
    from app.core import html_report
    return html_report.build_html_report(
        html_ctx, title="AVS Migration Analytics", subtitle="Management Report",
        period_label="01 Jul 2025 → 30 Jun 2026",
        appendices=["inconsistency"]).decode("utf-8")


def test_the_html_report_is_a_single_self_contained_file(html_doc):
    """No stylesheet, font, script or image is fetched: it must open offline."""
    assert html_doc.startswith("<!DOCTYPE html>")
    assert "</html>" in html_doc
    # Nothing is loaded from anywhere — no src=, no link rel=stylesheet, no http.
    assert "<script src=" not in html_doc
    assert '<link rel="stylesheet"' not in html_doc
    assert "https://" not in html_doc.split("<script>")[0]   # head + cover markup
    # …and the pieces that would otherwise be fetched are inlined.
    assert "Plotly.newPlot(" in html_doc
    assert "<style>" in html_doc


def test_the_html_report_carries_every_selected_report(html_doc):
    for anchor in ('id="rpt-avs"', 'id="rpt-eos"', 'id="rpt-native"', 'id="appendix"'):
        assert anchor in html_doc
    assert 'href="#rpt-eos"' in html_doc          # and each is in the contents


def test_the_html_report_keeps_charts_accordions_and_sortable_tables(html_doc):
    assert html_doc.count('<div class="chart"') >= 4      # interactive figures
    # Matched on the div id, since the inlined Plotly bundle mentions newPlot too.
    assert html_doc.count('Plotly.newPlot("fig') == html_doc.count('<div class="chart"')
    assert '<details class="acc"' in html_doc             # drill-down accordions
    assert 'table class="data"' in html_doc
    assert "expand-all" in html_doc and "collapse-all" in html_doc


def test_the_html_report_carries_the_eos_matrix(html_doc):
    assert "Monthly programme matrix" in html_doc
    assert "Gen1 to Gen1" in html_doc and "Gen1 to Gen2" in html_doc
    assert "FY26 Total" in html_doc
    assert "Total number of migration start" in html_doc


def test_html_values_are_escaped_but_insight_bold_survives():
    from app.core import html_report
    assert html_report.esc('<script>alert("x")</script>') == (
        "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;")
    # The insight engine writes **bold**; it renders, and injection still cannot.
    assert html_report.rich("**Americas** leads") == "<b>Americas</b> leads"
    assert html_report.rich("**<b>x</b>** y") == "<b>&lt;b&gt;x&lt;/b&gt;</b> y"
    assert html_report.esc(pd.NaT) == "" and html_report.esc(None) == ""


def test_the_html_and_pdf_reports_count_the_same_things(html_ctx, matrix_fact):
    """Both renderers read the same helpers, so the tiles must agree."""
    from app.core import exporter as exp
    pop = segments.population(matrix_fact, segments.CAT_EOS_ALL)
    waves = kpi.wave_index(pop)
    head = exp.headline(pop, waves, None, None)
    from app.core import html_report
    doc = html_report.build_html_report(html_ctx, reports=["eos"],
                                        drilldown=False).decode("utf-8")
    # Four Gen-tagged accounts, one of which never completes a latest wave.
    assert f'<div class="value">{head["engagements"].value:,}</div>' in doc
    assert f'<div class="value">{head["completed"].value:,}</div>' in doc


def test_an_empty_report_renders_rather_than_raising(html_ctx):
    """Filters that select nothing must still produce a readable file."""
    from app.core import html_report
    doc = html_report.build_html_report(
        html_ctx, where="WHERE 1 = 0", scope_label="Filtered view").decode("utf-8")
    assert doc.startswith("<!DOCTYPE html>")
    assert "No nominations fall into this report" in doc


def test_small_count_axes_get_whole_number_ticks():
    """A count reaching 3 must not tick every 0.5 and print "3, 3, 2, 2, 1, 1"."""
    from app.core import html_report
    from app.ui import charts as charts_mod

    table = pd.DataFrame({"period": ["2025-03", "2025-09", "2026-05"],
                          "Nominations": [1, 1, 3], "Cumulative": [1, 2, 5]})
    fig = charts_mod.trend_chart(table, "period", "Nominations", "Cumulative")
    html_report._integer_ticks(fig)
    assert fig.layout.yaxis.dtick == 1          # bars: 0..3
    assert fig.layout.yaxis2.dtick == 1         # cumulative line: 0..5

    # A big axis is left to Plotly, whose own ticks are already whole numbers —
    # dtick=1 there would try to draw four hundred of them.
    big = pd.DataFrame({"period": ["2025-03", "2025-09"],
                        "Nominations": [1, 2], "Cumulative": [200, 428]})
    fig = charts_mod.trend_chart(big, "period", "Nominations", "Cumulative")
    html_report._integer_ticks(fig)
    assert fig.layout.yaxis.dtick == 1
    assert fig.layout.yaxis2.dtick is None


def test_report_values_are_escaped_exactly_once(html_ctx, matrix_fact):
    """An "&" in an account name must not reach the page as "&amp;amp;"."""
    from app.core import exporter as exp, html_report

    pop = segments.population(matrix_fact, segments.CAT_EOS_ALL)
    waves = kpi.wave_index(pop)
    rows, layout, _total = exp.account_rows(pop, waves, True)
    named = rows.copy()
    named.loc[named.index[0], "customer_name"] = "Ação & Café <Ltd>"
    frame = exp.format_accounts(named, layout, escape=html_report.plain)

    # The shared formatter hands the renderer raw text …
    assert "Ação & Café <Ltd>" in list(frame["Customer"])
    # … and the renderer escapes it once, so the browser shows the original.
    markup = html_report._table(frame, "t")
    assert "Ação &amp; Café &lt;Ltd&gt;" in markup
    assert "&amp;amp;" not in markup


def test_non_latin_account_names_survive_the_html_report(html_ctx, matrix_fact):
    """A Japanese account name is reported, not dropped or mangled."""
    from app.core import html_report
    import app.state as state_mod
    from app.core import loader as loader_mod, rollup as rollup_mod

    fact = matrix_fact.copy()
    fact["customer_name"] = fact["customer_name"].astype("string")
    fact.loc[fact.index[0], "customer_name"] = "株式会社ジェーシービー"
    customer = rollup_mod.build_customer_rollup(fact, pd.Timestamp("2026-03-01"))
    ctx = state_mod.DataContext(
        filename="jp.csv", signature="s", raw=pd.DataFrame(), mapping={},
        fact=fact, customer=customer, report=dict(html_ctx.report),
        as_of=pd.Timestamp("2026-03-01"),
        con=loader_mod.make_connection(fact, customer))

    doc = html_report.build_html_report(ctx, reports=["eos"]).decode("utf-8")
    assert "株式会社ジェーシービー" in doc          # verbatim, not escaped away
    assert 'charset="utf-8"' in doc.lower()


# --------------------------------------------------------------------------- #
# WW Region, stage codes and the pipeline colours
# --------------------------------------------------------------------------- #
def test_stage_labels_shorten_the_axis_and_hand_back_a_key(matrix_fact):
    """Five 30-character status names on one axis leave no room for the plot."""
    short, legend = kpi.stage_labels(matrix_fact)
    assert set(short) <= {"Stage 2", "Stage 4", "Stage 7"}
    assert legend == sorted(legend, key=lambda pair: pair[0])   # ordered by code
    assert dict(legend)["Stage 7"] == "Completed"
    # A row with no code keeps its full label rather than hiding behind a number.
    uncoded = matrix_fact.assign(migration_status_code=pd.NA,
                                 migration_status_label="Something Else")
    short, legend = kpi.stage_labels(uncoded)
    assert set(short) == {"Something Else"} and legend == []


def test_the_regional_cut_reads_ww_region_and_stage_codes(matrix_fact):
    from app.core import exporter as exp
    waves = kpi.wave_index(matrix_fact)
    pivot, heat, legend = exp.region_status(waves.last)
    assert list(heat.index) == ["Americas - Enterprise"]   # the full WW Region
    assert all(str(s).startswith("Stage ") for s in pivot.index)
    assert legend                                          # …with its key


def test_on_track_and_completed_are_different_colours():
    """Both drew green: the palette keyed "On Track", the state reads "On-Track"."""
    from app.config import STATUS_COLORS
    from app.ui import charts as charts_mod
    colours = charts_mod._color_for([kpi.STATE_ON_TRACK, kpi.STATE_COMPLETED])
    assert len(set(colours)) == 2
    assert colours[1] == STATUS_COLORS["Completed"]
    assert colours[0] == STATUS_COLORS["On Track"]


def test_a_pie_gets_selectable_chips_because_streamlit_cannot_report_slices():
    """Streamlit returns no selection points for pie traces, whatever the mode."""
    from app.ui import drilldown as dd
    assert hasattr(dd, "selectable_slices")
    assert dd.selectable_slices([], key="k") == []


# --------------------------------------------------------------------------- #
# HTML report — the second round of changes
# --------------------------------------------------------------------------- #
def test_the_header_carries_only_the_period_pill(html_doc):
    assert html_doc.count('<span class="chip">') == 1
    assert "Period:" in html_doc
    for gone in ("Scope:", "As of:", "Dataset:", "Accounts:", "Generated:"):
        assert f"{gone}</b>" not in html_doc


def test_a_this_fy_row_is_added_when_the_period_is_something_else(html_ctx):
    """The dashboard's two-row rule, in the file: a month keeps its fiscal year."""
    from app.core import html_report

    month = html_report.build_html_report(
        html_ctx, reports=["eos"], drilldown=False,
        period_label="01 Nov 2025 -> 30 Nov 2025",
        date_window=(pd.Timestamp("2025-11-01"),
                     pd.Timestamp("2025-11-30"))).decode("utf-8")
    assert "Two periods:" in month
    assert "This FY (FY26)" in month
    assert month.count('<div class="kpis">') == 2      # FY row, then period row

    fy_span = metrics.date_preset_range(html_ctx.as_of, "This FY", 7)
    same = html_report.build_html_report(
        html_ctx, reports=["eos"], drilldown=False, period_label="This FY",
        date_window=(fy_span[0], fy_span[1])).decode("utf-8")
    assert "Two periods:" not in same                  # nothing to compare against
    assert same.count('<div class="kpis">') == 1


def test_underlying_data_shows_the_accounts_not_just_the_chart_numbers(html_doc):
    """Same as the app's drill-down: the records the metric counted."""
    assert "Underlying accounts —" in html_doc
    assert "Monthly numbers —" in html_doc             # the counts are kept too
    assert "records</span>" in html_doc                # badged by record count
    assert "Accounts by state" in html_doc


def test_money_axes_are_written_in_k_and_m(html_ctx):
    from app.core import html_report
    doc = html_report.build_html_report(html_ctx, reports=["eos"],
                                        drilldown=False).decode("utf-8")
    # The ACR chart's axis is $-prefixed and SI-formatted ($2M, $840k) rather
    # than a raw 2,000,000.
    assert '"tickprefix": "$"' in doc or '"tickprefix":"$"' in doc


def test_the_report_offers_a_wide_reading_mode(html_doc):
    assert 'id="toggle-width"' in html_doc
    assert "--page-w" in html_doc and "body.wide" in html_doc
