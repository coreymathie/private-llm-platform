# Answer-quality evaluation

`python scripts/rag_eval.py --check` runs the gateway's real ingestion, access control and retrieval over the
console's own sample library (Cypress Harbor Credit Union, a fictional credit union: 59 documents in six
collections, 3 of them restricted) and fails if a gated metric drops below `thresholds.json` or any question
leaks a restricted passage. CI runs it on every push, and the console's Answer quality screen shows the committed
results (`demo/data/rag_eval.json`).

## The question sets

Two files, one JSON object per line:

- `golden/questions.jsonl`: the **gated set**, 59 questions (50 answerable, 9 to decline). `thresholds.json` was
  measured on it, and CI enforces it.
- `golden/questions_heldout.jsonl`: the **held-out set**, 237 more questions written later, after the gated set's
  results were known. They are never used to tune the documents, the retriever, the relevance floor or the
  answerer, and they carry no quality thresholds; the ACL leak gate applies to them like every other question.

Each question has:

- `persona`: who asks, as defined in `demo/engine.py` (Priya in HR, Dana in IT and digital banking, Marcus in
  Compliance and BSA, Audrey in internal audit, and the lobby kiosk). Their groups and roles decide what they can
  read, exactly as in the console.
- `doc` and `answer_contains`: the document that answers the question and a phrase the answer must contain.
- `doc: null`: a question the assistant should decline.
- `category`: `paraphrase` for answerable questions; for declines, `restricted_probe` (the answer is in the
  restricted document named by `probe`, and the asker is not cleared for it), `kiosk_internal` (a staff-only
  procedure asked at the lobby kiosk), `not_in_library`, `out_of_scope` or `ambiguous` ("What's the limit?").

Together the two files hold 296 questions: 235 answerable, with at least 3 for every one of the 59 documents
(each restricted document 5 times, by the one persona cleared for it), and 61 to decline: 21 restricted
probes (every restricted document asked by each of the four personas who must not see it), 10 kiosk questions
about staff procedures, 13 questions nothing in the library answers, 9 off-topic and 8 ambiguous ones.
`tests/test_retrieval.py::test_golden_set_is_well_formed_and_covers_the_library` checks these properties: the
answer phrase is in the document, the asker may read it, the question is not copied from the document, every
document has at least three questions, and each restricted document is probed by every persona not cleared for
it.

