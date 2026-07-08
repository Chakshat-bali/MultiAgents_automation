"""
competitive/company_repository.py — DB operations for companies and intel reports.

WHY A SEPARATE REPOSITORY?
    The existing TaskRepository handles tasks.
    CompanyRepository handles companies + intel reports.
    Each repository owns exactly one domain — single responsibility.
    If we add a third feature later, it gets its own repository.

PATTERN:
    All methods are async — they use await for every DB call.
    Methods return ORM objects or None — never raise on "not found".
    Callers decide what to do with None (raise HTTPException, etc.)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from competitive.models import CompanyRecord, IntelReportRecord

logger = structlog.get_logger(__name__)


class CompanyRepository:
    """All database operations for companies and intel reports."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ── Company CRUD ──────────────────────────────────────────────────────────

    async def create_company(
        self,
        name: str,
        domain: str | None = None,
        category: str | None = None,
        description: str | None = None,
    ) -> CompanyRecord:
        """Insert a new company record."""
        company = CompanyRecord(
            id=str(uuid.uuid4()),
            name=name,
            domain=domain,
            category=category,
            description=description,
            active=True,
        )
        self.session.add(company)
        await self.session.flush()   # gets DB-generated values without committing
        logger.info("Company created", name=name, id=company.id)
        return company

    async def get_company(self, company_id: str) -> Optional[CompanyRecord]:
        """Fetch a single company by ID. Returns None if not found."""
        result = await self.session.execute(
            select(CompanyRecord)
            .options(selectinload(CompanyRecord.reports))
            .where(CompanyRecord.id == company_id)
        )
        return result.scalar_one_or_none()

    async def get_company_by_name(self, name: str) -> Optional[CompanyRecord]:
        """Fetch a single company by name (case-insensitive)."""
        result = await self.session.execute(
            select(CompanyRecord)
            .options(selectinload(CompanyRecord.reports))
            .where(CompanyRecord.name.ilike(name))
        )
        return result.scalars().first()

    async def list_companies(self, active_only: bool = True) -> list[CompanyRecord]:
        """
        List all companies, optionally filtered to active only.

        WHY selectinload?
            By default SQLAlchemy uses lazy loading — accessing company.reports
            would trigger a NEW query. In async code, lazy loading is forbidden
            (you can't run sync queries in an async context).
            selectinload tells SQLAlchemy to fetch reports in the SAME query
            using a SELECT ... IN (...) strategy. No extra roundtrips.
        """
        query = select(CompanyRecord).options(selectinload(CompanyRecord.reports))
        if active_only:
            query = query.where(CompanyRecord.active == True)
        query = query.order_by(CompanyRecord.created_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def deactivate_company(self, company_id: str) -> bool:
        """
        Soft delete — sets active=False instead of deleting.

        WHY SOFT DELETE?
            Hard deleting a company would also delete all its intel reports
            (cascade delete). But those reports are valuable history.
            Soft delete preserves history while hiding the company from active tracking.
        """
        result = await self.session.execute(
            update(CompanyRecord)
            .where(CompanyRecord.id == company_id)
            .values(active=False)
        )
        return result.rowcount > 0

    # ── Intel Report operations ───────────────────────────────────────────────

    async def create_report(
        self,
        company_id: str,
        task_id: str,
        report_text: str,
        signal_level: str = "low",
        confidence: float = 0.5,
    ) -> IntelReportRecord:
        """Save a completed CI report after the agent finishes."""
        report = IntelReportRecord(
            id=str(uuid.uuid4()),
            company_id=company_id,
            task_id=task_id,
            report_text=report_text,
            signal_level=signal_level,
            confidence=confidence,
            slack_sent=False,
        )
        self.session.add(report)
        await self.session.flush()
        logger.info("Intel report created", company_id=company_id, signal=signal_level)
        return report

    async def mark_slack_sent(self, report_id: str) -> None:
        """Mark a report as sent to Slack — prevents duplicate sends."""
        await self.session.execute(
            update(IntelReportRecord)
            .where(IntelReportRecord.id == report_id)
            .values(slack_sent=True)
        )

    async def get_reports_for_company(
        self, company_id: str, limit: int = 10
    ) -> list[IntelReportRecord]:
        """Get recent intel reports for a company, newest first."""
        result = await self.session.execute(
            select(IntelReportRecord)
            .where(IntelReportRecord.company_id == company_id)
            .order_by(IntelReportRecord.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def delete_all_reports(self) -> int:
        """Hard delete ALL intel reports from the database. Returns count deleted."""
        from sqlalchemy import delete as sql_delete
        result = await self.session.execute(sql_delete(IntelReportRecord))
        count = result.rowcount
        logger.info("All intel reports deleted", count=count)
        return count
