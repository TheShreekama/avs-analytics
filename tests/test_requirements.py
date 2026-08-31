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
