"""Local Penn State vector search. Install: python -m pip install chromadb==1.5.9

Build: python vector_search.py index chunks.json
Search: python vector_search.py search "How can my company sponsor a capstone?"
First run downloads the MiniLM embedding model. No API key required.
This is retrieval only: results are evidence candidates, not verified answers.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

MODEL = 'all-MiniLM-L6-v2'


def load_chunks(path):
    chunks = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(chunks, list) or not chunks:
        raise ValueError('Expected a nonempty list in chunks.json.')
    seen = set()
    for i, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            raise ValueError(f'Chunk {i} must be an object.')
        for field in ('chunk_id', 'document_id', 'text', 'url', 'title'):
            if not isinstance(chunk.get(field), str) or not chunk[field].strip():
                raise ValueError(f'Chunk {i} needs a nonempty {field}.')
        if chunk['chunk_id'] in seen:
            raise ValueError('Duplicate chunk IDs found. Regenerate chunks.json.')
        seen.add(chunk['chunk_id'])
        sources = chunk.get('sources')
        if not isinstance(sources, list) or not sources:
            raise ValueError(f'Chunk {i} needs sources with URLs and titles.')
        for source in sources:
            if not isinstance(source, dict) or not all(isinstance(source.get(k), str) and source[k].strip() for k in ('url', 'title')):
                raise ValueError(f'Chunk {i} has invalid source metadata.')
    return chunks


def embedding_tools():
    import onnxruntime
    from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
    from tokenizers import Tokenizer
    onnxruntime.disable_telemetry_events()
    ef = ONNXMiniLM_L6_V2(preferred_providers=['CPUExecutionProvider'])
    print('Loading local MiniLM model (downloads automatically on first use)...', file=sys.stderr)
    ef(['Initialize the embedding model.'])
    # Use a separate tokenizer for counting: the embedding tokenizer truncates
    # and pads, which would otherwise conceal overlong inputs.
    tokenizer = Tokenizer.from_str(ef.tokenizer.to_str())
    tokenizer.no_truncation()
    tokenizer.no_padding()
    return ef, tokenizer


def split_for_model(text, tokenizer, limit=220, overlap=30):
    """Split at tokenizer offsets so every non-whitespace character survives."""
    encoded = tokenizer.encode(text, add_special_tokens=False)
    offsets = encoded.offsets
    if not offsets:
        raise ValueError('Text has no embeddable tokens.')
    start = 0
    while start < len(offsets):
        end = min(start + limit, len(offsets))
        left = 0 if start == 0 else offsets[start][0]
        right = len(text) if end == len(offsets) else offsets[end][0]
        part = text[left:right].strip()
        # A slice beginning mid-word can tokenize differently; verify again.
        while len(tokenizer.encode(part).ids) > 256 and end > start + 1:
            end -= 1
            right = offsets[end][0]
            part = text[left:right].strip()
        if not part or len(tokenizer.encode(part).ids) > 256:
            raise ValueError('Could not split text within the model token limit.')
        yield left, right, part
        if end == len(offsets):
            break
        start = max(start + 1, end - overlap)


def index(args):
    import chromadb
    chunks = load_chunks(args.input)
    ef, tokenizer = embedding_tools()
    records = []
    for chunk in chunks:
        for left, right, text in split_for_model(chunk['text'], tokenizer):
            record_id = hashlib.sha256(f"{chunk['chunk_id']}:{MODEL}:{left}:{right}".encode()).hexdigest()
            metadata = {
                'parent_chunk_id': chunk['chunk_id'],
                'document_id': chunk['document_id'],
                'url': chunk['url'], 'title': chunk['title'],
                'sources_json': json.dumps(chunk['sources'], ensure_ascii=False),
                'character_start': left, 'character_end': right,
                'embedding_model': MODEL,
            }
            if chunk.get('content_hash'):
                metadata['content_hash'] = chunk['content_hash']
            records.append((record_id, text, metadata))
    args.db.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(args.db.resolve()),
        settings=chromadb.Settings(anonymized_telemetry=False))
    name = 'psu_' + uuid.uuid4().hex
    # Build separately; a failed rebuild leaves the active index unchanged.
    collection = client.create_collection(name=name, embedding_function=None,
        configuration={'hnsw': {'space': 'cosine'}}, metadata={'embedding_model': MODEL})
    try:
        for start in range(0, len(records), 32):
            batch = records[start:start + 32]
            vectors = ef([r[1] for r in batch])
            collection.add(ids=[r[0] for r in batch], documents=[r[1] for r in batch],
                metadatas=[r[2] for r in batch], embeddings=vectors)
            print(f'Indexed {min(start + 32, len(records))}/{len(records)} passages', flush=True)
        if collection.count() != len(records):
            raise RuntimeError('Database count did not match the input.')
        manifest = {
            'collection': name, 'embedding_model': MODEL,
            'indexed_at': datetime.now(timezone.utc).isoformat(),
            'input_sha256': hashlib.sha256(args.input.read_bytes()).hexdigest(),
            'parent_chunks': len(chunks), 'indexed_passages': len(records),
            'note': 'Index time is not scrape time. Source freshness is unknown.',
        }
        temporary = args.db / f'active-{uuid.uuid4().hex}.tmp'
        temporary.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        os.replace(temporary, args.db / 'active_index.json')
    except Exception:
        client.delete_collection(name)
        raise
    print(f'Built vector database in {args.db}. Original chunks: {len(chunks)}; indexed passages: {len(records)}.')
    print('Long chunks are split further to fit MiniLM. Previous collections are retained for recovery.')


def search(args):
    import chromadb
    manifest_path = args.db / 'active_index.json'
    if not manifest_path.exists():
        raise ValueError('No active index. First run: python vector_search.py index chunks.json')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('embedding_model') != MODEL:
        raise ValueError('Index model differs from this script. Rebuild the index.')
    question = args.question.strip()
    if not question:
        raise ValueError('Enter a nonempty question.')
    ef, tokenizer = embedding_tools()
    if len(tokenizer.encode(question).ids) > 256:
        raise ValueError('Question exceeds the model input limit. Please shorten it.')
    client = chromadb.PersistentClient(path=str(args.db.resolve()),
        settings=chromadb.Settings(anonymized_telemetry=False))
    collection = client.get_collection(manifest['collection'], embedding_function=None)
    count = collection.count()
    if not count:
        raise ValueError('Active index is empty. Rebuild it.')
    result = collection.query(query_embeddings=ef([question]), n_results=min(args.top_k, count),
        include=['documents', 'metadatas', 'distances'])
    for i, (rid, text, meta, distance) in enumerate(zip(result['ids'][0], result['documents'][0],
            result['metadatas'][0], result['distances'][0]), 1):
        print(f'\nRESULT {i}: {meta["title"]}')
        print(f'Cosine similarity: {1 - distance:.3f} (not a confidence percentage)')
        print(f'Passage ID: {rid}')
        for source in json.loads(meta['sources_json']):
            print(f'Source: {source["url"]}')
        print(text)
    print('\nThese are nearest matches, not proof the question can be answered. Review the passages.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    build = commands.add_parser('index', help='Build embeddings and persistent database')
    build.add_argument('input', type=Path)
    build.add_argument('--db', type=Path, default=Path('vector_db'))
    query = commands.add_parser('search', help='Find matching passages')
    query.add_argument('question')
    query.add_argument('--db', type=Path, default=Path('vector_db'))
    query.add_argument('--top-k', type=int, default=5)
    args = parser.parse_args()
    if args.command == 'search' and args.top_k < 1:
        parser.error('--top-k must be positive.')
    try:
        (index if args.command == 'index' else search)(args)
    except ImportError as error:
        parser.exit(1, f'Missing dependency: {error}\nRun: python -m pip install chromadb==1.5.9\n')
    except Exception as error:
        parser.exit(1, f'Error: {error}\n')


if __name__ == '__main__':
    main()
