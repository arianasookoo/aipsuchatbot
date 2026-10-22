FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir chromadb==1.5.9

COPY . .

RUN python vector_search.py index chunks.json

# Chat server: docker run -p 8000:8000 --entrypoint python <image> server.py --host 0.0.0.0
EXPOSE 8000

ENTRYPOINT ["python", "hybrid_search.py"]
