# BRD Quality Assessment Tool

A tool that audits a **Business Requirements Document (BRD)** against its source **Statement of Work (SOW)** and **Minutes of Meeting (MoM)**, flagging contradictions, scope drift, missing coverage, and other quality issues. Runs locally as a FastAPI service with a single-page web UI.

---

## What it does

Upload three documents (SOW + optional MoM + the BRD being reviewed). The tool runs a battery of rule-based, semantic, and LLM-backed detectors and returns a list of findings with line numbers, severity, and source citations.

- **14 detectors** spanning numeric contradictions, scope coverage, terminology drift, process gaps, role/responsibility issues, platform constraints, and more.
- **Optional LLM layer** (Groq) for higher-order business-context risks that rules can't catch.
- **Line-anchored findings** so you can jump from a finding straight to the offending line in a built-in document preview.
- **DOCX report export** for sharing with stakeholders.

---

## Quickstart

### Requirements

- Python 3.10+
- (Optional) A [Groq](https://console.groq.com) API key for LLM-backed checks

### Install

```bash
git clone https://github.com/palakugupta/BRD_TOOL.git
cd BRD_TOOL
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> `requirements.txt` is currently a `pip freeze` from a conda env and may include extra packages. The minimum runtime deps are: `fastapi`, `uvicorn`, `python-dotenv`, `python-docx`, `pypdf`, `sentence-transformers`, `torch`, `groq`.

### Configure

Create a `.env` file in the **project root** (not inside `backend/`):

```env
GROQ_API_KEY=your_groq_key_here
# Optional override:
# GROQ_MODEL=llama-3.3-70b-versatile
```

Without a key the LLM detector cleanly no-ops; everything else still runs.

### Run

```bash
cd backend
uvicorn app.main:app --reload
```

Open `http://localhost:8000` in a browser, upload the three documents, and click **Run Analysis**.

---

## Detectors

| Detector | Type | What it flags |
|---|---|---|
| `different_data` | Pattern + semantic | Numeric or integration-mode contradictions between BRD and SOW/MoM, gated by project-phase context |
| `incomplete_data` | Rule + semantic | SOW topics or required features missing from the BRD |
| `hallucination` | Semantic | BRD claims with no support in SOW/MoM |
| `depth_mismatch` | Heuristic | Areas where BRD detail diverges from SOW depth |
| `duplicate_data` | Pattern | Repeated requirements within the BRD |
| `terminology_drift` | Semantic | Inconsistent domain vocabulary vs SOW/MoM |
| `missing_process_steps` | Semantic | Process flows truncated relative to the agreed flow |
| `organization_mismatch` | Pattern | Org/role references that don't align with SOW/MoM |
| `process_flow_validator` | Rule | Broken or out-of-order process steps in the BRD |
| `process_dependency_validator` | Rule | Missing dependencies in process descriptions |
| `business_rule_violation` | Rule | Stated rules that contradict SOW/MoM |
| `platform_constraints` | Pattern | Implementation choices that violate platform constraints |
| `role_responsibility_violation` | Pattern | Misassigned RACI / role boundaries |
| `llm_business_context` | LLM (Groq) | Scope drift, KPI/SLA mismatches, domain misuse, and other higher-order risks |

---

## API

The web UI uses these endpoints. They're also fine to drive directly.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/upload-documents` | Upload SOW (optional), MoM (optional), and BRD. Chunks the BRD and returns `doc_id`s. |
| `POST` | `/api/run-full-analysis` | Run every detector against the BRD; returns findings + coverage score. |
| `GET`  | `/api/document-preview/{doc_id}` | Line-numbered text of a document with findings overlaid. |
| `GET`  | `/api/report/download` | DOCX report of the latest analysis. |
| `GET`  | `/health` | Liveness probe. |

---

## How chunking works

`create_brd_chunks(doc_id, full_text, chunk_chars=120)` walks the BRD line by line and emits a new chunk whenever the running character count crosses `chunk_chars`. Each chunk stores `start_line` and `end_line` so every finding can be traced back to a contiguous line range.

A single line longer than `chunk_chars` always gets emitted as its own chunk — the loop never stalls.

---

## Project layout

```
BRD_TOOL/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI entrypoint; loads .env, mounts routers + static
│   │   ├── database.py                # SQLite schema + connection helper
│   │   ├── models.py                  # documents / chunks / findings / rules / runs
│   │   ├── semantic.py                # SBERT embeddings (all-MiniLM-L6-v2)
│   │   ├── llm_client.py              # Groq client + business-context prompt
│   │   ├── export_docx.py             # DOCX report generator
│   │   ├── detectors/                 # 14 detectors (see table above)
│   │   ├── routers/
│   │   │   └── analysis.py            # Upload + run-analysis endpoints
│   │   └── preprocessing/             # Requirement-block extraction
│   └── static/
│       └── index.html                 # Single-page UI
├── requirements.txt
└── .env                               # GROQ_API_KEY (not committed)
```

---

## Persistence

A single SQLite file at `backend/tool_cb.db`:

- `documents` — uploaded SOW / MoM / BRD with full text and line count
- `chunks` — BRD chunks with line ranges
- `findings` — detector output, deduped by `(chunk_id, error_type, line, source_reference)` and by overlapping key terms on the same line
- `rules` — seed-able rule patterns for `incomplete_data` coverage checks
- `analysis_runs` — per-run metadata (total findings, coverage score)

The schema initializes on startup; no migrations required.

---

## Configuration reference

| Variable | Default | Purpose |
|---|---|---|
| `GROQ_API_KEY` | — | Enables the `llm_business_context` detector |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model used for the business-context prompt |

If neither `GROQ_API_KEY`, `FREE_LLM_API_KEY`, nor `OPENAI_API_KEY` is set, `is_llm_configured()` returns False and the LLM detector returns early — the rest of the analysis is unaffected.

---

## Notes

- The LLM detector caps SOW/MoM/BRD prompt text at ~20k/20k/24k characters; longer documents are truncated before being sent to Groq.
- Embeddings are optional at the dependency level: if `torch` / `sentence-transformers` aren't installed, semantic detectors return cleanly without crashing.
- All detector output flows through `insert_finding`, which deduplicates aggressively to keep reports concise.
