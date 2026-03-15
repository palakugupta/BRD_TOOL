"""
hallucination.py
────────────────
Detects BRD content not grounded in any source document.
"""

import re
from typing import List, Dict, Any, Optional

from ..models import insert_finding


COMMON_WORDS = {
    # Generic verbs
    "system","will","include","based","using","capture","create","update","delete",
    "manage","track","allow","enable","support","define","generate","process",
    "store","send","receive","review","approve","complete","connect","access",
    "display","provide","require","implement","configure","integrate","submit",
    "assign","convert","prepare","migrate","synchronize","remain","exceed",
    "enforce","produce","maintain","ensure","reduce","improve","deliver","perform",
    "execute","handle","record","identify","establish","confirm","validate",
    "monitor","report",

    # CRM domain
    "sales","customer","business","management","information","details","status",
    "teams","users","roles","types","level","standard","module","section","field",
    "table","report","screen","button","portal","stage","phase","record","entry",
    "action","event","workflow","template","document","quote","quotes","order",
    "orders","leads","opportunities","pricing","product","products","master",
    "approval","approvals","discount","workspace","dashboard","dashboards",
    "pipeline","conversion","tracking","qualification","assignment","creation",
    "generation","mapping","catalogue","catalogues","costing","worksheet",
    "worksheets","integration","integrations","migration","existing","partner",
    "website","forms","submissions","enquiries","finance","account","accounts",
    "opportunity","contact","contacts","channel","channels","segment","segments",

    # Salesforce
    "salesforce","salescloud","manufacturing","platform","license","object",
    "objects","profile","profiles","permission","permissions","hierarchy",
    "rollup","validation","trigger","triggers","workflow","approval","junction",
    "lookup","formula","picklist","layout","related","custom","metadata",
    "sandbox","production","deployment","release","sprint","backlog","grooming",
    "velocity","burndown","acceptance","criteria","stories","epics","kanban",

    # Project specific
    "jindal","kasmo","aluminium","exotel","dispatch","proforma","invoice",
    "invoicing","payment","payments","purchase","vendor","quotation","quotations",
    "material","materials","tooling","costing","drawing","drawings","feasibility",
    "amendment","amendments","outbound","inbound","downstream","upstream",
    "enrichment","normalization","deduplication","scoring","routing","ingestion",
    "auditable","auditability","versioning","handoff","handoffs",

    # filler
    "automatic","automatically","manual","manually","predefined","approved",
    "required","following","available","current","multiple","single","total",
    "general","specific","defined","active","assigned","configured","linked",
    "submitted","rejected","closed","unified","consistent","structured",
    "standardized","integrated","aware","driven","facing",

    # connectors
    "which","their","there","where","these","those","about","after","before",
    "should","would","could","must","shall","also","each","both","other","more",
    "such","than","then","when","into","onto","upon","within","between","through",
    "during","across","against",
}


WORD_RE = re.compile(r"[a-z]{5,}")
LONG_WORD_RE = re.compile(r"[a-z]{7,}")


def _build_source_tokens(sow_text: str, mom_text: str):

    source = (sow_text + "\n" + mom_text).lower()

    words = set(WORD_RE.findall(source))

    token_list = re.findall(r"[a-z]{4,}", source)

    bigrams = set()

    for i in range(len(token_list) - 1):
        bigrams.add(token_list[i] + " " + token_list[i + 1])

    return words, bigrams


def detect(
    sow_text: str,
    mom_text: str,
    brd_text: str,
    chunks: List[Dict[str, Any]],
) -> None:

    source_words, source_bigrams = _build_source_tokens(sow_text, mom_text)

    def find_chunk(line_no: int) -> Optional[Dict[str, Any]]:
        for ch in chunks:
            if ch["start_line"] <= line_no <= ch["end_line"]:
                return ch
        return None

    lines = brd_text.splitlines()

    hallucinations = []

    for i, line in enumerate(lines, start=1):

        lower = line.lower().strip()

        # Skip empty or short lines
        if not lower or len(lower) < 40:
            continue

        # Skip headings / labels
        if ":" in lower:
            continue

        # Ignore short sentences
        if len(lower.split()) < 12:
            continue

        tokens = set(LONG_WORD_RE.findall(lower))

        novel_words = [
            t for t in tokens
            if t not in source_words
            and t not in COMMON_WORDS
        ]

        token_list = re.findall(r"[a-z]{4,}", lower)

        brd_bigrams = set()

        for j in range(len(token_list) - 1):
            brd_bigrams.add(token_list[j] + " " + token_list[j + 1])

        novel_words = [
            w for w in novel_words
            if not any(w in bg for bg in source_bigrams)
        ]

        # stronger hallucination trigger
        if len(novel_words) >= 5:

            ch = find_chunk(i)

            if not ch:
                continue

            hallucinations.append(
                {
                    "chunk_id": ch["chunk_id"],
                    "line_number": i,
                    "words": sorted(novel_words)[:5],
                    "line_text": line.strip()[:120],
                }
            )

    # Cap findings
    for h in hallucinations[:5]:

        insert_finding(
            chunk_id=h["chunk_id"],
            error_type="hallucination",
            severity="major",
            line_number=h["line_number"],
            description=h["line_text"],
            source_reference=(
                "Hallucination: line contains specific terms not found in sources "
                f"({', '.join(h['words'])})."
            ),
        )