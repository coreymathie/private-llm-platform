# Corey Mathie, 2026
"""
Answer-quality evaluation over the console's own sample library: the Cypress Harbor Credit Union documents
(demo/data/library.json, written by scripts/sample_library.py) and staff and member questions in two files:
evals/golden/questions.jsonl, the gated set that evals/thresholds.json was measured on, and
evals/golden/questions_heldout.jsonl, a larger held-out set written later and never used for tuning. Both are
reported; quality thresholds apply to the gated set, and the ACL leak gate (0) to every question.

    python scripts/rag_eval.py                 # Markdown tables for every retrieval configuration
    python scripts/rag_eval.py --json          # machine-readable
    python scripts/rag_eval.py --check         # exit 1 if a gated metric is below evals/thresholds.json, or any leak
    python scripts/rag_eval.py --console-data  # write demo/data/rag_eval.json for the console's Evals screen

Each question names the persona who asks it (demo/engine.py's PERSONAS: groups, roles) and either the document
that answers it with a phrase the answer must contain, or no document: a question the assistant should decline,
because nothing in the library answers it or because the answer sits in a document the asker is not cleared for.
Its category says which: paraphrase (answerable), restricted_probe (the answer is in the restricted document named
by "probe", which the asker may not read), kiosk_internal (a staff-only procedure asked at the lobby kiosk),
not_in_library, out_of_scope or ambiguous.

Runs offline and deterministically. Ingestion, collection and document access lists, access decisions and
retrieval are the gateway's own code (gateway/rag.py, gateway/identity.py, gateway/retrieval.py); questions go
through the console's "All sources" path (demo/engine.py: retrieve_all, then answer, which declines below the
relevance floor), with the browser demo's embedder (hashed bag-of-words, not a neural model) and its extractive
answerer (no LLM). The numbers measure that pipeline, not a real model's answers.

Metrics, per configuration (retrieval mode + reranker), at k passages:
  recall@1, recall@k   share of answerable questions whose expected document is in the top 1 / top k passages
  mrr                  mean reciprocal rank of the first passage from the expected document (0 if absent)
  citation_accuracy    share of answerable questions whose answer cites at least one source and only sources
                       from the expected document
  answer_contains      share of answerable questions whose answer contains the expected phrase (case-insensitive)
  decline_accuracy     share of decline questions answered with the assistant's "I don't know" and no citation
  acl_leaks            passages retrieved (top 12) from a document the asking persona may not read, counted for
                       every question asked as every persona; must be 0. Readability comes from the catalog's
                       access lists, decided here independently of the gateway's own access code.
  acl_leak_checks      retrievals checked for leaks (questions x personas)
  restricted_probes    of those, retrievals of a question about a restricted document (its doc or probe) by a
                       persona not cleared for that document
  declines_by_category decline questions declined correctly, per category: [declined, asked]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "evals" / "golden"
QUESTIONS = GOLDEN / "questions.jsonl"
HELDOUT = GOLDEN / "questions_heldout.jsonl"
LIBRARY = ROOT / "demo" / "data" / "library.json"
THRESHOLDS = ROOT / "evals" / "thresholds.json"
CONSOLE_DATA = ROOT / "demo" / "data" / "rag_eval.json"
CONFIGS = [("vector", "none"), ("bm25", "none"), ("hybrid", "none"), ("hybrid", "lexical")]
LEAK_TOP_K = 12

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _questions(path: Path, which: str) -> list[dict]:
    return [{**json.loads(line), "set": which} for line in path.read_text().splitlines() if line.strip()]


def load_golden(heldout: bool = False) -> tuple[dict, dict[str, str], list[dict]]:
    """The library catalog, every document's text by file name, and the gated questions (plus the held-out set).

    Each question carries "set": "gated" or "heldout".
    """
    catalog = json.loads(LIBRARY.read_text())
    texts = {d["file"]: (ROOT / "demo" / d["path"]).read_text() for d in catalog["documents"]}
    questions = _questions(QUESTIONS, "gated") + (_questions(HELDOUT, "heldout") if heldout else [])
    return catalog, texts, questions


def readable(catalog: dict, principal) -> set[str]:
    """Documents a principal may read, from the catalog's access lists alone (the leak check's oracle).

    Admin reads everything; reader:* or reader:<c> opens a collection; otherwise the collection's list must name
    one of the principal's groups, key or user. A document's own list must also match, except for admins.
    """
    if "admin" in principal.roles:
        return {d["file"] for d in catalog["documents"]}
    names = {f"group:{g}" for g in principal.groups} | {principal.label, f"key:{principal.label}"}
    readers = {r.split(":", 1)[1] for r in principal.roles if r.startswith("reader:")}
    open_cols = {
        c["name"]
        for c in catalog["collections"]
        if "*" in readers or c["name"] in readers or names & set(c.get("acl") or [])
    }
    return {
        d["file"]
        for d in catalog["documents"]
        if d["collection"] in open_cols and (not d["acl"] or names & set(d["acl"]))
    }


def _aggregate(k: int, mode: str, reranker: str, outcomes: list[dict]) -> dict:
    """Metrics over one set of per-question outcomes (see the module docstring)."""
    answers = [o for o in outcomes if o["doc"]]
    declines = [o for o in outcomes if not o["doc"]]
    n_ans, n_dec = len(answers) or 1, len(declines) or 1
    by_category: dict[str, list[int]] = {}
    for o in declines:
        tally = by_category.setdefault(o["category"], [0, 0])
        tally[0] += o["ok"]
        tally[1] += 1
    return {
        "mode": mode,
        "reranker": reranker,
        "recall@1": round(sum(o["rank"] == 1 for o in answers) / n_ans, 4),
        f"recall@{k}": round(sum(o["rank"] > 0 for o in answers) / n_ans, 4),
        "mrr": round(sum(1 / o["rank"] for o in answers if o["rank"]) / n_ans, 4),
        "citation_accuracy": round(sum(o["cite_ok"] for o in answers) / n_ans, 4),
        "answer_contains": round(sum(o["has"] for o in answers) / n_ans, 4),
        "decline_accuracy": round(sum(o["ok"] for o in declines) / n_dec, 4),
        "acl_leaks": sum(o["leaks"] for o in outcomes),
        "acl_leak_checks": sum(o["checks"] for o in outcomes),
        "restricted_probes": sum(o["probes"] for o in outcomes),
        "declines_by_category": dict(sorted(by_category.items())),
        "failures": [o["failure"] for o in outcomes if o["failure"]],
    }


def _counts(questions: list[dict]) -> dict:
    return {
        "questions": len(questions),
        "answerable": sum(1 for q in questions if q["doc"]),
        "declines": sum(1 for q in questions if not q["doc"]),
    }


async def _evaluate(k: int, configs: list[tuple[str, str]], heldout: bool) -> dict:
    from demo import engine
    from gateway import rag, store

    catalog, texts, questions = load_golden(heldout)
    store.init_db()
    rag.init_rag()
    for d in catalog["documents"]:
        await rag.add_document(
            d["collection"], d["file"], texts[d["file"]], "rag-eval", "2026-01-01T00:00:00+00:00", acl=d["acl"]
        )
    for c in catalog["collections"]:
        rag.set_collection_acl(c["name"], c.get("acl") or [], "rag-eval", "2026-01-01T00:00:00+00:00")
    personas = sorted({q["persona"] for q in questions})
    principals = {p: engine.persona_principal(p) for p in personas}
    allowed = {p: readable(catalog, principals[p]) for p in personas}
    restricted = [d["file"] for d in catalog["documents"] if d["acl"]]

    results, full = {}, {}
    for mode, reranker in configs:
        config = {"mode": mode, "reranker": reranker}
        outcomes = []
        for q in questions:
            sources, _access, _where = await engine.retrieve_all(principals[q["persona"]], q["question"], k, config)
            titles = [s.title for s in sources]
            reply = (await engine.answer(q["question"], sources)).content if sources else engine.NO_ANSWER
            cited = sorted({titles[n - 1] for n in rag.cited_numbers(reply) if 0 < n <= len(titles)})
            o = {"set": q["set"], "doc": q["doc"], "category": q.get("category", "decline"), "failure": None}
            if q["doc"]:
                o["rank"] = titles.index(q["doc"]) + 1 if q["doc"] in titles else 0
                o["cite_ok"] = bool(cited) and cited == [q["doc"]]
                o["has"] = q["answer_contains"].lower() in reply.lower()
                if not (o["rank"] == 1 and o["cite_ok"] and o["has"]):
                    o["failure"] = {"id": q["id"], "rank": o["rank"], "cited": cited, "contains": o["has"]}
            else:
                o["ok"] = reply == engine.NO_ANSWER and not cited
                if not o["ok"]:
                    o["failure"] = {"id": q["id"], "rank": 0, "cited": cited, "declined": False}
            target = q["doc"] if q["doc"] in restricted else q.get("probe")
            o["leaks"] = o["checks"] = o["probes"] = 0
            for p in personas:  # the same question from every persona: nothing it can't read may be retrieved
                hidden, _a, _w = await engine.retrieve_all(principals[p], q["question"], LEAK_TOP_K, config)
                o["leaks"] += sum(s.title not in allowed[p] for s in hidden)
                o["checks"] += 1
                o["probes"] += bool(target) and target not in allowed[p]
            outcomes.append(o)
        name = f"{mode}+{reranker}"
        results[name] = _aggregate(k, mode, reranker, [o for o in outcomes if o["set"] == "gated"])
        if heldout:
            full[name] = _aggregate(k, mode, reranker, outcomes)
    gated = [q for q in questions if q["set"] == "gated"]
    report = {
        "k": k,
        **_counts(gated),
        "documents": len(catalog["documents"]),
        "collections": len(catalog["collections"]),
        "restricted_documents": len(restricted),
        "personas": personas,
        "embedder": "demo hashed bag-of-words (512-d), not a neural model",
        "answerer": "demo extractive (no LLM), with the console's relevance floor",
        "results": results,
    }
    if heldout:  # the gated set plus the held-out set: reported, leak-gated, not quality-gated
        report["full"] = {**_counts(questions), "heldout": len(questions) - len(gated), "results": full}
    return report


def evaluate(k: int = 4, configs: list[tuple[str, str]] | None = None, heldout: bool = True) -> dict:
    """Run the eval in a throwaway database; restores the gateway settings and backend afterwards.

    heldout=False evaluates the gated set only (the browser re-run, which compares it with the committed results).
    """
    return asyncio.run(evaluate_async(k, configs, heldout))


async def evaluate_async(k: int = 4, configs: list[tuple[str, str]] | None = None, heldout: bool = True) -> dict:
    """evaluate() for callers already inside an event loop (the console runs it in the browser)."""
    from demo.engine import DEMO_EMBED_MODEL, DemoBackend
    from gateway import backends
    from gateway.config import settings

    saved = settings.model_dump()
    with tempfile.TemporaryDirectory() as tmp:
        settings.GATEWAY_DB_PATH = str(Path(tmp) / "eval.db")
        settings.GATEWAY_EMBED_MODEL = DEMO_EMBED_MODEL
        settings.GATEWAY_COLLECTION_DEFAULT_ACCESS = "open"  # every sample collection has its own list anyway
        settings.GATEWAY_RRF_K = 60
        backends.set_backend(DemoBackend())
        try:
            return await _evaluate(k, configs or CONFIGS, heldout)
        finally:
            for name, value in saved.items():
                setattr(settings, name, value)
            backends.set_backend(None)


def check(report: dict, thresholds: dict) -> list[str]:
    """Gated metrics below their minimum (or leaks above zero)."""
    problems = []
    for config, minimums in thresholds["configs"].items():
        got = report["results"].get(config)
        if got is None:
            problems.append(f"{config}: not evaluated")
            continue
        for metric, minimum in minimums.items():
            if got[metric] < minimum:
                problems.append(f"{config}: {metric} {got[metric]} < {minimum}")
    leak_results = report.get("full", report)["results"]  # every question, held-out ones included
    for config, got in leak_results.items():
        if got["acl_leaks"] > thresholds.get("max_acl_leaks", 0):
            problems.append(f"{config}: {got['acl_leaks']} restricted passages leaked")
    return problems


def metrics_table(results: dict, k: int) -> str:
    lines = [
        f"| Configuration | recall@1 | recall@{k} | MRR | citation accuracy | answer contains "
        "| decline accuracy | ACL leaks |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, r in results.items():
        lines.append(
            f"| `{name}` | {r['recall@1']:.3f} | {r[f'recall@{k}']:.3f} | {r['mrr']:.3f} | "
            f"{r['citation_accuracy']:.3f} | {r['answer_contains']:.3f} | {r['decline_accuracy']:.3f} | "
            f"{r['acl_leaks']} |"
        )
    return "\n".join(lines)


def declines_table(results: dict) -> str:
    cats = sorted({c for r in results.values() for c in r["declines_by_category"]})
    lines = [f"| Configuration | {' | '.join(c.replace('_', ' ') for c in cats)} |", "|---|" + "---:|" * len(cats)]
    for name, r in results.items():
        got = r["declines_by_category"]
        lines.append(
            f"| `{name}` | " + " | ".join(f"{got[c][0]}/{got[c][1]}" if c in got else "-" for c in cats) + " |"
        )
    return "\n".join(lines)


def leak_line(results: dict) -> str:
    r = next(iter(results.values()))
    return (
        f"ACL leak checks per configuration: {r['acl_leak_checks']} retrievals (every question as every persona, "
        f"top {LEAK_TOP_K}), {r['restricted_probes']} of them a restricted document's question asked by a persona "
        "not cleared for it."
    )


def markdown(report: dict) -> str:
    k = report["k"]
    lines = [
        f"Gated set: {report['questions']} questions ({report['answerable']} answerable, {report['declines']} to "
        f"decline) over the Cypress Harbor sample library: {report['documents']} documents in "
        f"{report['collections']} collections ({report['restricted_documents']} restricted), asked as "
        f"{len(report['personas'])} personas, k={k}. Embedder: {report['embedder']}. Answers: {report['answerer']}.",
        "",
        metrics_table(report["results"], k),
        "",
        leak_line(report["results"]),
    ]
    if "full" in report:
        f = report["full"]
        lines += [
            "",
            f"Full set (gated + {f['heldout']} held out): {f['questions']} questions ({f['answerable']} answerable, "
            f"{f['declines']} to decline). Quality thresholds apply to the gated set only; the leak gate to every "
            "question.",
            "",
            metrics_table(f["results"], k),
            "",
            leak_line(f["results"]),
            "",
            "Decline questions declined correctly, full set, by category:",
            "",
            declines_table(f["results"]),
        ]
    return "\n".join(lines)


def console_data(report: dict) -> dict:
    """What the console's Evals screen shows: this report, the gates, and the files that produced it.

    No timestamp, so the committed file only changes when results change (a test compares it to a fresh run).
    """
    catalog, _texts, questions = load_golden(heldout="full" in report)
    thresholds = json.loads(THRESHOLDS.read_text())
    docs = [f"demo/{d['path']}" for d in catalog["documents"]]
    return {
        "generated_by": "python scripts/rag_eval.py --console-data",
        "measured": True,
        "report": report,
        "thresholds": thresholds,
        "problems": check(report, thresholds),
        "questions": {
            q["id"]: {
                "question": q["question"],
                "doc": q["doc"],
                "persona": q["persona"],
                "category": q.get("category"),
                "set": q["set"],
            }
            for q in questions
        },
        "golden_files": ["demo/data/library.json", *docs, "evals/golden/questions.jsonl", "evals/thresholds.json"],
        "heldout_files": ["evals/golden/questions_heldout.jsonl"],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--k", type=int, default=4, help="passages retrieved per question (default 4, the API default)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check", action="store_true", help="fail if a metric is below evals/thresholds.json")
    ap.add_argument("--console-data", action="store_true", help=f"write {CONSOLE_DATA.relative_to(ROOT)}")
    args = ap.parse_args(argv)

    report = evaluate(args.k)
    if args.console_data:
        CONSOLE_DATA.parent.mkdir(parents=True, exist_ok=True)
        CONSOLE_DATA.write_text(json.dumps(console_data(report), indent=2) + "\n")
        print(f"wrote {CONSOLE_DATA.relative_to(ROOT)}", file=sys.stderr)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(markdown(report))
    if args.check:
        problems = check(report, json.loads(THRESHOLDS.read_text()))
        if problems:
            print("\nFAILED:", *problems, sep="\n  ", file=sys.stderr)
            return 1
        print("\nAll gated metrics meet evals/thresholds.json.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
