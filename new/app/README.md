# GRAP-Q interactive app

This folder hosts a small Gradio application that exposes the GRAP-Q
pipeline interactively: a user pastes buggy Qiskit code, and the app
runs the exact same stages described in the paper (query → BM25 →
cross-encoder → selector → span focusing → Ollama patch with
guardrail refinement → CompositeGuard) and renders every intermediate
artefact.

## No duplication by design

This folder contains only two Python modules:

| File | Role |
|---|---|
| `pipeline.py` | Orchestration wrapper. Delegates every stage to a function in `src/`. About 200 lines, no retrieval, chunking, BM25, re-ranking, selector, span focusing, guardrail, or Ollama logic lives here. |
| `server.py` | Gradio UI and HTML rendering only. Imports `run_interactive` from `pipeline.py` and nothing else. |

If you refactor `src/`, the app keeps working as long as the symbols
imported at the top of `pipeline.py` still exist.

## Prerequisites

1. Your `src/` package and its dependencies already installed
   (`pip install -r requirements.txt`). No new runtime dependencies
   are introduced by the app beyond Gradio itself.
2. Gradio:
   ```bash
   pip install gradio
   ```
3. A local Ollama daemon running the model used in the paper:
   ```bash
   ollama serve &
   ollama pull qwen2.5-coder:14b-instruct
   ```
   `src/ollama_client.py` already targets this daemon; the app does
   not need separate configuration.

## Run locally

From the repository root:

```bash
python -m app.server
# opens http://127.0.0.1:7860
```

## Deploy on a server

Bind to all interfaces and pick a port:

```bash
GRAP4Q_HOST=0.0.0.0 GRAP4Q_PORT=7860 python -m app.server
```

Typical deployment topologies:

- **Single-host**: Ollama and the app on the same machine, GPU
  attached. This is what we recommend for an average evaluator: one
  command, everything runs locally, Ollama auto-connects.
- **Split hosts**: the app on a small CPU VM, Ollama on a separate
  GPU node. Set `OLLAMA_HOST=http://<gpu-host>:11434` in the
  environment where you launch `python -m app.server`; this variable
  is read by `src/ollama_client.py`, which the app uses transitively,
  so no app code change is needed.

### Behind a reverse proxy

Gradio runs on the port you give it and exposes `/` plus a WebSocket
endpoint. An nginx snippet:

```nginx
location /grap4q/ {
    proxy_pass http://127.0.0.1:7860/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
}
```

### Public Gradio link (for a demo)

```bash
GRAP4Q_SHARE=true python -m app.server
```

Gradio prints a temporary `https://*.gradio.live` URL. Useful for a
reviewer screenshot session; not intended for production.

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `GRAP4Q_HOST` | `127.0.0.1` | bind address |
| `GRAP4Q_PORT` | `7860` | port |
| `GRAP4Q_SHARE` | `false` | `true` enables the public gradio.live tunnel |
| `GRAP4Q_CONFIG` | `WIN_base__hint__balanced__rerank` | pipeline configuration string (matches the paper's selected config) |
| `OLLAMA_HOST` | read by `src/ollama_client` | Ollama daemon URL |

## What reviewers see

A two-column screen. Left side: the buggy Python cell (editable,
syntax-highlighted), a dropdown of four representative Bugs4Q
examples, a "Pipeline configuration" accordion, and two buttons
(**Run GRAP-Q** / **Verify (py\_compile)**).

Right side: the pipeline trace (retrieval query, pool size, the
top-K selected spans with their BM25 and re-rank scores, the
allowed edit region, the LLM rationale, latency + refinement
count); a colour-coded diff; the five CompositeGuard verdicts
(EditRegionOK, ASTSyntaxOK, PassInterfaceOK,
QuantumRegisterSanityOK, QubitOrderHeuristicOK); and the final
patched code in an editable cell the user can copy directly.

The **Verify** button runs `python -m py_compile` on whatever is in
the patched-code cell, so a reviewer can hand-edit the patch and
immediately re-check syntactic validity.
