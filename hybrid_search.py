"""Search by meaning and keywords, using your existing Chroma database.

Run: python hybrid_search.py "How can an employer post jobs for engineering students?"
Requires vector_search.py in the same folder and an existing vector_db.
This is a small-corpus baseline; it loads all passages for keyword scoring.
It returns evidence candidates, not generated answers or calibrated confidence.
"""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re
import sys
from vector_search import MODEL, embedding_tools

STOP = set('a an the how can could would should my our your their its it i we you they to of on in at for from by with and or is are be do does have has will what which please me us about'.split())


def terms(text):
    result = []
    for word in re.findall(r'[a-z0-9]+', text.lower()):
        if word in STOP:
            continue
        if len(word) > 4 and word.endswith('ies'):
            word = word[:-3] + 'y'
        elif len(word) > 3 and word.endswith('s') and not word.endswith('ss'):
            word = word[:-1]
        if len(word) > 5 and word.endswith('ing'):
            word = word[:-3]
        result.append(word)
    return result


def keyword_scores(question, documents, metadatas):
    # Weight page titles so an exact topic match helps identify the right page.
    bags = [Counter(terms(meta['title']) * 3 + terms(text))
            for text, meta in zip(documents, metadatas)]
    lengths = [sum(b.values()) for b in bags]
    average = sum(lengths) / max(len(lengths), 1) or 1
    frequency = Counter(term for bag in bags for term in bag)
    scores = []
    for bag, length in zip(bags, lengths):
        score = 0.0
        for term in set(terms(question)):
            tf = bag[term]
            if not tf:
                continue
            df = frequency[term]
            idf = math.log(1 + (len(bags) - df + 0.5) / (df + 0.5))
            score += idf * tf * 2.5 / (tf + 1.5 * (0.25 + 0.75 * length / average))
        scores.append(score)
    return scores


def retrieve(question, db, top_k=5):
    import chromadb
    manifest_path = db / 'active_index.json'
    if not manifest_path.exists():
        raise ValueError('Build the database first: python vector_search.py index chunks.json')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('embedding_model') != MODEL:
        raise ValueError('Index embedding model does not match vector_search.py.')
    if not question.strip():
        raise ValueError('Enter a question.')
    ef, tokenizer = embedding_tools()
    if len(tokenizer.encode(question).ids) > 256:
        raise ValueError('Question is too long. Please shorten it.')
    client = chromadb.PersistentClient(path=str(db.resolve()),
        settings=chromadb.Settings(anonymized_telemetry=False))
    collection = client.get_collection(manifest['collection'], embedding_function=None)
    corpus = collection.get(include=['documents', 'metadatas'])
    if not corpus['ids']:
        raise ValueError('The active database is empty.')
    lexical = keyword_scores(question, corpus['documents'], corpus['metadatas'])
    keyword_order = sorted(range(len(lexical)), key=lambda i: (-lexical[i], corpus['ids'][i]))
    vector = collection.query(query_embeddings=ef([question]),
        n_results=min(100, len(corpus['ids'])), include=['distances'])
    vector_ranks = {rid: rank for rank, rid in enumerate(vector['ids'][0], 1)}
    distances = dict(zip(vector['ids'][0], vector['distances'][0]))
    keyword_ranks = {corpus['ids'][i]: rank for rank, i in enumerate(
        [i for i in keyword_order if lexical[i] > 0][:100], 1)}
    results = []
    for i, rid in enumerate(corpus['ids']):
        vr, kr = vector_ranks.get(rid), keyword_ranks.get(rid)
        if vr is None and kr is None:
            continue
        # Reciprocal rank fusion combines ranked lists without treating their
        # different score scales as comparable. This remains a tuning baseline.
        score = (1 / (60 + vr) if vr else 0) + (1 / (60 + kr) if kr else 0)
        meta = corpus['metadatas'][i]
        results.append({'passage_id': rid, 'text': corpus['documents'][i],
            'title': meta['title'], 'sources': json.loads(meta['sources_json']),
            'fusion_score': score, 'keyword_rank': kr, 'vector_rank': vr,
            'cosine_similarity': 1 - distances[rid] if rid in distances else None,
            'document_id': meta['document_id']})
    results.sort(key=lambda r: (-r['fusion_score'], r['passage_id']))
    # Avoid spending every slot on the same page. More passages can be added
    # later when assembling the evidence for answer generation.
    selected, seen = [], set()
    for result in results:
        if result['document_id'] in seen:
            continue
        selected.append(result)
        seen.add(result['document_id'])
        if len(selected) == top_k:
            break
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('question')
    parser.add_argument('--db', type=Path, default=Path('vector_db'))
    parser.add_argument('--top-k', type=int, default=5)
    parser.add_argument('--json', action='store_true', help='Print structured results')
    args = parser.parse_args()
    if args.top_k < 1:
        parser.error('--top-k must be positive.')
    try:
        results = retrieve(args.question, args.db, args.top_k)
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
            return
        for i, result in enumerate(results, 1):
            print(f'\nRESULT {i}: {result["title"]}')
            print(f'Keyword rank: {result["keyword_rank"]}; meaning rank: {result["vector_rank"]}')
            for source in result['sources']:
                print(f'Source: {source["url"]}')
            print(result['text'])
        print('\nEvidence candidates only. Review support before generating an answer.')
    except Exception as error:
        parser.exit(1, f'Error: {error}\n')


if __name__ == '__main__':
    main()
