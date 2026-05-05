#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Inference pipeline for GRAP-Q vs Pure-LLM

Modes:
  --mode diagnostic : compare GRAP-Q vs Pure-LLM on TEST split, save plots + timing
  --mode test       : GRAP-Q only on TEST split, save patched .py + conversational rationale
  --mode single     : patch a single .py (optionally score vs gold)

Deterministic split:
  Reuses/creates results/grap_vs_llm_deep/splits_70_25_5.json (same set across modes)

Leak-free donor policy:
  - Retrieval index is built from buggy.py for all cases (no labels).
  - Cross-case donors allowed ONLY from TRAIN (not from VAL/TEST).
  - Optionally exclude TRAIN donor windows overlapping their own gold-changed lines.

Requires:
  pip install pandas numpy matplotlib sentence-transformers requests tqdm
"""

import os, re, json, math, difflib, shutil, subprocess, sys, ast, random, time
import numpy as np, pandas as pd, matplotlib.pyplot as plt
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any
from hashlib import md5
from tqdm import tqdm

# ------------------------------- CLI -------------------------------
import argparse

def build_argparser():
    p = argparse.ArgumentParser(description="GRAP-Q inference")
    p.add_argument("--mode", choices=["diagnostic","test","single"], required=True,
                   help="diagnostic: compare GRAP vs LLM on TEST (plots+timing). test: GRAP on TEST (patch+talk). single: one file.")
    p.add_argument("--single_file", type=str, default=None,
                   help="(single) path to buggy .py file")
    p.add_argument("--gold_fixed", type=str, default=None,
                   help="(single optional) gold fixed file for scoring")
    p.add_argument("--best_config", type=str, default="results/qeval_ablation_plus/best_config.txt",
                   help="path to BEST_CONFIG.txt produced by ablation")
    p.add_argument("--db_root", type=str, default="data/bugs4q/Bugs4Q-Database",
                   help="dataset root")
    p.add_argument("--out_dir", type=str, default="results/infer",
                   help="where to save artifacts")
    p.add_argument("--work_dir", type=str, default=".work/infer",
                   help="scratch dir")
    p.add_argument("--allow_train_donors", action="store_true", default=True,
                   help="allow donors only from TRAIN (leak-free)")
    p.add_argument("--exclude_train_donor_changed", action="store_true", default=True,
                   help="exclude donor windows overlapping their own gold")
    p.add_argument("--data_percent_test", type=int, default=100,
                   help="percentage of TEST cases to use (deterministic)")
    p.add_argument("--use_donors_in_single", action="store_true", default=False,
                   help="in single mode, also build dataset index as donor pool")
    p.add_argument("--seed", type=int, default=7, help="random seed")
    return p

# ------------------------------- GLOBALS / KNOBS -------------------------------
TOPK             = 2
OVERRETRIEVE     = 80
RERANK_MODEL     = "cross-encoder/ms-marco-MiniLM-L-6-v2"
OLLAMA_URL       = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
MODEL_REWRITE    = os.environ.get("OLLAMA_MODEL_REWRITE", "llama3.1:8b")
MODEL_PATCH      = os.environ.get("OLLAMA_MODEL_PATCH",   "qwen2.5-coder:14b-instruct")
NUM_CTX_REWRITE  = int(os.environ.get("NUM_CTX_REWRITE", "8192"))
NUM_CTX_PATCH    = int(os.environ.get("NUM_CTX_PATCH",  "12288"))
TEMP_REWRITE     = float(os.environ.get("TEMP_REWRITE", "0.2"))
TEMP_PATCH       = float(os.environ.get("TEMP_PATCH",   "0.0"))
ALLOW_CLI_FALLBACK = True
MAX_REFINES      = 2
PYTEST_TIMEOUT   = 90

plt.rcParams["figure.dpi"] = 150
plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False})

# ------------------------------- Text utils -------------------------------
WORD_RE   = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
STOPWORDS = set("a an and are as at be by for from has have in is it its of on or that the to was were will with not this self none true false return def class if elif else try except finally while for".split())
Q_TOKENS  = set("""
x y z h s sdg t tdg rx ry rz rzz rzx rxy sx cx ccx cnot cz swap cswap iswap ecr u u1 u2 u3
measure barrier qreg creg backend provider aer terra pulse schedule bind assign_parameters
QuantumCircuit QuantumRegister ClassicalRegister Parameter ParameterVector
DAGCircuit PassManager layout mapper transpile basis_gates optimization_level qasm dag layout pass
CouplingMap AncillaAllocation NoiseModel Calibrations LayoutPass Unroller
""".split())

def safe_read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""

def read_source_strict(p_like) -> str:
    p = Path(p_like).expanduser().resolve()
    if not p.exists():             raise FileNotFoundError(f"[single] Path does not exist: {p}")
    if not p.is_file():            raise IsADirectoryError(f"[single] Expected a file but got a directory: {p}")
    if p.stat().st_size == 0:      raise ValueError(f"[single] File is empty: {p}")
    last_err = None
    for enc in ("utf-8","utf-8-sig","utf-16","latin-1"):
        try:
            s = p.read_text(encoding=enc, errors="strict")
            if not s.strip():
                raise ValueError(f"[single] File has no non-whitespace text: {p}")
            return s
        except Exception as e:
            last_err = e
            continue
    s = p.read_text(encoding="utf-8", errors="replace")
    if s.strip(): return s
    raise RuntimeError(f"[single] Could not read {p}. Last error: {last_err}")

def tokenize(s: str) -> List[str]:
    return [w.lower() for w in WORD_RE.findall(s) if w and w.lower() not in STOPWORDS]

def top_tokens_query_from_text(text: str, k: int = 6) -> str:
    toks=[w.lower() for w in WORD_RE.findall(text) if w and w.lower() not in STOPWORDS]
    from collections import Counter
    c=Counter(toks)
    for w in ("def","class","import","return","from","if","else","raise","assert","self"): c[w]=0
    for t in list(Q_TOKENS)[:20]: c[t] *= 2
    return " ".join([w for w,_ in c.most_common(k)])

def changed_lines_in_A(a_text: str, b_text: str) -> set[int]:
    a = a_text.splitlines(); b = b_text.splitlines()
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    touched=set()
    for tag,i1,i2,j1,j2 in sm.get_opcodes():
        if tag in ("replace","delete"):
            touched.update(range(i1+1, i2+1))
    return touched

def dcg(scores): return sum(s / math.log2(i+2) for i,s in enumerate(scores))

def ecdf(arr):
    arr=np.asarray(arr,float); arr=arr[~np.isnan(arr)]
    x=np.sort(arr); y=np.arange(1,len(x)+1)/max(1,len(x))
    return x,y

# ------------------------------- Dataset & chunking -------------------------------
# Case IDs excluded from the paper's 42-case evaluation set. Four of these
# ship with capital-F filename variants (Fixed.py / Fix.py) that do not
# match our lowercase discovery rule on Linux; the fifth (Terra-0-4000/1)
# is likewise absent from the Linux snapshot used for the paper. Listing
# them explicitly makes the evaluation set OS-independent: on case-
# insensitive filesystems (Windows NTFS, macOS APFS default) these folders
# would otherwise be picked up and inflate the count to 47.
PAPER_EXCLUDED_CASES = frozenset({
    "Terra-0-4000/1",
    "Terra-0-4000/3",
    "Terra-0-4000/6",
    "Terra-0-4000/7",
    "stackoverflow-1-5/1",
})

def iter_cases(db_root: Path, apply_paper_filter: bool = True):
    # Use os.walk (returns filenames in their actual on-disk case) plus
    # literal-string membership so that discovery is byte-for-byte case-
    # sensitive on every OS. See src/dataset.py for the refactored version
    # of this function.
    for dirpath, _dirnames, filenames in os.walk(db_root):
        if "buggy.py" not in filenames:
            continue
        fixed_name = None
        for nm in ("fixed.py","fix.py"):
            if nm in filenames:
                fixed_name = nm
                break
        if fixed_name is None:
            continue
        d = Path(dirpath)
        buggy = d/"buggy.py"
        fixed = d/fixed_name
        try:
            txt = buggy.read_text(encoding="utf-8", errors="replace")
            if not txt.strip():
                print(f"[WARN] Skipping empty buggy.py: {buggy}")
                continue
        except Exception as e:
            print(f"[WARN] Skipping unreadable {buggy}: {e}")
            continue
        cid = str(d.relative_to(db_root)).replace(os.sep,"/").replace("\\","/")
        if apply_paper_filter and cid in PAPER_EXCLUDED_CASES:
            continue
        yield cid, d, Path(buggy), Path(fixed)

@dataclass
class CodeChunk:
    chunk_id: str; repo_key: str; file_path: str
    start_line: int; end_line: int; symbol: str; kind: str; text: str

class ASTChunker:
    def __init__(self, window_fallback=80, window_overlap=10):
        self.window_fallback=window_fallback; self.window_overlap=window_overlap
    def chunk_file(self, case_dir: Path, file_path: Path, repo_key: str) -> List[CodeChunk]:
        rel = str(file_path.relative_to(case_dir)) if case_dir in file_path.parents else file_path.name
        src = safe_read(file_path); lines = src.splitlines()
        try: root = ast.parse(src)
        except Exception: root = None
        chunks=[]
        def add(s,e,sym,kind):
            s=max(1,int(s)); e=max(s,int(e))
            chunks.append(CodeChunk(
                chunk_id = md5(f"{repo_key}:{rel}:{s}-{e}".encode()).hexdigest()[:12],
                repo_key = repo_key, file_path=rel, start_line=s, end_line=e,
                symbol=sym, kind=kind, text="\n".join(lines[s-1:e])
            ))
        if root is not None:
            for node in ast.walk(root):
                if isinstance(node,(ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    s=getattr(node,"lineno",1); e=getattr(node,"end_lineno",s); sym=getattr(node,"name","<sym>")
                    add(s,e,sym,"class" if isinstance(node,ast.ClassDef) else "function")
        if not chunks:
            step=self.window_fallback-self.window_overlap; i=0; n=len(lines)
            while i < n:
                s=i+1; e=min(i+self.window_fallback, n); add(s,e,"<module>","module"); i+=step
        return chunks

# ------------------------------- Mini BM25 index -------------------------------
class _MiniBM25:
    def __init__(self, docs):
        from collections import Counter
        self.docs=docs; self.N=len(docs); self.lens=[len(d) for d in docs]
        self.avg = sum(self.lens)/max(1,self.N)
        df=Counter()
        for d in docs: df.update(set(d))
        self.df=dict(df)
    def idf(self,t):
        df=self.df.get(t,0)
        return 0.0 if df==0 else math.log(1+(self.N-df+0.5)/(df+0.5))
    def score(self, q, doc, dl):
        k1,b=1.5,0.75; from collections import Counter
        f=Counter(doc); s=0.0
        for t in q:
            if t not in self.df: continue
            tf=f.get(t,0)
            if tf==0: continue
            denom=tf+k1*(1-b+b*dl/max(1,self.avg))
            s+=self.idf(t)*(tf*(k1+1))/denom
        return s

class HybridIndex:
    def __init__(self, boost_map: Optional[Dict[str,float]]=None, include_paths: bool=False):
        self.boost_map = {k.lower(): float(v) for k,v in (boost_map or {}).items()}
        self.include_paths = include_paths
        self.records=[]; self.docs=[]; self.bm25=None
    def build(self, chunks: List[CodeChunk]):
        self.records=[]; self.docs=[]
        for c in chunks:
            header = f"{c.symbol} {c.kind} "
            if self.include_paths: header += c.file_path + " "
            toks = tokenize(header + "\n" + c.text)
            boost_sum = sum(self.boost_map.get(t, 0.0) for t in toks)
            self.records.append({"chunk":c, "tokens":toks, "boost_sum": float(boost_sum)})
            self.docs.append(toks)
        self.bm25 = _MiniBM25(self.docs)
    def search(self, query: str, topk: int = 10):
        q = tokenize(query)
        scored=[]
        for i, rec in enumerate(self.records):
            s = self.bm25.score(q, rec["tokens"], len(rec["tokens"]))
            s += 0.02 * rec.get("boost_sum", 0.0)
            scored.append((s,i))
        scored.sort(reverse=True)
        out=[]
        for s,i in scored[:topk]:
            c = self.records[i]["chunk"]
            out.append({
                "score": float(s), "re_score": 0.0,
                "file": c.file_path, "symbol": c.symbol, "kind": c.kind,
                "start": int(c.start_line), "end": int(c.end_line),
                "preview": "\n".join(c.text.splitlines()[:120]),
                "repo_key": c.repo_key,
            })
        return out

def quantum_boost_map(alpha: float = 1.8) -> Dict[str, float]:
    return {t.lower(): alpha for t in Q_TOKENS}

# ------------------------------- Reranker -------------------------------
class CrossEncoderReranker:
    def __init__(self, model_name: str):
        try:
            from sentence_transformers import CrossEncoder
            self.model = CrossEncoder(model_name)
            self.enabled=True
        except Exception as e:
            print("[WARN] CrossEncoder unavailable:", e)
            self.model=None; self.enabled=False
    def score_pairs(self, pairs: List[Tuple[str,str]]) -> np.ndarray:
        if not self.enabled: return np.zeros(len(pairs))
        return np.asarray(self.model.predict(pairs), dtype=float)

def apply_rerank(query: str, pool_u: List[Dict], rr: Optional[CrossEncoderReranker]):
    if rr is None or not rr.enabled: return pool_u
    pairs=[(query, h.get("preview","")) for h in pool_u]
    scores=rr.score_pairs(pairs)
    for h,s in zip(pool_u, scores): h["re_score"]=float(s)
    return sorted(pool_u, key=lambda r: r.get("re_score",0.0), reverse=True)

# ------------------------------- Priors & selection -------------------------------
def syntax_prior_of(hit: Dict) -> float:
    txt = (hit.get("preview","") + " " + hit.get("symbol","")).lower()
    prior = 0.0
    if any(t in txt for t in ["assert","raise","error","exception"]): prior += 0.10
    if any(t.lower() in txt for t in Q_TOKENS):                       prior += 0.15
    if re.search(r'\b(run|apply)\b', txt):                             prior += 0.12
    if "dag" in txt or "layout" in txt:                                prior += 0.08
    return prior

def apply_syntax_prior(pool_u: List[Dict], alpha: float = 0.5):
    out=[]
    for h in pool_u:
        sp = syntax_prior_of(h)
        base = h.get("re_score", h.get("score", 0.0))
        h2 = dict(h); h2["syn_prior"] = sp
        h2["score"] = base * (1.0 + alpha*sp)
        out.append(h2)
    return sorted(out, key=lambda r: r.get("score",0.0), reverse=True)

def select_by_coverage_balanced(pool_u, topk, w_gain=0.8, w_base=1.0, w_rerank=1.5,
                                w_div_file=0.15, w_div_sym=0.10, pen_overlap=0.10):
    sel, covered = [], set()
    seen_files, seen_syms = set(), set()
    base = np.array([h.get("score",0.0) for h in pool_u], dtype=float)
    bn   = (base - base.min()) / (base.max() - base.min() + 1e-9)
    rn   = np.array([h.get("re_score",0.0) for h in pool_u], dtype=float)
    for h,b,r in zip(pool_u, bn, rn):
        h["_bn"]=float(b); h["_rn"]=float(r)
    for _ in range(min(topk, len(pool_u))):
        best, best_score=None, -1e9
        for h in pool_u:
            if h in sel: continue
            rng=set(range(h["start"], h["end"]+1))
            gain=len(rng - covered)
            size=max(1, h["end"]-h["start"]+1)
            gain_norm=gain/size
            overlap_frac=1.0 - gain_norm
            s  = w_gain*gain_norm + w_base*h["_bn"] + w_rerank*h["_rn"]
            s += (w_div_file if h["file"] not in seen_files else 0.0)
            s += (w_div_sym  if h["symbol"] not in seen_syms else 0.0)
            s -= pen_overlap*overlap_frac
            if s > best_score: best, best_score = h, s
        if best is None: break
        sel.append(best)
        covered |= set(range(best["start"], best["end"]+1))
        seen_files.add(best["file"]); seen_syms.add(best["symbol"])
    return sel

def select_by_coverage_old(hits, topk, w_new_file=10.0, w_new_symbol=6.0, w_rerank=2.0):
    selected, covered = [], set()
    seen_files, seen_symbols = set(), set()
    pool = hits[:]
    for _ in range(min(topk, len(pool))):
        best, best_score = None, -1.0
        for h in pool:
            if h in selected: continue
            rng = set(range(h["start"], h["end"] + 1))
            gain = len(rng - covered)
            tie  = h.get("re_score", h.get("score", 0.0))
            s = gain + (w_new_file if h["file"] not in seen_files else 0.0) \
                     + (w_new_symbol if h["symbol"] not in seen_symbols else 0.0) \
                     + (w_rerank * tie)
            if s > best_score:
                best, best_score = h, s
        if best is None: break
        selected.append(best)
        covered |= set(range(best["start"], best["end"] + 1))
        seen_files.add(h["file"]); seen_symbols.add(h["symbol"])
    return selected

# ------------------------------- Edit helpers / tests -------------------------------
def enforce_in_region(edits: List[Dict], allowed: List[Tuple[int,int]]) -> List[Dict]:
    ok=[]
    for e in edits or []:
        st=int(e.get("start",1)); en=int(e.get("end",st)); repl=e.get("replacement","")
        for (a,b) in allowed:
            if st>=a and en<=b:
                ok.append({"file":e.get("file","buggy.py"), "start":st, "end":en, "replacement":repl})
                break
    return ok

def apply_edits(src_repo: Path, edits: List[Dict], out_repo: Path) -> Path:
    if out_repo.exists(): shutil.rmtree(out_repo)
    shutil.copytree(src_repo, out_repo)
    p=out_repo/"buggy.py"
    if not p.exists(): return out_repo
    lines=p.read_text(encoding="utf-8",errors="replace").splitlines()
    for e in edits or []:
        st, en = max(1,int(e["start"])), min(len(lines), int(e["end"]))
        new = lines[:st-1] + str(e.get("replacement","")).splitlines() + lines[en:]
        lines = new
    p.write_text("\n".join(lines), encoding="utf-8")
    return out_repo

def run_pytest(path: Path, timeout=90):
    try:
        p = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=path, text=True, capture_output=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + "\n" + (p.stderr or "")
    except Exception as e:
        return 99, f"(pytest error) {e}"

def last_failing_assert(trace: str) -> str:
    tail = "\n".join(trace.splitlines()[-120:])
    m = re.search(r"(E\s+AssertionError[^\n]*\n(?:[^\n]*\n){0,6})", tail)
    return (m.group(1).strip() if m else tail[-400:].strip())

# ------------------------------- Guardrails & metrics -------------------------------
def _ast_ok(src: str) -> Tuple[bool, str]:
    try:
        ast.parse(src); return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError: {e.msg} at line {e.lineno}"

def _find_registers(src: str):
    q_regs=set(); c_regs=set()
    for m in re.finditer(r'(\w+)\s*=\s*QuantumRegister\(', src): q_regs.add(m.group(1))
    for m in re.finditer(r'(\w+)\s*=\s*ClassicalRegister\(', src): c_regs.add(m.group(1))
    return q_regs, c_regs

def _pass_interface_ok(before_src: str, after_src: str) -> Tuple[bool,str]:
    def sigs(s):
        out=set()
        try:
            t=ast.parse(s)
            for n in ast.walk(t):
                if isinstance(n, ast.FunctionDef) and n.name=="run":
                    out.add(tuple(a.arg for a in n.args.args))
        except Exception: pass
        return out
    b=sigs(before_src); a=sigs(after_src)
    if not b: return True, ""
    if b != a: return False, f"Pass interface changed: {b} -> {a}"
    return True, ""

def _no_reg_mix_ok(src: str) -> Tuple[bool,str]:
    q_regs, c_regs = _find_registers(src)
    for m in re.finditer(r'measure\s*\(\s*([A-Za-z_]\w*)', src):
        if m.group(1) in c_regs: return False, f"measure() uses classical register '{m.group(1)}' as quantum"
    for m in re.finditer(r'(cx|cz|rz|rx|ry|swap)\s*\(\s*([A-Za-z_]\w*)', src):
        if m.group(2) in c_regs: return False, f"{m.group(1)}() uses classical register '{m.group(2)}' as quantum"
    return True, ""

def _qubit_order_heuristic_ok(before_src: str, after_src: str, edited_ranges: List[Tuple[int,int]]) -> Tuple[bool,str]:
    b_lines=before_src.splitlines(); a_lines=after_src.splitlines()
    def slice_lines(lines, ranges):
        out=[]
        for s,e in ranges:
            s=max(1,s); e=min(len(lines), max(s,e))
            out.extend(lines[s-1:e])
        return "\n".join(out)
    b=slice_lines(b_lines, edited_ranges)
    a=slice_lines(a_lines, edited_ranges)
    if re.search(r'\bq\[\s*1\s*\]\s*,\s*q\[\s*0\s*\]', a) and re.search(r'\bq\[\s*0\s*\]\s*,\s*q\[\s*1\s*\]', b):
        return False, "Potential qubit order swap in edited lines"
    return True, ""

def guardrail_validate_patch(bug_file: Path, edits: List[Dict]) -> Tuple[bool, List[str]]:
    before = safe_read(bug_file)
    after  = before.splitlines()
    ranges=[]
    for e in edits or []:
        s=max(1,int(e.get("start",1))); en=int(e.get("end",s))
        replacement = str(e.get("replacement","")).splitlines()
        after = after[:s-1] + replacement + after[en:]
        ranges.append((s,en))
    after_src = "\n".join(after)
    oks=[]; msgs=[]
    ok,msg = _ast_ok(after_src); oks.append(ok);  (not ok) and msgs.append(msg)
    ok,msg = _pass_interface_ok(before, after_src); oks.append(ok); (not ok) and msgs.append(msg)
    ok,msg = _no_reg_mix_ok(after_src); oks.append(ok); (not ok) and msgs.append(msg)
    ok,msg = _qubit_order_heuristic_ok(before, after_src, ranges); oks.append(ok); (not ok) and msgs.append(msg)
    return all(oks), msgs

def evaluate_candidate(bug_repo: Path, fix_repo: Path, cand_repo: Optional[Path]) -> Dict[str, Any]:
    a = safe_read(bug_repo/"buggy.py").splitlines()
    b = safe_read(fix_repo/"buggy.py").splitlines()
    c = safe_read(cand_repo/"buggy.py").splitlines() if cand_repo and (cand_repo/"buggy.py").exists() else []
    def _touched(x,y):
        sm = difflib.SequenceMatcher(None, x, y, autojunk=False)
        touched=set()
        for tag,i1,i2,j1,j2 in sm.get_opcodes():
            if tag in ("replace","delete"):
                touched.update(range(i1+1,i2+1))
        return touched
    gold=_touched(a,b); pred=_touched(a,c) if c else set()
    inter=len(gold & pred)
    lp = inter / max(1,len(pred))
    lr = inter / max(1,len(gold))
    lf = 0.0 if lp+lr==0 else 2*lp*lr/(lp+lr)
    return {"lines_p":lp,"lines_r":lr,"lines_f1":lf}

def count_lines_edited(bug_repo: Path, edits: List[Dict]) -> Tuple[int,int]:
    src_lines = safe_read(bug_repo/"buggy.py").splitlines()
    touched=0; delta=0
    for e in edits or []:
        st=max(1,int(e.get("start",1))); en=int(e.get("end",st))
        repl = str(e.get("replacement","")).splitlines()
        old_len = en-st+1
        touched += max(0, old_len)
        delta += abs(len(repl) - old_len)
    return touched, delta

def api_drift_score(before: str, after: str) -> float:
    def names(s):
        try:
            t=ast.parse(s); out=set()
            for n in ast.walk(t):
                if isinstance(n, ast.FunctionDef): out.add(("fun", n.name, len(n.args.args)))
                if isinstance(n, ast.ClassDef):    out.add(("cls", n.name, 0))
            return out
        except Exception:
            return set()
    b=names(before); a=names(after)
    if not b and not a: return 0.0
    j = len(b & a)/max(1,len(b | a))
    return 1.0 - j

def identifier_jaccard(before: str, after: str) -> float:
    B=set(tokenize(before)); A=set(tokenize(after))
    if not (A or B): return 1.0
    return len(A & B)/max(1,len(A | B))

def distortion_flags(bug_repo: Path, edits: List[Dict], cand_repo: Optional[Path], lines_f1: float) -> Dict[str, Any]:
    before = safe_read(bug_repo/"buggy.py")
    after  = safe_read(cand_repo/"buggy.py") if cand_repo and (cand_repo/"buggy.py").exists() else ""
    ast_ok, _ = _ast_ok(after) if after else (False,"")
    drift    = api_drift_score(before, after) if after else np.nan
    jacc     = identifier_jaccard(before, after) if after else np.nan
    touched, delta = count_lines_edited(bug_repo, edits)
    excessive_no_gain = (lines_f1==0.0 and delta>=5)
    flags = {
        "ast_parse_fail": (not ast_ok),
        "api_drift_gt40": bool(drift!=drift and False or (drift>0.40)),
        "id_jacc_lt60":   bool(jacc!=jacc and False or (jacc<0.60)),
        "excessive_no_gain": excessive_no_gain,
        "drift": float(drift if drift==drift else np.nan),
        "id_jacc": float(jacc if jacc==jacc else np.nan),
        "delta_abs_lines": int(delta),
        "lines_touched": int(touched)
    }
    return flags

# ------------------------------- Donor policy -------------------------------
def _case_from_hitfile(path_str: str) -> Optional[str]:
    if not path_str: return None
    parts = path_str.split("/")
    return "/".join(parts[:2]) if len(parts) >= 2 else None

def donor_is_allowed_for_case(hit: Dict, current_cid: str, TRAIN_CIDS: set,
                              allow_train_donors: bool, exclude_train_donor_changed: bool,
                              meta: Dict[str, Any]) -> bool:
    donor_cid = _case_from_hitfile(hit.get("file",""))
    if donor_cid is None: return False
    if donor_cid == current_cid:
        return True
    if not allow_train_donors:
        return False
    if donor_cid not in TRAIN_CIDS:
        return False
    if not exclude_train_donor_changed:
        return True
    gold = meta.get(donor_cid,{}).get("gold", set())
    s,e = int(hit.get("start",1)), int(hit.get("end",1))
    return not any((ln in gold) for ln in range(s, e+1))

# ------------------------------- Splitting -------------------------------
def deterministic_splits(all_case_ids: List[str]) -> Tuple[List[str], List[str], List[str]]:
    order = [ (c, md5(c.encode()).hexdigest()) for c in all_case_ids ]
    order.sort(key=lambda t: t[1])
    ordered = [c for c,_ in order]
    n=len(ordered)
    n_train = int(round(0.70*n))
    n_val   = int(round(0.25*n))
    n_test  = max(0, n - n_train - n_val)
    train = ordered[:n_train]
    val   = ordered[n_train:n_train+n_val]
    test  = ordered[n_train+n_val:]
    return train, val, test

# ------------------------------- Ollama I/O -------------------------------
import requests
def run(cmd, **kw): return subprocess.run(cmd, text=True, capture_output=True, **kw)
def have_ollama_cli():
    try: return run(["ollama","--version"], timeout=5).returncode==0
    except Exception: return False
def _to_prompt(msgs):
    system=[]; convo=[]
    for m in msgs:
        role=(m.get("role") or "user").lower(); content=m.get("content") or ""
        if role=="system": system.append(content.strip())
        elif role=="user":  convo.append(f"USER:\n{content}\n")
        else:               convo.append(f"ASSISTANT:\n{content}\n")
    return ("\n".join(system).strip(), "".join(convo)+"ASSISTANT:\n")
def _http_json(url, payload, timeout=180):
    r=requests.post(url, json=payload, timeout=timeout); r.raise_for_status(); return r.json()
def _ollama_cli(msgs, model, temperature=0.2, num_ctx=8192, timeout=180):
    sys_txt, prompt = _to_prompt(msgs)
    env=os.environ.copy(); env["OLLAMA_NUM_CTX"]=str(num_ctx)
    p=run(["ollama","run", model, prompt], timeout=timeout, env=env)
    if p.returncode!=0: raise RuntimeError(p.stderr)
    return p.stdout.strip()
def ollama_chat(msgs, *, model, temperature, num_ctx, timeout=180):
    try:
        data=_http_json(f"{OLLAMA_URL}/api/chat", {"model":model,"messages":msgs,"stream":False,"options":{"temperature":temperature,"num_ctx":num_ctx}}, timeout=timeout)
        return data.get("message",{}).get("content") or data.get("response","") or "".join(m.get("content","") for m in data.get("messages",[]))
    except Exception: pass
    try:
        sys_txt, prompt=_to_prompt(msgs)
        payload={"model":model,"prompt":prompt,"stream":False,"options":{"temperature":temperature,"num_ctx":num_ctx}}
        if sys_txt: payload["system"]=sys_txt
        data=_http_json(f"{OLLAMA_URL}/api/generate", payload, timeout=timeout)
        return data.get("response","")
    except Exception: pass
    if ALLOW_CLI_FALLBACK and have_ollama_cli():
        return _ollama_cli(msgs, model=model, temperature=temperature, num_ctx=num_ctx, timeout=timeout)
    raise RuntimeError("Ollama not reachable (API and CLI failed).")

# ------------------------------- Prompts -------------------------------
REWRITE_SYS = (
    "You are a software search assistant. Produce 3–8 SHORT queries (<=6 words) "
    "to retrieve the buggy code. Prefer function/class names, module names, error keywords, "
    "and quantum terms (cx, rz, swap, dag, layout, qasm, QuantumCircuit, DAGCircuit) only if relevant. "
    "Return JSON: {'queries':['...']}. No prose."
)
PATCH_SYS = (
    "You are a senior Python engineer. Return STRICT JSON ONLY:\n"
    "{'edits':[{'file':'<rel path>','start':<int 1-based>,'end':<int>,'replacement':'<new full text lines start..end>'}],"
    " 'rationale':'<one paragraph>'}\n"
    "HARD CONSTRAINTS:\n"
    " • Edit ONLY within the allowed line ranges provided.\n"
    " • Do NOT add new files; keep imports unless the context explicitly requires a change.\n"
    " • Keep changes minimal; preserve public APIs.\n"
    "QUANTUM GUARDRAILS:\n"
    " • Preserve qubit order and register semantics; do not swap classical/quantum registers.\n"
    " • Do not change pass interfaces (e.g., run(self, dag)).\n"
    " • Do not silently alter layout or coupling behavior.\n"
    "JSON only. No code fences."
)
def extract_json(s: str) -> dict:
    m=re.search(r"```json\s*(\{.*?\})\s*```", s, re.S)
    raw=m.group(1) if m else s.strip()
    return json.loads(raw)

# ------------------------------- LLM helpers -------------------------------
def llm_rewrite_queries(seed_query: str) -> List[str]:
    msgs=[{"role":"system","content":REWRITE_SYS},
          {"role":"user","content":json.dumps({"seed_query":seed_query, "rules":["<=6 words/query","no quotes/paths"]})}]
    out=ollama_chat(msgs, model=MODEL_REWRITE, temperature=TEMP_REWRITE, num_ctx=NUM_CTX_REWRITE)
    try:
        obj=extract_json(out)
        if isinstance(obj, dict) and "queries" in obj: return [q.strip() for q in obj["queries"] if isinstance(q,str) and q.strip()]
        if isinstance(obj, list): return [q.strip() for q in obj if isinstance(q,str) and q.strip()]
    except Exception:
        pass
    return [q.strip("-• ").strip() for q in out.splitlines() if q.strip()][:6]

def llm_patch_once(cid: str, focused_ctx: List[Dict], allowed_ranges: List[Tuple[int,int]], extra_feedback: str = "") -> dict:
    payload={"case":cid,
             "allowed_ranges":allowed_ranges,
             "context":focused_ctx,
             "instruction":"Return strict JSON only. No markdown fences.",
             "feedback": extra_feedback}
    msgs=[{"role":"system","content":PATCH_SYS},
          {"role":"user","content":json.dumps(payload)}]
    out=ollama_chat(msgs, model=MODEL_PATCH, temperature=TEMP_PATCH, num_ctx=NUM_CTX_PATCH)
    try:
        return extract_json(out)
    except Exception:
        msgs.append({"role":"system","content":"Your previous output was not valid JSON. Return ONLY JSON now."})
        out2=ollama_chat(msgs, model=MODEL_PATCH, temperature=0.0, num_ctx=NUM_CTX_PATCH)
        return extract_json(out2)

# ------------------------------- Selection from config -------------------------------
def parse_cfg_name(name: str):
    parts=name.split("__")
    # e.g., AST_base__nohint__balanced__noR__nosyntax
    chunking = parts[0]
    use_hints = (parts[1]=="hint")
    selector = parts[2]
    use_rerank = (parts[3]=="rerank")
    use_syntax = (parts[4]=="syntax")
    return chunking, use_hints, selector, use_rerank, use_syntax

def pick_index(chunking: str, idx_ast_base, idx_ast_q, idx_win_base, idx_win_q):
    return {"AST_base": idx_ast_base, "AST_q": idx_ast_q, "WIN_base": idx_win_base, "WIN_q": idx_win_q}[chunking]

def select_fn_from_name(selector: str):
    return select_by_coverage_old if selector=="old" else select_by_coverage_balanced

# ------------------------------- Run GRAP / LLM on a set -------------------------------
def run_grap_on_cases(case_ids: List[str], meta, best_index, best_hints, best_select, rr_global, best_syntax,
                      TRAIN_CIDS:set, allow_train_donors:bool, exclude_train_donor_changed:bool,
                      WORK_DIR:Path, OUT_DIR:Path, label="TEST",
                      save_patched_dir: Optional[Path]=None, conversational: bool=False) -> Tuple[pd.DataFrame, float]:
    rows=[]; logs_all=[]; t0_all=time.perf_counter()
    if save_patched_dir:
        save_patched_dir.mkdir(parents=True, exist_ok=True)
    for cid in tqdm(case_ids, desc=f"[GRAP-Q|{label}] cases"):
        t0=time.perf_counter()
        q0 = meta[cid]["query"]
        q  = (q0 + " cx rz dag") if best_hints else q0
        pool = best_index.search(q, topk=max(OVERRETRIEVE, 6*TOPK))
        pool = [h for h in pool if donor_is_allowed_for_case(h, cid, TRAIN_CIDS, allow_train_donors, exclude_train_donor_changed, meta)]
        pool = apply_rerank(q, pool, rr_global)
        if best_syntax: pool = apply_syntax_prior(pool, alpha=0.5)
        selected  = best_select(pool, TOPK)

        bug_path  = meta[cid]["paths"]["bug"]
        focused_ctx=[]; allowed=[]
        for i,h in enumerate(selected,1):
            lo,hi,_ = focus_span(h, bug_path)
            allowed.append((lo,hi))
            snippet = safe_read(bug_path).splitlines()[lo-1:hi]
            focused_ctx.append({"rank":i,"file":h["file"],"span":f"{lo}-{hi}","symbol":h["symbol"],"code":"\n".join(snippet)})

        tiny_b = WORK_DIR / f"{cid.replace('/','__')}__g_bug"; tiny_f = WORK_DIR / f"{cid.replace('/','__')}__g_fix"
        if tiny_b.exists(): shutil.rmtree(tiny_b)
        if tiny_f.exists(): shutil.rmtree(tiny_f)
        tiny_b.mkdir(parents=True, exist_ok=True); tiny_f.mkdir(parents=True, exist_ok=True)
        shutil.copy(meta[cid]["paths"]["bug"], tiny_b/"buggy.py"); shutil.copy(meta[cid]["paths"]["fix"], tiny_f/"buggy.py")

        feedback=""; patch={"edits":[],"rationale":""}; cand_repo=None; guard_notes=[]; rationale_autofill=False; autofill_reason=""
        for it in range(MAX_REFINES+1):
            proposal = llm_patch_once(cid, focused_ctx, allowed, extra_feedback=feedback)
            if not isinstance(proposal.get("rationale",""), str) or not proposal.get("rationale","").strip():
                proposal["rationale"] = "Autofill: minimal, localized fix within allowed span; keep APIs/layout/register semantics; address failure indicated by guardrails/tests."
                rationale_autofill=True; autofill_reason="missing_or_empty"
            edits = enforce_in_region(proposal.get("edits",[]), allowed)
            ok, reasons = guardrail_validate_patch(tiny_b/"buggy.py", edits)
            if not ok:
                feedback = "Guardrail violations:\n- " + "\n- ".join(reasons) + "\nFix minimally within allowed ranges."
                guard_notes.extend(reasons)
                if it==MAX_REFINES: break
                continue
            patch={"edits":edits,"rationale":proposal.get("rationale","")}
            cand_repo = WORK_DIR / f"{cid.replace('/','__')}__g_cand"
            apply_edits(tiny_b, edits, cand_repo)
            src = safe_read(cand_repo/"buggy.py")
            ok,_ = _ast_ok(src)
            if not ok:
                feedback = "Your edit produced a SyntaxError. Repair minimally."
                guard_notes.append("syntax_fail_after_apply")
                if it==MAX_REFINES: break
                continue
            rc, out = run_pytest(cand_repo, timeout=PYTEST_TIMEOUT)
            if rc==0: break
            if rc in (5,4): feedback="No runnable tests. Ensure edit compiles and is minimal."
            else:           feedback="Last failing assertion/stack:\n"+last_failing_assert(out)
            if it==MAX_REFINES: break

        rep = evaluate_candidate(tiny_b, tiny_f, cand_repo)
        touched, delta = count_lines_edited(tiny_b, patch.get("edits",[]))
        flags = distortion_flags(tiny_b, patch.get("edits",[]), cand_repo, rep["lines_f1"])

        # Save patched file & rationale if requested
        if save_patched_dir and cand_repo and (cand_repo/"buggy.py").exists():
            out_py = save_patched_dir / f"{cid.replace('/','__')}_patched.py"
            out_py.write_text(safe_read(cand_repo/"buggy.py"), encoding="utf-8")
            out_js = save_patched_dir / f"{cid.replace('/','__')}_rationale.json"
            out_js.write_text(json.dumps({"case":cid,"rationale":patch.get("rationale",""),"selected":selected,"allowed":allowed}, indent=2), encoding="utf-8")
            if conversational:
                print(f"\n— Case {cid} —")
                print(f"Patched file: {out_py}")
                print(f"Rationale: {patch.get('rationale','')[:600]}")

        elapsed = time.perf_counter() - t0
        rows.append({
            "case": cid, "method":"GRAP", "lines_f1":rep["lines_f1"], "lines_p":rep["lines_p"], "lines_r":rep["lines_r"],
            "num_edits": len(patch.get("edits",[])), "lines_touched": touched, "delta_abs_lines": delta,
            "rationale_autofill": bool(rationale_autofill),
            "elapsed_sec": float(elapsed),
            **flags
        })
        logs_all.append({"case":cid,"guardrail_notes":guard_notes,"selected":selected,"allowed":allowed,
                         "patch":patch,"rationale_autofill":rationale_autofill,"autofill_reason":autofill_reason})

    total = time.perf_counter() - t0_all
    df=pd.DataFrame(rows)
    df.to_csv(OUT_DIR/f"grap_results_{label.lower()}.csv", index=False)
    with open(OUT_DIR/f"grap_logs_{label.lower()}.json","w",encoding="utf-8") as f: json.dump(logs_all, f, indent=2)
    return df, total

def run_llm_on_cases(case_ids: List[str], meta, WORK_DIR:Path, OUT_DIR:Path, label="TEST") -> Tuple[pd.DataFrame, float]:
    rows=[]; logs_all=[]; t0_all=time.perf_counter()
    for cid in tqdm(case_ids, desc=f"[Pure-LLM|{label}] cases"):
        t0=time.perf_counter()
        bug_path = meta[cid]["paths"]["bug"]; fix_path = meta[cid]["paths"]["fix"]
        code = "\n".join(safe_read(bug_path).splitlines()[:220])
        ctx = [{"rank":1,"file":f"{cid}/buggy.py","span":"1-220","symbol":"<file>","code":code}]
        msgs=[{"role":"system","content":PATCH_SYS},
              {"role":"user","content":json.dumps({"case":cid,"context":ctx,"instruction":"Return strict JSON only."})}]
        rationale_autofill=False; autofill_reason=""
        try:
            out=ollama_chat(msgs, model=MODEL_PATCH, temperature=TEMP_PATCH, num_ctx=NUM_CTX_PATCH)
            patch=extract_json(out)
        except Exception as e:
            patch={"edits":[],"rationale":f"error: {e}"}
        if not isinstance(patch.get("rationale",""), str) or not patch.get("rationale","").strip():
            patch["rationale"] = "Autofill: file-level attempt based on first 220 lines; keep APIs/layout/register semantics; apply smallest plausible fix."
            rationale_autofill=True; autofill_reason="missing_or_empty"
        edits = patch.get("edits",[]) or []
        tiny_b = WORK_DIR / f"{cid.replace('/','__')}__p_bug"; tiny_f = WORK_DIR / f"{cid.replace('/','__')}__p_fix"
        if tiny_b.exists(): shutil.rmtree(tiny_b)
        if tiny_f.exists(): shutil.rmtree(tiny_f)
        tiny_b.mkdir(parents=True, exist_ok=True); tiny_f.mkdir(parents=True, exist_ok=True)
        shutil.copy(bug_path, tiny_b/"buggy.py"); shutil.copy(fix_path, tiny_f/"buggy.py")
        cand_repo=None
        if edits:
            cand_repo = WORK_DIR / f"{cid.replace('/','__')}__p_cand"
            apply_edits(tiny_b, edits, cand_repo)
        rep = evaluate_candidate(tiny_b, tiny_f, cand_repo)
        touched, delta = count_lines_edited(tiny_b, edits)
        flags = distortion_flags(tiny_b, edits, cand_repo, rep["lines_f1"])
        elapsed = time.perf_counter() - t0
        rows.append({
            "case": cid, "method":"LLM", "lines_f1":rep["lines_f1"], "lines_p":rep["lines_p"], "lines_r":rep["lines_r"],
            "num_edits": len(edits), "lines_touched": touched, "delta_abs_lines": delta,
            "rationale_autofill": bool(rationale_autofill),
            "elapsed_sec": float(elapsed),
            **flags
        })
        logs_all.append({"case":cid,"patch":patch,"rationale_autofill":rationale_autofill,"autofill_reason":autofill_reason})
    total = time.perf_counter() - t0_all
    df=pd.DataFrame(rows)
    df.to_csv(OUT_DIR / f"llm_results_{label.lower()}.csv", index=False)
    with open(OUT_DIR/f"llm_logs_{label.lower()}.json","w",encoding="utf-8") as f: json.dump(logs_all, f, indent=2)
    return df, total

# ------------------------------- Focus spans -------------------------------
FOCUS_MAX = 24; FOCUS_PAD = 3
FOCUS_PAT = re.compile(
    r"(assert|raise|error|exception|todo|fixme|bug|fail|"
    r"cx|rz|swap|measure|quantumcircuit|dagcircuit|layout|transpile|run\(|apply\()",
    re.I
)
def focus_span(hit: Dict, full_path: Path) -> Tuple[int,int,List[int]]:
    s, e = int(hit["start"]), int(hit["end"])
    try:
        lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return s, e, []
    seg = lines[s-1:e]
    matches = [i for i,ln in enumerate(seg, start=s) if FOCUS_PAT.search(ln)]
    if not matches:
        mid = (s+e)//2
        lo=max(1, mid - FOCUS_MAX//2)
        hi=min(len(lines), lo + FOCUS_MAX - 1)
        return lo, hi, []
    lo = max(1, min(matches) - FOCUS_PAD)
    hi = min(len(lines), max(matches) + FOCUS_PAD)
    if hi - lo + 1 > FOCUS_MAX:
        hi = lo + FOCUS_MAX - 1
    return lo, hi, [m for m in matches if lo <= m <= hi]

# ------------------------------- Plots -------------------------------
def savefig(path): Path(path).parent.mkdir(parents=True, exist_ok=True); plt.tight_layout(); plt.savefig(path); plt.close()
def mean_ci95(a):
    a=np.asarray(pd.to_numeric(a, errors="coerce").dropna(), float)
    if len(a)==0: return np.nan, (np.nan, np.nan)
    m=a.mean(); se=a.std(ddof=1)/np.sqrt(len(a)) if len(a)>1 else 0.0
    return m, (m-1.96*se, m+1.96*se)

def plots_for_set(df_grap, df_llm, OUT_DIR:Path, tag:str, timing: Dict[str, Any]):
    df_all  = pd.concat([df_grap, df_llm], ignore_index=True)
    df_wide = df_all.pivot(index="case", columns="method", values="lines_f1")
    df_all.to_csv(OUT_DIR/f"combined_results_{tag}.csv", index=False)

    # Macro bar (Lines-F1 mean ± 95% CI)
    m_g,ci_g = mean_ci95(df_grap["lines_f1"])
    m_l,ci_l = mean_ci95(df_llm["lines_f1"])
    plt.figure(figsize=(6,4))
    means=[m_g,m_l]; cis=[ci_g,ci_l]; xs=np.arange(2)
    plt.bar(xs, means, yerr=[[means[i]-cis[i][0] for i in range(2)],[cis[i][1]-means[i] for i in range(2)]], capsize=6)
    plt.xticks(xs, ["GRAP-Q","Pure-LLM"]); plt.ylim(0,1); plt.ylabel("Lines-F1"); plt.title(f"Macro comparison ({tag})")
    savefig(OUT_DIR/f"macro_linesf1_bar_{tag}.png")

    # ECDF Lines-F1
    plt.figure(figsize=(6,4))
    x,y = ecdf(df_grap["lines_f1"]); plt.plot(x,y,label="GRAP-Q")
    x,y = ecdf(df_llm["lines_f1"]);  plt.plot(x,y,label="Pure-LLM")
    plt.xlabel("Lines-F1"); plt.ylabel("ECDF"); plt.title(f"Distribution ({tag})"); plt.legend()
    savefig(OUT_DIR/f"ecdf_linesf1_{tag}.png")

    # Patch minimality
    plt.figure(figsize=(6,4))
    plt.scatter(df_grap["delta_abs_lines"], df_grap["lines_f1"], label="GRAP-Q")
    plt.scatter(df_llm["delta_abs_lines"],  df_llm["lines_f1"],  label="Pure-LLM", marker="x")
    plt.xlabel("Δ lines edited (abs)"); plt.ylabel("Lines-F1"); plt.title(f"Minimality vs correctness ({tag})"); plt.legend()
    savefig(OUT_DIR/f"scatter_minimality_{tag}.png")

    # Edit efficiency
    def efficiency(df): 
        d = pd.to_numeric(df["delta_abs_lines"], errors="coerce").fillna(0.0)
        return pd.to_numeric(df["lines_f1"], errors="coerce").fillna(0.0) / (d.replace(0, np.nan)/10.0)
    eff_g = efficiency(df_grap); eff_l = efficiency(df_llm)
    plt.figure(figsize=(6,4))
    plt.boxplot([eff_g.dropna(), eff_l.dropna()], labels=["GRAP-Q","Pure-LLM"], showmeans=True)
    plt.ylabel("Lines-F1 per 10 edited lines"); plt.title(f"Edit efficiency ({tag})")
    savefig(OUT_DIR / f"box_efficiency_{tag}.png")


    # Distortion rates (stacked)
    def rate(df, col): s=pd.to_numeric(df[col], errors="coerce").fillna(0).astype(bool); return float(s.mean())
    rates = pd.DataFrame({
        "syntax_fail":[rate(df_grap,"ast_parse_fail"), rate(df_llm,"ast_parse_fail")],
        "api_drift>0.40":[rate(df_grap,"api_drift_gt40"), rate(df_llm,"api_drift_gt40")],
        "id_jacc<0.60":[rate(df_grap,"id_jacc_lt60"), rate(df_llm,"id_jacc_lt60")],
        "excessive_no_gain":[rate(df_grap,"excessive_no_gain"), rate(df_llm,"excessive_no_gain")]
    }, index=["GRAP-Q","Pure-LLM"])
    bottom=np.zeros(2)
    plt.figure(figsize=(7.2,4.2))
    for col in rates.columns:
        plt.bar(["GRAP-Q","Pure-LLM"], rates[col].values, bottom=bottom, label=col)
        bottom += rates[col].values
    plt.ylim(0,1); plt.ylabel("share of cases"); plt.title(f"Distortion/Failure modes ({tag})"); plt.legend(fontsize=8, ncol=2)
    savefig(OUT_DIR/f"distortion_rates_stacked_{tag}.png")

    # Patch size hist
    plt.figure(figsize=(6,4))
    plt.hist(pd.to_numeric(df_grap["delta_abs_lines"], errors="coerce"), bins=20, alpha=0.6, label="GRAP-Q")
    plt.hist(pd.to_numeric(df_llm["delta_abs_lines"],  errors="coerce"),  bins=20, alpha=0.6, label="Pure-LLM")
    plt.xlabel("Δ lines edited (abs)"); plt.ylabel("count"); plt.title(f"Patch size distribution ({tag})"); plt.legend()
    savefig(OUT_DIR/f"hist_patch_size_{tag}.png")

    # Win-rate + diff curve
    df_wide = df_all.pivot(index="case", columns="method", values="lines_f1")
    joined = df_wide.dropna()
    if not joined.empty:
        wins  = float((joined["GRAP"] > joined["LLM"]).mean())
        loss  = float((joined["GRAP"] < joined["LLM"]).mean())
        ties  = float((joined["GRAP"] == joined["LLM"]).mean())
        plt.figure(figsize=(6,4))
        plt.bar(["GRAP better","LLM better","Tie"], [wins,loss,ties])
        plt.ylim(0,1); plt.ylabel("share of cases"); plt.title(f"Head-to-head win-rate ({tag})")
        savefig(OUT_DIR/f"winrate_{tag}.png")
        diff = (joined["GRAP"] - joined["LLM"]).sort_values()
        plt.figure(figsize=(7,4))
        plt.plot(range(len(diff)), diff.values); plt.axhline(0, linestyle="--")
        plt.xlabel("cases (sorted)"); plt.ylabel("GRAP − LLM (Lines-F1)"); plt.title(f"Per-case advantage ({tag})")
        savefig(OUT_DIR/f"paired_diff_curve_{tag}.png")

    # API drift & identifier Jaccard
    plt.figure(figsize=(8,4))
    plt.subplot(1,2,1)
    plt.boxplot([pd.to_numeric(df_grap["drift"], errors="coerce").dropna(),
                 pd.to_numeric(df_llm["drift"],  errors="coerce").dropna()], labels=["GRAP-Q","Pure-LLM"], showmeans=True)
    plt.title(f"API drift (1−Jaccard of API, {tag})")
    plt.subplot(1,2,2)
    plt.boxplot([pd.to_numeric(df_grap["id_jacc"], errors="coerce").dropna(),
                 pd.to_numeric(df_llm["id_jacc"],  errors="coerce").dropna()], labels=["GRAP-Q","Pure-LLM"], showmeans=True)
    plt.title(f"Identifier Jaccard ({tag})"); plt.tight_layout()
    savefig(OUT_DIR/f"box_api_id_jacc_{tag}.png")

    # Timing bar (total) + per-case distribution
    plt.figure(figsize=(6,4))
    plt.bar(["GRAP-Q","Pure-LLM"], [timing["grap_total_sec"], timing["llm_total_sec"]])
    plt.ylabel("seconds"); plt.title(f"Total wall-clock time ({tag})")
    savefig(OUT_DIR/f"bar_timing_total_{tag}.png")

    plt.figure(figsize=(7,4))
    plt.boxplot([pd.to_numeric(df_grap["elapsed_sec"], errors="coerce").dropna(),
                 pd.to_numeric(df_llm["elapsed_sec"], errors="coerce").dropna()],
                 labels=["GRAP-Q","Pure-LLM"], showmeans=True)
    plt.ylabel("seconds"); plt.title(f"Per-case runtime ({tag})")
    savefig(OUT_DIR/f"box_timing_per_case_{tag}.png")

# ------------------------------- Single-file run -------------------------------
def run_single_file(single_path: Path, gold_fixed: Optional[Path], use_donors: bool,
                    allow_train_donors: bool, exclude_train_donor_changed: bool,
                    BEST_CONFIG: str, DB_ROOT: Path, OUT_DIR: Path, WORK_DIR: Path,
                    rng_seed:int):
    random.seed(rng_seed); np.random.seed(rng_seed)
    OUT_DIR.mkdir(parents=True, exist_ok=True); WORK_DIR.mkdir(parents=True, exist_ok=True)

    try:
        src_text = read_source_strict(single_path)
    except Exception as e:
        print(f"[ERROR] {e}"); sys.exit(2)

    single_case_id = "SINGLE/CASE"
    case_dir = WORK_DIR / "single_case_repo"
    if case_dir.exists(): shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir/"buggy.py").write_text(src_text, encoding="utf-8")

    fix_dir = None
    if gold_fixed and Path(gold_fixed).exists():
        fix_dir = WORK_DIR / "single_case_repo_fix"
        if fix_dir.exists(): shutil.rmtree(fix_dir)
        fix_dir.mkdir(parents=True, exist_ok=True)
        fix_txt = read_source_strict(gold_fixed)
        (fix_dir/"buggy.py").write_text(fix_txt, encoding="utf-8")

    # Build indices (local + optional donors)
    chunker = ASTChunker()
    single_chunks = chunker.chunk_file(case_dir, case_dir/"buggy.py", repo_key=single_case_id)

    dataset_chunks_ast=[]; dataset_chunks_win=[]; meta={}
    TRAIN_CIDS=set()
    if use_donors:
        all_ids=[]
        for cid, ddir, bug_f, fix_f in iter_cases(DB_ROOT):
            all_ids.append(cid)
        train, val, test = deterministic_splits(all_ids)
        TRAIN_CIDS=set(train)
        meta_cases={}
        for cid, ddir, bug_f, fix_f in iter_cases(DB_ROOT):
            btxt = safe_read(bug_f); ftxt = safe_read(fix_f)
            meta_cases[cid] = {"gold": changed_lines_in_A(btxt, ftxt),
                               "paths":{"bug":bug_f,"fix":fix_f},
                               "query": top_tokens_query_from_text(btxt, k=6)}
            for ch in chunker.chunk_file(ddir, bug_f, repo_key=cid):
                ch.file_path = f"{cid}/{ch.file_path}"
                dataset_chunks_ast.append(ch)
        meta = meta_cases

    try:
        BEST_CONFIG = Path(BEST_CONFIG).read_text(encoding="utf-8").strip().splitlines()[0]
    except Exception:
        BEST_CONFIG = "AST_base__nohint__balanced__noR__nosyntax"
    print(f"[INFO] BEST_CONFIG: {BEST_CONFIG}")
    chunking, use_hints, selector, use_rerank, use_syntax = parse_cfg_name(BEST_CONFIG)
    select_fn = select_fn_from_name(selector)
    rr = CrossEncoderReranker(RERANK_MODEL) if use_rerank else None
    if rr is not None and not rr.enabled: rr=None

    if chunking.startswith("AST"):
        idx_local = HybridIndex(quantum_boost_map(1.8) if "q" in chunking else {})
        idx_local.build(single_chunks)
        # donors (optional)
        if use_donors and dataset_chunks_ast:
            idx_donors = HybridIndex(quantum_boost_map(1.8) if "q" in chunking else {})
            idx_donors.build(dataset_chunks_ast)
    else:
        # fallback to windowing for single if ever needed
        idx_local = HybridIndex({})
        idx_local.build(single_chunks)

    def search_combined(query: str):
        pool = idx_local.search(query, topk=max(OVERRETRIEVE, 6*TOPK))
        if use_donors:
            pool += idx_donors.search(query, topk=max(OVERRETRIEVE, 6*TOPK))
        filtered=[]
        for h in pool:
            donor_cid = _case_from_hitfile(h.get("file","")) or single_case_id
            if donor_cid == single_case_id:
                filtered.append(h)
            elif use_donors and donor_is_allowed_for_case(h, single_case_id, TRAIN_CIDS, True, True, meta):
                filtered.append(h)
        seen=set(); out=[]
        for h in filtered:
            key=(h["file"], h["start"], h["end"])
            if key in seen: continue
            seen.add(key); out.append(h)
        return out

    seed_query = top_tokens_query_from_text(src_text, k=6)
    q  = (seed_query + " cx rz dag") if use_hints else seed_query

    pool = search_combined(q)
    pool = apply_rerank(q, pool, rr)
    if use_syntax: pool = apply_syntax_prior(pool, alpha=0.5)
    selected = select_fn(pool, TOPK)

    focused_ctx=[]; allowed=[]
    for i,h in enumerate(selected,1):
        lo,hi,_ = focus_span(h, case_dir/"buggy.py")
        allowed.append((lo,hi))
        snippet = src_text.splitlines()[lo-1:hi]
        focused_ctx.append({"rank":i,"file":h["file"],"span":f"{lo}-{hi}","symbol":h["symbol"],"code":"\n".join(snippet)})

    feedback=""; patch={"edits":[],"rationale":""}; cand_repo = WORK_DIR / "single_case_repo_cand"
    if cand_repo.exists(): shutil.rmtree(cand_repo)
    rationale_autofill=False

    for it in range(MAX_REFINES+1):
        proposal = llm_patch_once(single_case_id, focused_ctx, allowed, extra_feedback=feedback)
        if not isinstance(proposal.get("rationale",""), str) or not proposal.get("rationale","").strip():
            proposal["rationale"] = "Autofill: minimal, localized fix within allowed span; keep APIs/layout/register semantics."
            rationale_autofill=True
        edits = enforce_in_region(proposal.get("edits",[]), allowed)
        ok, reasons = guardrail_validate_patch(case_dir/"buggy.py", edits)
        if not ok:
            feedback = "Guardrail violations:\n- " + "\n- ".join(reasons) + "\nFix minimally within allowed ranges."
            if it==MAX_REFINES: break
            continue
        patch={"edits":edits,"rationale":proposal.get("rationale","")}
        apply_edits(case_dir, edits, cand_repo)
        src = safe_read(cand_repo/"buggy.py")
        ok,_ = _ast_ok(src)
        if not ok:
            feedback = "Your edit produced a SyntaxError. Repair minimally."
            if it==MAX_REFINES: break
            continue
        break

    touched, delta = count_lines_edited(case_dir, patch.get("edits",[]))
    flags = distortion_flags(case_dir, patch.get("edits",[]), cand_repo, lines_f1=0.0)
    scores = {}
    if fix_dir is not None:
        scores = evaluate_candidate(case_dir, fix_dir, cand_repo)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fixed_out = OUT_DIR / "single_fixed.py"
    fixed_out.write_text(safe_read(cand_repo/"buggy.py") if (cand_repo/"buggy.py").exists() else "", encoding="utf-8")
    report = {
        "best_config": BEST_CONFIG,
        "seed_query": seed_query,
        "query_used": q,
        "selected_spans": allowed,
        "num_edits": len(patch.get("edits",[])),
        "lines_touched": touched,
        "delta_abs_lines": delta,
        "rationale": patch.get("rationale",""),
        "rationale_autofill": bool(rationale_autofill),
        "distortion_flags": flags,
        "scores_if_gold": scores
    }
    (OUT_DIR/"single_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n=== Single-file patch summary ===")
    if scores:
        print(f"Lines-F1: {scores['lines_f1']:.3f} | P: {scores['lines_p']:.3f} | R: {scores['lines_r']:.3f}")
    else:
        print("(No gold provided, skipping Lines-F1/P/R)")
    print(f"Edits: {len(patch.get('edits',[]))} | Lines touched: {touched} | Δabs lines: {delta}")
    print(f"Rationale: {patch.get('rationale','')}")
    print(f"Fixed code saved to: {fixed_out}")

# ------------------------------- Main -------------------------------
def main():
    args = build_argparser().parse_args()
    random.seed(args.seed); np.random.seed(args.seed)

    DB_ROOT = Path(args.db_root)
    OUT_DIR = Path(args.out_dir); OUT_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR= Path(args.work_dir); WORK_DIR.mkdir(parents=True, exist_ok=True)

    # Build dataset, indices, and split (shared for diagnostic/test)
    chunker = ASTChunker()
    all_chunks_ast, all_chunks_win, meta = [], [], {}
    ALL_CIDS=[]
    print("[INFO] Scanning dataset...")
    for cid, case_dir, bug_f, fix_f in iter_cases(DB_ROOT):
        ALL_CIDS.append(cid)
        # AST chunks
        for ch in chunker.chunk_file(case_dir, bug_f, repo_key=cid):
            ch.file_path = f"{cid}/{ch.file_path}"
            all_chunks_ast.append(ch)
        # window chunks
        text = safe_read(bug_f); lines=text.splitlines()
        win, overlap = 80, 10; step=max(1,win-overlap); i=0
        while i < len(lines):
            s=i+1; e=min(i+win, len(lines))
            all_chunks_win.append(
                CodeChunk(
                    chunk_id=md5(f"{cid}/{bug_f.name}:{s}-{e}".encode()).hexdigest()[:12],
                    repo_key=cid, file_path=f"{cid}/{bug_f.name}",
                    start_line=s, end_line=e, symbol=f"<win@{s}-{e}>", kind="module",
                    text="\n".join(lines[s-1:e])
                )
            )
            i+=step
        bug_txt = text; fix_txt = safe_read(fix_f)
        meta[cid] = {"gold": changed_lines_in_A(bug_txt, fix_txt),
                     "query": top_tokens_query_from_text(bug_txt, k=6),
                     "project": cid.split("/")[0],
                     "paths": {"bug": bug_f, "fix": fix_f}}

    # Split (deterministic) — same file used across modes
    splits_path = Path("results/grap_vs_llm_deep/splits_70_25_5.json")
    splits_path.parent.mkdir(parents=True, exist_ok=True)
    if splits_path.exists():
        splits = json.loads(safe_read(splits_path))
        TRAIN_CIDS=set(splits["train_ids"]); VAL_CIDS=splits["val_ids"]; TEST_CIDS=splits["test_ids"]
    else:
        train, val, test = deterministic_splits(ALL_CIDS)
        TRAIN_CIDS=set(train); VAL_CIDS=val; TEST_CIDS=test
        splits = {"n":len(ALL_CIDS),"train":len(train),"val":len(val),"test":len(test),
                  "train_ids":train,"val_ids":val,"test_ids":test}
        splits_path.write_text(json.dumps(splits, indent=2), encoding="utf-8")

    # Deterministic TEST subset %
    if not (1 <= int(args.data_percent_test) <= 100):
        print("[ERROR] --data_percent_test must be in [1..100]"); sys.exit(2)
    keep = max(1, int(math.ceil(len(TEST_CIDS)*int(args.data_percent_test)/100.0)))
    TEST_CIDS = [c for c,_h in sorted(((c, md5(c.encode()).hexdigest()) for c in TEST_CIDS),
                                      key=lambda t:t[1])][:keep]
    print(f"[INFO] Split sizes -> TRAIN={len(TRAIN_CIDS)} VAL={len(VAL_CIDS)} TEST={len(TEST_CIDS)} (using {len(TEST_CIDS)} cases)")

    # Build four indices
    def build_index(chunks, use_boost: bool):
        boost = quantum_boost_map(1.8) if use_boost else {}
        try: idx = HybridIndex(boost_map=boost, include_paths=False)
        except TypeError: idx = HybridIndex()
        idx.build(chunks); return idx
    idx_ast_base   = build_index(all_chunks_ast, use_boost=False)
    idx_ast_q      = build_index(all_chunks_ast, use_boost=True)
    idx_win_base   = build_index(all_chunks_win, use_boost=False)
    idx_win_q      = build_index(all_chunks_win, use_boost=True)

    # Load config
    try:
        BEST_CONFIG = Path(args.best_config).read_text(encoding="utf-8").strip().splitlines()[0]
    except Exception:
        BEST_CONFIG = "AST_base__nohint__balanced__noR__nosyntax"
    print(f"[INFO] BEST_CONFIG: {BEST_CONFIG}")

    best_chunking, best_hints, best_selector, best_rerank, best_syntax = parse_cfg_name(BEST_CONFIG)
    best_index  = pick_index(best_chunking, idx_ast_base, idx_ast_q, idx_win_base, idx_win_q)
    best_select = select_fn_from_name(best_selector)
    rr_global   = CrossEncoderReranker(RERANK_MODEL) if best_rerank else None
    if rr_global is not None and not rr_global.enabled: rr_global=None

    # ---------- MODE: DIAGNOSTIC ----------
    if args.mode == "diagnostic":
        print("[MODE] diagnostic — TEST set, GRAP vs LLM, plots + timing")
        df_grap, t_grap = run_grap_on_cases(TEST_CIDS, meta, best_index, best_hints, best_select, rr_global, best_syntax,
                                            TRAIN_CIDS, args.allow_train_donors, args.exclude_train_donor_changed,
                                            WORK_DIR, OUT_DIR, label="TEST",
                                            save_patched_dir=None, conversational=False)
        df_llm,  t_llm  = run_llm_on_cases(TEST_CIDS, meta, WORK_DIR, OUT_DIR, label="TEST")
        timing = {
            "grap_total_sec": float(t_grap),
            "llm_total_sec":  float(t_llm),
            "grap_mean_per_case_sec": float(pd.to_numeric(df_grap["elapsed_sec"], errors="coerce").mean()),
            "llm_mean_per_case_sec":  float(pd.to_numeric(df_llm["elapsed_sec"], errors="coerce").mean())
        }
        (OUT_DIR/"timing_summary_test.json").write_text(json.dumps(timing, indent=2), encoding="utf-8")
        print(f"[TIME] GRAP-Q total={timing['grap_total_sec']:.2f}s (mean/case={timing['grap_mean_per_case_sec']:.2f}s)")
        print(f"[TIME] LLM    total={timing['llm_total_sec']:.2f}s (mean/case={timing['llm_mean_per_case_sec']:.2f}s)")
        plots_for_set(df_grap, df_llm, OUT_DIR, tag="test", timing=timing)
        print(f"[DONE] Diagnostic artifacts in: {OUT_DIR.resolve()}")
        return

    # ---------- MODE: TEST (patch only, conversational) ----------
    if args.mode == "test":
        print("[MODE] test — TEST set, GRAP-Q patches + conversational rationales")
        patched_dir = OUT_DIR / "patched_test"
        df_grap, t_grap = run_grap_on_cases(TEST_CIDS, meta, best_index, best_hints, best_select, rr_global, best_syntax,
                                            TRAIN_CIDS, args.allow_train_donors, args.exclude_train_donor_changed,
                                            WORK_DIR, OUT_DIR, label="TEST",
                                            save_patched_dir=patched_dir, conversational=True)
        # Conversational overall wrap-up
        m_f1 = pd.to_numeric(df_grap["lines_f1"], errors="coerce").fillna(0).mean()
        print("\n=== GRAP-Q test run summary ===")
        print(f"Avg Lines-F1 (vs gold): {m_f1:.3f} on {len(df_grap)} cases")
        print(f"Patched files saved under: {patched_dir.resolve()}")
        print(f"Total runtime: {t_grap:.2f}s (mean/case ~{pd.to_numeric(df_grap['elapsed_sec'], errors='coerce').mean():.2f}s)")
        return

    # ---------- MODE: SINGLE ----------
    if args.mode == "single":
        if not args.single_file:
            print("[ERROR] --single_file is required in single mode"); sys.exit(2)
        run_single_file(Path(args.single_file), Path(args.gold_fixed) if args.gold_fixed else None,
                        use_donors=args.use_donors_in_single,
                        allow_train_donors=args.allow_train_donors,
                        exclude_train_donor_changed=args.exclude_train_donor_changed,
                        BEST_CONFIG=args.best_config, DB_ROOT=DB_ROOT,
                        OUT_DIR=OUT_DIR, WORK_DIR=WORK_DIR,
                        rng_seed=args.seed)
        return

if __name__ == "__main__":
    main()
