# Corey Mathie, 2026
"""Hybrid retrieval (BM25 + vectors fused with RRF), rerankers, retrieval settings, and the RAG eval gate."""

import json

import pytest

from gateway import rag, retrieval
from gateway.config import settings
from scripts import rag_eval

from .conftest import ADMIN, new_key


def test_bm25_prefers_rare_terms_and_scores_no_overlap_as_zero():
    docs = [retrieval.tokenize(t) for t in ("the policy covers travel", "travel policy for VPN tokens", "lunch menu")]
    scores = retrieval.bm25_scores(retrieval.tokenize("VPN policy"), docs)
    assert scores[1] > scores[0] > 0 and scores[2] == 0.0
    assert retrieval.bm25_scores([], docs) == [0.0, 0.0, 0.0]
    assert retrieval.tokenize("The receipts, Receipts!") == ["receipt", "receipt"]


def test_rrf_matches_the_formula_and_rewards_agreement():
    fused = retrieval.rrf([[0, 1, 2], [1, 0]], k=60)
    assert fused[0] == pytest.approx(1 / 61 + 1 / 62)
    assert fused[1] == pytest.approx(1 / 62 + 1 / 61)
    assert fused[2] == pytest.approx(1 / 63)


def test_rank_modes_and_score_details():
    texts = ["hotel cap is $180 per night", "laptops lock after 5 minutes", "meals are $75 per day"]
    vec = [0.1, 0.9, 0.2]  # a vector ranking that disagrees with the words
    assert [i for i, _ in retrieval.rank("hotel cap per night", texts, vec, mode="vector", top_k=3)] == [1, 2, 0]
    bm = retrieval.rank("hotel cap per night", texts, None, mode="bm25", top_k=1)
    assert bm[0][0] == 0 and set(bm[0][1]) == {"bm25", "final"}
    hy = retrieval.rank("hotel cap per night", texts, vec, mode="hybrid", top_k=3)
    assert set(hy[0][1]) == {"vector", "bm25", "rrf", "final"}
    with pytest.raises(ValueError, match="unknown retrieval mode"):
        retrieval.rank("x", texts, vec, mode="magic")


def test_lexical_reranker_prefers_passages_covering_all_query_terms():
    rr = retrieval.LexicalReranker()
    passages = ["receipts receipts receipts receipts", "itemized receipts are required over $25 for lunch"]
    scores = rr.rerank("receipt for a lunch over $25", passages)
    assert scores[1] > scores[0]
    ranked = retrieval.rank("receipt for lunch", passages, [0.9, 0.1], mode="hybrid", top_k=2, reranker=rr)
    assert ranked[0][0] == 1 and "rerank" in ranked[0][1]


def test_cross_encoder_is_an_explicit_opt_in_with_clear_errors(monkeypatch):
    assert retrieval.get_reranker("none") is None
    with pytest.raises(ValueError, match="GATEWAY_CROSS_ENCODER_MODEL"):
        retrieval.CrossEncoderReranker("")
    monkeypatch.setitem(__import__("sys").modules, "sentence_transformers", None)  # simulate "not installed"
    with pytest.raises(RuntimeError, match="sentence-transformers"):
        retrieval.CrossEncoderReranker("/models/some-cross-encoder")
    with pytest.raises(ValueError, match="unknown reranker"):
        retrieval.get_reranker("llm-judge")


@pytest.mark.parametrize("mode", ["vector", "bm25", "hybrid"])
def test_ask_uses_the_configured_mode_and_reports_it(client, monkeypatch, mode):
    monkeypatch.setattr(settings, "GATEWAY_RETRIEVAL_MODE", mode)
    for title, text in (
        ("travel.md", "Hotel stays are capped at $180 per night."),
        ("it.md", "Laptops lock after 5 minutes."),
    ):
        client.post("/v1/collections/p/documents/text", json={"title": title, "text": text}, headers=ADMIN)
    embedded = []
    real = rag.embed

    async def spy(texts, model=None):
        embedded.extend(texts)
        return await real(texts, model)

    monkeypatch.setattr(rag, "embed", spy)
    r = client.post(
        "/v1/collections/p/ask",
        json={"question": "hotel cap per night?"},
        headers={"Authorization": f"Bearer {new_key(client)}"},
    )
    body = r.json()
    assert r.status_code == 200 and body["retrieval"] == {"mode": mode, "reranker": "none"}
    assert body["sources"][0]["title"] == "travel.md"
    assert embedded == ([] if mode == "bm25" else ["hotel cap per night?"])  # bm25 never embeds the question
    from gateway import audit

    entry = next(e for e in audit.recent(50) if e["event"] == "document_question")
    assert entry["payload"]["retrieval"]["mode"] == mode


