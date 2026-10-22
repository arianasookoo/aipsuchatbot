#!/usr/bin/env bash
# One-time setup on macOS / Linux: venv, deps, index, model choice, .env. Safe to re-run.
# Usage (from the repo folder):  bash setup.sh            # picks a model by hardware
#                                 bash setup.sh gemma3:27b  # or name the Ollama model yourself (GB10 / big GPU)
set -e
cd "$(dirname "$0")"

[ -x .venv/bin/python ] || python3 -m venv .venv
py=.venv/bin/python
$py -m pip install --quiet chromadb==1.5.9 -r requirements-dev.txt
[ -f vector_db/active_index.json ] || $py vector_search.py index chunks.json
$py answer.py --selfcheck
[ -f .env ] || cp .env.example .env

has_gpu=0
if command -v nvidia-smi >/dev/null 2>&1; then has_gpu=1; fi
# Apple silicon with >= 16 GB handles the 12B model
if [ "$(uname -s)" = Darwin ] && [ "$(uname -m)" = arm64 ] && [ "$(sysctl -n hw.memsize)" -ge 17179869184 ]; then has_gpu=1; fi

if command -v ollama >/dev/null 2>&1; then
  if ! grep -q '^NAVIGATOR_LLM_MODEL=' .env; then
    if [ -n "$1" ]; then model=$1; elif [ $has_gpu = 1 ]; then model=gemma3:12b; else model=gemma3:4b; fi
    echo "Ollama found. Pulling $model (gpu-class machine: $has_gpu)..."
    ollama pull "$model"
    printf '\nNAVIGATOR_LLM_BASE=http://127.0.0.1:11434/v1\nNAVIGATOR_LLM_KEY=ollama\nNAVIGATOR_LLM_MODEL=%s\n' "$model" >> .env
    [ $has_gpu = 1 ] || echo "No GPU: gemma3:4b runs on CPU, ~15-25 s per answer. Its citation rate is not measured yet (run eval/run_answers.py then eval/claims.py to measure)."
  fi
elif ! grep -q '^NVIDIA_API_KEY=.' .env; then
  echo "No Ollama installed. Either install it from https://ollama.com and re-run, or put a free key from https://build.nvidia.com into .env as NVIDIA_API_KEY=..."
fi

echo
echo "Setup done. Start the server with:"
echo "    .venv/bin/python serve.py"
echo "then open http://localhost:8008/app.html"
