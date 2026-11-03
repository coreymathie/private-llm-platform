# Console

The console is the platform's user-facing surface: an employee assistant in front, with administration and
governance behind it. One set of static files serves two purposes. As a public demo it runs the gateway's own
Python modules in the browser against simulated services. As the operator console it is served by the gateway
at `/console/` and calls the real HTTP API. This document covers the two modes, the fictional business the demo
is set in, each screen, and how to run and publish the console.

## Two modes, one codebase

The console is one set of static files in [`demo/`](../demo/): `index.html`, `app.js`, `assistant.js`,
`screens.js`, `adapters.js`, `ui.js` and `styles.css`, with the shared navigation shell in `shell.js`. An
adapter selects the data source; the screens do not know which one is active.

| Mode | Adapter | Behaviour | Header label |
|---|---|---|---|
| **Demo** (GitHub Pages) | `DemoAdapter` | Loads Pyodide 0.26.4 and runs the gateway's own modules through `demo/engine.py`, with a simulated backend (hashed bag-of-words embeddings, extractive answers, a stand-in Ollama model inventory) | *Demo* |
| **Live** | `LiveAdapter` | The gateway serves the same files at `/console/`; the adapter calls its HTTP API with the admin key or token entered on Settings, held in memory, or in `sessionStorage` on request | *Live · connected to &lt;host&gt;* |

The mode comes from `GET ./api-mode` (a static file answers `demo`; the gateway answers `live`) or from
`?mode=demo|live`.

In demo mode the following gateway modules run in the browser through Pyodide: keys and rate limiting, roles
and permission-aware retrieval, citations, the audit hash chain, policy validation, model pinning, and the RAG
eval. Nothing leaves the page. There is no LLM in the browser; answers are extractive and labelled as
**simulated**.

**Start-up.** In demo mode the Ask and Usage and impact screens render at once, while Pyodide loads. The assistant
lists its start-up steps with their progress (loading the Python runtime, the gateway's code and the sample
library, then indexing the documents and access lists) and notes that the first load downloads the Python
runtime and its packages (about 34 MB before compression; `scripts/demo_smoke.py` measures the files Pyodide
requests). Until the engine is ready, names come from a static copy of the personas, suggested questions are
replaced by a neutral placeholder, and the composer is disabled with "Getting ready…". Other screens show the
same steps until they can render.

**Figures and page translation.** Numbers and money are formatted en-US ("$1,100", "$93K", "$1.4B", two decimals below $10)
whatever the browser locale. Elements that hold figures (KPI tiles, tables of numbers, charts, meters, numbers
inside sentences) carry `translate="no"` so browser page translation leaves them as written; labels and prose
remain translatable.

## Sample business: Cypress Harbor Credit Union

The console is set in a sample business so that the platform can be assessed the way an institution would use
it. **Cypress Harbor Credit Union** is *fictional*: 340 employees in 11 departments, 11 branches in South
Florida, and one on-prem GPU server. The console opens on **Harbor Assistant**, the employee-facing chat, following the pattern
of an internal Copilot-style assistant; administration and governance sit behind it in the sidebar.

- **Library**: 59 documents in six collections (staff policies, member information, member services, lending,
  compliance, branch operations), each with an owner, department, version and review date (all within 12 months
  of the usage period). 46 come from [`scripts/sample_library.py`](../scripts/sample_library.py), which is also
  the single source for the department list, document owners and access rules (checked in CI). Member
  information (fees, hours, rates, how to join) is written for members and is readable by `group:public` and
  `group:staff`; every other collection is `group:staff` only. HR compensation (`group:hr`), the payments
  on-call runbook (`group:engineering`) and the BSA/AML escalation procedure (`group:compliance`) are restricted
  by document access list; front-line staff refer unusual activity under an all-staff referral policy.
- **People**: Priya Shah (Human resources), Dana Ortiz (IT and digital banking), Marcus Bell (Compliance and
  BSA, the BSA officer), Audrey Kim (Internal audit: `reader:*`, read-only across every collection, restricted
  documents still hidden, no free-form chat) and the branch lobby kiosk (an API key in `group:public`, so it
  reads Member information only). Suggested questions per person come from `demo/engine.py` and each is tested
  to cite the document it demonstrates; Audrey's salary-band suggestion is labelled as a refusal. The demo also
  creates two API keys: `member-faq-portal` (`group:public`) and `staff-intranet-search` (`group:staff`). API
  keys and the bootstrap admin appear in the technical view.