@pytest.fixture(scope="module")
def eval_report():
    return rag_eval.evaluate()  # gated, development and held-out sets, about 95 s: shared by the tests below


def test_rag_eval_meets_thresholds_and_has_no_acl_leaks(eval_report):
    report = eval_report
    assert report["questions"] >= 40 and report["restricted_documents"] == 3 and report["declines"] >= 5
    thresholds = json.loads(rag_eval.THRESHOLDS.read_text())
    assert set(thresholds) >= {"configs", "development", "heldout"}  # every set is quality-gated
    assert rag_eval.check(report, thresholds) == []
    assert all(r["acl_leaks"] == 0 for r in report["results"].values())
    dev, held = report["development"], report["heldout"]
    assert dev["questions"] >= 200 and held["questions"] >= 150
    for section in (dev, held):  # the leak gate applies to every question in every set
        for r in section["results"].values():
            assert r["acl_leaks"] == 0 and r["acl_leak_checks"] == section["questions"] * len(report["personas"])
            assert r["restricted_probes"] >= 80
    assert settings.GATEWAY_RETRIEVAL_MODE == "hybrid"  # settings restored after the run


def test_leak_gate_covers_the_development_and_held_out_questions():
    clean = {"hybrid+none": {"recall@1": 1.0, "acl_leaks": 0}}
    report = {
        "results": clean,
        "development": {"results": {"hybrid+none": {"recall@1": 0.9, "acl_leaks": 0}}},
        "heldout": {"results": {"hybrid+none": {"recall@1": 0.1, "acl_leaks": 1}}},
    }
    thresholds = {"max_acl_leaks": 0, "configs": {"hybrid+none": {"recall@1": 0.9}}}
    assert rag_eval.check(report, thresholds) == ["hybrid+none: 1 restricted passages leaked"]
    thresholds["heldout"] = {"configs": {"hybrid+none": {"recall@1": 0.2}}}
    assert rag_eval.check(report, thresholds) == [
        "heldout hybrid+none: recall@1 0.1 < 0.2",
        "hybrid+none: 1 restricted passages leaked",
    ]


def test_rag_eval_gate_fails_on_regressions_and_leaks():
    report = {"results": {"hybrid+none": {"recall@1": 0.5, "acl_leaks": 2}}}
    problems = rag_eval.check(
        report, {"max_acl_leaks": 0, "configs": {"hybrid+none": {"recall@1": 0.9}, "bm25+none": {}}}
    )
    assert problems == [
        "hybrid+none: recall@1 0.5 < 0.9",
        "bm25+none: not evaluated",
        "hybrid+none: 2 restricted passages leaked",
    ]


DECLINE_CATEGORIES = {"restricted_probe", "kiosk_internal", "not_in_library", "out_of_scope", "ambiguous"}