Questions are paraphrased the way staff and members ask ("I left my work phone on the train. Who do I call and
how soon?"), not copied from the documents. The held-out set was trimmed to at most four questions per open
document by count before its results were reviewed; no question was removed or reworded because of its result.
Neither the documents nor the answerer were changed in response to eval results; a miss stays a miss. The
library and the questions share one author, so treat the numbers as a regression baseline for this pipeline,
not a quality claim about a deployment.

## Results

`python scripts/rag_eval.py` (about 47 s on the build host; `--json` for per-question failures). Before: the
gated set alone.

| Configuration | recall@1 | recall@4 | MRR | citation accuracy | answer contains | decline accuracy | ACL leaks |
|---|---:|---:|---:|---:|---:|---:|---:|
| `vector+none` | 0.800 | 0.960 | 0.872 | 0.860 | 0.840 | 0.222 | 0 |
| `bm25+none` | 1.000 | 1.000 | 1.000 | 0.900 | 0.860 | 0.111 | 0 |
| `hybrid+none` | 0.880 | 1.000 | 0.940 | 0.920 | 0.840 | 0.222 | 0 |
| `hybrid+lexical` | 0.960 | 1.000 | 0.975 | 0.880 | 0.860 | 0.222 | 0 |

ACL leak checks per configuration: 295 retrievals (every question as every persona, top 12), 28 of them a restricted document's question asked by a persona not cleared for it.

After: the gated and held-out sets together.

| Configuration | recall@1 | recall@4 | MRR | citation accuracy | answer contains | decline accuracy | ACL leaks |
|---|---:|---:|---:|---:|---:|---:|---:|
| `vector+none` | 0.774 | 0.949 | 0.853 | 0.698 | 0.808 | 0.246 | 0 |
| `bm25+none` | 0.906 | 0.979 | 0.938 | 0.702 | 0.808 | 0.131 | 0 |
| `hybrid+none` | 0.838 | 0.983 | 0.903 | 0.698 | 0.808 | 0.246 | 0 |
| `hybrid+lexical` | 0.877 | 0.970 | 0.916 | 0.689 | 0.804 | 0.295 | 0 |

ACL leak checks per configuration: 1480 retrievals (every question as every persona, top 12), 144 of them a restricted document's question asked by a persona not cleared for it.

Decline questions declined correctly, full set, by category:

| Configuration | ambiguous | kiosk internal | not in library | out of scope | restricted probe |
|---|---:|---:|---:|---:|---:|
| `vector+none` | 3/8 | 5/10 | 2/13 | 1/9 | 4/21 |
| `bm25+none` | 2/8 | 4/10 | 0/13 | 1/9 | 1/21 |
| `hybrid+none` | 2/8 | 5/10 | 3/13 | 1/9 | 4/21 |
| `hybrid+lexical` | 2/8 | 5/10 | 3/13 | 1/9 | 7/21 |

The gated numbers are unchanged; the larger set is harder. On it, hybrid retrieval still puts the right
document in the top 4 for 0.983 of answerable questions, but citation accuracy falls to 0.698: of the 71
answerable questions not cited correctly, 48 cite the right document plus a second one (the extractive
answerer adds a sentence from another passage), 21 cite only another document, and 2 cite nothing. Decline
accuracy stays low (0.246 hybrid) for the reason below. Hybrid retrieval declines 4 of the 21 restricted probes:
the restricted document never reaches the asker (0 leaks), but an open document that shares words with the
question answers instead (for example, the OFAC Screening Procedure for a question about the BSA officer's
filing deadline, or the Benefits Overview for a salary-band question).

## ACL leak check

Every question is also asked as every persona, and each retrieval (top 12 passages) is checked against what that
persona may read according to the catalog's collection and document access lists. The eval decides readability
itself (`rag_eval.readable`), independently of `gateway/identity.py`, so a regression in the gateway's access code
shows up as a leak. Any passage from a document the persona may not read counts; the gate is 0. The report counts
the checks (`acl_leak_checks`, questions x personas) and, among them, the restricted probes
(`restricted_probes`: a question about a restricted document, retrieved as a persona not cleared for it).

## Thresholds

Each minimum in `thresholds.json` is one point below the value measured when the gated set was introduced,
rounded down, so the gate catches regressions without failing on the current state. Raise a threshold when
retrieval or answering improves; never lower one to make a change pass. `max_acl_leaks` stays 0 and covers both
files. The held-out set has no quality thresholds: gating it would mean setting new, lower minimums, which is a
decision for the maintainer rather than a side effect of growing the set.

Decline accuracy is low. The console declines only when the best passage's embedding similarity is below a fixed
floor (`RELEVANCE_FLOOR` in `demo/engine.py`), so a question that shares a few words with an unrelated document
is answered from it instead of declined. In bm25-only mode there is no embedding similarity, so the floor never
applies. Those answers never contain restricted content (the leak gate proves that); they are unhelpful, not
unsafe. A real model told to answer only from the sources declines more often; measure it against a deployment
before relying on this number.

## What is measured

The embedder is the browser demo's hashed bag-of-words vector (deterministic, offline), not a neural embedding
model, and answers come from the demo's extractive answerer (no LLM) with the console's relevance floor. Results
with a real embedding model and LLM will differ; run the same questions against a deployment to measure them.

The previous golden set (12 generic policy documents and 43 questions written for an unrelated fictional
company) is kept in git history only; its numbers are no longer published.
