"""Serve the chat widget and a retrieval API backed by hybrid_search.py.

Run: python server.py            then open http://127.0.0.1:8000
API: POST /api/chat  {"message": "..."}  ->  {"reply": "...", "sources": [...], "passages": [...]}
Requires an existing vector_db (python vector_search.py index chunks.json).
Replies are retrieved evidence excerpts, not generated answers.
"""
import argparse
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading

import hybrid_search
import vector_search

ROOT = Path(__file__).resolve().parent
STATIC = {'/': ('index.html', 'text/html; charset=utf-8'),
          '/index.html': ('index.html', 'text/html; charset=utf-8'),
          '/chatbot.js': ('chatbot.js', 'text/javascript; charset=utf-8'),
          '/chatbot.css': ('chatbot.css', 'text/css; charset=utf-8')}
MAX_BODY = 16 * 1024
EXCERPT_WORDS = 90

# Loading MiniLM takes seconds, so load it once instead of on every request.
# The ONNX session is not guaranteed thread-safe, so searches run one at a time.
hybrid_search.embedding_tools = lru_cache(maxsize=1)(vector_search.embedding_tools)
search_lock = threading.Lock()


def excerpt(text, limit=EXCERPT_WORDS):
    words = text.split()
    return ' '.join(words[:limit]) + (' …' if len(words) > limit else '')


def answer(question, db, top_k):
    with search_lock:
        results = hybrid_search.retrieve(question, db, top_k)
    if not results:
        return {'reply': 'I could not find an official Penn State page about that. '
                         'Try rephrasing your question.', 'sources': [], 'passages': []}
    sources, seen = [], set()
    for result in results:
        for source in result['sources']:
            if source['url'] not in seen:
                seen.add(source['url'])
                sources.append({'title': source['title'], 'url': source['url']})
    best = results[0]
    reply = (f'The most relevant official page I found is "{best["title"]}":\n\n'
             f'{excerpt(best["text"])}\n\nCheck the linked sources for full details.')
    passages = [{'title': r['title'], 'text': r['text'], 'sources': r['sources'],
                 'fusion_score': r['fusion_score']} for r in results]
    return {'reply': reply, 'sources': sources[:top_k], 'passages': passages}


class Handler(BaseHTTPRequestHandler):
    db = Path('vector_db')
    top_k = 3

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split('?', 1)[0]
        if path == '/api/health':
            return self.send_json(200, {'status': 'ok'})
        if path not in STATIC:
            return self.send_json(404, {'error': 'Not found.'})
        name, content_type = STATIC[path]
        body = (ROOT / name).read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path.split('?', 1)[0] != '/api/chat':
            return self.send_json(404, {'error': 'Not found.'})
        try:
            length = int(self.headers.get('Content-Length', 0))
        except ValueError:
            length = -1
        if not 0 < length <= MAX_BODY:
            return self.send_json(400, {'error': 'Send a JSON body under 16 KB.'})
        try:
            message = json.loads(self.rfile.read(length)).get('message')
        except (ValueError, AttributeError):
            return self.send_json(400, {'error': 'Body must be JSON like {"message": "..."}.'})
        if not isinstance(message, str) or not message.strip():
            return self.send_json(400, {'error': 'Enter a question.'})
        try:
            return self.send_json(200, answer(message, self.db, self.top_k))
        except ValueError as error:
            # retrieve() raises ValueError for user-fixable problems (e.g. too long).
            return self.send_json(400, {'error': str(error)})
        except Exception as error:
            print(f'Search failed: {error!r}', file=sys.stderr)
            return self.send_json(500, {'error': 'Search failed. Please try again.'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--db', type=Path, default=Path('vector_db'))
    parser.add_argument('--top-k', type=int, default=3)
    args = parser.parse_args()
    if args.top_k < 1:
        parser.error('--top-k must be positive.')
    if not (args.db / 'active_index.json').exists():
        parser.exit(1, 'Error: build the database first: python vector_search.py index chunks.json\n')
    Handler.db, Handler.top_k = args.db, args.top_k
    hybrid_search.embedding_tools()  # warm the model before accepting requests
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f'Serving on http://{args.host}:{args.port}', file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
