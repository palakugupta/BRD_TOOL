"""
duplicate_data.py
─────────────────
Detects repeated/duplicate content within the BRD.
"""

from difflib import SequenceMatcher
from typing import List, Dict, Any, Optional
import re

from ..models import insert_finding


def _is_heading(text: str) -> bool:
    """Return True if the line looks like a heading rather than content."""

    t = text.strip()

    if not t:
        return True

    # All caps headings
    if t.upper() == t and len(t.split()) <= 6:
        return True

    # Ends with colon
    if t.endswith(":"):
        return True

    # Numbered heading like "1. Lead Management"
    if re.match(r"^\d+[\.\)]\s+\w", t) and len(t) < 40:
        return True

    return False


def detect(
    brd_text: str,
    chunks: List[Dict[str, Any]],
) -> None:

    lines = brd_text.splitlines()

    sentences = [
        (i, line.strip())
        for i, line in enumerate(lines, start=1)
        if len(line.strip()) >= 60 and not _is_heading(line.strip())
    ]

    if len(sentences) < 2:
        return

    def find_chunk_id(line_no: int) -> Optional[int]:

        for ch in chunks:
            if ch["start_line"] <= line_no <= ch["end_line"]:
                return ch["chunk_id"]

        return None

    findings_added = 0
    reported_pairs = set()

    for i in range(len(sentences)):

        line_i, text_i = sentences[i]

        for j in range(i + 1, len(sentences)):

            line_j, text_j = sentences[j]

            # Must be at least 5 lines apart
            if abs(line_j - line_i) < 5:
                continue

            pair_key = (min(line_i, line_j), max(line_i, line_j))

            if pair_key in reported_pairs:
                continue

            similarity = SequenceMatcher(
                None,
                text_i.lower(),
                text_j.lower(),
            ).ratio()

            if similarity >= 0.85:

                chunk_id = find_chunk_id(line_i) or find_chunk_id(line_j)

                if not chunk_id:
                    continue

                insert_finding(
                    chunk_id=chunk_id,
                    error_type="duplicate_data",
                    severity="minor",
                    line_number=line_i,
                    description=text_i,
                    source_reference=(
                        f"Duplicate Data: lines {line_i} and {line_j} "
                        f"are {similarity:.0%} similar."
                    ),
                )

                reported_pairs.add(pair_key)
                findings_added += 1

                if findings_added >= 5:
                    return