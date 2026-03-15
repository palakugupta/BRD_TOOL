"""
different_data.py
─────────────────
Semantic numeric contradiction detector.

High-level idea:
1. Extract numeric facts from SOW + MoM as short sentences:
   - "Configuration & Development: 9 weeks"
   - "Data migration: up to 200000 records"
2. Embed those facts and all BRD sentences.
3. For each BRD sentence with a number:
   - Find the most similar source fact by cosine similarity.
   - If meaning is similar BUT the numeric value is different → different_data.
"""

import re
from typing import Dict, List, Any, Optional, Tuple

from ..models import insert_finding
from ..semantic import embed_sentences, most_similar


NUMBER_UNIT_RE = re.compile(
    r"(?P<num>\d[\d,]*\.?\d*\s*[kKlL]?)\s+(?P<unit>[A-Za-z]{3,})"
)


def _normalize_number(raw: str) -> float:
    raw = raw.lower().replace(",", "").strip()

    if raw.endswith("k"):
        return float(raw[:-1]) * 1000

    if raw.endswith("l"):
        return float(raw[:-1]) * 100000

    return float(raw)


def _sentence_split(text: str) -> List[str]:
    """
    Very simple sentence splitter.
    """
    pieces = re.split(r"(?<=[\.\?\!])\s+", text)
    return [p.strip() for p in pieces if p.strip()]


def _extract_numeric_facts(source_text: str) -> List[Dict[str, Any]]:
    """
    Extract numeric facts from SOW + MoM.
    """

    sentences = _sentence_split(source_text)

    facts: List[Dict[str, Any]] = []

    for sent in sentences:

        for m in NUMBER_UNIT_RE.finditer(sent):

            raw_num = m.group("num")
            unit = m.group("unit").lower().rstrip("s")

            try:
                num = _normalize_number(raw_num)
            except ValueError:
                continue

            start, end = m.span()

            window_start = max(0, start - 80)
            window_end = min(len(sent), end + 80)

            context = sent[window_start:window_end].strip()

            facts.append(
                {
                    "text": context,
                    "number": num,
                    "unit": unit,
                }
            )

    return facts


def _extract_brd_numeric_sentences(brd_text: str) -> List[Tuple[int, str, float, str]]:
    """
    Extract numeric sentences from BRD.
    """

    lines = brd_text.splitlines()
    full = "\n".join(lines)

    sentences = _sentence_split(full)

    results: List[Tuple[int, str, float, str]] = []

    cursor = 0

    for sent in sentences:

        idx = full.find(sent, cursor)

        if idx == -1:
            continue

        line_no = full.count("\n", 0, idx) + 1

        cursor = idx + len(sent)

        for m in NUMBER_UNIT_RE.finditer(sent):

            raw_num = m.group("num")
            unit = m.group("unit").lower().rstrip("s")

            try:
                num = _normalize_number(raw_num)
            except ValueError:
                continue

            results.append((line_no, sent, num, unit))

    return results


def detect(
    sow_text: str,
    mom_text: str,
    brd_text: str,
    chunks: List[Dict[str, Any]],
    similarity_threshold: float = 0.6,
) -> None:

    source_text = (sow_text or "") + "\n" + (mom_text or "")

    facts = _extract_numeric_facts(source_text)

    if not facts:
        return

    fact_texts = [f["text"] for f in facts]

    fact_embs = embed_sentences(fact_texts)

    brd_items = _extract_brd_numeric_sentences(brd_text)

    if not brd_items:
        return

    brd_sentences = [item[1] for item in brd_items]

    brd_embs = embed_sentences(brd_sentences)

    def find_chunk_id(line_no: int) -> Optional[int]:

        for ch in chunks:

            if ch["start_line"] <= line_no <= ch["end_line"]:
                return ch["chunk_id"]

        return None

    def fmt(n: float) -> str:
        return str(int(n)) if n == int(n) else str(n)

    findings_added = 0

    for idx, (line_no, brd_sent, brd_num, brd_unit) in enumerate(brd_items):

        sims = most_similar(brd_embs[idx], fact_embs, top_k=1)

        if not sims:
            continue

        fact_idx, sim = sims[0]

        if sim < similarity_threshold:
            continue

        fact = facts[fact_idx]

        if fact["unit"] != brd_unit:
            continue

        src_num = fact["number"]

        if src_num == brd_num:
            continue

        chunk_id = find_chunk_id(line_no)

        if not chunk_id:
            continue

        critical_units = {"week", "month", "record"}

        severity = "critical" if brd_unit in critical_units else "major"

        insert_finding(
            chunk_id=chunk_id,
            error_type="different_data",
            severity=severity,
            line_number=line_no,
            description=brd_sent.strip(),
            source_reference=(
                f"Different Data: BRD {fmt(brd_num)} {brd_unit} vs "
                f"source {fmt(src_num)} {brd_unit} (\"{fact['text']}\")"
            ),
        )

        findings_added += 1

        if findings_added >= 10:
            break