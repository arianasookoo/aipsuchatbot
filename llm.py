"""Minimal OpenAI-compatible chat client. Standard library only.

Defaults to NVIDIA's free endpoint for development. Point it at a local model
(vLLM / Ollama on the sponsor's GB10) with two environment variables and no
code change:

    NAVIGATOR_LLM_BASE=http://gb10:8000/v1   NAVIGATOR_LLM_KEY=anything
    NAVIGATOR_LLM_MODEL=qwen3-8b

Honest limitation: model ids on the NVIDIA endpoint get renamed to dated
variants, so the default is resolved by prefix from /v1/models at first call.
A local server must set NAVIGATOR_LLM_MODEL explicitly.
"""
import json
import os
import time
import urllib.error
import urllib.request

BASE = os.environ.get("NAVIGATOR_LLM_BASE", "https://integrate.api.nvidia.com/v1").rstrip("/")
KEY = os.environ.get("NAVIGATOR_LLM_KEY") or os.environ.get("NVIDIA_API_KEY", "")
# kimi-k3 answered in ~3 s on 2026-10-14; deepseek-v4.1-flash hung, kimi-k2.6 and the nemotron ids 404'd.
MODEL_PREFIX = os.environ.get("NAVIGATOR_LLM_MODEL", "moonshotai/kimi-k3")
_model = None


def _request(path, payload=None, timeout=120):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, method="POST" if data else "GET",
                                 headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 529) and attempt < 3:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"LLM HTTP {e.code}: {e.read()[:300]!r}") from None


def model():
    """Newest model id matching MODEL_PREFIX (exact id wins)."""
    global _model
    if _model:
        return _model
    ids = [m["id"] for m in _request("/models")["data"]]
    if MODEL_PREFIX in ids:
        _model = MODEL_PREFIX
    else:
        hits = sorted(i for i in ids if i.startswith(MODEL_PREFIX))
        if not hits:
            raise RuntimeError(f"no model matches prefix {MODEL_PREFIX!r}; set NAVIGATOR_LLM_MODEL")
        _model = hits[-1]
    return _model


# Reasoning models think for 30-40 s before answering a 1,500-token evidence prompt; with thinking
# off, kimi-k3 answers in ~3.5 s (measured 2026-10-14). Set NAVIGATOR_LLM_THINKING=1 to leave it on.
NO_THINK = {} if os.environ.get("NAVIGATOR_LLM_THINKING") == "1" else {"thinking": {"type": "disabled"}}


def chat(messages, temperature=0.0, max_tokens=1500):
    """messages: [{"role": "system"|"user"|"assistant", "content": str}] -> reply text."""
    if not KEY:
        raise RuntimeError("set NVIDIA_API_KEY or NAVIGATOR_LLM_KEY")
    body = {"model": model(), "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    try:
        out = _request("/chat/completions", {**body, **NO_THINK})
    except RuntimeError as e:  # a local server may reject the vendor-specific field
        if "HTTP 400" not in str(e) or not NO_THINK:
            raise
        out = _request("/chat/completions", body)
    return (out["choices"][0]["message"].get("content") or "").strip()


if __name__ == "__main__":
    print("model:", model())
    print(chat([{"role": "user", "content": "Reply with the single word READY."}], max_tokens=5))
