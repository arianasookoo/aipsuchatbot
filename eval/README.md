# Evaluation

Measured numbers for the requirements that carry numbers, re-runnable by anyone on the team.
All scripts run from the repo root with the index built (`python vector_search.py index chunks.json`).

| Requirement | Metric | Result (2026-10-14) | Target | Script |
|---|---|---|---|---|
| R4 retrieval relevance | hit@3 over 35 labeled in-scope queries | **94.3%** (33/35), MRR 0.800 | ≥ 85% | `run_eval.py` |
| R14 supported claims | sentences judged supported by their cited passages | **97.9%** (137/140) | ≥ 95% | `claims.py` |
| Unsupported questions | refusal rate on 5 out-of-scope queries | **100%** (5/5); 1 in-scope query also refused (#15) | 100% | `claims.py` |
| R11 resource metadata | records with title, category, unit, URL, retrieval date | **30/30**; contact found on 10/30 (never guessed) | 30/30 | `../enrich.py --check` |
| Response time | p50 / p95 seconds | sequential **5.3 / 35.2**; 10 concurrent users **23.0 / 29.0, 0 errors** (second run same day, endpoint degraded: **48.4 / 60.0, 2 client timeouts**; a bare one-word request took 26 s) | p95 ≤ 5 s at 10 users | `run_answers.py`, `load_test.py` |
| Response time, local model | p50 / p95 seconds, gemma3:12b via Ollama on an RTX 5080 laptop (16 GB) | sequential **4.1 / 5.8**; 10 concurrent users **22.9 / 32.9, 0 errors** | p95 ≤ 5 s at 10 users | same, with the three `NAVIGATOR_LLM_*` variables set |
| R14 + refusals, local model | same judge procedure, judged by qwen2.5:7b-instruct | **91.9%** supported (124/135); OOS refusal **80%** (4/5); 0 in-scope refusals | ≥ 95% / 100% | `claims_local.csv`, `answers_local.jsonl` |
| Corpus freshness | every indexed URL re-fetched, text hashed with the scraper's element rules | 2026-10-22: **96 checked, 0 removed, 2 redirected** (`employers/cpt.aspx` moved under `employers/recruiting/`, accessibility page is now https); baseline recorded, content diffs start on the next run | ≤ 1 month old (R9) | `../refresh.py`, `freshness.json`, monthly CI job `freshness.yml` |

**Response time is the one open requirement, and the local-model row shows why it is a hardware question.** On a 16 GB laptop GPU a 12B model answers one question in ~4 s but serves one request at a time, so ten users queue (p95 32.9 s, zero errors). Raising Ollama's parallel slots to 4 spilled a third of the model to CPU and one request took 119 s, so that knob is useless at this memory size. The same client against a larger local model with batching (vLLM on the sponsor's GB10, 128 GB) is the path to 5 s at 10 users. Local grounding is also lower (91.9% vs 97.9% remote) because the 12B model is weaker and the local judge is stricter; those two numbers are not directly comparable and the manual 30-answer audit remains the ground truth.

**Response time against the free remote endpoint.** Retrieval takes ~0.3 s; the rest is the model endpoint. Single requests to the free NVIDIA endpoint ranged from 3 s to 37 s during testing, and it rate-limits at ~10 simultaneous long prompts, so `answer.py` caps in-flight model calls (`NAVIGATOR_LLM_CONCURRENCY`, default 4) and queues the rest: zero errors, longer waits. Meeting 5 s at 10 users needs a model the team controls: the sponsor's GB10 running a local model through the same `llm.py` with two environment variables changed. That is the planned Nov 9 work, and the load test re-runs there unchanged.

## Files

| File | What it does |
|---|---|
| `queries.jsonl` | 40 questions: 35 in-scope across the seven README categories with hand-labeled expected pages, 5 out-of-scope that should be refused. Edit and re-run; labels are the team's to review. |
| `run_eval.py` | hit@3 and MRR through `hybrid_search.retrieve`. `--min-hit3 0.85` makes it a CI gate. Writes `results.csv`. |
| `run_answers.py` | Runs every query through `answer.py`, records the answer, cited passages, refusal flag, seconds. Writes `answers.jsonl`. |
| `claims.py` | Splits each answer into sentences and asks a judge model whether each is supported by only the passages it cited. Writes `claims.csv`. |
| `load_test.py` | N concurrent users against a running `serve.py`; p50/p95/max. |
| `answers_local.jsonl`, `claims_local.csv` | The same two outputs produced with the local gemma3:12b model, kept separately so both rows above are reproducible. |

## How to read the numbers honestly

- Retrieval labels were written by one person (Advait Sadineni) against the 96 scraped pages. The two misses (#18, #26) returned pages a reader might call relevant; the labels were kept strict rather than adjusted to pass.
- Per category: recruiting 7/7, research 5/5, capstone 5/5, student orgs 4/5, events 4/5, giving 5/5, employee education 3/3. Employee education has only two pages in the corpus, which is a coverage problem for the scraper, not a ranking problem.
- The three unsupported sentences: one is a sentence-splitting artifact ("Monday through Friday)." split off its parent), one adds an approval window the page does not state, one names a calendar page not among the cited passages. The one in-scope refusal (#15, capstone submission deadline) is a retrieval miss: the deadline sentence sits in a chunk that was not in the top five.
- The claim judge is a second model checking the first. The test plan's 30-answer manual audit remains the ground truth; `claims.csv` lists every sentence so that audit is a read-through, not a rebuild.
- Latency here is this laptop plus a remote model endpoint, or this laptop's GPU for the local row. On the sponsor's hardware the number changes; re-run there.
- Local model setup (any OpenAI-compatible server works; this is what the local row used):

  ```
  ollama pull gemma3:12b
  set NAVIGATOR_LLM_BASE=http://127.0.0.1:11434/v1
  set NAVIGATOR_LLM_KEY=ollama
  set NAVIGATOR_LLM_MODEL=gemma3:12b
  ```

## Pipeline these scripts measure

```
question -> hybrid_search.retrieve (keyword + MiniLM/Chroma, rank fusion)  <- run_eval.py measures this
         -> answer.py: 5 passages -> model -> sentences, each must cite [n]
            uncited sentences dropped; NO_VERIFIED_ANSWER -> closest-page handoff
         -> claims.py: judge model checks each sentence against its cited passages
```
