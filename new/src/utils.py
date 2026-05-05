"""Shared utilities: tokenization, safe I/O, line-diff helpers."""
from __future__ import annotations

import difflib
import re
from pathlib import Path

WORD_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
STOPWORDS = set(
    "a an and are as at be by for from has have in is it its of on or "
    "that the to was were will with not this self none true false return "
    "def class if elif else try except finally while for".split()
)
Q_TOKENS = set("""
x y z h s sdg t tdg rx ry rz rzz rzx rxy sx cx ccx cnot cz swap cswap
iswap ecr u u1 u2 u3 measure barrier qreg creg backend provider aer
terra pulse schedule bind assign_parameters QuantumCircuit QuantumRegister
ClassicalRegister Parameter ParameterVector DAGCircuit PassManager layout
mapper transpile basis_gates optimization_level qasm dag pass CouplingMap
AncillaAllocation NoiseModel Calibrations LayoutPass Unroller
""".split())


def safe_read(p: Path | str) -> str:
    try:
        return Path(p).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def tokenize(s: str) -> list[str]:
    return [w.lower() for w in WORD_RE.findall(s)
            if w and w.lower() not in STOPWORDS]


def top_tokens_query_from_text(text: str, k: int = 6) -> str:
    from collections import Counter
    toks = tokenize(text)
    c = Counter(toks)
    for w in ("def", "class", "import", "return", "from", "if", "else",
              "raise", "assert", "self"):
        c[w] = 0
    for t in list(Q_TOKENS)[:20]:
        c[t] *= 2
    return " ".join(w for w, _ in c.most_common(k))


def changed_lines_in_A(a_text: str, b_text: str) -> set[int]:
    """Set of line indices (1-based) in A that differ from B."""
    a, b = a_text.splitlines(), b_text.splitlines()
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    touched: set[int] = set()
    for tag, i1, i2, _j1, _j2 in sm.get_opcodes():
        if tag in ("replace", "delete"):
            touched.update(range(i1 + 1, i2 + 1))
    return touched
