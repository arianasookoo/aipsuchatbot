"""Retrieval evaluation for requirement R4 (relevant page in the top 3 for >= 85% of queries).

Reads queries.jsonl, runs each query through hybrid_search.retrieve, reports hit@3
and MRR, writes results.csv. Out-of-scope queries (expected_urls == []) are not
counted toward R4; they are scored by eval/claims.py as refusals.

Run from the repo root with the index built:
    python eval/run_eval.py                  # prints hit@3, MRR, writes eval/results.csv
    python eval/run_eval.py --min-hit3 0.85  # exit 1 below the threshold (used by CI)
    python eval/run_eval.py --selfcheck

Honest limitation: relevance is judged by URL match against hand-labeled
expected_urls (labeled 2026-10-14 by Advait Sadineni against the 96 scraped pages).
A relevant page missing from the labels counts as a miss. Labels are reviewable
by anyone: edit queries.jsonl and re-run.
"""
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
QUERIES = HERE / "queries.jsonl"
RESULTS = HERE / "results.csv"
K = 3


def search(query, k=K, db=ROOT / "vector_db"):
    from hybrid_search import retrieve
    return [{"urls": [s["url"] for s in r["sources"]], "title": r["title"]} for r in retrieve(query, db, k)]


def norm(u):
    u = u.strip().lower().split("#")[0].split("?")[0]
    u = u.replace("http://", "https://").replace("https://www.", "https://")
    return u.rstrip("/")


def load_queries(path=QUERIES):
    return [json.loads(l) for l in path.read_text(encoding="utf8").splitlines()
            if l.strip() and not l.startswith("//")]


def score(rows, search_fn=search, k=K):
    out, hits, rr = [], 0, 0.0
    n = sum(1 for r in rows if r["expected_urls"])
    for r in rows:
        res = search_fn(r["query"], k)
        exp = {norm(u) for u in r["expected_urls"]}
        rank = next((i + 1 for i, x in enumerate(res) if exp & {norm(u) for u in x["urls"]}), None)
        if exp:
            hits += rank is not None
            rr += 1 / rank if rank else 0
        out.append({"id": r["id"], "category": r["category"], "query": r["query"],
                    "hit_rank": rank or "", "top_titles": " | ".join(x["title"] for x in res)})
    return out, (hits / n if n else 0.0), (rr / n if n else 0.0), n


def per_category(out):
    agg = {}
    for r in out:
        if r["category"] == "out-of-scope":
            continue
        h, t = agg.get(r["category"], (0, 0))
        agg[r["category"]] = (h + bool(r["hit_rank"]), t + 1)
    return agg


def main():
    min_hit = float(sys.argv[sys.argv.index("--min-hit3") + 1]) if "--min-hit3" in sys.argv else None
    rows = load_queries()
    out, hit3, mrr, n = score(rows)
    with RESULTS.open("w", newline="", encoding="utf8") as f:
        w = csv.DictWriter(f, fieldnames=out[0].keys())
        w.writeheader()
        w.writerows(out)
    print(f"in-scope queries: {n}   hit@{K}: {hit3:.1%}   MRR: {mrr:.3f}   target: 85%   "
          f"{'PASS' if hit3 >= 0.85 else 'FAIL'}")
    for c, (h, t) in per_category(out).items():
        print(f"  {c:24} {h}/{t}")
    print(f"wrote {RESULTS}")
    if min_hit is not None and hit3 < min_hit:
        sys.exit(f"hit@3 {hit3:.1%} is below the required {min_hit:.0%}")


def _selfcheck():
    fake = lambda q, k: [{"urls": ["https://lf.psu.edu/sponsors/sponsor-a-project/"], "title": "a"},
                         {"urls": ["https://x.psu.edu/other"], "title": "b"}]
    rows = [{"id": 1, "category": "s", "query": "a", "expected_urls": ["http://www.lf.psu.edu/sponsors/sponsor-a-project"]},
            {"id": 2, "category": "s", "query": "b", "expected_urls": ["https://psu.edu/missing"]},
            {"id": 3, "category": "out-of-scope", "query": "c", "expected_urls": []}]
    out, hit3, mrr, n = score(rows, fake)
    assert n == 2 and out[0]["hit_rank"] == 1 and out[1]["hit_rank"] == "" and out[2]["hit_rank"] == ""
    assert abs(hit3 - 0.5) < 1e-9 and abs(mrr - 0.5) < 1e-9 and per_category(out) == {"s": (1, 2)}
    assert len(load_queries()) >= 35
    print("selfcheck ok")


if __name__ == "__main__":
    _selfcheck() if "--selfcheck" in sys.argv else main()
