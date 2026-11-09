# Corey Mathie, 2026
"""
Write demo/data/sample_company.json: 90 days of usage of the private assistant at a fictional
mid-size credit union, so the console's Business impact view shows the platform at a realistic
scale.

Cypress Harbor Credit Union does not exist. Every number in the file is generated here from a
fixed seed and the assumptions below; none of it is a measurement of this repo or of any real
institution. The console labels it "Sample company data" wherever it appears, and keeps it apart
from the measured eval results (Answer quality) and the requests made in the browser (This session).

    python scripts/generate_sample_company.py            # write the file
    python scripts/generate_sample_company.py --check    # exit 1 if the committed file differs

The model, in short:
- 340 employees in the departments of scripts/sample_library.py (read from demo/data/library.json),
  all signed in through SSO. Each department has a 30-day active count; on any day a share of those
  people ask questions, so a day's active users never exceed the 30-day actives. The share grows after
  launch (a typical adoption curve), and questions follow the working week.
- Questions are generated per department and per day, then split into topics. A topic is asked only by
  the departments that can read the documents behind it (the BSA/AML investigation topic only by
  Compliance and BSA), so topic counts, department counts and daily totals all come from the same rows.
- Most questions are answered from documents with citations; some find nothing in the documents the
  asker may read, and a small share touch documents the asker isn't cleared for, which the retrieval
  layer filters out before scoring.
- Adoption (about half of staff in 30 days, under a third on a workday) is set close to published rates of
  AI use at work. Time saved uses a stated minutes-per-answer assumption and stays below published
  self-reported savings; the hourly cost is the BLS total compensation for credit intermediation, and the
  infrastructure cost is two L40S GPUs at a public on-demand rate, a ceiling for one on-prem server.

Every headline figure is listed in the file's "benchmarks" table (computed from the generated rows, last 30
days) with the assumption behind it and, where one has been checked, the published source it is calibrated to.
A figure is "cited" only with a source someone fetched and read: title, publisher, year, URL, access date and the
quoted sentence (SOURCES). The console's "How these sample numbers were set" panel and docs/console.md render from
that table.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "demo" / "data" / "sample_company.json"
LIBRARY = ROOT / "demo" / "data" / "library.json"  # written by scripts/sample_library.py
SEED = 20261008
END = date(2026, 10, 7)
DAYS = 90
HOLIDAYS = {date(2026, 9, 7)}  # Labor Day

# Department: headcount, questions per active user per workday, share of staff active in 30 days,
# relative rate of questions that find nothing to cite
STAFFING = {
    "Member services and branches": (160, 3.0, 0.45, 1.0),
    "Lending": (48, 3.5, 0.60, 0.9),
    "IT and digital banking": (34, 2.4, 0.70, 1.1),
    "Payments and fraud operations": (26, 4.0, 0.60, 0.9),
    "Finance and accounting": (18, 2.2, 0.55, 1.1),
    "Compliance and BSA": (12, 4.5, 0.75, 0.8),
    "Marketing": (12, 1.6, 0.50, 1.3),
    "Human resources": (10, 2.9, 0.60, 1.0),
    "Facilities and security": (8, 1.2, 0.25, 1.2),
    "Executive": (8, 1.2, 0.50, 1.2),
    "Internal audit": (4, 3.0, 0.75, 0.9),
}

ALL_STAFF = "all"
MSB, PAY, LEND, FIN = (
    "Member services and branches",
    "Payments and fraud operations",
    "Lending",
    "Finance and accounting",
)
CARDS, LOANS, OPENING = (
    "Card disputes and provisional credit",
    "Loan products, rates and exceptions",
    "Account opening and identity verification",
)
WIRES, FEES, COMPLAINTS = (
    "Wire transfers and callbacks",
    "Fees, hours and member rates",
    "Complaints and member escalations",
)
RECORDS, BRANCH, IT_POLICY = (
    "Records retention and privacy",
    "Branch security and cash handling",
    "IT and security policy",
)
TRAVEL, REFERRALS = "Travel and expenses", "Unusual activity and OFAC referrals"
BSA = "BSA/AML investigations (Compliance and BSA only)"
# Topic: base share, who can ask it (departments that can read the documents behind it)
TOPICS = [
    (CARDS, 0.14, [MSB, PAY]),
    (LOANS, 0.13, [LEND, MSB]),
    (OPENING, 0.11, [MSB, PAY]),
    (WIRES, 0.08, [MSB, PAY, FIN]),
    (FEES, 0.07, ALL_STAFF),
    (COMPLAINTS, 0.06, ALL_STAFF),
    ("Benefits, leave and pay", 0.09, ALL_STAFF),
    (RECORDS, 0.05, ALL_STAFF),
    (BRANCH, 0.05, [MSB, "Facilities and security", PAY]),
    (IT_POLICY, 0.07, ALL_STAFF),
    (TRAVEL, 0.04, ALL_STAFF),
    (REFERRALS, 0.04, ALL_STAFF),
    (BSA, 0.03, ["Compliance and BSA"]),
    ("Other", 0.04, ALL_STAFF),
]
# Topics a department asks about more than the base share (weight x3)
FOCUS = {
    MSB: {CARDS, OPENING, FEES},
    LEND: {LOANS},
    "IT and digital banking": {IT_POLICY},
    PAY: {WIRES, CARDS, REFERRALS},
    FIN: {TRAVEL, WIRES},
    "Compliance and BSA": {BSA, REFERRALS, COMPLAINTS, RECORDS},
    "Marketing": {FEES, COMPLAINTS},
    "Human resources": {"Benefits, leave and pay"},
    "Facilities and security": {BRANCH},
    "Executive": {COMPLAINTS, "Other"},
    "Internal audit": {RECORDS, IT_POLICY},
}

COMPANY = {
    "name": "Cypress Harbor Credit Union",
    "short": "Cypress Harbor CU",
    "fictional": True,
    "industry": "Credit union (financial services)",
    "headquarters": "Fort Lauderdale, Florida",
    "members": 92400,
    "assets_usd": 1_400_000_000,
    "employees": sum(h for h, *_ in STAFFING.values()),
    "branches": 11,
    "deployment": "One on-prem GPU server (2 x NVIDIA L40S) running vLLM; SSO through the credit union's IdP",
    "regulators": ["NCUA", "CFPB", "Florida OFR"],
}

# Two NVIDIA L40S GPUs at CoreWeave's public on-demand rate for an 8 x L40S instance ($18.00 an hour), around the
# clock (8,760 hours a year / 12 = 730 hours a month): an owned server with power and support is assumed to cost no
# more than renting the same GPUs. See SOURCES["infrastructure"].
GPUS, L40S_NODE_PER_HOUR_USD, L40S_NODE_GPUS, HOURS_PER_MONTH = 2, 18.00, 8, 730

ASSUMPTIONS = {
    "minutes_saved_per_answer": 6,
    # BLS ECEC, June 2026: total compensation for private-industry credit intermediation (SOURCES["hourly_cost"])
    "loaded_cost_per_hour_usd": 65.97,
    "infrastructure_per_month_usd": round(GPUS * L40S_NODE_PER_HOUR_USD / L40S_NODE_GPUS * HOURS_PER_MONTH),
    "note": "Minutes saved per cited answer (versus searching shared drives or asking a colleague; an assumption), "
    "the hourly cost of an employee (BLS total compensation per hour for credit intermediation, June 2026), and the "
    "monthly infrastructure cost (two L40S GPUs at a public cloud on-demand rate, as a ceiling for the on-prem "
    "server). Sample figures calibrated to published sources, not measurements.",
}


def asks(department: str, topic: tuple) -> bool:
    return topic[2] == ALL_STAFF or department in topic[2]


def split(total: int, weights: list[float]) -> list[int]:
    """Largest-remainder split of an integer by weights (sums exactly to total)."""
    s = sum(weights)
    raw = [total * w / s for w in weights]
    out = [int(x) for x in raw]
    for i in sorted(range(len(raw)), key=lambda i: (out[i] - raw[i], i))[: total - sum(out)]:
        out[i] += 1
    return out


def access_text(collection: dict, documents: list[dict], groups: dict) -> str:
    """Who may read a collection, in words, from the catalog's access lists."""
    acl = collection.get("acl") or []
    text = "All staff and the lobby kiosk" if "group:public" in acl else "All staff" if acl else "Everyone"
    for d in documents:
        if d["collection"] == collection["name"] and d["acl"]:
            who = " or ".join(groups[e.split(":", 1)[1]] for e in d["acl"])
            text += f"; {d['title']}: {who} only"
    return text


