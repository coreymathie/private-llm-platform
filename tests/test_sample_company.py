# Corey Mathie, 2026
"""The console's sample-company data: reproducible, internally consistent, and labelled fictional."""

import json
from pathlib import Path

import pytest

from scripts import generate_sample_company as gen

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "demo" / "data" / "sample_company.json").read_text())


def test_committed_file_matches_the_generator():
    assert gen.main(["--check"]) == 0


def test_generation_is_deterministic():
    assert gen.render(gen.build()) == gen.render(gen.build())


def test_daily_numbers_add_up():
    assert len(DATA["days"]) == gen.DAYS
    staff = DATA["company"]["employees"]
    for d in DATA["days"]:
        assert d["answered"] + d["no_answer"] == d["questions"]
        assert 0 <= d["active_users"] <= staff
        assert d["restricted_withheld"] <= d["questions"]
        assert d["p50_ms"] < d["p95_ms"]


def test_headcounts_sum_to_employees_and_departments_match_the_catalog():
    catalog = json.loads((ROOT / "demo" / "data" / "library.json").read_text())
    assert sum(x["headcount"] for x in DATA["departments"]) == DATA["company"]["employees"] == 340
    assert sorted(x["department"] for x in DATA["departments"]) == sorted(catalog["departments"])
    heads = {x["department"]: x["headcount"] for x in DATA["departments"]}
    assert heads["Facilities and security"] < heads["IT and digital banking"]  # a small team, not 13% of staff
    for x in DATA["departments"]:
        assert 0 < x["active_users_30d"] <= x["headcount"]


def test_thirty_day_actives_are_at_least_the_busiest_day():
    monthly = sum(x["active_users_30d"] for x in DATA["departments"])
    assert max(d["active_users"] for d in DATA["days"]) <= monthly


@pytest.mark.parametrize("days", [7, 30, 90])
def test_topics_for_any_range_add_up_to_the_questions_asked(days):
    rows = DATA["days"][-days:]
    asked = sum(d["questions"] for d in rows)
    assert sum(sum(d["topics"].values()) for d in rows) == asked
    if days == 30:
        assert sum(t["questions_30d"] for t in DATA["topics"]) == asked
        assert sum(x["questions_30d"] for x in DATA["departments"]) == asked


def test_topics_are_asked_only_by_departments_that_can_read_them():
    by_dept = {x["department"]: x["questions_30d"] for x in DATA["departments"]}
    restricted = [t for t in DATA["topics"] if t["asked_by"] != "All staff"]
    assert restricted
    for t in restricted:
        assert t["questions_30d"] <= sum(by_dept[d] for d in t["asked_by"]), t["topic"]
    bsa = next(t for t in DATA["topics"] if t["topic"].startswith("BSA/AML"))
    assert bsa["asked_by"] == ["Compliance and BSA"] and 0 < bsa["questions_30d"] < by_dept["Compliance and BSA"]


def test_it_is_labelled_fictional_and_assumptions_are_stated():
    assert DATA["company"]["fictional"] is True
    assert "not measurements" in DATA["disclaimer"]
    assert DATA["assumptions"]["minutes_saved_per_answer"] > 0


def test_recent_activity_names_documents_that_exist():
    catalog = json.loads((ROOT / "demo" / "data" / "library.json").read_text())
    titles = {d["title"] for d in catalog["documents"]}
    bsa = next(n for n in DATA["notable"] if "BSA" in n["detail"])
    assert "Unusual Activity Referral Policy" in bsa["detail"] and "Unusual Activity Referral Policy" in titles


def test_every_headline_figure_states_its_basis_and_every_cited_one_has_a_url():
    """The "How these sample numbers were set" panel: a figure is cited only with a fetched, quoted source."""
    figures = DATA["benchmarks"]
    assert {b["id"] for b in figures} >= {"staffing", "adoption", "time_saved", "hourly_cost", "infrastructure"}
    assert set(gen.SOURCES) <= {b["id"] for b in figures}
    for b in figures:
        assert b["figure"] and b["value"] and b["basis"], b["id"]
        if b["status"] == "cited":
            assert b["sources"], b["id"]
            for src in b["sources"]:
                assert src["url"].startswith("https://"), b["id"]
                assert src["title"] and src["publisher"] and src["year"] and src["quote"], b["id"]
                assert src["accessed"] == "2026-11-05", b["id"]
                assert "|" not in src["quote"], b["id"]  # the quote sits in a Markdown table cell
        else:
            assert b["status"] == "assumption" and b["sources"] == [], b["id"]

    # The generator's parameters are the published figures quoted in SOURCES, not rounded or adjusted copies.
    a = DATA["assumptions"]
    assert f"Cost ($) {a['loaded_cost_per_hour_usd']:.2f}" in gen.SOURCES["hourly_cost"][0]["quote"]
    assert f"${gen.L40S_NODE_PER_HOUR_USD:.2f} / Hour" in gen.SOURCES["infrastructure"][0]["quote"]
    assert "GPU Count 8" in gen.SOURCES["infrastructure"][0]["quote"] and gen.L40S_NODE_GPUS == 8
    assert a["infrastructure_per_month_usd"] == round(2 * 18.00 / 8 * 730) == 3285
    ncua = gen.SOURCES["membership"][0]["quote"]
    assert "146.1 million members" in ncua and "$2.50 trillion" in ncua

    # The sample stays within the cited figures: adoption near published AI-use rates, time saved below published
    # self-reported savings.
    staff = DATA["company"]["employees"]
    monthly = sum(x["active_users_30d"] for x in DATA["departments"])
    work = [d for d in DATA["days"][-30:] if d["active_users"] > 40]
    daily = sum(d["active_users"] for d in work) / len(work)
    assert 0.39 <= monthly / staff <= 0.60  # Gallup: roughly half (financial activities) weekly; RPS: 39.2%
    assert daily / staff < 0.392  # a workday is a narrower window than a week
    answered = sum(d["answered"] for d in DATA["days"][-30:])
    hours = answered * DATA["assumptions"]["minutes_saved_per_answer"] / 60
    weeks = 30 / 7
    assert hours / monthly / weeks / 40 < 0.054  # users save 5.4% of their work hours
    assert hours / staff / weeks / 40 < 0.022  # 2.2% of employed adults' work hours, Q2 2026


def test_console_doc_quotes_the_sample_figures_table():
    assert gen.benchmarks_markdown(DATA) in (ROOT / "docs" / "console.md").read_text()
