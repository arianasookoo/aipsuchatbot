# Evaluation

Measured numbers for the requirements that carry numbers, re-runnable by anyone on the team.
All scripts run from the repo root with the index built (`python vector_search.py index chunks.json`).

| Requirement | Metric | Result (2026-10-14) | Target | Script |
|---|---|---|---|---|
| R4 retrieval relevance | hit@3 over 35 labeled in-scope queries | **94.3%** (33/35), MRR 0.800 | ≥ 85% | `run_eval.py` |
| R14 supported claims | sentences judged supported by their cited passages | **97.9%** (137/140) | ≥ 95% | `claims.py` |
| Unsupported questions | refusal rate on 5 out-of-scope queries | **100%** (5/5); 1 in-scope query also refused (#15) | 100% | `claims.py` |
| R11 resource metadata | records with title, category, unit, URL, retrieval date | **30/30**; contact found on 10/30 (never guessed) | 30/30 | `../enrich.py --check` |
| Response time | p50 / p95 seconds | sequential **5.3 / 35.2**; 10 concurrent users **23.0 / 29.0, 0 errors** | p95 ≤ 5 s at 10 users | `run_answers.py`, `load_test.py` |

**Response time is the one open requirement.** Retrieval takes ~0.3 s; the rest is the model endpoint. Single requests to the free NVIDIA endpoint ranged from 3 s to 37 s during testing, and it rate-limits at ~10 simultaneous long prompts, so `answer.py` caps in-flight model calls (`NAVIGATOR_LLM_CONCURRENCY`, default 4) and queues the rest: zero errors, longer waits. Meeting 5 s at 10 users needs a model the team controls: the sponsor's GB10 running a local model through the same `llm.py` with two environment variables changed. That is the planned Nov 9 work, and the load test re-runs there unchanged.

## Files

| File | What it does |
|---|---|
| `queries.jsonl` | 40 questions: 35 in-scope across the seven README categories with hand-labeled expected pages, 5 out-of-scope that should be refused. Edit and re-run; labels are the team's to review. |
| `run_eval.py` | hit@3 and MRR through `hybrid_search.retrieve`. `--min-hit3 0.85` makes it a CI gate. Writes `results.csv`. |
| `run_answers.py` | Runs every query through `answer.py`, records the answer, cited passages, refusal flag, seconds. Writes `answers.jsonl`. |
| `claims.py` | Splits each answer into sentences and asks a judge model whether each is supported by only the passages it cited. Writes `claims.csv`. |
| `load_test.py` | N concurrent users against a running `serve.py`; p50/p95/max. |

## How to read the numbers honestly

- Retrieval labels were written by one person (Advait Sadineni) against the 96 scraped pages. The two misses (#18, #26) returned pages a reader might call relevant; the labels were kept strict rather than adjusted to pass.
- Per category: recruiting 7/7, research 5/5, capstone 5/5, student orgs 4/5, events 4/5, giving 5/5, employee education 3/3. Employee education has only two pages in the corpus, which is a coverage problem for the scraper, not a ranking problem.
- The three unsupported sentences: one is a sentence-splitting artifact ("Monday through Friday)." split off its parent), one adds an approval window the page does not state, one names a calendar page not among the cited passages. The one in-scope refusal (#15, capstone submission deadline) is a retrieval miss: the deadline sentence sits in a chunk that was not in the top five.
- The claim judge is a second model checking the first. The test plan's 30-answer manual audit remains the ground truth; `claims.csv` lists every sentence so that audit is a read-through, not a rebuild.
- Latency here is this laptop plus a remote model endpoint. On the sponsor's hardware with a local model the number changes; re-run there.

## Pipeline these scripts measure

```
question -> hybrid_search.retrieve (keyword + MiniLM/Chroma, rank fusion)  <- run_eval.py measures this
         -> answer.py: 5 passages -> model -> sentences, each must cite [n]
            uncited sentences dropped; NO_VERIFIED_ANSWER -> closest-page handoff
         -> claims.py: judge model checks each sentence against its cited passages
```