# Published sources the sample is calibrated to, by figure id: a list of {"title", "publisher", "year", "url",
# "quote", "accessed"}. Each was fetched and read in full on the access date, and "quote" is copied from the page
# (a table row is quoted as its label and values). A figure without a source is labelled an assumption.
ACCESSED = "2026-11-05"
_NCUA = {
    "title": "Quarterly Credit Union Data Summary 2026 Q2",
    "publisher": "National Credit Union Administration",
    "year": 2026,
    "url": "https://ncua.gov/files/publications/analysis/quarterly-data-summary-2026-Q2.pdf",
    "quote": "As of June 30, 2026, there were 4,214 federally insured credit unions with 146.1 million members. ... "
    "Total assets in federally insured credit unions rose by $120 billion, or 5.0 percent, over the year ending in "
    "2026Q2, to $2.50 trillion.",
    "accessed": ACCESSED,
}
_RPS_2026 = {
    "title": "Does generative AI save time at work?",
    "publisher": "Federal Reserve Bank of St. Louis, FRED Blog",
    "year": 2026,
    "url": "https://fred.stlouisfed.org/blog/2026/08/does-generative-ai-save-time-at-work",
    "accessed": ACCESSED,
}
SOURCES: dict[str, list[dict]] = {
    "membership": [_NCUA],
    "adoption": [
        {
            "title": "AI Benefits at Work Unevenly Distributed",
            "publisher": "Gallup",
            "year": 2026,
            "url": "https://news.gallup.com/poll/714602/benefits-work-unevenly-distributed.aspx",
            "quote": "Roughly half of employees in the professional and business services, financial activities and "
            "information/media industries regularly use AI.",
            "accessed": ACCESSED,
        },
        {
            **_RPS_2026,
            "quote": "The share of employed adults who used generative AI for work in the past week grew from 28.2% "
            "in Q3 2024 to 39.2% by Q2 2026, indicating adoption is broadening.",
        },
    ],
    "time_saved": [
        {
            "title": "Generative AI, Productivity and the Future of Work",
            "publisher": "Federal Reserve Bank of St. Louis, Open Vault",
            "year": 2025,
            "url": "https://www.stlouisfed.org/open-vault/2025/oct/generative-ai-productivity-future-work",
            "quote": "On average, generative AI users reported saving time amounting to 5.4% of their work hours, or "
            "roughly 2.2 hours per week in a 40-hour work week.",
            "accessed": ACCESSED,
        },
        {
            **_RPS_2026,
            "quote": "Perhaps most importantly, the share of work hours saved thanks to AI assistance grew from 1.6% "
            "to 2.2%.",
        },
    ],
    "hourly_cost": [
        {
            "title": "Employer Costs for Employee Compensation, Table 4. Private industry workers by occupational and "
            "industry group (June 2026)",
            "publisher": "U.S. Bureau of Labor Statistics",
            "year": 2026,
            "url": "https://www.bls.gov/news.release/ecec.t04.htm",
            "quote": "Credit intermediation and related activities industry: Total compensation, Cost ($) 65.97; "
            "Wages and salaries 42.35; Total benefits 23.62",
            "accessed": ACCESSED,
        }
    ],
    "infrastructure": [
        {
            "title": "CoreWeave Cloud Pricing",
            "publisher": "CoreWeave",
            "year": 2026,
            "url": "https://www.coreweave.com/pricing",
            "quote": "NVIDIA L40S (GPU Count 8, North America): On-Demand Price: $18.00 / Hour",
            "accessed": ACCESSED,
        }
    ],
}

