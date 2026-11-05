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
- Time saved uses a stated minutes-per-answer assumption and a loaded hourly cost; the
  infrastructure cost is a stated monthly figure for one on-prem GPU server.

Every headline figure is listed in the file's "benchmarks" table (computed from the generated rows, last 30
days) with the assumption behind it and, where one has been checked, the published source it is calibrated to.
A figure is "cited" only with a source someone fetched and read: title, publisher, year, URL and the quoted
sentence. The console's "How these sample numbers were set" panel and docs/console.md render from that table.
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
    "Member services and branches": (160, 3.0, 0.86, 1.0),
    "Lending": (48, 3.5, 0.90, 0.9),
    "IT and digital banking": (34, 2.4, 0.85, 1.1),
    "Payments and fraud operations": (26, 4.0, 0.92, 0.9),
    "Finance and accounting": (18, 2.2, 0.78, 1.1),
    "Compliance and BSA": (12, 4.5, 1.0, 0.8),
    "Marketing": (12, 1.6, 0.67, 1.3),
    "Human resources": (10, 2.9, 0.9, 1.0),
    "Facilities and security": (8, 1.2, 0.75, 1.2),
    "Executive": (8, 1.2, 0.75, 1.2),
    "Internal audit": (4, 3.0, 1.0, 0.9),
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

ASSUMPTIONS = {
    "minutes_saved_per_answer": 6,
    "loaded_cost_per_hour_usd": 52,
    "infrastructure_per_month_usd": 4200,
    "note": "Minutes saved per cited answer (versus searching shared drives or asking a colleague), "
    "the loaded hourly cost of an employee, and the monthly cost of the on-prem GPU server, power and "
    "support. Illustrative assumptions for the sample company, not measurements.",
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


# Published sources the sample is calibrated to, by figure id: {"title", "publisher", "year", "url", "quote",
# "range"}. Empty until a source has been fetched and read; a figure without one is labelled an assumption.
SOURCES: dict[str, dict] = {}


def headline_figures(data: dict) -> list[dict]:
    """The dashboard's headline figures (last 30 days), the assumption behind each, and its source if cited."""
    days, co, a = data["days"][-30:], data["company"], data["assumptions"]
    work = [d for d in days if d["active_users"] > 40]
    staff = co["employees"]
    active30 = sum(x["active_users_30d"] for x in data["departments"])
    asked, answered = sum(d["questions"] for d in days), sum(d["answered"] for d in days)
    up, down = sum(d["thumbs_up"] for d in days), sum(d["thumbs_down"] for d in days)
    hours = answered * a["minutes_saved_per_answer"] / 60
    per_user_week = hours / active30 / (len(days) / 7)
    rows = [
        (
            "staffing",
            "Staffing ratios",
            f"{staff} employees for {co['members']:,} members and ${co['assets_usd'] / 1e9:.1f}B in assets: "
            f"{co['members'] / staff:.0f} members and ${co['assets_usd'] / staff / 1e6:.1f}M in assets per employee",
            "Set for a mid-size credit union; to be checked against NCUA call-report ratios (members and assets per "
            "full-time-equivalent employee).",
        ),
        (
            "adoption",
            "Employees using it",
            f"{active30} of {staff} employees ({active30 / staff:.0%}) asked at least one question in 30 days; "
            f"{sum(d['active_users'] for d in work) / len(work):.0f} on an average workday",
            "Department adoption shares in STAFFING for a sanctioned internal assistant open to every employee; to be "
            "checked against published rates of generative AI use among employees.",
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
            f"{per_user_week:.1f} hours per active employee per week ({per_user_week / 40:.1%} of a 40-hour week)",
            "Minutes saved versus searching shared drives or asking a colleague; to be checked against published "
            "figures for time spent searching for information and self-reported time savings from generative AI.",
        ),
        (
            "hourly_cost",
            "Loaded hourly cost",
            f"${a['loaded_cost_per_hour_usd']} per hour",
            "Wages plus benefits per hour worked; to be checked against the BLS Employer Costs for Employee "
            "Compensation for financial activities.",
        ),
        (
            "infrastructure",
            "Infrastructure cost",
            f"${a['infrastructure_per_month_usd']:,} per month: ${a['infrastructure_per_month_usd'] / answered:.2f} "
            "per answer",
            "One on-prem server with 2 x NVIDIA L40S, with power and support; to be checked against hardware and "
            "cloud GPU list prices.",
        ),
        (
            "answer_rate",
            "Answered from documents",
            f"{answered / asked:.1%} of questions answered with citations",
            "The share that finds nothing to cite falls from about 11% to about 7% over 90 days as the library fills "
            "its gaps; to be checked against published help-desk and policy-question resolution rates.",
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
        src = SOURCES.get(fid)
        out.append(
            {
                "id": fid,
                "figure": figure,
                "value": value,
                "basis": basis,
                "status": "cited" if src else "assumption",
                "source": src,
            }
        )
    return out


def benchmarks_markdown(data: dict) -> str:
    """The table docs/console.md quotes (a test keeps the two identical)."""
    lines = ["| Figure | Sample value (last 30 days) | How it was set | Source |", "|---|---|---|---|"]
    for b in data["benchmarks"]:
        src = b["source"]
        cite = (
            f'[{src["title"]}]({src["url"]}), {src["publisher"]}, {src["year"]}: "{src["quote"]}"'
            if src
            else "Assumption (no public benchmark cited)"
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
        engagement = (0.50 + 0.30 * (1 - math.exp(-2.6 * progress))) if workday else 0.06
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
