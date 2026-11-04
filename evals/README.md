# Answer-quality evaluation

`python scripts/rag_eval.py --check` runs the gateway's real ingestion, access control and retrieval over the
console's own sample library (Cypress Harbor Credit Union, a fictional credit union: 59 documents in six
collections, 3 of them restricted) and fails if a metric drops below `thresholds.json` on any of the three
question sets, or if any question leaks a restricted passage. CI runs it on every push, and the console's
Answer quality screen shows the committed results (`demo/data/rag_eval.json`).

## The question sets

Three files, one JSON object per line:

- `golden/questions.jsonl`: the **gated set**, 59 questions (50 answerable, 9 to decline), the first set.
- `golden/questions_dev.jsonl`: 237 more questions (until this change `golden/questions_heldout.jsonl`). With the
  gated set they form the **development set**, 296 questions (235 answerable, 61 to decline). The answerer's
  citation and decline rules (below) were designed by reading these questions' failures one by one, so the
  development set flatters the answerer.
- `heldout/questions.jsonl`: the **held-out set**, 183 questions (124 answerable, 59 to decline), written by
  `scripts/heldout_questions.py` (seed 20261104) **before** the answerer changed, with newly written questions
  about facts the development set mostly does not ask about and conversational framings chosen by the seed
  ("Quick question: ...", "... I couldn't find it on the intranet."). Its results were recorded on the
  unchanged code first; it was not used to design or tune the change. CI runs the generator's `--check`.

Each question has:

- `persona`: who asks, as defined in `demo/engine.py` (Priya in HR, Dana in IT and digital banking, Marcus in
  Compliance and BSA, Audrey in internal audit, and the lobby kiosk). Their groups and roles decide what they can
  read, exactly as in the console.
- `doc` and `answer_contains`: the document that answers the question and a phrase the answer must contain.
- `doc: null`: a question the assistant should decline.
- `category`: `paraphrase` for answerable questions; for declines, `restricted_probe` (the answer is in the
  restricted document named by `probe`, and the asker is not cleared for it), `kiosk_internal` (a staff-only
  procedure asked at the lobby kiosk), `not_in_library`, `out_of_scope` or `ambiguous` ("What's the limit?").

The development set holds at least 3 questions for every document (each restricted document 5 times, by the
one persona cleared for it) and 61 to decline: 21 restricted probes (every restricted document asked by each of
the four personas who must not see it), 10 kiosk questions about staff procedures, 13 questions nothing in the
library answers, 9 off-topic and 8 ambiguous ones. The held-out set asks about every document at least once
(124 answerable) and has 59 to decline: 15 restricted probes (again every restricted document by every persona
not cleared for it), 11 kiosk questions, 15 not in the library, 9 off-topic and 9 ambiguous.
`tests/test_retrieval.py::test_golden_set_is_well_formed_and_covers_the_library` and
`::test_held_out_set_is_generated_separately_and_covers_every_document` check these properties: the answer
phrase is in the document, the asker may read it, the question is not copied from the document, no held-out
question repeats a development question, and each restricted document is probed by every persona not cleared
for it.

The library and the questions share one author, so treat the numbers as a regression baseline for this pipeline,
not a quality claim about a deployment.

## What changed in the answerer

The demo's extractive answerer (`demo/engine.py::extractive_answer`; no LLM) used to quote the best-scoring
sentences from any retrieved passage and declined only when the best passage's embedding similarity was below a
fixed floor. On the development set, 48 of its 71 hybrid citation misses cited the right document plus a second
one, and most questions it should decline were answered from an open document that shared a word or two with the
question. It now:

1. **Declines when no retrieved document covers the question.** A document qualifies only if its passages and
   title contain at least 2 of the question's content words and more than a third of them (content words: the
   question's terms without common English function words such as "my", "here" or "get", and without
   question-form words such as "how long"). A one-word question qualifies only the one document whose title has
   the word, or else the only document that contains it. If nothing qualifies, the answer is "I don't know".
