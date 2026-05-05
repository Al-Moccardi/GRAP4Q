"""Diagnose ONE case under ONE variant by capturing every step of the
request/response cycle. Use when the ablation runner produces empty
edits and you need to know whether the issue is:

  * Context overflow (prompt longer than NUM_CTX_PATCH)
  * Malformed JSON output that extract_json can't recover
  * Real model refusal (well-formed JSON with edits=[])
  * Some other Ollama error

Usage:
    python -m ablation.scripts.diagnose_one_case \\
        --case StackExchange/10 \\
        --variant v2 \\
        --splits experiments/splits_75_25_5.json

The script does NOT touch the runner. It loads donors and builds the
per-case index exactly the way the orchestrator does, then calls the
variant message builder, fires one Ollama request, and prints
everything.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from src.ollama_client import (
    MODEL_PATCH, NUM_CTX_PATCH, TEMP_PATCH, extract_json, ollama_chat)
from src.patching.agent import AgentConfig, select_fn
from src.retrieval import (
    CrossEncoderReranker, HybridIndex, apply_rerank, apply_syntax_prior,
    focus_span)
from src.retrieval.bm25 import quantum_boost_map
from src.retrieval.chunkers import WindowChunker
from src.utils import safe_read, top_tokens_query_from_text

from ablation.agent_variant import pick_donor_exemplars
from ablation.prompts.variants import (
    USES_DONOR_EXEMPLARS, VARIANTS,
    build_messages_v1, build_messages_v2,
    build_messages_v3, build_messages_v4)


def _load_donors(splits_path: Path, db_root: Path):
    doc = json.loads(splits_path.read_text(encoding="utf-8"))
    train_ids = (doc.get("train_ids")
                 or (doc.get("splits") or {}).get("train")
                 or doc.get("train") or [])
    chunker = WindowChunker(window=20, overlap=5)
    chunks = []
    for cid in train_ids:
        case_dir = db_root / str(cid)
        buggy = case_dir / "buggy.py"
        if not buggy.exists():
            continue
        try:
            cs = chunker.chunk_file(case_dir=case_dir, file_path=buggy,
                                    repo_key=f"donor:{cid}")
            chunks.extend(cs if isinstance(cs, list) else list(cs))
        except Exception:
            pass
    return chunks


def _build_per_case_index(buggy_path: Path, donor_chunks):
    src = buggy_path.read_text(encoding="utf-8")
    n_lines = max(1, len(src.splitlines()))
    win = max(6, min(40, n_lines // 3 + 2))
    overlap = max(2, win // 4)
    chunker = WindowChunker(window=win, overlap=overlap)
    own = []
    with tempfile.TemporaryDirectory(prefix="grap4q_diag_") as d:
        case_dir = Path(d)
        fp = case_dir / "buggy.py"
        fp.write_text(src, encoding="utf-8")
        cs = chunker.chunk_file(case_dir=case_dir, file_path=fp,
                                repo_key="query")
        own = list(cs) if not isinstance(cs, list) else cs
    idx = HybridIndex(boost_map=quantum_boost_map())
    idx.build(list(own) + list(donor_chunks))
    return idx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True,
                    help="Case id, e.g. 'StackExchange/10'.")
    ap.add_argument("--variant", required=True, choices=VARIANTS)
    ap.add_argument("--db-root", default="data/bugs4q/Bugs4Q-Database",
                    type=Path)
    ap.add_argument("--splits", default="experiments/splits_75_25_5.json",
                    type=Path)
    ap.add_argument("--config-name",
                    default="WIN_base__hint__balanced__rerank")
    args = ap.parse_args()

    case_dir = args.db_root / args.case
    buggy_path = case_dir / "buggy.py"
    if not buggy_path.exists():
        raise SystemExit(f"buggy.py not found at {buggy_path}")

    print("=" * 70)
    print(f"DIAGNOSTIC: case={args.case} variant={args.variant}")
    print("=" * 70)
    print(f"MODEL_PATCH:   {MODEL_PATCH}")
    print(f"NUM_CTX_PATCH: {NUM_CTX_PATCH}")
    print(f"TEMP_PATCH:    {TEMP_PATCH}")
    print()

    src = safe_read(buggy_path)
    print(f"Source: {len(src)} chars, {len(src.splitlines())} lines")
    print()

    # Build retrieval pipeline like the orchestrator does.
    donors = _load_donors(args.splits, args.db_root)
    print(f"Loaded {len(donors)} TRAIN donor chunks.")
    index = _build_per_case_index(buggy_path, donors)

    cfg = AgentConfig.from_name(args.config_name)
    seed = top_tokens_query_from_text(src, k=6)
    q = (seed + " cx rz dag") if cfg.use_hints else seed
    pool = index.search(q, topk=max(cfg.overretrieve, 6 * cfg.topk))

    rr = None
    if cfg.use_rerank:
        try:
            rr = CrossEncoderReranker()
        except Exception as e:
            print(f"Reranker unavailable: {e}")
    pool = apply_rerank(q, pool, rr)
    if cfg.use_syntax_prior:
        pool = apply_syntax_prior(pool)
    print(f"Pool size after rerank+prior: {len(pool)}")

    donor_exemplars = []
    if USES_DONOR_EXEMPLARS.get(args.variant, False):
        donor_exemplars = pick_donor_exemplars(pool, args.db_root, k=2)
        print(f"Selected {len(donor_exemplars)} donor exemplar(s) for "
              f"V{args.variant[1:]}.")

    selected = select_fn(cfg.selector)(pool, cfg.topk)
    own_selected = [h for h in selected
                    if not str(h.get("file", "")).startswith("donor:")]
    if len(own_selected) < cfg.topk:
        own_pool = [h for h in pool
                    if not str(h.get("file", "")).startswith("donor:")]
        own_selected = own_pool[:cfg.topk]
    selected = own_selected
    print(f"Selected {len(selected)} own-file span(s) for focus.")

    allowed: list[tuple[int, int]] = []
    focused_ctx: list[dict] = []
    src_lines = src.splitlines()
    for i, h in enumerate(selected, start=1):
        lo, hi, _ = focus_span(h, src)
        allowed.append((lo, hi))
        focused_ctx.append({
            "rank": i, "file": h["file"], "span": f"{lo}-{hi}",
            "symbol": h["symbol"],
            "code": "\n".join(src_lines[lo - 1:hi]),
        })
    print(f"Allowed ranges: {allowed}")
    print()

    builders = {
        "v1": lambda: build_messages_v1(args.case, focused_ctx, allowed),
        "v2": lambda: build_messages_v2(args.case, focused_ctx, allowed,
                                        buggy_source=src),
        "v3": lambda: build_messages_v3(args.case, focused_ctx, allowed,
                                        buggy_source=src,
                                        donor_exemplars=donor_exemplars),
        "v4": lambda: build_messages_v4(args.case, focused_ctx, allowed,
                                        buggy_source=src),
    }
    msgs = builders[args.variant]()

    sys_msg = msgs[0]["content"]
    user_msg = msgs[1]["content"]
    total_chars = len(sys_msg) + len(user_msg)
    # Rough token estimate: ~4 chars per token for English, ~3 for code.
    rough_tokens = total_chars // 3

    print("PROMPT SIZING")
    print("-" * 70)
    print(f"  System message: {len(sys_msg):,} chars")
    print(f"  User message:   {len(user_msg):,} chars")
    print(f"  TOTAL:          {total_chars:,} chars")
    print(f"  Rough tokens estimate (chars/3): {rough_tokens:,}")
    print(f"  Model context budget: {NUM_CTX_PATCH:,} tokens")
    over = rough_tokens > NUM_CTX_PATCH
    over_marker = "YES \u26a0" if over else "no"
    print(f"  OVER BUDGET? {over_marker}")
    print()

    print("SYSTEM MESSAGE (full)")
    print("-" * 70)
    print(sys_msg)
    print()
    print("USER MESSAGE (full)")
    print("-" * 70)
    if len(user_msg) > 4000:
        print(user_msg[:2000])
        print(f"\n... [{len(user_msg) - 4000} chars elided] ...\n")
        print(user_msg[-2000:])
    else:
        print(user_msg)
    print()

    print("CALLING OLLAMA ...")
    print("-" * 70)
    import time
    t0 = time.time()
    try:
        raw = ollama_chat(msgs, model=MODEL_PATCH,
                          temperature=TEMP_PATCH, num_ctx=NUM_CTX_PATCH)
        elapsed = time.time() - t0
        print(f"Latency: {elapsed:.1f}s")
        print(f"Response: {len(raw):,} chars")
    except Exception as e:
        elapsed = time.time() - t0
        print(f"Latency: {elapsed:.1f}s")
        print(f"OLLAMA EXCEPTION: {type(e).__name__}: {e}")
        return
    print()

    print("RAW LLM RESPONSE (full)")
    print("-" * 70)
    print(raw if raw else "(empty string)")
    print()

    print("PARSE RESULT")
    print("-" * 70)
    try:
        parsed = extract_json(raw)
        print("extract_json: SUCCESS")
        print(f"  keys: {sorted(parsed.keys()) if isinstance(parsed, dict) else type(parsed).__name__}")
        edits = parsed.get("edits") if isinstance(parsed, dict) else None
        if isinstance(edits, list):
            print(f"  edits count: {len(edits)}")
            for i, e in enumerate(edits, start=1):
                if isinstance(e, dict):
                    print(f"    edit {i}: file={e.get('file')!r} "
                          f"start={e.get('start')} end={e.get('end')} "
                          f"replacement_chars="
                          f"{len(str(e.get('replacement', '')))}")
        else:
            print(f"  edits is not a list: {type(edits).__name__}")
        rationale = parsed.get("rationale") if isinstance(parsed, dict) else None
        if isinstance(rationale, str):
            preview = rationale[:200] + ("..." if len(rationale) > 200 else "")
            print(f"  rationale ({len(rationale)} chars): {preview!r}")
    except Exception as e:
        print(f"extract_json: FAILED with {type(e).__name__}: {e}")
        # Try to find any JSON-looking substring.
        import re as _re
        m = _re.search(r"\{[^}]*\}", raw)
        if m:
            print(f"  First {{...}} substring found at offset {m.start()}: "
                  f"{m.group(0)[:200]!r}")
        else:
            print("  No JSON-like substring found in response.")

    print()
    print("=" * 70)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