# Published totals quoted in the basis text (from the sources above)
NCUA_MEMBERS, NCUA_ASSETS_USD = 146.1e6, 2.50e12


def headline_figures(data: dict) -> list[dict]:
    """The dashboard's headline figures (last 30 days), the assumption behind each, and its source if cited."""
    days, co, a = data["days"][-30:], data["company"], data["assumptions"]
    work = [d for d in days if d["active_users"] > 40]
    staff = co["employees"]
    active30 = sum(x["active_users_30d"] for x in data["departments"])
    asked, answered = sum(d["questions"] for d in days), sum(d["answered"] for d in days)
    up, down = sum(d["thumbs_up"] for d in days), sum(d["thumbs_down"] for d in days)
    hours = answered * a["minutes_saved_per_answer"] / 60
    weeks = len(days) / 7
    per_user_week = hours / active30 / weeks
    per_staff_week = hours / staff / weeks
    daily = sum(d["active_users"] for d in work) / len(work)
    infra = a["infrastructure_per_month_usd"]
    rows = [
        (
            "membership",
            "Members and assets",
            f"{co['members']:,} members and ${co['assets_usd'] / 1e9:.1f}B in assets: "
            f"${co['assets_usd'] / co['members']:,.0f} in assets per member",
            f"Set for a mid-size credit union. Federally insured credit unions hold about "
            f"${round(NCUA_ASSETS_USD / NCUA_MEMBERS, -2):,.0f} in assets per member ($2.50 trillion for 146.1 "
            f"million members, NCUA, June 30, 2026); the sample is "
            f"{1 - co['assets_usd'] / co['members'] / (NCUA_ASSETS_USD / NCUA_MEMBERS):.0%} below that average.",
        ),
        (
            "staffing",
            "Staffing ratios",
            f"{staff} employees: {co['members'] / staff:.0f} members and ${co['assets_usd'] / staff / 1e6:.1f}M in "
            "assets per employee",
            "Set for a mid-size credit union. NCUA's quarterly summary reports members and assets but not employees, "
            "and no published members-per-employee figure has been checked.",
        ),
        (
            "adoption",
            "Employees using it",
            f"{active30} of {staff} employees ({active30 / staff:.0%}) asked at least one question in 30 days; "
            f"{daily:.0f} ({daily / staff:.0%}) on an average workday",
            "Department shares in STAFFING (25% to 75% of staff in 30 days) and a workday share that rises after "
            "launch, set close to published rates of AI use at work: roughly half of financial-activities employees "
            "use AI daily or weekly (Gallup, January to March 2026), and 39.2% of employed adults used generative AI "
            "for work in the past week (Real-Time Population Survey, Q2 2026).",
        ),
        (
            "questions",
            "Questions per active employee",
            f"{sum(d['questions'] for d in work) / sum(d['active_users'] for d in work):.1f} per workday "
            f"({asked:,} in 30 days)",
            "Per-department questions per active user per workday (1.2 to 4.5 in STAFFING).",
        ),
        (
            "time_saved",
            "Hours saved",
            f"{a['minutes_saved_per_answer']} minutes per cited answer: {hours:,.0f} hours in 30 days, "
            f"{per_user_week:.1f} hours per active employee per week ({per_user_week / 40:.1%} of a 40-hour week), "
            f"{per_staff_week / 40:.1%} of all staff hours",
            "Minutes saved per answer (versus searching shared drives or asking a colleague) are an assumption. The "
            f"result, {per_user_week / 40:.1%} of an active employee's week and {per_staff_week / 40:.1%} of all staff "
            "hours, stays below published self-reported savings from generative AI: 5.4% of users' work hours, and "
            "2.2% of employed adults' work hours (Q2 2026).",
        ),
        (
            "hourly_cost",
            "Loaded hourly cost",
            f"${a['loaded_cost_per_hour_usd']:.2f} per hour",
            "Wages plus benefits per hour: the BLS total compensation cost for private-industry credit intermediation "
            "(June 2026), used as published.",
        ),
        (
            "infrastructure",
            "Infrastructure cost",
            f"${infra:,} per month: ${infra / answered:.2f} per answer",
            "Two NVIDIA L40S GPUs at the public on-demand rate for an 8-GPU L40S instance "
            f"(${L40S_NODE_PER_HOUR_USD:.2f} an hour, so "
            f"${GPUS * L40S_NODE_PER_HOUR_USD / L40S_NODE_GPUS:.2f} for two) for {HOURS_PER_MONTH} hours a "
            "month. The on-prem server, with power and support, is assumed to cost no more than renting the same GPUs.",
        ),
        (
            "answer_rate",
            "Answered from documents",
            f"{answered / asked:.1%} of questions answered with citations",
            "The share that finds nothing to cite falls from about 11% to about 7% over 90 days as the library fills "
            "its gaps; no comparable published rate for an internal policy assistant has been checked.",
        ),
        (
            "helpful",
            "Answers rated helpful",
            f"{up / (up + down):.1%} of {up + down:,} ratings; {(up + down) / answered:.0%} of answers rated",
            "Rating rate and helpful share chosen for illustration.",
        ),
        (
            "latency",
            "Response time",
            f"median {sum(d['p50_ms'] * d['questions'] for d in days) / asked / 1000:.1f} s, slowest-day 95th "
            f"percentile {max(d['p95_ms'] for d in days) / 1000:.1f} s",
            "Chosen for illustration; the gateway's own overhead is measured separately (docs/benchmarks.md).",
        ),
        (
            "restricted",
            "Restricted content withheld",
            f"{sum(d['restricted_withheld'] for d in days) / asked:.1%} of questions",
            "Share of questions that touch a document the asker is not cleared for (1.8% to 3% a day).",
        ),
    ]
    out = []
    for fid, figure, value, basis in rows:
        sources = SOURCES.get(fid, [])
        out.append(
            {
                "id": fid,
                "figure": figure,
                "value": value,
                "basis": basis,
                "status": "cited" if sources else "assumption",
                "sources": sources,
            }
        )
    return out


