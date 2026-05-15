"""
llm_business_context.py
LLM-backed detector that reviews the BRD against SOW/MoM using business context.

This detector is optional: if no LLM is configured it will safely no-op.
"""

from typing import List, Dict, Any, Optional

from ..models import insert_finding
from ..llm_client import analyze_business_context, is_llm_configured, LLMUnavailable


def _find_chunk_for_line(
    line_number: Optional[int],
    chunks: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if line_number is None:
        # Fallback: attach to first chunk, if any
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
) -> None:
    """
    Run LLM-based business-context checks and store additional findings.

    The goal is to capture higher-level risks (scope drift, KPI/SLA mismatches,
    process inconsistencies, domain misuse) that are difficult to encode as
    static rules.
    """
    print(f"[llm_business_context] START — sow_len={len(sow_text)} mom_len={len(mom_text)} brd_len={len(brd_text)} chunks={len(chunks)}")

    configured = is_llm_configured()
    print(f"[llm_business_context] is_llm_configured = {configured}")

    if not configured:
        print("[llm_business_context] END (no LLM configured)")
        return

    if not brd_text.strip():
        print("[llm_business_context] END (empty BRD)")
        return

    print("[llm_business_context] calling analyze_business_context()...")
    try:
        issues = analyze_business_context(
            sow_text=sow_text or "",
            mom_text=mom_text or "",
            brd_text=brd_text or "",
            max_issues=12,
        )
    except LLMUnavailable as e:
        print("LLM unavailable:", e)
        print("[llm_business_context] END (LLMUnavailable)")
        return
    except Exception as e:
        import traceback
        print("LLM context detector crashed:", e)
        traceback.print_exc()
        print("[llm_business_context] END (exception)")
        return

    print(f"[llm_business_context] got {len(issues)} issues from LLM")

    severity_map = {
        "critical": "critical",
        "major": "major",
        "minor": "minor",
    }

    for issue in issues:
        line_no = issue.get("line_number")
        try:
            line_int = int(line_no) if line_no is not None else None
        except Exception as e:
            import traceback
            print(f"LLM context: failed to parse line_number={line_no!r}: {e}")
            traceback.print_exc()
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

    print("[llm_business_context] END")

