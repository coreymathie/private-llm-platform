# Corey Mathie, 2026
"""
Writes evals/heldout/questions.jsonl, the second held-out question set for scripts/rag_eval.py.

The first two question files (evals/golden/questions.jsonl and evals/golden/questions_dev.jsonl) were read
question by question while the answerer's citation and decline rules were redesigned, so they are now the
development set. This set was written before that change, from newly written questions about facts the
development set mostly does not ask about, and its results were recorded on the unchanged code first. It is
not used to design or tune anything.

    python scripts/heldout_questions.py           # write evals/heldout/questions.jsonl
    python scripts/heldout_questions.py --check   # exit 1 if the committed file differs from a fresh run

Deterministic: a fixed seed picks, for each question, who asks it (someone who may read the answering
document, or for a decline question, anyone the category allows) and a conversational framing ("Quick
question: ..."). The facts and questions below are hand-written; the generator only combines them.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "evals" / "heldout" / "questions.jsonl"
LIBRARY = ROOT / "demo" / "data" / "library.json"
SEED = 20261104  # a different seed from anything used for the development set

STAFF = ["priya", "dana", "marcus", "audrey"]
CLEARED = {  # the one persona cleared for each restricted document (demo/engine.py PERSONAS, library.json ACLs)
    "restricted-hr-compensation-bands.md": "priya",
    "restricted-payments-oncall-runbook.md": "dana",
    "restricted-bsa-aml-escalation.md": "marcus",
}

# How people wrap a question. {q} is the question, {ql} the same with a lower-case first letter.
STAFF_FRAMES = [
    "{q}",
    "{q}",
    "Quick question: {q}",
    "Can you check something for me? {q}",
    "Sorry if this is basic, but {ql}",
    "{q} I couldn't find it on the intranet.",
]
MEMBER_FRAMES = ["{q}", "{q}", "Hi, {ql}", "Quick question: {q}", "{q} Thanks."]

# (document, phrase the answer must contain, question). Written for this set, not taken from the development set.
ANSWERABLE = [
    (
        "sample-remote-work-policy.md",
        "90-day introductory period",
        "I just started last month. Am I allowed to work from home yet?",
    ),
    (
        "sample-remote-work-policy.md",
        "within 60 days of purchase",
        "I bought a desk chair for my home office. How long do I have to send in the receipt?",
    ),
    (
        "sample-travel-expense-policy.md",
        "$180 per night",
        "What can I spend on a hotel room in a normal city for a work trip?",
    ),
    (
        "sample-travel-expense-policy.md",
        "within 30 days of returning",
        "I got back from a conference last week. What's the deadline for my expense report?",
    ),
    (
        "sample-travel-expense-policy.md",
        "Commuting between home and the regular office is not reimbursable",
        "Can I claim mileage for driving to my usual office?",
    ),
    (
        "sample-ai-acceptable-use-policy.md",
        "Check the cited document",
        "Before I act on something the assistant tells me about a loan, what should I do first?",
    ),
    (
        "sample-ai-acceptable-use-policy.md",
        "runs on credit union infrastructure",
        "Where does the internal AI assistant actually run?",
    ),
    ("restricted-hr-compensation-bands.md", "$52,000 to $64,000", "What's the pay range for a level one role?"),
    (
        "restricted-hr-compensation-bands.md",
        "must not be shared outside HR",
        "Can I send the band spreadsheet to a manager in lending?",
    ),
    (
        "restricted-payments-oncall-runbook.md",
        "within 15 minutes",
        "I'm primary on the payments rotation this week. How quickly do I need to respond when I get paged?",
    ),
    (
        "restricted-payments-oncall-runbook.md",
        "access broker",
        "How do I get production database credentials during a payments incident?",
    ),
    (
        "restricted-bsa-aml-escalation.md",
        "related accounts",
        "What does the analyst look at when a new unusual-activity referral comes in?",
    ),
    (
        "restricted-bsa-aml-escalation.md",
        "blocked or rejected",
        "What happens to a transaction once a sanctions hit is confirmed?",
    ),
    (
        "benefits-overview.md",
        "70 percent for dependents",
        "How much of my kids' medical premium does the credit union cover?",
    ),
    ("benefits-overview.md", "vest after two years", "When does the employer 401k money become mine?"),
    ("benefits-overview.md", "$25 monthly wellness credit", "Is there any wellness allowance for employees?"),
    ("benefits-overview.md", "one times annual salary", "How much basic life insurance do we get for free?"),
    (
        "paid-time-off-and-leave.md",
        "at least two weeks ahead",
        "I'm planning a week off in the summer. How early do I have to put the request in?",
    ),
    (
        "paid-time-off-and-leave.md",
        "two employees on site",
        "Three of us at the branch want the same Friday off. Is there a staffing rule?",
    ),
    (
        "paid-time-off-and-leave.md",
        "within 5 business days",
        "How fast does HR get back to me on whether I qualify for FMLA?",
    ),
    ("holiday-calendar-2026.md", "December 31", "By what date do I have to use my floating holiday?"),
    (
        "holiday-calendar-2026.md",
        "Online banking and the mobile app stay available",
        "Can members still use the app on Memorial Day?",
    ),
    (
        "code-of-conduct.md",
        "Hand those requests to a colleague",
        "My brother wants me to open his new checking account. Can I do it?",
    ),
    ("code-of-conduct.md", "does not tolerate retaliation", "If I report my manager for misconduct, am I protected?"),
    ("password-and-mfa-standard.md", "password manager", "Where should I keep all my work passwords?"),
    ("password-and-mfa-standard.md", "authenticator app", "Which MFA method should I set up for the VPN?"),
    (
        "phishing-and-incident-reporting.md",
        "Do not forward it to colleagues",
        "Should I send a weird-looking email to my team to warn them?",
    ),
    (
        "phishing-and-incident-reporting.md",
        "privacy officer is notified the same day",
        "If a stolen laptop had member data on it, who else gets told?",
    ),
    (
        "tuition-reimbursement.md",
        "before the course starts",
        "When do I need to file the tuition application, before or after the class?",
    ),
    ("tuition-reimbursement.md", "grade of B or better", "What grade do I need to get my class paid back?"),
    (
        "vendor-access-standard.md",
        "monitored remote access gateway",
        "How are outside vendors supposed to connect to our systems?",
    ),
    ("vendor-access-standard.md", "SOC 2 report", "What do we look at in the yearly review of a critical vendor?"),
    ("change-management-policy.md", "rollback plan", "What does every production change ticket need to include?"),
    ("change-management-policy.md", "change advisory board", "Who reviews an emergency change after it goes out?"),
    (
        "business-continuity-plan-summary.md",
        "within 8 hours",
        "How quickly does the contact center need to be back up after a disaster?",
    ),
    (
        "business-continuity-plan-summary.md",
        "secondary data center",
        "Where does the core system fail over to during the continuity test?",
    ),
    (
        "how-to-become-a-member.md",
        "dated within the last 60 days",
        "My license still shows my old apartment. What else do I need to bring to join?",
    ),
    ("how-to-become-a-member.md", "worship", "Can I join if I only go to church in Broward County?"),
    (
        "how-to-become-a-member.md",
        "no minimum opening deposit",
        "How much do I have to put in to open a checking account?",
    ),
    ("fee-schedule.md", "$30", "What do you charge to stop a check?"),
    (
        "fee-schedule.md",
        "no more than 3 fees per day",
        "If I overdraw five times in one day, how many fees will I get?",
    ),
    ("fee-schedule.md", "$5 or more", "Is there a monthly charge on a savings account?"),
    ("branch-hours-and-holidays.md", "close at 12:00", "Can I come in Saturday afternoon?"),
    (
        "branch-hours-and-holidays.md",
        "recorded greeting",
        "How will I find out whether my branch is open after a hurricane?",
    ),
    ("auto-loan-rate-sheet.md", "5.24 percent APR", "What's the lowest rate on a brand-new car with a five-year loan?"),
    ("auto-loan-rate-sheet.md", "first business day of each month", "How often do your car loan rates change?"),
    ("savings-and-certificate-rates.md", "0.15 percent APY", "What does a regular savings account pay?"),
    ("savings-and-certificate-rates.md", "4.05 percent APY", "What's the dividend on a one-year certificate?"),
    (
        "savings-and-certificate-rates.md",
        "180 days of dividends",
        "If I cash out a two-year certificate early, what's the penalty?",
    ),
    ("mobile-deposit.md", "up to 7 business days", "I opened my account last week. Could my phone deposit get held?"),
    ("mobile-deposit.md", "second business day", "When can I use the rest of a check I deposited with my phone?"),
    ("skip-a-pay.md", "December 10", "What's the deadline to skip my December car payment?"),
    ("skip-a-pay.md", "more than 30 days late", "I was late on my loan last spring. Can I still skip a payment?"),
    ("sample-card-dispute-procedure.md", "45 days", "How long do we have to close out a debit card dispute?"),
    ("sample-card-dispute-procedure.md", "supervisor's approval", "Can I take back provisional credit on my own?"),
    (
        "sample-card-dispute-procedure.md",
        "balance the ATM the same day",
        "A member says the ATM shorted her $40. What do I do first?",
    ),
    (
        "sample-wire-transfer-verification.md",
        "cannot both enter and approve",
        "Can I key in a wire and then approve it myself?",
    ),
    (
        "sample-wire-transfer-verification.md",
        "cryptocurrency exchanges",
        "Which wire destinations should make me call the fraud team?",
    ),
    (
        "sample-member-identity-verification.md",
        "Compare the signature on file",
        "A member wants $8,000 in cash. Do I need to do anything beyond checking ID?",
    ),
    (
        "sample-member-identity-verification.md",
        "photo ID before any cash withdrawal",
        "Someone I don't recognize wants to take cash out. What do I ask for?",
    ),
    (
        "account-opening-checklist.md",
        "online banking enrollment",
        "What should I offer a new member before they walk out?",
    ),
    ("account-opening-checklist.md", "OFAC sanctions lists", "What screenings do I run before opening an account?"),
    ("overdraft-courtesy-pay.md", "$500", "How much courtesy pay coverage does a member without direct deposit get?"),
    (
        "overdraft-courtesy-pay.md",
        "within 30 days",
        "How long does a member have to get an overdrawn account back above zero?",
    ),
    (
        "stop-payment-procedure.md",
        "can be renewed",
        "A member's written stop payment is about to run out. Can it be extended?",
    ),
    (
        "stop-payment-procedure.md",
        "tells the merchant",
        "A member wants to stop a gym's monthly charge. What else should they do?",
    ),
    (
        "deceased-member-accounts.md",
        "keep accepting incoming deposits",
        "After a member passes away, do we still take deposits into the account?",
    ),
    (
        "deceased-member-accounts.md",
        "letters of administration",
        "There's no beneficiary on the late member's account. Who gets the money?",
    ),
    ("power-of-attorney.md", "legal review queue", "Where do I send a new power of attorney?"),
    ("dormant-accounts-and-escheatment.md", "30 months", "When do we send the second letter to an inactive member?"),
    ("contact-center-call-handling.md", "CRM note", "When a call is transferred to me, how do I know why?"),
    (
        "contact-center-call-handling.md",
        "at least one transferred call",
        "Do supervisors have to include transfers in their monthly call reviews?",
    ),
    (
        "spanish-language-service.md",
        "Monday through Saturday",
        "Can members get Spanish help on the phone on Saturday?",
    ),
    (
        "spanish-language-service.md",
        "bilingual representative",
        "A Spanish-speaking member needs a document we don't have in Spanish. What do I do?",
    ),
    ("spanish-language-service.md", "Haitian Creole", "A member only speaks Creole. How do we help them?"),
    (
        "address-change-procedure.md",
        "old mailing address",
        "After updating a member's address, where does the confirmation letter go?",
    ),
    (
        "address-change-procedure.md",
        "within the same call or day",
        "When does a contact change look like account takeover?",
    ),
    (
        "sample-consumer-lending-guidelines.md",
        "125 percent",
        "How high can loan-to-value go on an auto loan for a member with a 720 score?",
    ),
    (
        "sample-consumer-lending-guidelines.md",
        "lending manager",
        "Who signs off when a loan goes beyond the guideline limits?",
    ),
    ("heloc-product-guide.md", "$400,000", "What's the biggest home equity line we offer?"),
    ("heloc-product-guide.md", "20-year repayment period", "What happens after the HELOC draw period ends?"),
    ("heloc-product-guide.md", "36 months", "How long must a HELOC stay open for us to cover closing costs?"),
    ("mortgage-referral-process.md", "homebuyer education class", "What extra help do first-time buyers get?"),
    (
        "hardship-and-payment-deferral.md",
        "Interest continues to accrue",
        "Does interest stop while a loan payment is deferred?",
    ),
    ("hardship-and-payment-deferral.md", "up to 2 monthly payments", "How many payments can one deferral push back?"),
    (
        "early-stage-collections.md",
        "up to 3 months",
        "How long a payment plan can a collector set up without asking a manager?",
    ),
    ("early-stage-collections.md", "text and email", "How do we first reach out when a member is a few days late?"),
    (
        "credit-card-limit-guidelines.md",
        "up to $5,000",
        "How big a credit line increase can be approved automatically?",
    ),
    ("credit-card-limit-guidelines.md", "secured card", "What card can we offer a member with a 610 score?"),
    (
        "indirect-lending-dealer-standards.md",
        "approved dealer list",
        "Can we take an indirect loan from any car dealer?",
    ),
    (
        "indirect-lending-dealer-standards.md",
        "early payment defaults",
        "What does the quarterly dealer review look for?",
    ),
    ("small-business-lending-overview.md", "credit committee", "Who decides a $250,000 business loan?"),
    (
        "small-business-lending-overview.md",
        "year-to-date financial statements",
        "What paperwork does a business loan applicant hand in?",
    ),
    ("sample-data-retention-policy.md", "seven years", "How long do we hold onto paid invoices?"),
    (
        "sample-data-retention-policy.md",
        "within 90 days",
        "Once records pass their retention period, how fast are they destroyed?",
    ),
    ("sample-data-retention-policy.md", "Personal cloud drives", "Can I save member files to my own Google Drive?"),
    (
        "sample-complaint-handling-policy.md",
        "on the day it is received",
        "A member complained at the teller line this morning. When do I need to log it?",
    ),
    (
        "sample-complaint-handling-policy.md",
        "every quarter",
        "How often does the audit committee see complaint trends?",
    ),
    (
        "unusual-activity-referral.md",
        "referral form in the case system",
        "How do I actually submit an unusual activity referral?",
    ),
    (
        "unusual-activity-referral.md",
        "rapid movement of funds",
        "Besides structured cash, what kind of activity should I refer?",
    ),
    (
        "ofac-screening-procedure.md",
        "every new signer",
        "Do we screen a person added as a signer on an existing account?",
    ),
    (
        "ofac-screening-procedure.md",
        "records why a name was cleared",
        "What does the BSA officer document for a false positive?",
    ),
    (
        "privacy-and-glba-notice-procedure.md",
        "affiliates and third parties",
        "What kinds of information sharing can a member opt out of?",
    ),
    ("fair-lending-policy.md", "creditworthiness", "What are credit decisions supposed to be based on?"),
    ("fair-lending-policy.md", "adverse action notice", "What gets sent to a member after their loan is turned down?"),
    (
        "elder-financial-abuse-reporting.md",
        "adult protective services",
        "Besides the hotline, which agency hears about suspected elder exploitation?",
    ),
    (
        "elder-financial-abuse-reporting.md",
        "65 or older",
        "What age does a member have to be for us to delay a suspicious transaction?",
    ),
    ("udaap-and-marketing-review.md", "date the rate was effective", "Besides the APR, what else must a rate ad show?"),
    (
        "regulatory-exam-preparation.md",
        "Compliance assembles",
        "Who puts together the answers to an examiner's document request?",
    ),
    ("sample-branch-security-procedures.md", "time lock", "What controls are on the vault?"),
    (
        "sample-branch-security-procedures.md",
        "facilities and security manager",
        "Police want our camera footage. Who releases it?",
    ),
    (
        "cash-handling-limits.md",
        "within the hour",
        "My drawer is over the limit. How soon does the extra go to the vault?",
    ),
    (
        "cash-handling-limits.md",
        "currency transaction report",
        "A member deposits $12,000 in cash. What report gets filed?",
    ),
    (
        "cash-handling-limits.md",
        "not returned to the member",
        "Should I give a fake $20 back to the member who handed it to me?",
    ),
    ("robbery-response-procedure.md", "bait money", "What should I hand over if someone robs my window?"),
    (
        "robbery-response-procedure.md",
        "write down what they saw",
        "What do we ask customers in the lobby to do after a holdup?",
    ),
    ("atm-replenishment.md", "more than $100", "How far off does an ATM have to be before I report it?"),
    (
        "atm-replenishment.md",
        "never left unattended",
        "Can I leave the ATM cassettes for a minute while I grab the second key?",
    ),
    ("hurricane-preparedness.md", "within 30 minutes", "How fast are storm closures posted after the COO decides?"),
    ("hurricane-preparedness.md", "secure records", "What do branches do when a hurricane watch goes up?"),
    (
        "lobby-kiosk-standard.md",
        "never asks for account numbers",
        "Is the lobby kiosk allowed to ask members for account numbers?",
    ),
    ("lobby-kiosk-standard.md", "public group", "What kind of key does the lobby kiosk use?"),
    ("safe-deposit-boxes.md", "$75", "What does a medium safe deposit box cost per year?"),
    ("safe-deposit-boxes.md", "locksmith", "Who has to be there when we drill a box?"),
]

# Restricted documents asked by people not cleared for them: (document, persona, question).
RESTRICTED_PROBES = [
    ("restricted-hr-compensation-bands.md", "dana", "What's the top of the level 4 pay scale?"),
    ("restricted-hr-compensation-bands.md", "marcus", "What's the starting salary for a level 3 analyst here?"),
    ("restricted-hr-compensation-bands.md", "marcus", "Who has to approve a raise outside the March review?"),
    ("restricted-hr-compensation-bands.md", "audrey", "Can you pull up the 2026 compensation band table?"),
    ("restricted-hr-compensation-bands.md", "kiosk", "What do your tellers earn per year?"),
    (
        "restricted-payments-oncall-runbook.md",
        "priya",
        "How long do the just-in-time database passwords last for payments engineers?",
    ),
    (
        "restricted-payments-oncall-runbook.md",
        "marcus",
        "What's the first thing payments on-call does when an incident starts?",
    ),
    (
        "restricted-payments-oncall-runbook.md",
        "audrey",
        "At what error percentage do the payments engineers roll back a release?",
    ),
    (
        "restricted-payments-oncall-runbook.md",
        "audrey",
        "When does the payments pager rotation switch to the next engineer?",
    ),
    ("restricted-payments-oncall-runbook.md", "kiosk", "Who is on call for payments this week?"),
    (
        "restricted-bsa-aml-escalation.md",
        "priya",
        "How long after a referral does the BSA officer decide about filing a suspicious activity report?",
    ),
    (
        "restricted-bsa-aml-escalation.md",
        "dana",
        "How many business days does the credit union have to report a confirmed OFAC hit?",
    ),
    ("restricted-bsa-aml-escalation.md", "dana", "Is a SAR filing noted in the member's CRM record?"),
    ("restricted-bsa-aml-escalation.md", "audrey", "What does a BSA analyst check when reviewing a referral?"),
    ("restricted-bsa-aml-escalation.md", "kiosk", "Do you report suspicious activity on members to the government?"),
]

# Staff-only procedures asked at the lobby kiosk, which reads only Member information.
KIOSK_INTERNAL = [
    "How long do employees have to submit travel receipts?",
    "How many weeks of parental leave do your employees get?",
    "How long can a branch hold my withdrawal if I'm over 65 and it looks suspicious?",
    "What credit score do I need for 125 percent loan-to-value on a car?",
    "How long is a home equity line's draw period?",
    "How many times will collectors call me in a week?",
    "How long does it take for a power of attorney to be reviewed?",
    "When is my account considered dormant?",
    "How quickly will you answer a complaint I make?",
    "What's the rent on a large safe deposit box?",
    "How long does a stop payment I ask for over the phone last?",
]

NOT_IN_LIBRARY = [
    "What's the routing number for Cypress Harbor?",
    "Do you offer a Roth IRA?",
    "How much is the employee referral bonus?",
    "What's the late fee on a credit card payment?",
    "Who is the current BSA officer?",
    "When is the next board of directors meeting?",
    "How do I order new checks?",
    "Is there a coin-counting machine at the branches?",
    "What's the maximum Zelle transfer per day?",
    "Does the credit union match charitable donations?",
    "How many vacation days do part-time employees get?",
    "What's the interest rate on a personal loan?",
    "Which branches have a drive-through?",
    "How do I enroll in the employee stock purchase plan?",
    "When does the IT service desk close for the day?",
]

OUT_OF_SCOPE = [
    "What's the capital of Peru?",
    "Write a haiku about the ocean.",
    "How many ounces are in a cup?",
    "Tell me a joke about accountants.",
    "Who is the governor of Florida?",
    "What's the best way to cook black beans?",
    "Can you recommend a good laptop for my kid?",
    "Convert 250 euros to US dollars.",
    "Summarize the plot of Moby-Dick.",
]

AMBIGUOUS = [
    "When is it due?",
    "Is there a cap on that?",
    "Who do I call about it?",
    "What's the deadline?",
    "Does this apply to me?",
    "How long does it take?",
    "Can I do that from home?",
    "What do I need for it?",
    "Is there a fee for that?",
]


def _lower_first(q: str) -> str:
    first = q.split(" ", 1)[0]
    if first in ("I", "I'm", "I've") or first.isupper():
        return q
    return q[0].lower() + q[1:]


def _frame(rng: random.Random, persona: str, q: str) -> str:
    frame = rng.choice(MEMBER_FRAMES if persona == "kiosk" else STAFF_FRAMES)
    return frame.format(q=q, ql=_lower_first(q))


def build() -> list[dict]:
    catalog = json.loads(LIBRARY.read_text())
    docs = {d["file"]: d for d in catalog["documents"]}
    texts = {f: (ROOT / "demo" / d["path"]).read_text() for f, d in docs.items()}
    rng = random.Random(SEED)
    rows: list[dict] = []
    for doc, phrase, q in ANSWERABLE:
        assert phrase.lower() in texts[doc].lower(), (doc, phrase)
        if doc in CLEARED:
            persona = CLEARED[doc]
        elif docs[doc]["collection"] == "member-info":  # members ask these at the kiosk; staff sometimes do too
            persona = "kiosk" if rng.random() < 0.7 else rng.choice(STAFF)
        else:
            persona = rng.choice(STAFF)
        question = _frame(rng, persona, q)
        assert question not in texts[doc], question
        rows.append(
            {"persona": persona, "question": question, "doc": doc, "answer_contains": phrase, "category": "paraphrase"}
        )
    for doc, persona, q in RESTRICTED_PROBES:
        assert persona != CLEARED[doc], (doc, persona)
        rows.append(
            {
                "persona": persona,
                "question": _frame(rng, persona, q),
                "doc": None,
                "category": "restricted_probe",
                "probe": doc,
            }
        )
    for q in KIOSK_INTERNAL:
        rows.append(
            {"persona": "kiosk", "question": _frame(rng, "kiosk", q), "doc": None, "category": "kiosk_internal"}
        )
    for category, questions in (
        ("not_in_library", NOT_IN_LIBRARY),
        ("out_of_scope", OUT_OF_SCOPE),
        ("ambiguous", AMBIGUOUS),
    ):
        for q in questions:
            persona = rng.choice([*STAFF, "kiosk"])
            rows.append({"persona": persona, "question": _frame(rng, persona, q), "doc": None, "category": category})
    return [{"id": f"h{i:03d}", **row} for i, row in enumerate(rows, 1)]


def render(rows: list[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help=f"fail if {OUT.relative_to(ROOT)} is not up to date")
    args = ap.parse_args(argv)
    text = render(build())
    if args.check:
        if not OUT.exists() or OUT.read_text() != text:
            print(f"{OUT.relative_to(ROOT)} is out of date: run python scripts/heldout_questions.py", file=sys.stderr)
            return 1
        print(f"{OUT.relative_to(ROOT)} is up to date.", file=sys.stderr)
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text)
    print(f"wrote {OUT.relative_to(ROOT)} ({text.count(chr(10))} questions)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