2. **Answers from one document.** The qualifying document that covers the most content words answers (ties: the
   best sentence), and only its passages are quoted and cited, so a second document is never added just because
   it was retrieved.

The relevance floor still applies first. Both rules use only the passages in the prompt, which the gateway has
already filtered by the asker's access, so no restricted content is read, scored or counted. The thresholds (2
words, more than a third) were chosen on the development set by the sum of decline accuracy and answer-contains,
subject to the gated set's existing minimums; nothing in the rule names a document, a question or a phrase.

## Results

`python scripts/rag_eval.py` (about 95 s on the build host; `--json` for per-question failures). Before: the
answerer as it was, on all three sets (the held-out set measured before the change was written). After: the
answerer above. Retrieval did not change, so recall and MRR are identical before and after.

### Before the change

Gated set:

| Configuration | recall@1 | recall@4 | MRR | citation accuracy | answer contains | decline accuracy | false declines | ACL leaks |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `vector+none` | 0.800 | 0.960 | 0.872 | 0.860 | 0.840 | 0.222 | 0.020 | 0 |
| `bm25+none` | 1.000 | 1.000 | 1.000 | 0.900 | 0.860 | 0.111 | 0.000 | 0 |
| `hybrid+none` | 0.880 | 1.000 | 0.940 | 0.920 | 0.840 | 0.222 | 0.020 | 0 |
| `hybrid+lexical` | 0.960 | 1.000 | 0.975 | 0.880 | 0.860 | 0.222 | 0.020 | 0 |

Development set:

| Configuration | recall@1 | recall@4 | MRR | citation accuracy | answer contains | decline accuracy | false declines | ACL leaks |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `vector+none` | 0.774 | 0.949 | 0.853 | 0.698 | 0.808 | 0.246 | 0.013 | 0 |
| `bm25+none` | 0.906 | 0.979 | 0.938 | 0.702 | 0.808 | 0.131 | 0.000 | 0 |
| `hybrid+none` | 0.838 | 0.983 | 0.903 | 0.698 | 0.808 | 0.246 | 0.009 | 0 |
| `hybrid+lexical` | 0.877 | 0.970 | 0.916 | 0.689 | 0.804 | 0.295 | 0.013 | 0 |

| Configuration | ambiguous | kiosk internal | not in library | out of scope | restricted probe |
|---|---:|---:|---:|---:|---:|
| `vector+none` | 3/8 | 5/10 | 2/13 | 1/9 | 4/21 |
| `bm25+none` | 2/8 | 4/10 | 0/13 | 1/9 | 1/21 |
| `hybrid+none` | 2/8 | 5/10 | 3/13 | 1/9 | 4/21 |
| `hybrid+lexical` | 2/8 | 5/10 | 3/13 | 1/9 | 7/21 |

Held-out set:

| Configuration | recall@1 | recall@4 | MRR | citation accuracy | answer contains | decline accuracy | false declines | ACL leaks |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `vector+none` | 0.581 | 0.823 | 0.677 | 0.565 | 0.597 | 0.271 | 0.024 | 0 |
| `bm25+none` | 0.774 | 0.935 | 0.845 | 0.556 | 0.669 | 0.186 | 0.000 | 0 |
| `hybrid+none` | 0.726 | 0.911 | 0.802 | 0.524 | 0.621 | 0.254 | 0.040 | 0 |
| `hybrid+lexical` | 0.734 | 0.895 | 0.804 | 0.556 | 0.621 | 0.271 | 0.048 | 0 |

| Configuration | ambiguous | kiosk internal | not in library | out of scope | restricted probe |
|---|---:|---:|---:|---:|---:|
| `vector+none` | 3/9 | 7/11 | 1/15 | 5/9 | 0/15 |
| `bm25+none` | 2/9 | 5/11 | 1/15 | 3/9 | 0/15 |
| `hybrid+none` | 3/9 | 7/11 | 1/15 | 4/9 | 0/15 |
| `hybrid+lexical` | 3/9 | 7/11 | 1/15 | 4/9 | 1/15 |


