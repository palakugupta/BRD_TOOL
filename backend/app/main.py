from pathlib import Path
from dotenv import load_dotenv

# Load env BEFORE any routers/detectors/llm_client import so GROQ_API_KEY is
# guaranteed visible regardless of which directory uvicorn is launched from.
# Explicit path = project-root /.env (backend/.env holds an empty placeholder
# that would otherwise clobber the real key when CWD is backend/).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_PROJECT_ROOT / ".env", override=True)

from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response

from .database import init_db
from .models import seed_default_rules
from .routers import analysis
from .export_docx import generate_docx_report
from .export_excel import generate_excel_report


app = FastAPI(title="Tool CB - BRD Quality Tool")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()
    seed_default_rules()


@app.get("/health")
def health_check():
    return {"status": "ok"}


app.include_router(analysis.router)


# ─────────────────────────────────────────────
# Download DOCX report
# ─────────────────────────────────────────────

@app.get("/api/report/download")
def download_report():

    BASE_DIR = Path(__file__).resolve().parent.parent
    db_path = BASE_DIR / "tool_cb.db"

    print("DOCX generator using DB:", db_path)

    data = generate_docx_report(str(db_path))

    fname = f"BRD_Analysis_Report_{datetime.now():%Y-%m-%d}.docx"

    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"'
        },
    )


# ─────────────────────────────────────────────
# Download Excel report
# ─────────────────────────────────────────────

@app.get("/api/report/excel")
def download_excel_report():

    BASE_DIR = Path(__file__).resolve().parent.parent
    db_path = BASE_DIR / "tool_cb.db"

    print("Excel generator using DB:", db_path)

    data = generate_excel_report(str(db_path))

    fname = f"BRD_Analysis_Report_{datetime.now():%Y-%m-%d}.xlsx"

    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"'
        },
    )


# ─────────────────────────────────────────────
# Static frontend (must remain last)
# ─────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent

app.mount(
    "/",
    StaticFiles(directory=BASE_DIR / "static", html=True),
    name="static",
)
