"""Prepare scraper JSON for embeddings. Requires Python 3.9+, no packages.

Run: python3 prepare_chunks.py multi_seed_scrape_data.json
Output: chunks.json (text and provenance, NOT embeddings or a vector database).
Whitespace is normalized; menus and joined words need upstream HTML cleaning.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def prepare(pages, size=200, overlap=40):
    if not isinstance(pages, list):
        raise ValueError('Input must be a JSON list of page objects.')
    if size < 1 or not 0 <= overlap < size:
        raise ValueError('Require chunk size > 0 and 0 <= overlap < size.')
    groups = {}
    for number, page in enumerate(pages, 1):
        if not isinstance(page, dict):
            raise ValueError(f'Page {number} must be an object.')
        for field in ('url', 'title', 'content'):
            if not isinstance(page.get(field), str) or not page[field].strip():
                raise ValueError(f'Page {number} needs a nonempty string: {field}.')
        url = page['url'].strip()
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc:
            raise ValueError(f'Page {number} has an invalid HTTP(S) URL.')
        content = re.sub(r'\s+', ' ', page['content']).strip()
        key = digest(content)
        group = groups.setdefault(key, {'text': content, 'sources': []})
        source = {'url': url, 'title': page['title'].strip()}
        if source not in group['sources']:
            group['sources'].append(source)
    chunks = []
    for content_hash, group in groups.items():
        # Hash includes source URLs so changing provenance changes document ID.
        sources = sorted(group['sources'], key=lambda s: (s['url'], s['title']))
        document_id = digest(content_hash + '\n' + '\n'.join(s['url'] for s in sources))
        words = group['text'].split()
        start = 0
        while start < len(words):
            end = min(start + size, len(words))
            text = ' '.join(words[start:end])
            chunks.append({
                'chunk_id': digest(f'{document_id}:{size}:{overlap}:{start}:{end}'),
                'document_id': document_id,
                'content_hash': content_hash,
                'text': text,
                'url': sources[0]['url'],
                'title': sources[0]['title'],
                'sources': sources,
                'word_start': start,
                'word_end': end,
                'word_count': end - start,
                # The input scrape has no crawl timestamp; do not invent one.
                'scraped_at': None,
            })
            if end == len(words):
                break
            start = end - overlap
    return chunks, len(groups)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path, default=Path('chunks.json'))
    parser.add_argument('--chunk-size', type=int, default=200)
    parser.add_argument('--overlap', type=int, default=40)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error('Output must differ from input; keep the original scrape.')
    try:
        pages = json.loads(args.input.read_text(encoding='utf-8'))
        chunks, unique = prepare(pages, args.chunk_size, args.overlap)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(chunks, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    except (OSError, ValueError) as error:
        parser.exit(1, f'Error: {error}\n')
    print(f'Input pages: {len(pages)}; unique texts: {unique}; chunks: {len(chunks)}')
    print(f'Saved {args.output}')
    print('Review text before indexing: whitespace normalization does not remove menus or repair joined words.')


if __name__ == '__main__':
    main()
