"""Offline: the /api/chat response shape that the team's index.html + chatbot.js expect."""
from serve import chat_reply


def _out(refused, **kw):
    base = {"question": "q", "answer": "", "refused": refused, "citations": [],
            "evidence": [{"n": 1, "title": "T1", "url": "https://x.psu.edu/1", "text": "t1"}]}
    base.update(kw)
    return base


def test_answer_maps_citations_to_sources():
    out = _out(False, answer="Post jobs here [1].", citations=[{"n": 1, "title": "T1", "url": "https://x.psu.edu/1"}])
    r = chat_reply(out)
    assert r["reply"] == "Post jobs here [1]."
    assert r["sources"] == [{"title": "T1", "url": "https://x.psu.edu/1"}]
    assert r["passages"][0]["sources"][0]["url"] == "https://x.psu.edu/1"


def test_refusal_uses_fallback_as_only_source():
    out = _out(True, fallback={"title": "Connect", "url": "https://career.engr.psu.edu/connect.aspx"})
    r = chat_reply(out)
    assert "couldn't verify" in r["reply"]
    assert r["sources"] == [{"title": "Connect", "url": "https://career.engr.psu.edu/connect.aspx"}]
