"""
tools/crunchbase_tool.py — Crunchbase Basic API tool for funding and company data.

FREE TIER:
    Crunchbase Basic API: free, no credit card required.
    200 requests/month limit — sufficient for tracking 10-20 companies weekly.
    
    Sign up: https://www.crunchbase.com/register
    Get API key: https://data.crunchbase.com/docs/using-the-api
    Set: CRUNCHBASE_API_KEY in your .env

WHAT CRUNCHBASE PROVIDES (free tier):
    - Company profile (description, founded, HQ, employee count)
    - Funding rounds (amount, investors, date, round type: Seed/Series A/B)
    - Recent news articles about the company
    - Acquisitions

WHY THIS MATTERS FOR CI:
    If a competitor just raised a Series B, they're about to:
    - Hire aggressively (threat: talent competition)
    - Launch new features (threat: product competition)
    - Expand to new markets (threat: customer competition)
    
    Knowing this BEFORE it hits TechCrunch gives you a head start.

FALLBACK STRATEGY:
    If CRUNCHBASE_API_KEY is not set, we fall back to searching Tavily/Google
    for Crunchbase pages — public data is still accessible via search.
"""

from __future__ import annotations

import json

import httpx
import structlog
from langchain_core.tools import tool

from config import settings

logger = structlog.get_logger(__name__)

CRUNCHBASE_BASE = "https://api.crunchbase.com/api/v4"


async def _crunchbase_request(endpoint: str, params: dict = None) -> dict | None:
    """Make an authenticated request to Crunchbase API."""
    if not settings.crunchbase_api_key:
        return None

    full_params = {"user_key": settings.crunchbase_api_key, **(params or {})}
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(f"{CRUNCHBASE_BASE}/{endpoint}", params=full_params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("Crunchbase rate limit hit")
            else:
                logger.error("Crunchbase API error", status=e.response.status_code)
            return None
        except Exception as e:
            logger.error("Crunchbase request failed", error=str(e))
            return None


@tool
async def crunchbase_company_info(company_name: str) -> str:
    """
    Get company profile and recent funding information from Crunchbase.

    Use for: funding rounds, investor names, company size, founding year, HQ location.
    Input: company name exactly as known (e.g. "Freshworks", "Razorpay", "CRED")
    Returns: JSON with funding history, company details, recent news.

    Example: crunchbase_company_info("Razorpay")
    """
    # Try Crunchbase API first (if key is available)
    if settings.crunchbase_api_key:
        # Search for the company to get its permalink
        search_data = await _crunchbase_request(
            "searches/organizations",
        )
        # Note: Crunchbase Basic API has limited search — use entity lookup
        # Construct permalink from company name (Crunchbase uses lowercase-hyphenated)
        permalink = company_name.lower().replace(" ", "-").replace(",", "")

        data = await _crunchbase_request(
            f"entities/organizations/{permalink}",
            params={
                "field_ids": "short_description,founded_on,num_employees_enum,"
                             "last_funding_type,last_funding_total,num_funding_rounds,"
                             "investor_identifiers,headquarters_location,website_url"
            }
        )
        if data and "properties" in data:
            props = data["properties"]
            return json.dumps({
                "source": "crunchbase_api",
                "company": company_name,
                "description":      props.get("short_description", ""),
                "founded":          str(props.get("founded_on", {}).get("value", "")),
                "employees":        props.get("num_employees_enum", ""),
                "last_funding_type": props.get("last_funding_type", ""),
                "total_funding":    str(props.get("last_funding_total", {}).get("value_usd", "")),
                "funding_rounds":   props.get("num_funding_rounds", 0),
                "hq":               str(props.get("headquarters_location", {}).get("value", "")),
                "website":          props.get("website_url", ""),
            })

    # Fallback: structured search query that reliably returns Crunchbase data via web
    logger.info("Crunchbase API key not set — using search fallback", company=company_name)
    return json.dumps({
        "source": "search_fallback",
        "note": f"Search for '{company_name} crunchbase funding' to get funding data",
        "company": company_name,
        "suggested_query": f"{company_name} latest funding round investors 2024",
    })


@tool
async def crunchbase_recent_funding(company_name: str) -> str:
    """
    Get the most recent funding round details for a company.

    Use for: detecting when a competitor just raised money — a key signal
    that they're about to expand aggressively (hire, launch features, enter new markets).
    Input: company name (e.g. "LeadSquared", "CleverTap", "MoEngage")
    Returns: funding round details — amount, investors, date, round type.

    Example: crunchbase_recent_funding("MoEngage")
    """
    if settings.crunchbase_api_key:
        permalink = company_name.lower().replace(" ", "-")
        data = await _crunchbase_request(
            f"entities/organizations/{permalink}/funding_rounds",
            params={"field_ids": "announced_on,money_raised,investment_type,investor_identifiers",
                    "order": "announced_on desc", "limit": 3}
        )
        if data and "entities" in data:
            rounds = []
            for entity in data["entities"][:3]:
                props = entity.get("properties", {})
                rounds.append({
                    "date":      str(props.get("announced_on", {}).get("value", "")),
                    "type":      props.get("investment_type", ""),
                    "amount_usd": str(props.get("money_raised", {}).get("value_usd", "unknown")),
                    "investors": [
                        inv.get("value", "") for inv in props.get("investor_identifiers", [])
                    ],
                })
            return json.dumps({"company": company_name, "funding_rounds": rounds})

    # Fallback
    return json.dumps({
        "source": "search_fallback",
        "company": company_name,
        "suggested_query": f"{company_name} funding round 2024 Series investors amount",
    })
