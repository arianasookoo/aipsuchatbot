"""Generate a grounded answer for every query in queries.jsonl and record latency.

Writes answers.jsonl (input for claims.py) and prints p50/p95 seconds per answer.

Run from the repo root with the index built and an LLM endpoint configured:
    python eval/run_answers.py

Honest limitation: latency here is one sequential request at a time on this
machine; the 10-concurrent-user number comes from eval/load_test.py.
"""
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from run_eval import load_queries  # noqa: E402

OUT = HERE / "answers.jsonl"


def main():
    from answer import answer
    rows, secs = [], []
    for q in load_queries():
        t0 = time.perf_counter()
        a = answer(q["query"], ROOT / "vector_db")
        dt = time.perf_counter() - t0
        secs.append(dt)
        cited = {c["n"] for c in a["citations"]}
        rows.append({"id": q["id"], "category": q["category"], "query": q["query"],
                     "answer": a["answer"] if not a["refused"] else "NO_VERIFIED_ANSWER",
                     "cited": [e["text"] for e in a["evidence"] if e["n"] in cited],
                     "cited_urls": [c["url"] for c in a["citations"]],
                     "cited_titles": [c["title"] for c in a["citations"]],
                     "out_of_scope": q["category"] == "out-of-scope",
                     "refused": a["refused"], "seconds": round(dt, 2)})
        print(f"{q['id']:>3} {dt:5.1f}s {'REFUSED' if a['refused'] else 'answered':8} {q['query'][:60]}", flush=True)
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf8")
    s = sorted(secs)
    print(f"\n{len(rows)} answers   p50 {s[len(s)//2]:.1f}s   p95 {s[int(len(s)*0.95)-1]:.1f}s   wrote {OUT}")


if __name__ == "__main__":
    main()
