"""
Schema Onboarding API — CSV upload and automatic schema detection.
Path A: Technical admin connects existing DB (manual RBAC view config)
Path B: Non-technical user uploads CSV — auto-detect schema + LLM proposal
"""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from backend.core.auth import UserContext, get_current_user
from backend.llm.client import llm_json
from backend.llm.prompts.all_prompts import build_schema_proposal_prompt

router = APIRouter(prefix="/api/schema", tags=["schema"])


class SchemaProposal(BaseModel):
    table_name: str
    columns: list[dict]
    primary_key: list[str]
    predictive_targets: list[dict]
    suggested_views: list[dict]
    row_count_sample: int
    filename: str


@router.post("/onboard-csv", response_model=SchemaProposal)
async def onboard_csv(
    file: UploadFile = File(...),
    user: UserContext = Depends(get_current_user),
) -> SchemaProposal:
    """
    Upload a CSV file. UQS will:
    1. Auto-detect column names and data types
    2. Use LLM to propose a database schema
    3. Suggest RBAC views and predictive targets
    User confirms or edits the proposal before tables are created.
    """
    if not (file.filename or "").endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported for auto-onboarding.")

    content = await file.read()
    text = content.decode("utf-8", errors="ignore")

    # Parse CSV
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for i, row in enumerate(reader):
        if i >= 10:
            break
        rows.append(dict(row))

    if not rows:
        raise HTTPException(status_code=422, detail="CSV file appears to be empty.")

    headers = list(rows[0].keys())
    total_rows = text.count("\n") - 1  # Approximate

    # LLM schema proposal
    system_prompt, user_message = build_schema_proposal_prompt(
        csv_headers=headers,
        sample_rows=rows,
        file_name=file.filename or "upload.csv",
    )
    proposal = await llm_json(system_prompt, user_message, temperature=0.1)

    return SchemaProposal(
        table_name=proposal.get("table_name", "uploaded_data"),
        columns=proposal.get("columns", []),
        primary_key=proposal.get("primary_key", []),
        predictive_targets=proposal.get("predictive_targets", []),
        suggested_views=proposal.get("suggested_views", []),
        row_count_sample=len(rows),
        filename=file.filename or "",
    )


@router.get("/rbac-roles")
async def list_rbac_roles(user: UserContext = Depends(get_current_user)) -> dict:
    """List all configured RBAC roles and their accessible views."""
    from backend.core.rbac import ROLE_SCHEMA_MAP
    return {"roles": ROLE_SCHEMA_MAP}
