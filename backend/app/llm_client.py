import json
import os
from typing import Any, Dict, List, Optional


class LLMUnavailable(Exception):
    """Raised when no LLM provider or API key is configured."""


def _get_api_key() -> Optional[str]:
    # Prefer Groq; fall back to generic "free" keys if you want to wire in
    # another provider later.
    return (
        os.getenv("GROQ_API_KEY")
        or os.getenv("FREE_LLM_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("OPENAI_API_TOKEN")
    )


def is_llm_configured() -> bool:
    """
    Returns True if an API key is available for LLM calls.
    """
    return _get_api_key() is not None


def analyze_business_context(
    sow_text: str,
    mom_text: str,
    brd_text: str,
    max_issues: int = 12,
) -> List[Dict[str, Any]]:
    """
    Call the LLM to review BRD against SOW/MoM and return structured issues.

    The returned list contains dictionaries with at least:
      - line_number (int or null)
      - severity   ("critical" | "major" | "minor")
      - error_type (short slug)
      - description
      - source_reference
    """
    api_key = _get_api_key()
    if not api_key:
        raise LLMUnavailable(
            "No LLM API key configured (expected GROQ_API_KEY or FREE_LLM_API_KEY)"
        )

    try:
        # Groq has a generous free tier and is typically cheaper than OpenAI.
        from groq import Groq  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise LLMUnavailable(f"groq package not available: {exc}") from exc

    client = Groq(api_key=api_key)

    system_prompt = (
        "You are a senior business analyst and solution architect. "
        "You deeply understand how Statements of Work (SOW), Minutes of Meeting (MoM), "
        "and Business Requirement Documents (BRD) should align. "
        "You must ONLY return JSON, no prose. "
    )

    user_prompt = (
        "You are given three documents from the same implementation project:\n\n"
        "1) SOW (source of scope and commitments)\n"
        "2) MoM (clarifications and decisions)\n"
        "3) BRD (detailed requirements that should remain consistent with scope and decisions)\n\n"
        "Your job is to look for **business-context issues** in the BRD when compared to the SOW and MoM, "
        "not low-level wording. Focus on:\n"
        "- Scope drift or contradictions (BRD promises or excludes things that clash with SOW/MoM)\n"
        "- Misaligned business rules, SLAs, or KPIs\n"
        "- Process inconsistencies (missing or extra critical steps vs agreed flows)\n"
        "- Misuse of core domain concepts (e.g. leads vs opportunities, accounts vs contacts)\n"
        "- Any risk that the BRD would mis-set expectations vs the contractual SOW.\n\n"
        "IMPORTANT:\n"
        "- Only flag issues that are material from a business perspective.\n"
        "- Prefer fewer, high-signal issues over many small comments.\n"
        "- If you cannot find issues, return an empty JSON list [].\n\n"
        "Return a JSON array of objects with this exact shape:\n"
        "[\n"
        "  {\n"
        '    "line_number": <integer or null>,\n'
        '    "severity": "critical" | "major" | "minor",\n'
        '    "error_type": "business_context_mismatch" | "scope_risk" | "process_risk" | "kpi_sla_risk" | "domain_misuse",\n'
        '    "description": "Short, human-readable description of the issue in the BRD line.",\n'
        '    "source_reference": "Explain which part of SOW/MoM this conflicts with or why it is risky. Keep it under 3 sentences."\n'
        "  }\n"
        "]\n\n"
        "SOW:\n"
        f"\"\"\"{sow_text[:20000]}\"\"\"\n\n"
        "MoM:\n"
        f"\"\"\"{mom_text[:20000]}\"\"\"\n\n"
        "BRD:\n"
        f"\"\"\"{brd_text[:24000]}\"\"\"\n\n"
        f"Limit yourself to at most {max_issues} high-priority issues.\n\n"
        "Return ONLY the JSON array, no explanation, no markdown."
    )

    response = client.chat.completions.create(
        model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        messages=[  # type: ignore
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=1200,
    )

    content = response.choices[0].message.content or "[]"

    try:
        data = json.loads(content)
    except Exception:
        # Some providers occasionally wrap JSON in text; try to recover.
        start = content.find("[")
        end = content.rfind("]") + 1
        if start != -1 and end > start:
            try:
                data = json.loads(content[start:end])
            except Exception as exc:
                raise LLMUnavailable(f"Failed to parse LLM JSON: {exc}") from exc
        else:
            raise LLMUnavailable("LLM did not return valid JSON array")  # pragma: no cover

    if not isinstance(data, list):
        raise LLMUnavailable("LLM output is not a JSON array")  # pragma: no cover

    issues: List[Dict[str, Any]] = []
    for item in data[:max_issues]:
        if not isinstance(item, dict):
            continue
        issues.append(
            {
                "line_number": item.get("line_number"),  # may be None
                "severity": item.get("severity", "major"),
                "error_type": item.get("error_type", "business_context_mismatch"),
                "description": item.get("description", ""),
                "source_reference": item.get("source_reference", ""),
            }
        )

    return issues

