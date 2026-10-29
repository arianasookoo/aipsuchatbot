"""Latency under concurrent users (requirement: 95% of responses within 5 s at 10 users).

Fires the in-scope queries from queries.jsonl at a running serve.py with N
concurrent threads and reports p50 / p95 / max seconds and the error count.

Run:  python serve.py            (in one terminal)
      python eval/load_test.py --users 10 --rounds 2

Honest limitation: measures this laptop plus the remote model endpoint. The
sponsor's GB10 with a local model is a different number; re-run there.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_eval import load_queries  # noqa: E402


def ask(url, q):
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, data=json.dumps({"question": q}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            json.load(r)
        return time.perf_counter() - t0, None
    except urllib.error.HTTPError as e:
        return time.perf_counter() - t0, f"HTTP {e.code}: {e.read()[:120].decode(errors='replace')}"
    except Exception as e:
        return time.perf_counter() - t0, str(e)[:80]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://127.0.0.1:8008/ask")
    p.add_argument("--users", type=int, default=10)
    p.add_argument("--rounds", type=int, default=1, help="how many times each user asks")
    a = p.parse_args()
    qs = [q["query"] for q in load_queries() if q["expected_urls"]]
    jobs = [qs[(u * a.rounds + r) % len(qs)] for u in range(a.users) for r in range(a.rounds)]
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=a.users) as ex:
        results = list(ex.map(lambda q: ask(a.url, q), jobs))
    wall = time.perf_counter() - t0
    secs = sorted(s for s, _ in results)
    errors = [e for _, e in results if e]
    p95 = secs[max(0, int(len(secs) * 0.95) - 1)]
    print(f"{len(jobs)} requests, {a.users} concurrent   p50 {secs[len(secs)//2]:.1f}s   p95 {p95:.1f}s   "
          f"max {secs[-1]:.1f}s   errors {len(errors)}   wall {wall:.1f}s")
    print("requirement: p95 <= 5.0 s at 10 users ->", "PASS" if p95 <= 5 and not errors else "FAIL")
    for e in errors[:3]:
        print("  error:", e)


if __name__ == "__main__":
    main()
