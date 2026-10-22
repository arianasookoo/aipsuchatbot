"""Grounded answer service: retrieve evidence, answer with per-sentence citations,
refuse when the evidence does not support an answer.

Run: python answer.py "How can my company sponsor a capstone project?"
     python answer.py --json "..."
Requires an existing vector_db (python vector_search.py index chunks.json) and
an LLM endpoint (see llm.py; NVIDIA_API_KEY for development).

Design, so the numbers in eval/ mean something:
- Every sentence of the answer must end with a citation [n] that maps to one
  of the retrieved passages. Sentences without a valid citation are dropped
  before the answer is returned, so an uncited claim never reaches the user.
- If the model cannot support an answer it replies NO_VERIFIED_ANSWER. The
  service then still returns the closest official page as a handoff, so a
  refusal is never a dead end.
- The retrieval gate is deliberately loose (evidence is always shown to the
  model); the model's refusal plus the citation filter do the real work.

Honest limitation: citation presence is checked, citation correctness is not;
that is what eval/claims.py measures.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import functools

import hybrid_search
from hybrid_search import retrieve
from llm import chat

# hybrid_search.retrieve reloads the MiniLM model on every call (~3 s and a lot of RAM
# under concurrent requests). Cache it here so this service pays once per process.
# ponytail: proper fix is the same one-line cache inside vector_search.embedding_tools, as its own PR.
hybrid_search.embedding_tools = functools.lru_cache(maxsize=1)(hybrid_search.embedding_tools)
# Ten concurrent first requests each loaded the model and crashed (measured 2026-10-14), so
# retrieval is serialized; it takes ~0.3 s once cached and the model call runs outside the lock.
import os
import threading
_retrieval_lock = threading.Lock()
# The free NVIDIA endpoint returns 429 at ~10 simultaneous long prompts (measured 2026-10-14):
# cap in-flight model calls so extra users queue instead of getting an error.
_llm_slots = threading.Semaphore(int(os.environ.get("NAVIGATOR_LLM_CONCURRENCY", "4")))


def warm_up(db=Path("vector_db")):
    """Load the embedding model once before serving traffic."""
    with _retrieval_lock:
        retrieve("warm up", db, 1)

REFUSAL = "NO_VERIFIED_ANSWER"
TOP_K = 5
SYSTEM = f"""You help external organizations (companies, recruiters, research partners, donors) find official Penn State College of Engineering resources.

Rules:
1. Use ONLY the numbered evidence passages below. Do not use outside knowledge.
2. Every sentence must end with a citation like [2] naming the passage that supports it. A sentence may cite more than one passage: [1][3].
3. Name specific pages, programs, offices, and contacts from the evidence when they exist.
4. If the evidence does not directly answer the question asked, reply with exactly {REFUSAL} and nothing else. Never answer a different question than the one asked, and never write a sentence saying the evidence lacks something.
5. Answer in at most 5 sentences. No preamble.
6. Your first line must be exactly ANSWERABLE or {REFUSAL}, on its own line, before anything else. If the question is outside the evidence, there is nothing else."""


def build_prompt(question, evidence):
    blocks = [f"[{i}] {e['title']}\nURL: {e['sources'][0]['url']}\n{e['text']}"
              for i, e in enumerate(evidence, 1)]
    return f"Evidence:\n\n" + "\n\n".join(blocks) + f"\n\nQuestion: {question}"


def keep_cited(text, n):
    """Keep only sentences that carry at least one citation in 1..n."""
    kept = []
    for sent in re.split(r"(?<=[.!?\]])\s+", text.strip()):
        cites = [int(c) for c in re.findall(r"\[(\d+)\]", sent)]
        if cites and all(1 <= c <= n for c in cites):
            kept.append(sent.strip())
    return " ".join(kept)


def answer(question, db=Path("vector_db"), top_k=TOP_K, llm=chat, retriever=retrieve):
    with _retrieval_lock:
        evidence = retriever(question, db, top_k)
    with _llm_slots:
        reply = llm([{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": build_prompt(question, evidence)}])
    reply = re.sub(r"^\s*ANSWERABLE\s*", "", reply)  # decision line, see SYSTEM rule 6
    cited_text = "" if REFUSAL in reply[:40] else keep_cited(reply, len(evidence))
    used = sorted({int(c) for c in re.findall(r"\[(\d+)\]", cited_text)})
    citations = [{"n": i, "title": evidence[i - 1]["title"], "url": evidence[i - 1]["sources"][0]["url"]}
                 for i in used]
    refused = not cited_text
    out = {"question": question, "answer": cited_text, "refused": refused, "citations": citations,
           "evidence": [{"n": i, "title": e["title"], "url": e["sources"][0]["url"], "text": e["text"]}
                        for i, e in enumerate(evidence, 1)]}
    if refused:
        # Hand off to the top page only when keyword and vector search agree it is
        # close (both rank <= 3). A keyword-only hit sends "football tickets" to the
        # internships page (measured 2026-10-14); then the contact page is the safer handoff.
        top = evidence[0] if evidence and all(
            (evidence[0].get(k) or 99) <= 3 for k in ("keyword_rank", "vector_rank")) else None
        out["fallback"] = ({"title": top["title"], "url": top["sources"][0]["url"]} if top
                           else {"title": "Connect with Career Resources & Employer Relations",
                                 "url": "https://career.engr.psu.edu/connect.aspx"})
    return out


def render(out):
    """Plain text for the chat widget (it renders textContent, never HTML)."""
    if out["refused"]:
        msg = "I couldn't verify an answer to that from official Penn State Engineering pages."
        if out.get("fallback"):
            msg += f"\nThe closest official page is: {out['fallback']['title']}\n{out['fallback']['url']}"
        return msg
    lines = [out["answer"], "", "Sources:"]
    lines += [f"[{c['n']}] {c['title']}\n{c['url']}" for c in out["citations"]]
    return "\n".join(lines)


def _selfcheck():
    assert keep_cited("Post jobs on Nittany Lion Careers [1]. I think so. Fees apply [2][1].", 2) == \
        "Post jobs on Nittany Lion Careers [1]. Fees apply [2][1]."
    assert keep_cited("Made up fact [7].", 2) == ""
    fake_ev = [{"title": "T", "sources": [{"url": "https://x.psu.edu/a"}], "text": "t", "keyword_rank": 1, "vector_rank": 2}]
    fake_ret = lambda q, db, k: fake_ev
    out = answer("q", llm=lambda m: "ANSWERABLE\nYes [1].", retriever=fake_ret)
    assert out["answer"] == "Yes [1]." and out["citations"][0]["url"] == "https://x.psu.edu/a" and not out["refused"]
    out = answer("q", llm=lambda m: REFUSAL, retriever=fake_ret)
    assert out["refused"] and out["fallback"]["url"] == "https://x.psu.edu/a"
    weak = [{**fake_ev[0], "vector_rank": 20}]  # keyword-only hit: hand off to the contact page instead
    out = answer("q", llm=lambda m: REFUSAL, retriever=lambda q, db, k: weak)
    assert out["fallback"]["url"].endswith("/connect.aspx")
    print("selfcheck ok")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("question", nargs="?")
    p.add_argument("--db", type=Path, default=Path("vector_db"))
    p.add_argument("--json", action="store_true")
    p.add_argument("--selfcheck", action="store_true")
    a = p.parse_args()
    if a.selfcheck:
        return _selfcheck()
    if not a.question:
        p.error("question required")
    out = answer(a.question, a.db)
    print(json.dumps(out, ensure_ascii=False, indent=2) if a.json else render(out))


if __name__ == "__main__":
    main()
