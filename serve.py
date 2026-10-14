"""Serve the chat widget and the /ask endpoint. Standard library only.

Run: python serve.py            (then open http://localhost:8008/demo.html)
     python serve.py --port 9000

POST /ask  {"question": "..."}  ->  answer.py output plus "reply" (plain text for the widget)
GET  /...                       ->  static files from this folder (demo.html, chatbot.js, chatbot.css)

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

LOG = Path("query_log.jsonl")  # every question, answer, latency: feeds the eval set later


class Handler(SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/ask":
            return self.send_error(404)
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or b"{}"))
            q = str(body.get("question", "")).strip()[:500]
            if not q:
                raise ValueError("empty question")
            t0 = time.perf_counter()
            out = answer(q)
            out["reply"] = render(out)
            out["seconds"] = round(time.perf_counter() - t0, 2)
            with LOG.open("a", encoding="utf8") as f:
                f.write(json.dumps({k: out[k] for k in ("question", "answer", "refused", "citations", "seconds")},
                                   ensure_ascii=False) + "\n")
            data = json.dumps(out, ensure_ascii=False).encode()
            self.send_response(200)
        except Exception as e:  # never leak a stack trace to the widget; log it server-side
            print(f"ERROR /ask: {type(e).__name__}: {str(e)[:300]}", file=sys.stderr, flush=True)
            data = json.dumps({"reply": "Sorry, something went wrong on the server.", "error": str(e)[:200]}).encode()
            self.send_response(500)
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
    a = p.parse_args()
    warm_up()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), partial(Handler, directory=str(Path(__file__).parent)))
    print(f"Navigator demo: http://localhost:{a.port}/demo.html   (Ctrl+C to stop)", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
