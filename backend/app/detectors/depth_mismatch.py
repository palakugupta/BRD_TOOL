"""
depth_mismatch.py
Detects sections where the BRD is much shallower or deeper than the SOW.
"""

import re
from typing import List, Dict, Any

from ..models import insert_finding


KNOWN_MODULES = [
    "Lead Management",
    "Opportunity Management",
    "Quotation Management",
    "Quote Management",
    "Order Management",
    "Account Management",
    "Contact Management",
    "User Management",
    "Vendor Management",
    "Discounting",
    "Invoicing",
    "Payments",
    "Dispatch Management",
    "Case Management",
    "Activity Management",
    "Integrations",
    "Reports and Dashboards",
    "Data Migration",
    "Go Live Support",
    "User Training",
    "IVR",
]


# Improved heading detection
HEADING_PATTERN = re.compile(
    r"""
    ^
    (
        \d+(\.\d+)*\s+.*        |   # 1. Heading / 1.1 Heading
        [A-Z][A-Za-z\s/&\-\(\)]{3,80}  # Lead Management
    )
    [:–-]?$                    # optional : or dash
    """,
    re.VERBOSE,
)


def _extract_sections(text: str) -> Dict[str, Dict[str, Any]]:

    lines = text.splitlines()

    sections = {}
    current_heading = "intro"
    current_lines = []
    current_line_number = 1

    for i, line in enumerate(lines, start=1):

        stripped = line.strip()

        if not stripped:
            continue

        is_known = any(
            stripped.lower().startswith(m.lower())
            for m in KNOWN_MODULES
        )

        is_heading = (
            HEADING_PATTERN.match(stripped)
            and len(stripped.split()) <= 8
            and len(stripped) < 100
        )

        if is_known or is_heading:

            if current_lines:

                sections[current_heading] = {
                    "body": " ".join(current_lines),
                    "line": current_line_number,
                }

            current_heading = stripped.lower()[:60]
            current_lines = []
            current_line_number = i

        else:
            current_lines.append(stripped)

    if current_lines:

        sections[current_heading] = {
            "body": " ".join(current_lines),
            "line": current_line_number,
        }

    return sections


def _keyword_overlap(text_a: str, text_b: str) -> float:

    words_a = set(re.findall(r"[a-z]{4,}", text_a.lower()))
    words_b = set(re.findall(r"[a-z]{4,}", text_b.lower()))

    if not words_a:
        return 0.0

    return len(words_a & words_b) / len(words_a)


def detect(
    sow_text: str,
    brd_text: str,
    chunks: List[Dict[str, Any]],
) -> None:

    sow_sections = _extract_sections(sow_text)
    brd_sections = _extract_sections(brd_text)

    if not sow_sections or not brd_sections:
        return

    def find_chunk_id(line_no: int):

        for ch in chunks:
            if ch["start_line"] <= line_no <= ch["end_line"]:
                return ch["chunk_id"]

        return chunks[0]["chunk_id"] if chunks else None

    findings_added = 0

    for sow_heading, sow_data in sow_sections.items():

        sow_body = sow_data["body"]
        sow_word_count = len(sow_body.split())

        if sow_word_count < 20:
            continue

        best_heading = None
        best_score = 0.0

        sow_words = set(re.findall(r"[a-z]{4,}", sow_heading))

        # Heading similarity match
        for brd_heading in brd_sections:

            brd_words = set(re.findall(r"[a-z]{4,}", brd_heading))

            if not sow_words:
                continue

            score = len(sow_words & brd_words) / len(sow_words)

            if score > best_score:
                best_score = score
                best_heading = brd_heading

        # Body keyword match if heading weak
        if best_score < 0.3:

            for brd_heading, brd_data in brd_sections.items():

                brd_body = brd_data["body"]

                score = _keyword_overlap(
                    sow_body[:600],
                    brd_body[:600],
                )

                if score > best_score:
                    best_score = score
                    best_heading = brd_heading

        if best_heading is None or best_score < 0.2:
            continue

        brd_data = brd_sections[best_heading]
        brd_body = brd_data["body"]
        line_number = brd_data["line"]

        brd_word_count = len(brd_body.split())

        ratio = brd_word_count / sow_word_count if sow_word_count > 0 else 1.0

        if ratio < 0.3:

            insert_finding(
                chunk_id=find_chunk_id(line_number),
                error_type="depth_differs",
                severity="major",
                line_number=line_number,
                description=(
                    f"Section '{sow_heading[:60]}' has {sow_word_count} words in SOW "
                    f"but only {brd_word_count} in BRD ({ratio:.0%} coverage). "
                    "BRD may be missing detail."
                ),
                source_reference="SOW",
            )

            findings_added += 1

        elif ratio > 3.0:

            insert_finding(
                chunk_id=find_chunk_id(line_number),
                error_type="depth_differs",
                severity="minor",
                line_number=line_number,
                description=(
                    f"Section '{sow_heading[:60]}' has {brd_word_count} words in BRD "
                    f"vs {sow_word_count} in SOW ({ratio:.1f}x). "
                    "BRD may be over-elaborating."
                ),
                source_reference="SOW",
            )

            findings_added += 1

        if findings_added >= 5:
            break