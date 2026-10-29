"""Claim-level support scoring for requirement R14 (>= 95% of factual claims supported
by retrieved sources) plus the refusal rate on out-of-scope queries.

Reads answers.jsonl (from run_answers.py). Each answer is split into sentences;
a judge model is shown the sentences and ONLY the passages the answer cited, and
labels each sentence supported / unsupported. Writes claims.csv.

Run from the repo root:
    python eval/claims.py
    python eval/claims.py --selfcheck

Honest limitation: the judge is an LLM, so this is a second model checking the
first. It is a different model family from the answerer when NAVIGATOR_JUDGE_MODEL
is set, and the 30-answer manual audit in the test plan remains the ground truth.
Sentence = claim is crude; a sentence with two facts is scored as one.
"""
import csv
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

ANSWERS = HERE / "answers.jsonl"
OUT = HERE / "claims.csv"
TARGET = 0.95
REFUSAL = "NO_VERIFIED_ANSWER"
JUDGE = """You are checking whether each numbered sentence is directly supported by the evidence passages. A sentence is SUPPORTED only if every fact in it (names, numbers, steps, contacts, conditions) appears in the evidence. Ignore the citation markers like [1].

Evidence:
{evidence}

Sentences:
{sentences}

Reply with one line per sentence in the form `<number>: SUPPORTED` or `<number>: UNSUPPORTED`, nothing else."""


# Copy of answer.SENT_SPLIT so scoring splits sentences exactly as keep_cited does.
SENT_SPLIT = re.compile(r"(?<!\bDr\.)(?<!\bMr\.)(?<!\bMs\.)(?<!\bMrs\.)(?<!\bProf\.)(?<!\bSt\.)(?<!\bvs\.)(?<!\bNo\.)(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\bPh\.D\.)(?<!\bU\.S\.)(?<=[.!?\]])\s+")


def split_claims(answer):
    parts = SENT_SPLIT.split(answer.strip())
    return [re.sub(r"\s*\[\d+\]", "", p).strip() for p in parts if len(p.split()) >= 3]


def llm_judge(claims, evidence):
    from llm import chat
    if os.environ.get("NAVIGATOR_JUDGE_MODEL"):  # process-wide: claims.py only ever judges
        import llm
        llm.MODEL_PREFIX, llm._model = os.environ["NAVIGATOR_JUDGE_MODEL"], None
    prompt = JUDGE.format(evidence="\n\n".join(f"[{i}] {e}" for i, e in enumerate(evidence, 1)),
                          sentences="\n".join(f"{i}. {c}" for i, c in enumerate(claims, 1)))
    reply = chat([{"role": "user", "content": prompt}], max_tokens=2000)
    verdict = {int(n): v.upper().startswith("SUPPORTED") for n, v in re.findall(r"(\d+)\s*[:.)]\s*(\w+)", reply)}
    return [verdict.get(i, False) for i in range(1, len(claims) + 1)]


def score(rows, judge=llm_judge):
    out, supported, total, refusals, oos = [], 0, 0, 0, 0
    for r in rows:
        if r.get("out_of_scope"):
            oos += 1
            refusals += r["answer"].strip() == REFUSAL
            continue
        if r["answer"].strip() == REFUSAL:
            out.append({"id": r["id"], "claim": REFUSAL, "supported": ""})
            continue
        claims = split_claims(r["answer"])
        if not claims:
            continue
        # The answerer saw each passage with its title and URL, so the judge must too;
        # otherwise "see the Continuing Education page at <url>" is scored unsupported.
        titles = r.get("cited_titles") or [""] * len(r["cited"])
        urls = r.get("cited_urls") or [""] * len(r["cited"])
        evidence = [f"{t}\nURL: {u}\n{x}".strip() for t, u, x in zip(titles, urls, r["cited"])]
        flags = judge(claims, evidence)
        for c, ok in zip(claims, flags):
            total += 1
            supported += ok
            out.append({"id": r["id"], "claim": c, "supported": int(ok)})
    return out, (supported / total if total else 0.0), (refusals / oos if oos else None), total


def main():
    rows = [json.loads(l) for l in ANSWERS.read_text(encoding="utf8").splitlines() if l.strip()]
    out, pct, refusal_rate, total = score(rows)
    with OUT.open("w", newline="", encoding="utf8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "claim", "supported"])
        w.writeheader()
        w.writerows(out)
    in_scope_refused = sum(1 for r in rows if not r.get("out_of_scope") and r["answer"].strip() == REFUSAL)
    print(f"claims scored: {total}   supported: {pct:.1%}   target: {TARGET:.0%}   {'PASS' if pct >= TARGET else 'FAIL'}")
    print(f"out-of-scope refusal rate: {'n/a' if refusal_rate is None else f'{refusal_rate:.0%}'}   "
          f"in-scope refusals (should be 0): {in_scope_refused}")
    print(f"wrote {OUT}")


def _selfcheck():
    fake = lambda claims, ev: [c.rstrip(".").lower() in " ".join(ev).lower() for c in claims]
    rows = [{"id": 1, "answer": "Sponsors donate four thousand dollars [1]. The moon is cheese [1].",
             "cited": ["To support project expenses, sponsors donate four thousand dollars to the College."], "out_of_scope": False},
            {"id": 2, "answer": REFUSAL, "cited": [], "out_of_scope": True},
            {"id": 3, "answer": "Tuition is free.", "cited": [], "out_of_scope": True}]
    out, pct, rr, total = score(rows, fake)
    assert split_claims(rows[0]["answer"]) == ["Sponsors donate four thousand dollars.", "The moon is cheese."]
    assert total == 2 and abs(pct - 0.5) < 1e-9 and rr == 0.5 and len(out) == 2, (pct, rr, out)
    print("selfcheck ok")


if __name__ == "__main__":
    _selfcheck() if "--selfcheck" in sys.argv else main()
