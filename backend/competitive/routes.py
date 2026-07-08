"""
competitive/routes.py — FastAPI routes for the Competitive Intelligence feature.

NEW ENDPOINTS:
    POST   /companies              → Add a company to track
    GET    /companies              → List all tracked companies
    DELETE /companies/{id}         → Deactivate (soft delete) a company
    GET    /companies/{id}/reports → Get CI reports for a company
    POST   /ci/scan-now            → Manually trigger a scan (for testing)
    GET    /ci/reports             → Get all recent reports across companies

WHY SOFT DELETE (deactivate) INSTEAD OF HARD DELETE?
    If you delete a company, you lose all its CI reports history.
    Deactivating preserves history but stops future scans.
    The reports remain visible for historical analysis.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from competitive.company_repository import CompanyRepository
from competitive.models import CompanyRecord, IntelReportRecord
from db.database import get_db

logger = structlog.get_logger(__name__)

# APIRouter lets us group related routes and mount them in main.py
# prefix="/ci" means all routes here start with /ci
router = APIRouter(prefix="/ci", tags=["Competitive Intelligence"])


# ── Request/Response Schemas ──────────────────────────────────────────────────

class AddCompanyRequest(BaseModel):
    """Request body for adding a new company to track."""
    name:        str  = Field(..., min_length=2, max_length=200, description="Company name (e.g. 'Freshworks')")
    domain:      str  | None = Field(None, description="Website domain (e.g. 'freshworks.com')")
    category:    str  | None = Field(None, description="Industry category (e.g. 'CRM', 'HRMS')")
    description: str  | None = Field(None, description="Brief description of the company")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Freshworks",
                "domain": "freshworks.com",
                "category": "CRM",
                "description": "Cloud-based CRM and customer engagement platform"
            }
        }


class CompanyResponse(BaseModel):
    """Response schema for a single company."""
    id:          str
    name:        str
    domain:      str | None
    category:    str | None
    description: str | None
    active:      bool
    report_count: int = 0

    @classmethod
    def from_record(cls, record: CompanyRecord) -> "CompanyResponse":
        return cls(
            id=record.id,
            name=record.name,
            domain=record.domain,
            category=record.category,
            description=record.description,
            active=record.active,
            report_count=len(record.reports) if record.reports else 0,
        )


class ReportResponse(BaseModel):
    """Response schema for a single intel report."""
    id:           str
    company_id:   str
    company_name: str
    task_id:      str | None
    report_text:  str | None
    signal_level: str
    confidence:   float | None
    slack_sent:   bool
    created_at:   str

    @classmethod
    def from_record(cls, record: IntelReportRecord, company_name: str = "") -> "ReportResponse":
        return cls(
            id=record.id,
            company_id=record.company_id,
            company_name=company_name,
            task_id=record.task_id,
            report_text=record.report_text,
            signal_level=record.signal_level,
            confidence=record.confidence,
            slack_sent=record.slack_sent,
            created_at=record.created_at.isoformat() if record.created_at else "",
        )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/companies", response_model=CompanyResponse, status_code=201)
async def add_company(
    request: AddCompanyRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Add a new company to the competitive intelligence tracking list.

    The company will be included in the next weekly Monday scan.
    To run immediately, use POST /ci/scan-now after adding.
    """
    repo = CompanyRepository(db)
    
    # Check if company already exists
    existing = await repo.get_company_by_name(request.name)
    if existing and existing.active:
        return CompanyResponse.from_record(existing)

    company = await repo.create_company(
        name=request.name,
        domain=request.domain,
        category=request.category,
        description=request.description,
    )
    await db.commit()
    
    # Re-fetch with reports relationship loaded to avoid lazy-loading errors
    company = await repo.get_company(company.id)
    if not company:
        raise HTTPException(status_code=500, detail="Failed to retrieve created company")

    logger.info("Company added for CI tracking", name=request.name, id=company.id)
    return CompanyResponse.from_record(company)


@router.get("/companies", response_model=list[CompanyResponse])
async def list_companies(
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """
    List all tracked companies.

    active_only=true (default): only companies being actively scanned
    active_only=false: include deactivated companies (for history)
    """
    repo = CompanyRepository(db)
    companies = await repo.list_companies(active_only=active_only)
    return [CompanyResponse.from_record(c) for c in companies]


@router.delete("/companies/{company_id}", status_code=200)
async def deactivate_company(
    company_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Deactivate a company — stops future scans but preserves report history.

    WHY DEACTIVATE INSTEAD OF DELETE?
        Hard delete would cascade-delete all CI reports for this company.
        Deactivating preserves historical reports while stopping future scans.
    """
    repo = CompanyRepository(db)
    success = await repo.deactivate_company(company_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")
    await db.commit()
    return {"message": f"Company {company_id} deactivated. Historical reports preserved."}


@router.get("/companies/{company_id}/reports", response_model=list[ReportResponse])
async def get_company_reports(
    company_id: str,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
):
    """Get recent CI reports for a specific company."""
    repo = CompanyRepository(db)

    company = await repo.get_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")

    reports = await repo.get_reports_for_company(company_id, limit=limit)
    return [ReportResponse.from_record(r, company_name=company.name) for r in reports]


@router.post("/scan-now", status_code=202)
async def trigger_scan_now(
    company_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Manually trigger a CI scan immediately.
    company_id: if provided, scan only this company. If None, scan all active companies.
    Returns 202 Accepted immediately — scan runs in background.
    """
    import asyncio
    from competitive.scheduler import scan_company, weekly_ci_scan

    if company_id:
        repo = CompanyRepository(db)
        company = await repo.get_company(company_id)
        if not company:
            raise HTTPException(status_code=404, detail=f"Company {company_id} not found")

        # Scan only the requested company, not all companies
        asyncio.create_task(scan_company(
            company_id=company.id,
            company_name=company.name,
            domain=company.domain,
            category=company.category,
        ))
        return {"message": f"Scan triggered for {company.name}", "status": "running"}
    else:
        asyncio.create_task(weekly_ci_scan())
        return {"message": "Full scan triggered for all active companies", "status": "running"}


@router.get("/reports", response_model=list[ReportResponse])
async def list_all_reports(
    limit: int = 20,
    signal_level: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Get recent CI reports across all companies.

    signal_level filter: "high", "medium", "low", or None (all)
    Useful for: showing a unified dashboard of all recent intelligence.
    """
    from sqlalchemy import select, desc
    from competitive.models import IntelReportRecord, CompanyRecord
    from sqlalchemy.orm import selectinload

    query = (
        select(IntelReportRecord)
        .options(selectinload(IntelReportRecord.company))
        .order_by(desc(IntelReportRecord.created_at))
        .limit(min(limit, 100))
    )
    if signal_level:
        query = query.where(IntelReportRecord.signal_level == signal_level)

    result = await db.execute(query)
    reports = result.scalars().all()

    return [
        ReportResponse.from_record(r, company_name=r.company.name if r.company else "")
        for r in reports
    ]


@router.delete("/reports/all", status_code=200)
async def delete_all_reports(db: AsyncSession = Depends(get_db)):
    """
    Hard delete ALL intel reports from the database.
    Companies are preserved — only the generated reports are removed.
    """
    repo = CompanyRepository(db)
    count = await repo.delete_all_reports()
    await db.commit()
    logger.info("All reports cleared via API", count=count)
    return {"message": f"Deleted {count} report(s) successfully.", "count": count}