def test_golden_set_is_well_formed_and_covers_the_library():
    from demo.engine import PERSONAS, persona_principal

    catalog, texts, questions = rag_eval.load_golden(full=True)
    assert len({q["id"] for q in questions}) == len(questions)  # ids unique across the three files
    assert len({(q["persona"], q["question"]) for q in questions}) == len(questions)
    restricted = {d["file"] for d in catalog["documents"] if d["acl"]}
    collection = {d["file"]: d["collection"] for d in catalog["documents"]}
    for q in questions:
        assert q["persona"] in PERSONAS, q["id"]
        readable = rag_eval.readable(catalog, persona_principal(q["persona"]))
        if q["doc"]:
            assert q["answer_contains"].lower() in texts[q["doc"]].lower(), q["id"]  # the answer is really in the doc
            assert q["doc"] in readable, q["id"]  # an answerable question is asked by someone cleared for it
            assert q["question"] not in texts[q["doc"]], q["id"]  # paraphrased, not copied
            assert q["category"] == "paraphrase", q["id"]
        else:
            assert q["category"] in DECLINE_CATEGORIES, q["id"]
            if q["category"] == "restricted_probe":  # asked by someone who must not see the document
                assert q["probe"] in restricted and q["probe"] not in readable, q["id"]
            if q["category"] == "kiosk_internal":
                assert q["persona"] == "kiosk", q["id"]
    answered = {q["doc"] for q in questions if q["doc"]}
    assert {collection[d] for d in answered} == {c["name"] for c in catalog["collections"]}  # every collection
    assert restricted <= answered  # each restricted document, asked by someone with access
    declines = [q for q in questions if not q["doc"]]
    assert {q["persona"] for q in declines} >= {"kiosk", "priya", "dana", "audrey"}
    per_doc = {d["file"]: sum(q["doc"] == d["file"] for q in questions) for d in catalog["documents"]}
    assert min(per_doc.values()) >= 3, per_doc  # every document, at least three ways of asking
    assert {q["category"] for q in declines} == DECLINE_CATEGORIES
    for doc in restricted:  # each restricted document probed by every persona not cleared for it
        probers = {q["persona"] for q in declines if q.get("probe") == doc}
        blocked = {p for p in PERSONAS if p != "admin" and doc not in rag_eval.readable(catalog, persona_principal(p))}
        assert probers == blocked, (doc, probers, blocked)


def test_held_out_set_is_generated_separately_and_covers_every_document():
    """evals/heldout/questions.jsonl: its own generator (--check in CI), new questions, every document and category."""
    from demo.engine import PERSONAS, persona_principal
    from scripts import heldout_questions

    assert rag_eval.HELDOUT.read_text() == heldout_questions.render(heldout_questions.build())  # up to date
    catalog, _texts, questions = rag_eval.load_golden(full=True)
    held = [q for q in questions if q["set"] == "heldout"]
    dev_questions = {q["question"] for q in questions if q["set"] != "heldout"}
    assert len(held) >= 150 and not {q["question"] for q in held} & dev_questions  # nothing reused
    assert {q["doc"] for q in held if q["doc"]} == {d["file"] for d in catalog["documents"]}
    assert {q["category"] for q in held if not q["doc"]} == DECLINE_CATEGORIES
    restricted = {d["file"] for d in catalog["documents"] if d["acl"]}
    for doc in restricted:  # every persona not cleared for a restricted document probes it in this set too
        probers = {q["persona"] for q in held if q.get("probe") == doc}
        blocked = {p for p in PERSONAS if p != "admin" and doc not in rag_eval.readable(catalog, persona_principal(p))}
        assert probers == blocked, (doc, probers, blocked)


def test_eval_access_oracle_agrees_with_the_personas():
    from demo.engine import persona_principal

    catalog, _texts, _questions = rag_eval.load_golden()
    kiosk = rag_eval.readable(catalog, persona_principal("kiosk"))
    assert kiosk == {d["file"] for d in catalog["documents"] if d["collection"] == "member-info"}
    audrey = rag_eval.readable(catalog, persona_principal("audrey"))
    assert audrey == {d["file"] for d in catalog["documents"] if not d["acl"]}


def test_published_eval_numbers_match_a_fresh_run(eval_report):
    """The README, docs/benchmarks.md, evals/README.md and ADR 0006 quote the eval tables; they must match a fresh run
    exactly (the gated table everywhere; the development and held-out tables wherever those sets are published)."""
    k = eval_report["k"]
    gated = rag_eval.metrics_table(eval_report["results"], k)
    dev, held = eval_report["development"]["results"], eval_report["heldout"]["results"]
    tables = [rag_eval.metrics_table(dev, k), rag_eval.metrics_table(held, k), rag_eval.leak_line(dev)]
    tables += [rag_eval.leak_line(held), rag_eval.leak_line(eval_report["results"])]
    root = rag_eval.ROOT
    adr = "docs/adr/0006-hybrid-retrieval-and-rag-evals.md"
    for doc in ("docs/benchmarks.md", adr, "README.md", "evals/README.md"):
        assert gated in (root / doc).read_text(), doc
    for doc in ("docs/benchmarks.md", "README.md", "evals/README.md"):
        for table in tables:
            assert table in (root / doc).read_text(), (doc, table)
    for section in (dev, held):
        assert rag_eval.declines_table(section) in (root / "evals/README.md").read_text()
