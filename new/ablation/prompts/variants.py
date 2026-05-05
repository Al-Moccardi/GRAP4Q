"""Prompt variants for the GRAP-Q prompt sensitivity ablation.

V1 IS THE PRODUCTION PROMPT. We import it literally from
src/patching/prompts.py so any drift between the paper's published
numbers and this ablation's V1 column is impossible by construction.

The production prompt is intentionally lean: it specifies the JSON
output schema, four hard editing constraints, and three quantum
safety guardrails. It does NOT enumerate the deprecated patterns
the framework targets, nor does it include explicit anti-pattern
prohibitions. The ablation tests, additively, whether such content
helps the SLM, and subtractively whether the existing guardrails
are load-bearing.

  V1 baseline       Production PATCH_SYS, byte-identical (imported).
  V2 plus           V1 + DEPRECATED PATTERNS cheat-sheet appended to
                    the system prompt. Tests whether listing the
                    target patterns explicitly helps the model.
  V3 plus           V1 + ANTI-PATTERNS prohibition appended. Tests
                    whether explicit "DO NOT introduce" reduces the
                    LLM-introduces-deprecated failure mode.
  V4 plus (runtime) V1 + runtime defect-localiser in user payload
                    (regex-detected legacy patterns with line
                    numbers). Tests dynamic signaling vs static
                    prompt content.
  V5 plus           V1 + one (buggy_chunk -> fixed_chunk) donor
                    exemplar in user payload. Tests whether a single
                    in-context demonstration helps.
  V6 minus          V1 with the QUANTUM GUARDRAILS section removed.
                    Tests whether the existing quantum-specific
                    guardrails are load-bearing on Bugs4Q val.

All variants share the same OUTPUT FORMAT and HARD CONSTRAINTS so
the scorer treats them uniformly.
"""
from __future__ import annotations

import json
import re as _re
from dataclasses import dataclass

# Import the literal production prompt as V1. Any future change to
# src/patching/prompts.py::PATCH_SYS automatically propagates here.
from src.patching.prompts import PATCH_SYS as PATCH_SYS_V1


# ---------------------------------------------------------------------------
# Section markers in the production PATCH_SYS.
# Used by V6 to remove the QUANTUM GUARDRAILS block.
# ---------------------------------------------------------------------------
_QUANTUM_GUARDRAILS_HEADER = "QUANTUM GUARDRAILS:"


def _excise_section(prompt: str, header: str) -> str:
    """Remove a section starting with `header` and ending at the next
    section header or at the closing 'JSON only' line. Preserves
    surrounding structure cleanly.

    Section structure of the production prompt has NO blank lines
    between sections (the production prompt is compact); each
    section's body is a contiguous block of bullet lines, terminated
    either by the next ALL-CAPS HEADER followed by ':' or by a
    plain closing line.
    """
    idx = prompt.find(header)
    if idx == -1:
        return prompt
    # Find the end: next ALL-CAPS HEADER ending in ':' on its own line,
    # OR any line that doesn't start with " " or "{" (i.e., a non-bullet,
    # non-continuation line).
    after = prompt[idx + len(header):]
    # Skip the newline after the header itself.
    body_start = 0
    if after.startswith("\n"):
        body_start = 1
    # Walk line by line: stop at first line that is NOT a bullet
    # (doesn't start with " \u2022") and is non-empty.
    lines = after[body_start:].split("\n")
    body_consumed = 0
    for i, line in enumerate(lines):
        if line.startswith(" \u2022") or line.startswith("  "):
            body_consumed = i + 1
            continue
        # Hit a non-bullet line. Stop. Don't consume it.
        break
    end_offset = idx + len(header) + body_start + sum(
        len(ln) + 1 for ln in lines[:body_consumed])
    return prompt[:idx] + prompt[end_offset:]


# ---------------------------------------------------------------------------
# DEPRECATED PATTERNS cheat-sheet (added by V2). Drawn from the four
# legacy-API patterns the framework targets.
# ---------------------------------------------------------------------------
_DEPRECATED_PATTERNS_BLOCK = (
    "DEPRECATED PATTERNS TO FIX (when present in the focused span):\n"
    " \u2022 execute(qc, backend=bk[, shots=N])  \u2192  "
    "backend.run(qc[, shots=N])\n"
    " \u2022 'local_qasm_simulator'              \u2192  'qasm_simulator'\n"
    " \u2022 'local_statevector_simulator'       \u2192  "
    "'statevector_simulator'\n"
    " \u2022 result.get_data(qc)                 \u2192  "
    "result.get_counts(qc) (measurement) or .get_statevector() "
    "(statevector)\n"
    " \u2022 qc.iden(...)                        \u2192  qc.id(...)\n"
)


