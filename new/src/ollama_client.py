"""Thin Ollama client — HTTP primary, CLI fallback.

Environment variables honored:
    OLLAMA_BASE_URL        default http://localhost:11434
    OLLAMA_MODEL_REWRITE   default llama3.1:8b
    OLLAMA_MODEL_PATCH     default qwen2.5-coder:14b-instruct
"""
from __future__ import annotations

import json
import os
import re
import subprocess

import requests

OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
MODEL_REWRITE = os.environ.get("OLLAMA_MODEL_REWRITE", "llama3.1:8b")
MODEL_PATCH = os.environ.get("OLLAMA_MODEL_PATCH", "qwen2.5-coder:14b-instruct")
NUM_CTX_REWRITE = int(os.environ.get("NUM_CTX_REWRITE", "8192"))
NUM_CTX_PATCH = int(os.environ.get("NUM_CTX_PATCH", "12288"))
TEMP_REWRITE = float(os.environ.get("TEMP_REWRITE", "0.2"))
TEMP_PATCH = float(os.environ.get("TEMP_PATCH", "0.0"))
ALLOW_CLI_FALLBACK = True


def _to_prompt(msgs: list[dict]) -> tuple[str, str]:
    system: list[str] = []
    convo: list[str] = []
    for m in msgs:
        role = (m.get("role") or "user").lower()
        content = m.get("content") or ""
        if role == "system":
            system.append(content.strip())
        elif role == "user":
            convo.append(f"USER:\n{content}\n")
        else:
            convo.append(f"ASSISTANT:\n{content}\n")
    return "\n".join(system).strip(), "".join(convo) + "ASSISTANT:\n"


def _http_json(url: str, payload: dict, timeout: int = 180) -> dict:
    r = requests.post(url, json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _have_cli() -> bool:
    try:
        return subprocess.run(["ollama", "--version"],
                              capture_output=True, timeout=5).returncode == 0
    except Exception:
        return False


def _cli_chat(msgs: list[dict], *, model: str, temperature: float,
              num_ctx: int, timeout: int = 180) -> str:
    _sys, prompt = _to_prompt(msgs)
    env = os.environ.copy()
    env["OLLAMA_NUM_CTX"] = str(num_ctx)
    p = subprocess.run(["ollama", "run", model, prompt],
                       text=True, capture_output=True, timeout=timeout, env=env)
    if p.returncode != 0:
        raise RuntimeError(p.stderr)
    return p.stdout.strip()


def ollama_chat(msgs: list[dict], *, model: str, temperature: float,
                num_ctx: int, timeout: int = 180) -> str:
    """Chat with Ollama via HTTP API, falling back to generate API then CLI."""
    # 1. Chat API
    try:
        data = _http_json(f"{OLLAMA_URL}/api/chat", {
            "model": model, "messages": msgs, "stream": False,
            "options": {"temperature": temperature, "num_ctx": num_ctx},
        }, timeout=timeout)
        return (data.get("message", {}).get("content")
                or data.get("response", "")
                or "".join(m.get("content", "") for m in data.get("messages", [])))
    except Exception:
        pass
    # 2. Generate API (older)
    try:
        sys_txt, prompt = _to_prompt(msgs)
        payload = {
            "model": model, "prompt": prompt, "stream": False,
            "options": {"temperature": temperature, "num_ctx": num_ctx},
        }
        if sys_txt:
            payload["system"] = sys_txt
        data = _http_json(f"{OLLAMA_URL}/api/generate", payload, timeout=timeout)
        return data.get("response", "")
    except Exception:
        pass
    # 3. CLI
    if ALLOW_CLI_FALLBACK and _have_cli():
        return _cli_chat(msgs, model=model, temperature=temperature,
                         num_ctx=num_ctx, timeout=timeout)
    raise RuntimeError(
        "Ollama not reachable: HTTP chat/generate APIs failed and CLI not found. "
        "See docs/ollama_setup.md for install instructions."
    )


def extract_json(s: str) -> dict:
    """Pull JSON out of a model reply, tolerating ```json fences."""
    m = re.search(r"```json\s*(\{.*?\})\s*```", s, re.S)
    raw = m.group(1) if m else s.strip()
    return json.loads(raw)
