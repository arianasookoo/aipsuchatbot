"""Serve the chat widget and the /ask endpoint. Standard library only.

Run: python serve.py            (then open http://localhost:8008/demo.html)
     python serve.py --port 9000

POST /ask       {"question": "..."}  ->  answer.py output plus "reply" (plain text for the widget)
POST /api/chat  {"message": "..."}   ->  {"reply", "sources": [{title,url}], "passages"}: the shape
                                         index.html / chatbot.js on the team's `testing` branch expect
GET  /api/health                     ->  {"status": "ok"}
GET  /                               ->  app.html; only the files in STATIC are served, everything else is 404

Honest limitation: single-threaded dev server, one LLM call per request with no
caching. The load test in eval/ measures exactly that, which is the point.
"""
import argparse
import json
import sys
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from answer import answer, render, warm_up

HERE = Path(__file__).parent
LOG = HERE / "query_log.jsonl"  # every question, answer, latency: feeds the eval set later
STATIC = {"/app.html", "/demo.html", "/index.html", "/chatbot.js", "/chatbot.css"}  # never .env, .git, logs


def chat_reply(out):
    """answer.py output -> the {"reply","sources","passages"} shape the team's widget consumes."""
    if out["refused"]:
        text = "I couldn't verify an answer to that from official Penn State Engineering pages."
        sources = [out["fallback"]] if out.get("fallback") else []
    else:
        text, sources = out["answer"], [{"title": c["title"], "url": c["url"]} for c in out["citations"]]
    return {"reply": text, "sources": sources,
            "passages": [{"title": e["title"], "text": e["text"], "sources": [{"title": e["title"], "url": e["url"]}]}
                         for e in out["evidence"]]}


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/health":
            return self._json(200, {"status": "ok"})
        if path == "/":
            path = "/app.html"
        if path not in STATIC:
            return self.send_error(404)
        self.path = path
        return super().do_GET()

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path not in ("/ask", "/api/chat"):
            return self.send_error(404)
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            q = str(body.get("question") or body.get("message") or "").strip()[:500]
            if not q:
                raise ValueError("empty question")
            t0 = time.perf_counter()
            out = answer(q)
            out["reply"] = render(out)
            out["seconds"] = round(time.perf_counter() - t0, 2)
            with LOG.open("a", encoding="utf8") as f:
                f.write(json.dumps({k: out[k] for k in ("question", "answer", "refused", "citations", "seconds")},
                                   ensure_ascii=False) + "\n")
            self._json(200, chat_reply(out) if path == "/api/chat" else out)
        except Exception as e:  # never leak a stack trace to the widget; log it server-side
            print(f"ERROR {path}: {type(e).__name__}: {str(e)[:300]}", file=sys.stderr, flush=True)
            self._json(500, {"reply": "Sorry, something went wrong on the server."})

    def _json(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):  # quieter console
        if "POST" in fmt % args:
            super().log_message(fmt, *args)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8008)
    p.add_argument("--host", default="127.0.0.1", help="0.0.0.0 inside Docker")
    a = p.parse_args()
    warm_up()
    srv = ThreadingHTTPServer((a.host, a.port), partial(Handler, directory=str(HERE)))
    print(f"Navigator: http://localhost:{a.port}/app.html   (widget version: /demo.html, Ctrl+C to stop)", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