def benchmarks_markdown(data: dict) -> str:
    """The table docs/console.md quotes (a test keeps the two identical)."""
    lines = ["| Figure | Sample value (last 30 days) | How it was set | Source |", "|---|---|---|---|"]
    for b in data["benchmarks"]:
        cite = (
            "<br>".join(
                f'[{s["title"]}]({s["url"]}), {s["publisher"]}, {s["year"]} (accessed {s["accessed"]}): "{s["quote"]}"'
                for s in b["sources"]
            )
            or "Assumption (no public benchmark cited)"
        )
        lines.append(f"| {b['figure']} | {b['value']} | {b['basis']} | {cite} |")
    return "\n".join(lines)


def build() -> dict:
    rng = random.Random(SEED)
    library = json.loads(LIBRARY.read_text())
    names = library["departments"]
    if set(names) != set(STAFFING):
        raise SystemExit(f"STAFFING must list exactly the catalog's departments: {sorted(set(names) ^ set(STAFFING))}")
    start = END - timedelta(days=DAYS - 1)
    active30 = {n: round(STAFFING[n][0] * STAFFING[n][2]) for n in names}
    topic_names = [t[0] for t in TOPICS]
    weights = {n: [t[1] * (3 if t[0] in FOCUS.get(n, ()) else 1) if asks(n, t) else 0.0 for t in TOPICS] for n in names}

    days, per_dept = [], []  # per_dept[i][name] = (questions, no_answer)
    for i in range(DAYS):
        d = start + timedelta(days=i)
        progress = i / (DAYS - 1)
        workday = d.weekday() < 5 and d not in HOLIDAYS
        engagement = (0.40 + 0.20 * (1 - math.exp(-2.6 * progress))) if workday else 0.06
        weekday_factor = [1.12, 1.0, 1.0, 0.98, 0.86, 1, 1][d.weekday()]
        no_answer_rate = 0.11 - 0.04 * progress + rng.uniform(-0.01, 0.01)  # the library fills its gaps
        active = questions = no_answer = 0
        topics = [0] * len(TOPICS)
        rows = {}
        for n in names:
            _head, per_user, _adoption, gap = STAFFING[n]
            a = min(active30[n], int(active30[n] * engagement * rng.uniform(0.94, 1.05)))
            q = int(a * per_user * rng.uniform(0.9, 1.1) * weekday_factor)
            na = min(q, round(q * no_answer_rate * gap))
            jitter = [w * rng.uniform(0.9, 1.1) for w in weights[n]]
            for j, c in enumerate(split(q, jitter)):
                topics[j] += c
            rows[n] = (q, na)
            active, questions, no_answer = active + a, questions + q, no_answer + na
        per_dept.append(rows)
        answered = questions - no_answer
        days.append(
            {
                "date": d.isoformat(),
                "active_users": active,
                "questions": questions,
                "answered": answered,
                "no_answer": no_answer,
                "restricted_withheld": int(questions * rng.uniform(0.018, 0.03)),
                "pii_redacted": int(questions * rng.uniform(0.012, 0.02)),
                "injection_flagged": rng.randint(0, 2) if workday else 0,
                "thumbs_up": int(answered * rng.uniform(0.18, 0.24) * (0.86 + 0.06 * progress)),
                "thumbs_down": int(answered * rng.uniform(0.18, 0.24) * (0.14 - 0.06 * progress)),
                "p50_ms": int(rng.uniform(1650, 2050) - 220 * progress),
                "p95_ms": int(rng.uniform(4100, 4900) - 500 * progress),
                "topics": dict(zip(topic_names, topics, strict=True)),
            }
        )
    last30 = per_dept[-30:]
    departments = []
    for n in names:
        q30 = sum(r[n][0] for r in last30)
        na30 = sum(r[n][1] for r in last30)
        departments.append(
            {
                "department": n,
                "headcount": STAFFING[n][0],
                "active_users_30d": active30[n],
                "questions_30d": q30,
                "answer_rate": round(1 - na30 / q30, 3) if q30 else 0.0,
            }
        )
    topics = [
        {
            "topic": t[0],
            "asked_by": "All staff" if t[2] == ALL_STAFF else t[2],
            "questions_30d": sum(d["topics"][t[0]] for d in days[-30:]),
        }
        for t in TOPICS
    ]
    collections = [
        {
            "collection": c["label"],
            "name": c["name"],
            "documents": c["documents"],
            "passages": c["passages"],
            "access": access_text(c, library["documents"], library["groups"]),
        }
        for c in library["collections"]
    ]
    notable = [
        {
            "date": "2026-10-05",
            "kind": "access",
            "title": "Restricted procedure stayed restricted",
            "detail": "A branch employee asked how BSA referrals are decided. The BSA/AML escalation procedure was "
            "filtered out before retrieval; the answer cited the all-staff Unusual Activity Referral Policy instead.",
        },
        {
            "date": "2026-10-01",
            "kind": "ops",
            "title": "October rate sheets published and re-indexed",
            "detail": "The October auto loan and savings rate sheets replaced September's overnight; the lobby kiosk "
            "and staff questions on rates now cite the October versions.",
        },
        {
            "date": "2026-09-22",
            "kind": "compliance",
            "title": "Model pin verified after a server patch",
            "detail": "The served model's digest matched the lock file after OS patching; the ML-BOM was attached "
            "to the change ticket for the IT examination file.",
        },
        {
            "date": "2026-09-08",
            "kind": "access",
            "title": "Quarterly access review completed",
            "detail": "Human resources and compliance reviewed every SSO group-to-role mapping, collection access "
            "list and document access list; two departed contractors' API keys were revoked.",
        },
        {
            "date": "2026-08-18",
            "kind": "ops",
            "title": "Prompt-injection text found in an uploaded vendor PDF",
            "detail": "The answer kept the vendor's terms but ignored the embedded instructions; the document was "
            "flagged for the vendor-management team.",
        },
    ]
    data = {
        "generated_by": "scripts/generate_sample_company.py",
        "seed": SEED,
        "disclaimer": "Fictional sample company. Generated data for demonstration, not measurements.",
        "period": {"start": start.isoformat(), "end": END.isoformat(), "days": DAYS},
        "company": COMPANY,
        "assumptions": ASSUMPTIONS,
        "days": days,
        "departments": sorted(departments, key=lambda x: -x["questions_30d"]),
        "topics": sorted(topics, key=lambda x: -x["questions_30d"]),
        "collections": collections,
        "compliance": {
            "data_sent_to_external_ai": 0,
            "sso_coverage": 1.0,
            "audit_chain_verified_rate": 1.0,
            "model_pin_verified_rate": 1.0,
            "encryption_at_rest": True,
            "access_reviews_on_schedule": True,
        },
        "notable": notable,
    }
    data["benchmarks"] = headline_figures(data)
    return data


def render(data: dict) -> str:
    return json.dumps(data, indent=1) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if the committed file is stale")
    args = ap.parse_args(argv)
    text = render(build())
    if args.check:
        if not OUT.exists() or OUT.read_text() != text:
            print(f"{OUT.relative_to(ROOT)} is stale: run python scripts/generate_sample_company.py")
            return 1
        print(f"{OUT.relative_to(ROOT)} is current")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text)
    d = json.loads(text)["days"][-30:]
    print(f"wrote {OUT.relative_to(ROOT)}: {sum(x['questions'] for x in d):,} questions in the last 30 days")
    return 0


if __name__ == "__main__":
    sys.exit(main())