# ---------------------------------------------------------------------------
# ANTI-PATTERNS prohibition block (added by V3).
# ---------------------------------------------------------------------------
_ANTI_PATTERNS_BLOCK = (
    "ANTI-PATTERNS \u2014 NEVER INTRODUCE THESE INTO THE CODE:\n"
    " \u2022 Do NOT write execute(qc, backend=...) \u2014 it is deprecated.\n"
    " \u2022 Do NOT write 'local_*_simulator' \u2014 drop the local_ "
    "prefix.\n"
    " \u2022 Do NOT write .get_data(qc) \u2014 it was removed from Qiskit.\n"
    " \u2022 Do NOT write .iden(...) \u2014 the method is now .id(...).\n"
    "If the input ALREADY uses the modern form, KEEP IT UNCHANGED.\n"
)


def _insert_before_closing(prompt: str, block: str) -> str:
    """Insert `block` immediately before the closing 'JSON only.' line
    of the prompt. The closing line is the production prompt's terminal
    sentence."""
    closing = "JSON only. No code fences."
    idx = prompt.find(closing)
    if idx == -1:
        # Prompt doesn't have the expected closing; just append.
        return prompt.rstrip("\n") + "\n" + block
    return prompt[:idx] + block + prompt[idx:]


# ---------------------------------------------------------------------------
# V2: V1 + DEPRECATED PATTERNS cheat-sheet appended.
# ---------------------------------------------------------------------------
PATCH_SYS_V2 = _insert_before_closing(PATCH_SYS_V1, _DEPRECATED_PATTERNS_BLOCK)


# ---------------------------------------------------------------------------
# V3: V1 + ANTI-PATTERNS prohibition appended.
# ---------------------------------------------------------------------------
PATCH_SYS_V3 = _insert_before_closing(PATCH_SYS_V1, _ANTI_PATTERNS_BLOCK)


# ---------------------------------------------------------------------------
# V4 and V5: same system prompt as V1; payload-only variations.
# ---------------------------------------------------------------------------
PATCH_SYS_V4 = PATCH_SYS_V1
PATCH_SYS_V5 = PATCH_SYS_V1


# ---------------------------------------------------------------------------
# V6: V1 minus the QUANTUM GUARDRAILS section.
# ---------------------------------------------------------------------------
PATCH_SYS_V6 = _excise_section(PATCH_SYS_V1, _QUANTUM_GUARDRAILS_HEADER)


# ---------------------------------------------------------------------------
# Defect localisation regex catalogue (used by V4 only).
# ---------------------------------------------------------------------------
_DEFECT_LINE_PATTERNS = [
    ("DeprecatedExecuteAPI",
     _re.compile(r"\bexecute\s*\(\s*\w+\s*,\s*backend\s*=")),
    ("LegacyBackendName",
     _re.compile(r"['\"]local_(?:statevector|qasm|unitary)_simulator['\"]")),
    ("GetDataMisuse", _re.compile(r"\.get_data\s*\(")),
    ("IdenGateRename", _re.compile(r"\.iden\s*\(")),
]


def detect_defects_with_lines(source: str) -> list[tuple[str, int]]:
    """Return [(defect_name, 1-based-line)] for every regex hit."""
    hits: list[tuple[str, int]] = []
    for line_no, line in enumerate(source.splitlines(), start=1):
        for name, pat in _DEFECT_LINE_PATTERNS:
            if pat.search(line):
                hits.append((name, line_no))
    return hits


def _format_defects_list(defects: list[tuple[str, int]]) -> str:
    """When the regex finds nothing, do NOT claim 'none detected' - the
    catalogue covers only four legacy-API patterns. Many real defects
    fall outside its scope; a 'none detected' message would actively
    mislead the model."""
    if not defects:
        return ("(no legacy-API regex hits; the focused span may still "
                "contain defects \u2014 review it carefully)")
    return "; ".join(f"{name} at line {ln}" for name, ln in defects)


# ---------------------------------------------------------------------------
# DonorExemplar (used by V5).
# ---------------------------------------------------------------------------
@dataclass
class DonorExemplar:
    case_id: str
    buggy_chunk: str
    fixed_chunk: str


