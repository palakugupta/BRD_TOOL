"""
incomplete_data.py
──────────────────
Detects SOW topics/features missing from BRD using:
1) User-defined rules (rules table, error_type='incomplete_data')
2) Semantic coverage: SOW topics vs BRD sentences via embeddings
"""

import re
from typing import List, Dict, Any, Optional

from ..models import insert_finding, get_enabled_rules
from ..semantic import embed_sentences, most_similar


SKIP_WORDS = {
    "details","fields","layouts","process","processes","management",
    "standard","custom","business","attributes","values","provided",
    "jindal","kasmo","salesforce","configuration","implementation",
    "scope","assumptions","dependencies","project","system","platform",
    "requirements","document","description","category","section",
    "module","overview","current","proposed",
}

MIN_TOPIC_LENGTH = 6
MAX_TOPIC_LENGTH = 80


def _extract_candidate_topics(sow_text: str) -> List[str]:

    topics: List[str] = []
    lines = sow_text.splitlines()

    for line in lines:

        stripped = line.strip()

        if not stripped:
            continue

        if "|" in stripped:
            first_cell = stripped.split("|", 1)[0].strip()
            candidate = first_cell
        else:
            candidate = stripped

        if not (MIN_TOPIC_LENGTH <= len(candidate) <= MAX_TOPIC_LENGTH):
            continue

        candidate = re.sub(r"^[-•*\d\.]+\s*", "", candidate).strip()

        if not candidate or not candidate[0].isalpha():
            continue

        first_word = candidate.split()[0].lower()

        if first_word in SKIP_WORDS:
            continue

        if len(candidate.split()) == 1 and len(candidate) < 8:
            continue

        topics.append(candidate)

    seen = set()
    unique: List[str] = []

    for t in topics:

        low = t.lower()

        if low in seen:
            continue

        seen.add(low)
        unique.append(t)

    return unique


def _sentence_split(text: str) -> List[str]:

    parts = re.split(r"(?<=[\.\?\!])\s+", text)

    return [p.strip() for p in parts if p.strip()]


def _find_chunk_id(line_no: int, chunks: List[Dict[str, Any]]) -> Optional[int]:

    for ch in chunks:
        if ch["start_line"] <= line_no <= ch["end_line"]:
            return ch["chunk_id"]

    return chunks[0]["chunk_id"]


def detect(
    sow_text: str,
    brd_text: str,
    chunks: List[Dict[str, Any]],
    semantic_threshold: float = 0.4,
    max_semantic_findings: int = 8,
) -> None:

    if not chunks:
        return

    sow_lower = sow_text.lower()
    brd_lower = brd_text.lower()

    # ── Part 1: Rule-based incomplete data ─────────────────────

    rules = [r for r in get_enabled_rules() if r["error_type"] == "incomplete_data"]

    for rule in rules:

        token = (rule["pattern"] or "").strip()

        if not token:
            continue

        token_lower = token.lower()

        if token_lower in sow_lower and token_lower not in brd_lower:

            line_number = 1
            chunk_id = chunks[0]["chunk_id"]

            insert_finding(
                chunk_id=chunk_id,
                error_type="incomplete_data",
                severity=rule["severity"] or "major",
                line_number=line_number,
                description=(
                    f"Rule '{rule['rule_name']}': keyword '{token}' appears in SOW "
                    "but is missing from BRD."
                ),
                source_reference="SOW",
                rule_id=rule["rule_id"],
            )

    # ── Part 2: Semantic coverage ──────────────────────────────

    topics = _extract_candidate_topics(sow_text)

    if not topics:
        return

    brd_sentences = _sentence_split(brd_text)

    if not brd_sentences:
        return

    topic_embs = embed_sentences(topics)
    brd_embs = embed_sentences(brd_sentences)

    reported = 0

    for i, topic in enumerate(topics):

        tokens = [
            w for w in topic.lower().split()
            if len(w) >= 4 and w not in SKIP_WORDS
        ]

        if tokens and any(tok in brd_lower for tok in tokens):
            continue

        sims = most_similar(topic_embs[i], brd_embs, top_k=3)

        if not sims:
            continue

        best_idx, best_sim = sims[0]

        if best_sim >= semantic_threshold:
            continue

        # Find BRD line number for best semantic sentence
        sentence = brd_sentences[best_idx]
        line_number = brd_text[: brd_text.find(sentence)].count("\n") + 1
        chunk_id = _find_chunk_id(line_number, chunks)

        insert_finding(
            chunk_id=chunk_id,
            error_type="incomplete_data",
            severity="major",
            line_number=line_number,
            description=(
                f"SOW topic appears uncovered in BRD: '{topic}'. "
                "No semantically similar content was found in the BRD."
            ),
            source_reference="SOW",
        )

        reported += 1

        if reported >= max_semantic_findings:
            break