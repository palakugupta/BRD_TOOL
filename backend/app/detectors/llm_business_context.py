"""
LLM-backed detector that reviews the BRD against SOW/MoM using business context.
Optional: if no LLM key is configured, this will no-op.
"""

from typing import List, Dict, Any, Optional
import json

from ..models import insert_finding
from ..llm_client import analyze_business_context, is_llm_configured, LLMUnavailable


def _find_chunk_for_line(
    line_number: Optional[int],
    chunks: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if line_number is None:
        return chunks[0] if chunks else None
    for ch in chunks:
        if ch["start_line"] <= line_number <= ch["end_line"]:
            return ch
    return chunks[0] if chunks else None


def detect(
    sow_text: str,
    mom_text: str,
    brd_text: str,
    chunks: List[Dict[str, Any]],
    project_model: Optional[Dict[str, Any]] = None,
) -> None:
    if not is_llm_configured():
        return
    if not brd_text.strip():
        return

    # If a project_model is provided, inject it into the prompt by
    # prepending a compact JSON description to the SOW/MoM text so the
    # LLM has an explicit, structured mental model to work from.
    sow_for_llm = sow_text or ""
    mom_for_llm = mom_text or ""

    if project_model:
        try:
            model_json = json.dumps(project_model, ensure_ascii=False)
        except Exception:
            model_json = "{}"

        prefix = (
            "PROJECT MODEL (derived from SOW/MoM, JSON):\n"
            f"{model_json}\n\n"
            "The following SOW and MoM texts are the raw sources that this model was built from.\n\n"
        )
        sow_for_llm = prefix + sow_for_llm

    try:
        issues = analyze_business_context(
            sow_text=sow_for_llm,
            mom_text=mom_for_llm,
            brd_text=brd_text or "",
            max_issues=16,
        )
    except LLMUnavailable:
        return
    except Exception:
        return

    severity_map = {
        "critical": "critical",
        "major": "major",
        "minor": "minor",
    }

    for issue in issues:
        line_no = issue.get("line_number")
        try:
            line_int = int(line_no) if line_no is not None else None
        except Exception:
            line_int = None

        ch = _find_chunk_for_line(line_int, chunks)
        if not ch:
            continue

        severity_raw = str(issue.get("severity", "major")).lower()
        severity = severity_map.get(severity_raw, "major")

        error_type = str(issue.get("error_type") or "business_context_mismatch")
        description = str(issue.get("description") or "").strip()
        source_reference = str(issue.get("source_reference") or "").strip()

        if not description and not source_reference:
            continue

        insert_finding(
            chunk_id=ch["chunk_id"],
            error_type=error_type,
            severity=severity,
            line_number=line_int or 0,
            description=(description or source_reference)[:240],
            source_reference=source_reference[:400],
        )

