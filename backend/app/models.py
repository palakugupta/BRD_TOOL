from datetime import datetime
from typing import Tuple, List, Dict, Any, Optional

from .database import get_connection


def insert_document(doc_type: str, filename: str, full_text: str) -> Tuple[int, int]:
    lines = full_text.splitlines()
    line_count = len(lines)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO documents (doc_type, filename, upload_timestamp, full_text, line_count)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            doc_type,
            filename,
            datetime.utcnow().isoformat(),
            full_text,
            line_count,
        ),
    )
    doc_id = cur.lastrowid
    conn.commit()
    conn.close()
    return doc_id, line_count


def create_brd_chunks(doc_id: int, full_text: str, chunk_size: int = 50) -> int:
    lines = full_text.splitlines()
    total_lines = len(lines)
    if total_lines == 0:
        return 0

    conn = get_connection()
    cur = conn.cursor()

    chunk_count = 0
    start = 0
    while start < total_lines:
        end = min(start + chunk_size, total_lines)
        chunk_lines = lines[start:end]
        start_line = start + 1
        end_line = end
        chunk_text = "\n".join(chunk_lines)

        cur.execute(
            """
            INSERT INTO chunks (doc_id, start_line, end_line, chunk_text)
            VALUES (?, ?, ?, ?)
            """,
            (doc_id, start_line, end_line, chunk_text),
        )
        chunk_count += 1
        start = end

    conn.commit()
    conn.close()
    return chunk_count


def get_document(doc_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_chunks_for_brd(doc_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT chunk_id, doc_id, start_line, end_line, chunk_text
        FROM chunks
        WHERE doc_id = ?
        ORDER BY start_line
        """,
        (doc_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def insert_finding(
    chunk_id: int,
    error_type: str,
    severity: str,
    line_number: int,
    description: str,
    source_reference: str = "",
    rule_id: Optional[int] = None,
) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO findings (
            chunk_id,
            error_type,
            severity,
            line_number,
            description,
            source_reference,
            rule_id,
            detected_timestamp
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            chunk_id,
            error_type,
            severity,
            line_number,
            description,
            source_reference,
            rule_id,
            datetime.utcnow().isoformat(),
        ),
    )
    finding_id = cur.lastrowid
    conn.commit()
    conn.close()
    return finding_id


def get_findings_for_brd(doc_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT f.*
        FROM findings f
        JOIN chunks c ON f.chunk_id = c.chunk_id
        WHERE c.doc_id = ?
        ORDER BY f.line_number
        """,
        (doc_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_rule(
    rule_name: str,
    error_type: str,
    pattern: str,
    condition_logic: str,
    severity: str,
    enabled: int = 1,
) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO rules (
            rule_name,
            error_type,
            pattern,
            condition_logic,
            severity,
            enabled,
            created_timestamp
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rule_name,
            error_type,
            pattern,
            condition_logic,
            severity,
            enabled,
            datetime.utcnow().isoformat(),
        ),
    )
    rule_id = cur.lastrowid
    conn.commit()
    conn.close()
    return rule_id


def get_enabled_rules() -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM rules
        WHERE enabled = 1
        ORDER BY rule_id
        """
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def seed_default_rules() -> None:
    """
    Seed a minimal set of example rules for testing.
    Only runs when rules table is empty.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS cnt FROM rules")
    row = cur.fetchone()
    count = row["cnt"] if row else 0
    conn.close()
    if count and count > 0:
        return

    # Incomplete data: key integrations / modules must appear in BRD if in SOW
    defaults = [
        {
            "rule_name": "EXIM integration must be covered",
            "error_type": "incomplete_data",
            "pattern": "EXIM",
            "condition_logic": "If EXIM appears in SOW it must also appear in BRD",
            "severity": "major",
        },
        {
            "rule_name": "WhatsApp integration must be covered",
            "error_type": "incomplete_data",
            "pattern": "WhatsApp",
            "condition_logic": "If WhatsApp appears in SOW it must also appear in BRD",
            "severity": "major",
        },
        {
            "rule_name": "Data migration must be covered",
            "error_type": "incomplete_data",
            "pattern": "data migration",
            "condition_logic": "If data migration appears in SOW it must also appear in BRD",
            "severity": "major",
        },
        {
            "rule_name": "Invoicing must be covered",
            "error_type": "incomplete_data",
            "pattern": "Invoicing",
            "condition_logic": "If Invoicing appears in SOW it must also appear in BRD",
            "severity": "major",
        },
        {
            "rule_name": "Quote Management must be covered",
            "error_type": "incomplete_data",
            "pattern": "Quote Management",
            "condition_logic": "If Quote Management appears in SOW it must also appear in BRD",
            "severity": "major",
        },
    ]

    for r in defaults:
        create_rule(
            rule_name=r["rule_name"],
            error_type=r["error_type"],
            pattern=r["pattern"],
            condition_logic=r["condition_logic"],
            severity=r["severity"],
            enabled=1,
        )



