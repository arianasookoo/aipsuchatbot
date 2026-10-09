# AI Powered Penn State Engineering Engagement Navigator

This repository contains a proof-of-concept retrieval pipeline and chat interface for the Penn State Engineering Engagement Navigator. The project is intended to help external organizations find official Penn State resources for activities such as recruiting, research partnerships, capstone sponsorship, student organizations, events, giving, and employee education.

The current implementation can clean scraped webpages, create overlapping text chunks, build a local vector index, and retrieve relevant passages with their official source URLs. It does **not** yet generate final chatbot answers.

## Current status

The repository currently includes:

- 96 scraped Penn State Engineering pages.
- A repeatable cleaning step that removes recognized navigation and footer boilerplate while preserving the original scrape.
- 94 unique cleaned documents after exact-text deduplication.
- 324 overlapping source chunks of approximately 200 words.
- A local Chroma vector database using the `all-MiniLM-L6-v2` embedding model.
- Additional model-aware splitting that produces 577 indexed passages from the 324 source chunks.
- Semantic vector search and hybrid keyword/semantic retrieval.
- A standalone browser chat widget whose responses are still placeholders.

Cleaning reduces the source dataset from 74,524 words to 48,042 words. These figures describe the currently committed generated files.

## Pipeline

```text
multi_seed_scrape_data.json
        |
        v
clean_scrape.py
        |
        v
cleaned_scrape_data.json
        |
        v
prepare_chunks.py
        |
        v
chunks.json
        |
        v
vector_search.py index
        |
        v
local Chroma database (vector_db/)
        |
        v
hybrid_search.py
        |
        v
ranked evidence passages with source URLs
```

MiniLM converts passages and questions into numerical embeddings. Chroma stores those embeddings locally and performs similarity search. The hybrid search combines semantic similarity with keyword matching through reciprocal rank fusion.

Neither MiniLM nor Chroma writes chatbot answers. A later answer-generation service can give the retrieved evidence to a language model, such as Qwen3-8B, with instructions to cite the official sources and decline to answer when the evidence is insufficient.

## Repository files

| File | Purpose |
| --- | --- |
| `web-scraper.py` | Crawls the configured public Penn State seed domains and produces the original scrape. |
| `multi_seed_scrape_data.json` | Original scraped pages with `url`, `title`, and flattened `content`. Keep this file unchanged when cleaning. |
| `clean_scrape.py` | Removes recognized site navigation and footer boilerplate and records a cleaning audit for each page. |
| `cleaned_scrape_data.json` | Generated cleaned pages. |
| `prepare_chunks.py` | Validates pages, removes exact duplicate page text, creates overlapping chunks, and assigns content-based IDs. |
| `chunks.json` | Generated chunks with text, IDs, hashes, word positions, titles, URLs, and source provenance. |
| `vector_search.py` | Splits chunks to fit MiniLM, creates embeddings, builds a persistent Chroma collection, and performs semantic search. |
| `hybrid_search.py` | Combines semantic results with keyword relevance and returns one ranked passage per matching document. |
| `chatbot.js` | Dependency-free popout chat widget. It can call a future backend through its `onMessage` option. |
| `chatbot.css` | Chat widget styles. |
| `index.html` | Demonstration page for the chat widget. |

## Requirements

- Python 3.9 or newer
- Internet access on the first indexing run so the MiniLM model can be downloaded
- `chromadb==1.5.9`

No API key is required for the current cleaning, indexing, or retrieval pipeline.

## Local setup

Pull the latest changes:

```bash
git pull
```

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the vector database dependency:

```bash
python -m pip install chromadb==1.5.9
```

The embedding model downloads automatically during the first indexing run.

## Build the local retrieval pipeline

Run these commands from the repository root:

```bash
python clean_scrape.py multi_seed_scrape_data.json
python prepare_chunks.py cleaned_scrape_data.json
python vector_search.py index chunks.json
```

The final command creates `vector_db/` and writes an `active_index.json` manifest inside it. Each developer builds a local copy of this directory; it is intentionally excluded from Git.

The indexer builds a new Chroma collection before making it active. If indexing fails, the previous active index remains selected. Older collections are retained locally for recovery.

## Search the data

### Hybrid search

Hybrid search is the preferred current entry point:

```bash
python hybrid_search.py "How can an employer post jobs for engineering students?"
python hybrid_search.py "How can my company sponsor a capstone project?"
python hybrid_search.py "Who do I contact about a research partnership with Penn State engineering?"
```

Return structured JSON when integrating with another service:

```bash
python hybrid_search.py --json "How can my company sponsor a capstone project?"
```

Change the number of returned pages with `--top-k`:

```bash
python hybrid_search.py --top-k 3 "How can my company sponsor a capstone project?"
```

### Semantic-only search

To inspect MiniLM/Chroma results without keyword fusion:

```bash
python vector_search.py search "How can my company sponsor a capstone project?"
```

Similarity values are ranking signals, not confidence percentages. Retrieved passages are evidence candidates and must be checked before being used to support an answer.

## Chat widget

Open `index.html` in a browser to view the current interface prototype. The widget exposes `window.ChatbotPopout`:

```html
<link rel="stylesheet" href="chatbot.css">
<script src="chatbot.js"></script>
<script>
  ChatbotPopout.init({
    title: "Assistant",
    onMessage: async (text, history) => {
      // Call the future retrieval and answer backend here.
    }
  });
</script>
```

Without `onMessage`, the widget displays a placeholder reply.

## What has been tested

Initial manual searches cover:

- Posting jobs for engineering students
- Sponsoring a capstone project
- Starting a research partnership

The job-posting and capstone tests rank the expected pages first. The research test retrieves a passage containing the research-partnership contact email. These are initial checks only, not a complete retrieval evaluation.

## Current limitations

- The original scrape contains flattened text, so lost paragraph boundaries, headings, and hyperlink relationships cannot be completely reconstructed downstream.
- Some joined words and navigation fragments remain after cleaning.
- Fixed-size chunks can begin or end partway through a sentence.
- Hybrid search returns at most one passage per document, which can omit related instructions or contact details elsewhere on the same page.
- The current metadata does not yet include all planned fields, such as engagement category, College unit, contact method, crawl timestamp, retrieval date, and active/stale status.
- Document IDs are content-derived, so changing a page's content changes its document ID.
- The local Chroma index is rebuilt rather than incrementally updated.
- There is not yet a 30-question labeled retrieval evaluation set.
- There is no answer-generation service, retrieval API, or end-to-end backend.
- The chat interface still uses placeholder behavior.

## Suggested next work

1. Improve evidence assembly by allowing multiple relevant passages from a strong page, adding neighboring passages when useful, and removing overlapping duplicates.
2. Complete a documented spot check of at least 30 chunks.
3. Add the remaining source and operational metadata fields.
4. Build a labeled retrieval evaluation set with expected pages and required facts, including questions the indexed sources cannot answer.
5. Add grounded answer generation using a model such as Qwen3-8B. Supply only retrieved evidence, require official-source citations, and explicitly decline unsupported questions.
6. Expose retrieval and answer generation through a backend API.
7. Connect the backend to the existing chat widget.
8. Add Docker deployment, refresh, recovery, and operating documentation.

## Generated and sensitive files

Do not commit local environments, generated databases, or credentials. The repository ignores:

- `.venv/`
- `vector_db/`
- `.env`
- `__pycache__/`
- `*.pyc`

Store future API keys only in `.env` or another approved secret-management system. Never place keys directly in source code or commit them to Git.