### After the change

Gated set (59 questions):

| Configuration | recall@1 | recall@4 | MRR | citation accuracy | answer contains | decline accuracy | false declines | ACL leaks |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `vector+none` | 0.800 | 0.960 | 0.872 | 0.940 | 0.880 | 0.444 | 0.040 | 0 |
| `bm25+none` | 1.000 | 1.000 | 1.000 | 0.920 | 0.860 | 0.333 | 0.040 | 0 |
| `hybrid+none` | 0.880 | 1.000 | 0.940 | 0.940 | 0.880 | 0.333 | 0.040 | 0 |
| `hybrid+lexical` | 0.960 | 1.000 | 0.975 | 0.920 | 0.860 | 0.333 | 0.040 | 0 |

ACL leak checks per configuration: 295 retrievals (every question as every persona, top 12), 28 of them a restricted document's question asked by a persona not cleared for it.

Development set (296 questions):

| Configuration | recall@1 | recall@4 | MRR | citation accuracy | answer contains | decline accuracy | false declines | ACL leaks |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `vector+none` | 0.774 | 0.949 | 0.853 | 0.834 | 0.783 | 0.689 | 0.077 | 0 |
| `bm25+none` | 0.906 | 0.979 | 0.938 | 0.834 | 0.774 | 0.607 | 0.068 | 0 |
| `hybrid+none` | 0.838 | 0.983 | 0.903 | 0.838 | 0.791 | 0.656 | 0.068 | 0 |
| `hybrid+lexical` | 0.877 | 0.970 | 0.916 | 0.813 | 0.753 | 0.672 | 0.072 | 0 |

ACL leak checks per configuration: 1480 retrievals (every question as every persona, top 12), 144 of them a restricted document's question asked by a persona not cleared for it.

Decline questions declined correctly, development set, by category:

| Configuration | ambiguous | kiosk internal | not in library | out of scope | restricted probe |
|---|---:|---:|---:|---:|---:|
| `vector+none` | 7/8 | 10/10 | 8/13 | 5/9 | 12/21 |
| `bm25+none` | 7/8 | 9/10 | 8/13 | 5/9 | 8/21 |
| `hybrid+none` | 7/8 | 10/10 | 9/13 | 5/9 | 9/21 |
| `hybrid+lexical` | 7/8 | 10/10 | 9/13 | 5/9 | 10/21 |

Held-out set (183 questions):

| Configuration | recall@1 | recall@4 | MRR | citation accuracy | answer contains | decline accuracy | false declines | ACL leaks |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `vector+none` | 0.581 | 0.823 | 0.677 | 0.565 | 0.484 | 0.695 | 0.331 | 0 |
| `bm25+none` | 0.774 | 0.935 | 0.845 | 0.581 | 0.492 | 0.678 | 0.282 | 0 |
| `hybrid+none` | 0.726 | 0.911 | 0.802 | 0.565 | 0.484 | 0.695 | 0.290 | 0 |
| `hybrid+lexical` | 0.734 | 0.895 | 0.804 | 0.565 | 0.476 | 0.678 | 0.290 | 0 |

ACL leak checks per configuration: 915 retrievals (every question as every persona, top 12), 84 of them a restricted document's question asked by a persona not cleared for it.

Decline questions declined correctly, held-out set, by category:

| Configuration | ambiguous | kiosk internal | not in library | out of scope | restricted probe |
|---|---:|---:|---:|---:|---:|
| `vector+none` | 8/9 | 9/11 | 6/15 | 9/9 | 9/15 |
| `bm25+none` | 8/9 | 9/11 | 6/15 | 9/9 | 8/15 |
| `hybrid+none` | 8/9 | 9/11 | 6/15 | 9/9 | 9/15 |
| `hybrid+lexical` | 8/9 | 9/11 | 6/15 | 9/9 | 8/15 |


### Reading the numbers

Hybrid retrieval (`hybrid+none`), before and after:

