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
- A browser chat widget connected to a local retrieval API (`server.py`). Replies are excerpts from the best-matching official page plus source links, not generated answers.

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
| `Dockerfile` | Builds a ready-to-run terminal search image, including the local vector index. |
| `.dockerignore` | Keeps local environments, databases, credentials, and Git files out of the Docker image. |
| `server.py` | Standard-library web server that hosts the chat page and exposes hybrid search at `POST /api/chat`. |
| `chatbot.js` | Dependency-free popout chat widget. It calls the backend through its `onMessage` option. |
| `chatbot.css` | Chat widget styles. |
| `index.html` | Demonstration page with the chat widget wired to `/api/chat`. |

## Quick start with Docker

Docker is the simplest way to run the current terminal search. It installs the
Python dependencies, downloads the MiniLM model, and builds the Chroma index
inside the image.

### 1. Install Docker Desktop

Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) and
start it. Wait until Docker reports that it is running.

Verify the installation in a new terminal window:

```bash
docker --version
docker info
```

The first build needs an internet connection and several gigabytes of free disk
space. No API key is required.

### 2. Get the project ready

For a new checkout, clone the repository and enter it:

```bash
git clone https://github.com/arianasookoo/aipsuchatbot.git
cd aipsuchatbot
```

If the repository is already on your computer, enter it and pull the latest changes:

```bash
cd aipsuchatbot
git pull
```

The cleaned pages and `chunks.json` are already committed. You do not need to
run the web scraper or data-cleaning scripts before building the image.

### 3. Build the image

```bash
docker build -t aipsu-chatbot .
```

The first build takes longer because Docker installs Chroma, downloads MiniLM,
and creates the vector index. Later builds can reuse cached layers when the
dependencies have not changed.

### 4. Search from the terminal

Pass one question to the container:

```bash
docker run --rm aipsu-chatbot "How can my company sponsor a capstone project?"
```

Other examples:

```bash
docker run --rm aipsu-chatbot "How can an employer post jobs for engineering students?"
docker run --rm aipsu-chatbot "Who do I contact about a research partnership?"
```

Return only three source pages:

```bash
docker run --rm aipsu-chatbot --top-k 3 "How can my company sponsor a capstone project?"
```

Return structured JSON:

```bash
docker run --rm aipsu-chatbot --json "How can my company sponsor a capstone project?"
```

Each run prints ranked evidence passages and their official source URLs. It does
not yet generate a conversational answer.

### 5. Run the chat interface

Start the web server inside the container and publish its port:

```bash
docker run --rm -p 8000:8000 --entrypoint python aipsu-chatbot server.py --host 0.0.0.0
```

Open <http://localhost:8000> and ask a question in the chat panel. Press
`Ctrl+C` to stop the server.

### 6. Rebuild after changes

Rebuild the image after changing the code or `chunks.json`:

```bash
docker build -t aipsu-chatbot .
```

### Docker troubleshooting

- `zsh: command not found: docker`: install Docker Desktop, then open a new terminal.
- `failed to connect to the docker API`: start or restart Docker Desktop and wait for it to finish loading.
- `Input/output error` during installation: free disk space, restart Docker Desktop, and retry the build.

## Run without Docker (optional)

Requirements:

- Python 3.9 or newer
- Internet access on the first indexing run
- `chromadb==1.5.9`

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows, activate it with:

```powershell
.venv\Scripts\activate
```

Install the vector database dependency:

```bash
python -m pip install chromadb==1.5.9
```

The embedding model downloads automatically during the first indexing run.

## Build the local retrieval pipeline

The committed `chunks.json` is ready to index. Run this command from the
repository root:

```bash
python vector_search.py index chunks.json
```

Only regenerate the cleaned data and chunks after changing the source scrape:

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

## Chat interface

Start the backend after building `vector_db/`:

```bash
python server.py
```

Then open <http://127.0.0.1:8000>. Opening `index.html` directly from disk shows the
widget, but it cannot reach the backend. Options: `--port`, `--host`, `--db`, and
`--top-k` (number of source pages per reply, default 3).

The server loads MiniLM once at startup and exposes:

- `GET /api/health` returns `{"status": "ok"}`.
- `POST /api/chat` with `{"message": "How can my company sponsor a capstone project?"}`
  returns `reply` (an excerpt from the best-ranked page), `sources` (`title` and
  `url` for each page) and `passages` (the full ranked evidence). Invalid or overlong
  questions return status 400 with an `error` message.

The widget exposes `window.ChatbotPopout`. `onMessage` may return a string or
`{ text, sources }`; sources are shown as links under the reply:

```html
<link rel="stylesheet" href="chatbot.css">
<script src="chatbot.js"></script>
<script>
  ChatbotPopout.init({
    title: "Assistant",
    onMessage: async (text, history) => {
      const r = await fetch("/api/chat", { method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }) });
      const data = await r.json();
      return r.ok ? { text: data.reply, sources: data.sources } : data.error;
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
- There is no answer-generation service. Chat replies are retrieved excerpts, which can start or end mid-sentence.
- `server.py` is a development server with no authentication or rate limiting. Do not expose it publicly as is.

## Suggested next work

1. Improve evidence assembly by allowing multiple relevant passages from a strong page, adding neighboring passages when useful, and removing overlapping duplicates.
2. Complete a documented spot check of at least 30 chunks.
3. Add the remaining source and operational metadata fields.
4. Build a labeled retrieval evaluation set with expected pages and required facts, including questions the indexed sources cannot answer.
5. Add grounded answer generation using a model such as Qwen3-8B. Supply only retrieved evidence, require official-source citations, and explicitly decline unsupported questions.
6. Add answer generation to the `/api/chat` endpoint in `server.py`.
7. Expand the Docker workflow for the future backend, data refresh, recovery, and production deployment.

## Generated and sensitive files

Do not commit local environments, generated databases, or credentials. The repository ignores:

- `.venv/`
- `vector_db/`
- `.env`
- `__pycache__/`
- `*.pyc`

Store future API keys only in `.env` or another approved secret-management system. Never place keys directly in source code or commit them to Git.
