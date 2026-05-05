# Ollama setup for GRAP-Q

GRAP-Q uses [Ollama](https://ollama.com/) as the local LLM backend for the
patching agent (and optionally for query rewriting). Ollama is **not required**
for the offline baselines (`baselines/qchecker.py`,
`baselines/rule_based_apr.py`) or for the statistical tests on pre-computed
results.

## 1. Install Ollama

### macOS / Windows
Download the installer from <https://ollama.com/download>, run it, and Ollama
will auto-start on login.

### Linux
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### Verify
```bash
ollama --version
# should print e.g. 'ollama version 0.11.10'
curl -s http://localhost:11434/api/version
# should return a JSON {"version":"..."}
```

## 2. Pull the required models

GRAP-Q uses two Ollama models by default:

| Purpose | Model name | Approx. size |
|---|---|---|
| Patch generation | `qwen2.5-coder:14b-instruct` | ~9 GB |
| Query rewriting (optional) | `llama3.1:8b` | ~5 GB |

```bash
ollama pull qwen2.5-coder:14b-instruct
ollama pull llama3.1:8b
```

You can list the models currently installed with `ollama list`.

## 3. Hardware requirements

The defaults match Table 4 of the paper:

| Component | Minimum | Recommended |
|---|---|---|
| RAM | 16 GB | 32 GB |
| GPU VRAM | optional | 12+ GB (runs on CPU if absent, much slower) |
| Disk | 20 GB free | 30 GB free |

Quantized variants (`:q4_K_M`, `:q5_K_M`) fit on smaller GPUs — override
via the environment variables below.

## 4. Environment variables

All Ollama-related settings are controlled via environment variables so you
never have to edit source files:

| Variable | Default | Meaning |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama HTTP endpoint |
| `OLLAMA_MODEL_PATCH` | `qwen2.5-coder:14b-instruct` | Model for the patcher |
| `OLLAMA_MODEL_REWRITE` | `llama3.1:8b` | Model for query rewriting |
| `NUM_CTX_PATCH` | `12288` | Context window for patching |
| `NUM_CTX_REWRITE` | `8192` | Context window for rewriting |
| `TEMP_PATCH` | `0.0` | Temperature for patching (deterministic) |
| `TEMP_REWRITE` | `0.2` | Temperature for rewriting |

Example: use a lighter, quantized model on a laptop GPU:

```bash
export OLLAMA_MODEL_PATCH=qwen2.5-coder:7b-instruct-q4_K_M
ollama pull "$OLLAMA_MODEL_PATCH"
python scripts/run_grap4q.py --mode test --splits experiments/splits_70_15_15.json
```

## 5. Troubleshooting

**`RuntimeError: Ollama not reachable: ...`**
The HTTP API and the CLI both failed. Check:
1. `curl http://localhost:11434/api/version` — if this fails, Ollama isn't running.
   Start it with `ollama serve &` on Linux, or from the menu-bar app on macOS/Windows.
2. `ollama list` — did you actually pull the model named in `OLLAMA_MODEL_PATCH`?
3. Firewall rules on `127.0.0.1:11434`.

**`ConnectionResetError` during long runs**
Model inference exceeded Ollama's default 5-minute idle timeout. Increase
with `OLLAMA_KEEP_ALIVE=30m ollama serve`.

**Out of memory on GPU**
Try a smaller/quantized model, or force CPU with `OLLAMA_NUM_GPU=0 ollama serve`.

**Very slow inference (>60 s per case)**
Expected on CPU-only hardware; GRAP-Q runs ~130 s/case on the paper's
Intel Ultra 9 185H + RTX 4070. For a fair vs slow comparison, use the
`scripts/run_purellm.py` baseline at the same hardware settings.
