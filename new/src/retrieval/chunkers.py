"""AST-based and sliding-window code chunkers."""
from __future__ import annotations

import ast
from dataclasses import dataclass
from hashlib import md5
from pathlib import Path

from ..utils import safe_read


@dataclass
class CodeChunk:
    chunk_id: str
    repo_key: str
    file_path: str
    start_line: int
    end_line: int
    symbol: str
    kind: str
    text: str


class ASTChunker:
    """Extract functions / classes / modules as semantic code chunks.

    Falls back to fixed-size windows if the source cannot be parsed.
    """

    def __init__(self, window_fallback: int = 80, window_overlap: int = 10) -> None:
        self.window_fallback = window_fallback
        self.window_overlap = window_overlap

    def chunk_file(self, case_dir: Path, file_path: Path, repo_key: str) -> list[CodeChunk]:
        rel = (str(file_path.relative_to(case_dir))
               if case_dir in file_path.parents else file_path.name)
        src = safe_read(file_path)
        lines = src.splitlines()
        try:
            root = ast.parse(src)
        except Exception:
            root = None

        chunks: list[CodeChunk] = []

        def _add(s: int, e: int, sym: str, kind: str) -> None:
            s = max(1, int(s))
            e = max(s, int(e))
            chunks.append(CodeChunk(
                chunk_id=md5(f"{repo_key}:{rel}:{s}-{e}".encode()).hexdigest()[:12],
                repo_key=repo_key, file_path=rel,
                start_line=s, end_line=e,
                symbol=sym, kind=kind,
                text="\n".join(lines[s - 1:e]),
            ))

        if root is not None:
            for node in ast.walk(root):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    s = getattr(node, "lineno", 1)
                    e = getattr(node, "end_lineno", s)
                    sym = getattr(node, "name", "<sym>")
                    kind = "class" if isinstance(node, ast.ClassDef) else "function"
                    _add(s, e, sym, kind)
        if not chunks:
            # Fallback to sliding windows
            step = max(1, self.window_fallback - self.window_overlap)
            i = 0
            n = len(lines)
            while i < n:
                s = i + 1
                e = min(i + self.window_fallback, n)
                _add(s, e, "<module>", "module")
                i += step
        return chunks


class WindowChunker:
    """Fixed-size sliding window chunker."""

    def __init__(self, window: int = 80, overlap: int = 10) -> None:
        self.window = window
        self.overlap = overlap

    def chunk_file(self, case_dir: Path, file_path: Path, repo_key: str) -> list[CodeChunk]:
        rel = (str(file_path.relative_to(case_dir))
               if case_dir in file_path.parents else file_path.name)
        src = safe_read(file_path)
        lines = src.splitlines()
        chunks: list[CodeChunk] = []
        step = max(1, self.window - self.overlap)
        i = 0
        while i < len(lines):
            s = i + 1
            e = min(i + self.window, len(lines))
            chunks.append(CodeChunk(
                chunk_id=md5(f"{repo_key}:{rel}:{s}-{e}".encode()).hexdigest()[:12],
                repo_key=repo_key, file_path=rel,
                start_line=s, end_line=e,
                symbol=f"<win@{s}-{e}>", kind="module",
                text="\n".join(lines[s - 1:e]),
            ))
            i += step
        return chunks
