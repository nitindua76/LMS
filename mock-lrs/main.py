"""
Minimal xAPI 1.0.3 LRS for local development.
Stores statements in memory (lost on restart — use only in dev).

Endpoints:
  POST /statements  — store one statement or a JSON array of statements
  GET  /statements  — retrieve stored statements (most recent first)
  GET  /health      — returns count of stored statements
"""
import uuid
from datetime import datetime, timezone
from typing import Union

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(title="Mock xAPI LRS", version="1.0.3")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_statements: list[dict] = []


def _store(stmt: dict) -> str:
    if "id" not in stmt:
        stmt["id"] = str(uuid.uuid4())
    stmt.setdefault("stored", datetime.now(timezone.utc).isoformat())
    _statements.append(stmt)
    return stmt["id"]


@app.post("/statements")
async def post_statements(request: Request):
    """Accept a single statement or an array of statements."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if isinstance(body, list):
        ids = [_store(s) for s in body]
    elif isinstance(body, dict):
        ids = [_store(body)]
    else:
        raise HTTPException(status_code=400, detail="Body must be a statement object or array")

    return JSONResponse(content=ids, status_code=200, headers={"X-Experience-API-Version": "1.0.3"})


@app.get("/statements")
def get_statements(limit: int = 50, verb: str = ""):
    """Return stored statements, most recent first, optionally filtered by verb IRI."""
    result = list(reversed(_statements))
    if verb:
        result = [s for s in result if s.get("verb", {}).get("id", "") == verb]
    return {
        "statements": result[:limit],
        "more": "",
        "total": len(_statements),
    }


@app.get("/health")
def health():
    return {"status": "ok", "statement_count": len(_statements)}
