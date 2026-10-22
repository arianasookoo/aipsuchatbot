FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir chromadb==1.5.9

COPY . .

RUN python vector_search.py index chunks.json

ENTRYPOINT ["python", "hybrid_search.py"]
