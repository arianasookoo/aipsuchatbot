"""Offline: the /api/chat response shape that the team's index.html + chatbot.js expect."""
import threading
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer

import pytest

from serve import HERE, Handler, chat_reply


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


@pytest.fixture(scope="module")
def base_url():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(HERE)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _status(url):
    try:
        return urllib.request.urlopen(url, timeout=5).status
    except urllib.error.HTTPError as e:
        return e.code


def test_only_the_ui_files_are_served(base_url):
    assert _status(base_url + "/api/health") == 200
    assert _status(base_url + "/app.html") == 200
    assert _status(base_url + "/") == 200
    for leak in ("/.env", "/.env.example", "/.git/config", "/query_log.jsonl", "/answer.py", "/eval/queries.jsonl"):
        assert _status(base_url + leak) == 404, leak
