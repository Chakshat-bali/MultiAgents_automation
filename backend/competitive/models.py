"""
competitive/models.py — ORM models for the Competitive Intelligence extension.

NEW TABLE: companies
    Stores the list of competitor companies the user wants to track.
    The weekly scheduler reads this table to know who to research.

NEW TABLE: intel_reports
    Stores each generated competitive intelligence report.
    Linked to a company and to the underlying task in the tasks table.
    This lets us show "history" of reports per company in the UI.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import relationship

from db.database import Base


class CompanyRecord(Base):
    """
    Maps to the 'companies' table.

    WHY TRACK domain SEPARATELY FROM name?
        The domain (e.g. "freshworks.com") is used by the Apify scraper
        to find LinkedIn jobs, G2 reviews, and news about that specific company.
        The name (e.g. "Freshworks") is used in search queries and UI display.
        Having both lets us do precise scraping AND human-readable display.

    WHY category?
        "CRM", "HRMS", "Fintech", etc. — lets users filter the dashboard
        and lets the agent tailor its research prompt ("find competitors in the CRM space").
    """
    __tablename__ = "companies"

    id         = Column(String(36), primary_key=True, index=True)
    name       = Column(String(200), nullable=False)
    domain     = Column(String(200), nullable=True)   # e.g. "freshworks.com"
    category   = Column(String(100), nullable=True)   # e.g. "CRM", "HRMS"
    description= Column(Text, nullable=True)          # one-line about the company
    active     = Column(Boolean, default=True)        # soft delete — deactivate instead of delete
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship — one company has many reports
    reports = relationship("IntelReportRecord", back_populates="company", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Company {self.name} ({self.domain})>"


class IntelReportRecord(Base):
    """
    Maps to the 'intel_reports' table.

    Each time the scheduler runs for a company, it creates:
    1. A task in the tasks table (the underlying LangGraph run)
    2. An IntelReportRecord here (the CI-specific metadata)

    WHY LINK TO tasks table via task_id?
        So we can show the full agent step trace for any CI report.
        The user can click "see how this was generated" and see every
        researcher/summariser step — full transparency.

    signal_level: "high" | "medium" | "low"
        Set by the validator agent based on what it found.
        - high:   funding round, major product launch, executive departure
        - medium: new feature, team expansion, pricing change
        - low:    blog post, conference appearance, routine update
    """
    __tablename__ = "intel_reports"

    id           = Column(String(36), primary_key=True, index=True)
    company_id   = Column(String(36), ForeignKey("companies.id"), nullable=False, index=True)
    task_id      = Column(String(36), nullable=True)  # links to tasks table
    report_text  = Column(Text, nullable=True)         # the final markdown report
    signal_level = Column(String(10), default="low")  # "high" | "medium" | "low"
    confidence   = Column(Float, nullable=True)
    slack_sent   = Column(Boolean, default=False)     # did we send to Slack?
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship back to company
    company = relationship("CompanyRecord", back_populates="reports")

    def __repr__(self):
        return f"<IntelReport company={self.company_id} signal={self.signal_level}>"