- **Usage**: 90 days from [`scripts/generate_sample_company.py`](../scripts/generate_sample_company.py),
  labelled **sample** everywhere, apart from **measured** results (Answer quality, Benchmarks) and the
  **simulated** requests made in the tab.

## How the sample numbers were set

The Usage and impact figures are generated **sample** data. Each headline figure, the assumption behind it and its
published source (once one is checked) live in one table in
[`scripts/generate_sample_company.py`](../scripts/generate_sample_company.py) (`headline_figures`, written to
`demo/data/sample_company.json`); the console's *How these sample numbers were set* panel and the table below
render from it, and a test keeps them identical. A figure is marked cited only with a source that was fetched
and read, with its title, publisher, year, URL and the quoted sentence; a test fails if a cited figure has no URL.
No figure is cited yet: the published benchmarks named in the second column (NCUA call-report staffing ratios,
surveys of generative AI use and time savings, the BLS Employer Costs for Employee Compensation, GPU list prices,
help-desk resolution rates) have not been checked against these values, so each figure is an assumption.

| Figure | Sample value (last 30 days) | How it was set | Source |
|---|---|---|---|
| Staffing ratios | 340 employees for 92,400 members and $1.4B in assets: 272 members and $4.1M in assets per employee | Set for a mid-size credit union; to be checked against NCUA call-report ratios (members and assets per full-time-equivalent employee). | Assumption (no public benchmark cited) |
| Employees using it | 293 of 340 employees (86%) asked at least one question in 30 days; 217 on an average workday | Department adoption shares in STAFFING for a sanctioned internal assistant open to every employee; to be checked against published rates of generative AI use among employees. | Assumption (no public benchmark cited) |
| Questions per active employee | 3.0 per workday (14,430 in 30 days) | Per-department questions per active user per workday (1.2 to 4.5 in STAFFING). | Assumption (no public benchmark cited) |
| Hours saved | 6 minutes per cited answer: 1,337 hours in 30 days, 1.1 hours per active employee per week (2.7% of a 40-hour week) | Minutes saved versus searching shared drives or asking a colleague; to be checked against published figures for time spent searching for information and self-reported time savings from generative AI. | Assumption (no public benchmark cited) |
| Loaded hourly cost | $52 per hour | Wages plus benefits per hour worked; to be checked against the BLS Employer Costs for Employee Compensation for financial activities. | Assumption (no public benchmark cited) |
| Infrastructure cost | $4,200 per month: $0.31 per answer | One on-prem server with 2 x NVIDIA L40S, with power and support; to be checked against hardware and cloud GPU list prices. | Assumption (no public benchmark cited) |
| Answered from documents | 92.6% of questions answered with citations | The share that finds nothing to cite falls from about 11% to about 7% over 90 days as the library fills its gaps; to be checked against published help-desk and policy-question resolution rates. | Assumption (no public benchmark cited) |
| Answers rated helpful | 91.5% of 2,757 ratings; 21% of answers rated | Rating rate and helpful share chosen for illustration. | Assumption (no public benchmark cited) |
| Response time | median 1.6 s, slowest-day 95th percentile 4.5 s | Chosen for illustration; the gateway's own overhead is measured separately (docs/benchmarks.md). | Assumption (no public benchmark cited) |
| Restricted content withheld | 2.2% of questions | Share of questions that touch a document the asker is not cleared for (1.8% to 3% a day). | Assumption (no public benchmark cited) |

## Business and technical views

The header switch (or `?view=technical`) selects the audience. The business view shows what employees and
administrators see: plain-language access ("Restricted to the hr group"), document titles, and readable
audit-event names. The technical view adds retrieval scores and modes, API keys and token limits, raw
access-list entries, model digests, the lock file and ML-BOM, and the modules running in the tab. Light and
dark themes follow the system and can be switched in the header.

## Asking across every readable collection

*All sources I can read* (the default) searches every collection the person may read. The access decision
runs per collection before any passage is scored; passages are then ranked together. An answer quotes only
sentences from its best-matching document. A question that nothing in the library answers well receives
"I couldn't find that in the documents you can access" instead of an unrelated quote. This is a relevance
floor on vector similarity; the eval applies the same rule and reports how often it declines when it should.

## Navigation

Screens are grouped as Assistant, Admin and Governance, with breadcrumbs, a command palette
(<kbd>Ctrl</kbd>/<kbd>⌘</kbd> <kbd>K</kbd> or <kbd>/</kbd>), `g` + letter shortcuts (<kbd>?</kbd> lists them)
and a collapsible sidebar. A five-step guided tour is offered on the first visit.