def _format_one_exemplar(exemplars: list[DonorExemplar]) -> dict | None:
    if not exemplars:
        return None
    ex = exemplars[0]
    return {"buggy": ex.buggy_chunk, "fixed": ex.fixed_chunk}


# ---------------------------------------------------------------------------
# Message builders. All variants emit a [system, user] pair with a
# JSON-encoded user payload.
# ---------------------------------------------------------------------------
def _base_payload(case_id, focused_ctx, allowed_ranges, extra_feedback):
    return {
        "case": case_id,
        "allowed_ranges": allowed_ranges,
        "context": focused_ctx,
        "instruction": "Return strict JSON only. No markdown fences.",
        "feedback": extra_feedback,
    }


def build_messages_v1(case_id, focused_ctx, allowed_ranges,
                      extra_feedback="") -> list[dict]:
    return [
        {"role": "system", "content": PATCH_SYS_V1},
        {"role": "user",
         "content": json.dumps(_base_payload(
             case_id, focused_ctx, allowed_ranges, extra_feedback))},
    ]


def build_messages_v2(case_id, focused_ctx, allowed_ranges,
                      buggy_source: str = "",
                      extra_feedback="") -> list[dict]:
    return [
        {"role": "system", "content": PATCH_SYS_V2},
        {"role": "user",
         "content": json.dumps(_base_payload(
             case_id, focused_ctx, allowed_ranges, extra_feedback))},
    ]


def build_messages_v3(case_id, focused_ctx, allowed_ranges,
                      buggy_source: str = "",
                      extra_feedback="") -> list[dict]:
    return [
        {"role": "system", "content": PATCH_SYS_V3},
        {"role": "user",
         "content": json.dumps(_base_payload(
             case_id, focused_ctx, allowed_ranges, extra_feedback))},
    ]


def build_messages_v4(case_id, focused_ctx, allowed_ranges,
                      buggy_source: str,
                      extra_feedback="") -> list[dict]:
    detected = detect_defects_with_lines(buggy_source)
    payload = _base_payload(case_id, focused_ctx, allowed_ranges,
                            extra_feedback)
    payload["defects_detected_in_input"] = _format_defects_list(detected)
    return [
        {"role": "system", "content": PATCH_SYS_V4},
        {"role": "user", "content": json.dumps(payload)},
    ]


def build_messages_v5(case_id, focused_ctx, allowed_ranges,
                      buggy_source: str = "",
                      donor_exemplars: list[DonorExemplar] | None = None,
                      extra_feedback="") -> list[dict]:
    payload = _base_payload(case_id, focused_ctx, allowed_ranges,
                            extra_feedback)
    example = _format_one_exemplar(donor_exemplars or [])
    if example is not None:
        payload["example"] = example
    return [
        {"role": "system", "content": PATCH_SYS_V5},
        {"role": "user", "content": json.dumps(payload)},
    ]


def build_messages_v6(case_id, focused_ctx, allowed_ranges,
                      buggy_source: str = "",
                      extra_feedback="") -> list[dict]:
    return [
        {"role": "system", "content": PATCH_SYS_V6},
        {"role": "user",
         "content": json.dumps(_base_payload(
             case_id, focused_ctx, allowed_ranges, extra_feedback))},
    ]


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------
VARIANTS = ("v1", "v2", "v3", "v4", "v5", "v6")


VARIANT_DESCRIPTIONS = {
    "v1": "Baseline: production PATCH_SYS imported literally from "
          "src/patching/prompts.py.",
    "v2": "V1 + DEPRECATED PATTERNS cheat-sheet appended to system prompt.",
    "v3": "V1 + ANTI-PATTERNS prohibition appended to system prompt.",
    "v4": "V1 + runtime defect-localiser in user payload (regex-detected "
          "legacy patterns with line numbers).",
    "v5": "V1 + one (buggy_chunk, fixed_chunk) donor exemplar in user "
          "payload.",
    "v6": "V1 minus the QUANTUM GUARDRAILS section.",
}


# Indicates whether a variant's message builder consumes
# donor_exemplars. The orchestrator reads this dict to decide whether
# to populate exemplars before calling the builder.
USES_DONOR_EXEMPLARS = {
    "v1": False,
    "v2": False,
    "v3": False,
    "v4": False,
    "v5": True,
    "v6": False,
}
