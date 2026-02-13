"""FastAPI backend for the Factory Farm Violations Tracker."""

import os
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from database import get_connection, init_db

app = FastAPI(
    title="Factory Farm Violations Tracker",
    description="Public database of factory farm violations from EPA ECHO and USDA FSIS",
    version="1.0.0",
)


class ViolationOut(BaseModel):
    id: int
    facility_name: str
    location: Optional[str]
    state: Optional[str]
    county: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    violation_type: Optional[str]
    date: Optional[str]
    source: str
    source_id: Optional[str]
    description: Optional[str]
    severity: Optional[str]
    penalty_amount: Optional[float]


class StatsOut(BaseModel):
    total_violations: int
    by_source: dict
    by_severity: dict
    by_state: dict
    states_count: int


@app.on_event("startup")
def startup():
    init_db()


@app.get("/api/violations", response_model=dict)
def list_violations(
    search: Optional[str] = Query(None, description="Search facility name or description"),
    state: Optional[str] = Query(None, description="Filter by state (2-letter code)"),
    source: Optional[str] = Query(None, description="Filter by data source"),
    severity: Optional[str] = Query(None, description="Filter by severity: High, Medium, Low"),
    violation_type: Optional[str] = Query(None, description="Filter by violation type"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
):
    """Search and filter violations with pagination."""
    conn = get_connection()

    conditions = []
    params = []

    if search:
        conditions.append("(facility_name LIKE ? OR description LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    if state:
        conditions.append("state = ?")
        params.append(state.upper())
    if source:
        conditions.append("source LIKE ?")
        params.append(f"%{source}%")
    if severity:
        conditions.append("severity = ?")
        params.append(severity)
    if violation_type:
        conditions.append("violation_type LIKE ?")
        params.append(f"%{violation_type}%")
    if date_from:
        conditions.append("date >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("date <= ?")
        params.append(date_to)

    where = " AND ".join(conditions) if conditions else "1=1"

    # Count
    count_row = conn.execute(f"SELECT COUNT(*) as cnt FROM violations WHERE {where}", params).fetchone()
    total = count_row["cnt"]

    # Fetch page
    offset = (page - 1) * per_page
    rows = conn.execute(
        f"SELECT * FROM violations WHERE {where} ORDER BY date DESC NULLS LAST, id DESC LIMIT ? OFFSET ?",
        params + [per_page, offset],
    ).fetchall()

    conn.close()

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "data": [dict(r) for r in rows],
    }


@app.get("/api/violations/{violation_id}", response_model=dict)
def get_violation(violation_id: int):
    conn = get_connection()
    row = conn.execute("SELECT * FROM violations WHERE id = ?", [violation_id]).fetchone()
    conn.close()
    if not row:
        return {"error": "Not found"}
    return dict(row)


@app.get("/api/stats", response_model=StatsOut)
def get_stats():
    """Get aggregate statistics."""
    conn = get_connection()

    total = conn.execute("SELECT COUNT(*) as cnt FROM violations").fetchone()["cnt"]

    by_source = {}
    for row in conn.execute("SELECT source, COUNT(*) as cnt FROM violations GROUP BY source"):
        by_source[row["source"]] = row["cnt"]

    by_severity = {}
    for row in conn.execute("SELECT severity, COUNT(*) as cnt FROM violations GROUP BY severity"):
        by_severity[row["severity"] or "Unknown"] = row["cnt"]

    by_state = {}
    for row in conn.execute(
        "SELECT state, COUNT(*) as cnt FROM violations WHERE state IS NOT NULL GROUP BY state ORDER BY cnt DESC LIMIT 20"
    ):
        by_state[row["state"]] = row["cnt"]

    states_count = conn.execute(
        "SELECT COUNT(DISTINCT state) as cnt FROM violations WHERE state IS NOT NULL"
    ).fetchone()["cnt"]

    conn.close()

    return StatsOut(
        total_violations=total,
        by_source=by_source,
        by_severity=by_severity,
        by_state=by_state,
        states_count=states_count,
    )


@app.get("/api/states")
def get_states():
    """Get list of states with violation counts."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT state, COUNT(*) as count FROM violations WHERE state IS NOT NULL GROUP BY state ORDER BY state"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# Serve frontend
@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(os.path.dirname(__file__), "static", "index.html")) as f:
        return f.read()