| Set | citation accuracy | answer contains | decline accuracy | false declines |
|---|---:|---:|---:|---:|
| Gated (59) | 0.920 → 0.940 | 0.840 → 0.880 | 0.222 → 0.333 | 0.020 → 0.040 |
| Development (296) | 0.698 → 0.838 | 0.808 → 0.791 | 0.246 → 0.656 | 0.009 → 0.068 |
| Held-out (183) | 0.524 → 0.565 | 0.621 → 0.484 | 0.254 → 0.695 | 0.040 → 0.290 |

- **Declines generalize.** Decline accuracy rises about as much on the held-out set (0.254 to 0.695) as on the
  development set (0.246 to 0.656). Restricted probes declined: 4 of 21 to 9 of 21 (development), 0 of 15 to 9
  of 15 (held out). Off-topic questions: 9 of 9 held out.
- **Citations generalize only partly.** Citation accuracy rises 14 points on the development set and 4 on the
  held-out set. No answer cites two documents any more; the remaining misses are false declines (16 of 38 on the
  development set, 36 of 54 held out) and answers from a neighbouring document (22 and 18).
- **The cost is false declines, and the held-out set shows it is larger than the development set suggests.**
  Answerable questions answered "I don't know" rise from 0.009 to 0.068 on the development set but from 0.040 to
  0.290 on the held-out set, and answer-contains falls from 0.621 to 0.484 there. That gap is the honest
  estimate of overfitting: the coverage rule was calibrated on questions whose wording the author had read. The
  held-out questions use different words from the documents more often (recall@4 0.911 against 0.983 on the
  development set, before any answer is written), and the seeded framings add words no document contains, so
  fewer documents reach the coverage bar. Of the 124 held-out answerable questions, 36 are declined (hybrid): 10
  of the 41 with no framing, 7 of 19 framed with "Can you check something for me?" and 10 of 21 ending "I
  couldn't find it on the intranet." (2 of 18 starting "Quick question:").
- **Leaks stay at 0** in every configuration and every set: 2,395 retrievals checked per configuration (479
  questions, each as every persona).

The trade-off is deliberate and stays visible: a staff assistant that says "I don't know" when the library does
not cover a question is safer than one that quotes an unrelated policy, but on unfamiliar phrasings this
answerer now declines about 3 in 10 answerable questions. A real embedding model and LLM would reduce both
kinds of error; measure them against a deployment before relying on these numbers.

## ACL leak check

Every question is also asked as every persona, and each retrieval (top 12 passages) is checked against what that
persona may read according to the catalog's collection and document access lists. The eval decides readability
itself (`rag_eval.readable`), independently of `gateway/identity.py`, so a regression in the gateway's access code
shows up as a leak. Any passage from a document the persona may not read counts; the gate is 0. The report counts
the checks (`acl_leak_checks`, questions x personas) and, among them, the restricted probes
(`restricted_probes`: a question about a restricted document, retrieved as a persona not cleared for it).

## Thresholds

`thresholds.json` gates all three sets: `configs` (the gated set), `development` and `heldout`. Each minimum is
one point below the value measured after the change, rounded down. A gated-set minimum is raised only where the
change raised the measured value (citation accuracy, answer-contains and decline accuracy); the others keep the
values set when the gated set was introduced. CI fails only on a regression below these minimums; known failures
stay in the sets. Raise a threshold when retrieval or answering improves; never lower one to make a change pass.
`max_acl_leaks` stays 0 and covers every question. False declines are reported, not gated; a rise in them shows
up as a drop in answer-contains.

## What is measured

The embedder is the browser demo's hashed bag-of-words vector (deterministic, offline), not a neural embedding
model, and answers come from the demo's extractive answerer (no LLM) with the console's relevance floor and the
coverage check above. Results with a real embedding model and LLM will differ; run the same questions against a
deployment to measure them.

The previous golden set (12 generic policy documents and 43 questions written for an unrelated fictional
company) is kept in git history only; its numbers are no longer published.