![Usage and impact: questions answered, answered from documents, employees using it, hours saved, restricted content withheld, cost per answer, and adoption by department for the sample credit union](img/console-business.png)

## Screens

| Screen | Function |
|---|---|
| Ask | Chat with streamed answers, numbered citations and source cards; a citation opens the document with the quoted passage highlighted, its owner, version, review date and who may read it. Conversation history, suggested questions per person, copy / ask again / helpful / not helpful, ask as someone else or compare two people side by side, search one collection or all. Technical view: retrieval mode, reranker, passage count, model-only chat (readers get 403) and a retrieval-details table per answer (scores, access rule, injection flags, audit line) |
| Usage and impact | For the sample credit union over 7, 30 or 90 days: questions answered, share answered from documents with citations, employees using it, hours saved and cost per answer (with stated assumptions), restricted content withheld, member data sent outside (zero), answers rated helpful, each against the previous period; questions per day; adoption by department; topics; response time; knowledge-base collections and who may read them; governance checks; recent activity; how each sample number was set, with its assumption or source |
| Usage and impact › This session | Requests, identities, collections and documents, audit status and access decisions for what was done in this tab; guided "what to try" cards |
| Documents | The library with titles, owners and review dates, a filter, add or upload, per-collection and per-document access lists, and a plain-language access matrix of who can read which document |
| People and keys | People and applications with their roles and groups; API keys with usage against the rate limit, burst test and revoke (technical view); SSO group-to-role mapping |
| Audit log | The hash-chained log with readable event names, filters, search and paging; each row opens a decision timeline (sign-in, access decision, retrieval, sources, answer, hashes). "Log intact" check; demo mode adds a tamper-detection test |
| Access policy | The policy in effect, in plain language, then the runtime policy as JSON, validated with the gateway's own types and `identity.check_role`, applied and audited, with a "try a change" scenario before and after |
| Models | Backend health, served models, off/warn/enforce policy; the technical view adds digests, lock-file verification and validation, and ML-BOM model components |
| Answer quality | The `scripts/rag_eval.py` scorecard per configuration against `evals/thresholds.json`, measured on the Cypress Harbor library itself with 59 gated questions, plus the 296-question set with the held-out questions (no thresholds), asked as the five people (including questions to decline), and the questions not answered perfectly with who asked them; demo mode re-runs the gated set in the browser and compares |
| Settings | Mode, credential (live), modules running in the tab (technical view), and what is simulated |

## Running the console against the gateway

```bash
docker compose up        # then open http://localhost:8080/console/
docker compose logs gateway | grep "Bootstrap admin"     # the admin key to paste on Settings
```

That stack needs no model or GPU. The gateway talks to `mock-llm`, which is
[`scripts/mock_openai_server.py`](../scripts/mock_openai_server.py) in **simulated** mode (extractive answers,
hashed embeddings; not a language model). *Load sample data* on Usage and impact › This session adds the sample
library, each collection's access list and three keys (`hr-assistant` and `eng-assistant` in `group:staff`,
`lobby-kiosk` in `group:public`) through the API.

For real answers, Ollama remains the default backend:
`docker compose --env-file profiles/compose-ollama.env --profile ollama up -d`, then pull `llama3.1:8b` and
`nomic-embed-text` (see the top of `docker-compose.yml`). The earlier single-file admin page is still served at
`/admin`.

## Console endpoints

The console added these endpoints, all admin-only: `GET /admin/overview`, `GET /admin/audit/entries`,
`GET /admin/access-matrix?collection=`, `GET /admin/policy`, `POST /admin/policy/validate`,
`PUT /admin/policy` (in memory, audited as `policy_changed`; a restart reads the environment again),
`GET /admin/rate-limits`, `POST /admin/models/lock/validate` and `GET /admin/models/mlbom`. In addition,
`GET /console/api-mode` and per-request `retrieval_mode` / `reranker` on `/ask`.

## Verification

The browser engine runs under CPython in the test suite (`tests/test_demo_engine.py`,
`tests/test_console_engine.py`). `scripts/demo_smoke.py` drives the real console headlessly with Playwright in
both modes: every screen and its key interaction in demo mode, then the gateway and the simulated backend under
uvicorn in live mode (47 checks, no console errors, no horizontal scroll at 390 px). See
[testing.md](testing.md).

## Publishing the demo

Enable GitHub Pages for the repository (Settings → Pages → deploy from the `main` branch, root folder). The
console is then at `https://coreymathie.github.io/private-llm-platform/demo/`. `.nojekyll` makes Pages serve the
Python files as-is.
