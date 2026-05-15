import json
import os
from typing import Any, Dict, Optional

from .llm_client import _get_api_key, LLMUnavailable


def build_project_model(sow_text: str, mom_text: str) -> Optional[Dict[str, Any]]:
    """
    Use the LLM once per analysis run to build a structured
    'project model' from SOW + MoM.

    This captures domain concepts, processes, integrations, rules/SLAs,
    and explicit in-scope / out-of-scope decisions that the BRD must follow.
    """
    api_key = _get_api_key()
    if not api_key:
        raise LLMUnavailable(
            "No LLM API key configured (expected GROQ_API_KEY or FREE_LLM_API_KEY)"
        )

    try:
        from groq import Groq  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise LLMUnavailable(f"groq package not available: {exc}") from exc

    client = Groq(api_key=api_key)

    system_prompt = (
        "You are a senior business analyst. "
        "From the SOW and MoM, you must build a compact JSON 'project model' "
        "that captures business context WITHOUT copying large chunks of text."
    )

    user_prompt = (
        "Read the SOW and MoM below and build a JSON object that captures:\n"
        "- domain_glossary: map of key business terms to short definitions\n"
        "- core_entities: list of core CRM/ERP entities (Lead, Opportunity, Account, Contact, etc.)\n"
        "- business_processes: list of processes with name and ordered steps\n"
        "- integrations: list of external systems/tools with scope (in_scope | out_of_scope | unclear)\n"
        "- rules_and_slas: list of explicit business rules, KPIs, SLAs, approval requirements\n"
        "- explicit_out_of_scope: list of items explicitly marked out of scope\n\n"
        "Return a SINGLE JSON object with exactly these top-level keys. "
        "Be concise and avoid duplication. If a field is unknown, return an empty list/object for it.\n\n"
        "SOW:\n"
        f"\"\"\"{sow_text[:20000]}\"\"\"\n\n"
        "MoM:\n"
        f"\"\"\"{mom_text[:20000]}\"\"\"\n\n"
        "Return ONLY the JSON object, no markdown, no explanation."
    )

    response = client.chat.completions.create(
        model=os.getenv("GROQ_MODEL_PROJECT", os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")),
        messages=[  # type: ignore
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=1400,
    )

    content = response.choices[0].message.content or "{}"

    try:
        data = json.loads(content)
    except Exception:
        # Try to recover a JSON object if it's wrapped
        start = content.find("{")
        end = content.rfind("}") + 1
        if start != -1 and end > start:
            data = json.loads(content[start:end])
        else:
            raise LLMUnavailable("LLM did not return a valid JSON object")  # pragma: no cover

    if not isinstance(data, dict):
        raise LLMUnavailable("Project model is not a JSON object")  # pragma: no cover

    return data

