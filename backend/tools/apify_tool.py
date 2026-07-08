"""
tools/apify_tool.py — Apify web scraping tool for the Competitive Intelligence extension.

WHAT IS APIFY?
    Apify is a cloud web scraping platform. They have hundreds of pre-built
    "Actors" (scrapers) for specific websites — G2, LinkedIn, Google, etc.
    You don't write the scraper — you just call their API with the target URL
    and they return structured JSON.

FREE TIER:
    Apify gives $5/month free credits (as of 2024).
    Typical actor runs cost $0.001–$0.05 per run.
    For a project scraping 10 companies weekly = ~40 runs/month ≈ $0.40.
    Well within the free tier.

    Sign up: https://apify.com (no credit card for free tier)
    Get token: https://console.apify.com/account/integrations

ACTORS WE USE:
    - apify/google-search-scraper  → company news, press mentions
    - bebity/g2-reviews-scraper    → G2 customer reviews
    - apify/web-scraper            → generic page scraper (careers, about)

HOW APIFY ACTOR CALLS WORK:
    1. POST to /acts/{actor-id}/runs  → starts the actor, returns run ID
    2. GET  /acts/{actor-id}/runs/{run-id} → poll until status=SUCCEEDED
    3. GET  /acts/{actor-id}/runs/{run-id}/dataset/items → get the results

    We abstract this into one simple function: apify_scrape(actor_id, input_data)
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx
import structlog
from langchain_core.tools import tool

from config import settings

logger = structlog.get_logger(__name__)

APIFY_BASE = "https://api.apify.com/v2"
APIFY_TIMEOUT_SECONDS = 120   # max time to wait for a scrape job


async def _run_apify_actor(actor_id: str, actor_input: dict) -> list[dict]:
    """
    Run an Apify actor and wait for results.

    This is the core async function — all the @tool functions below call this.

    actor_id:    e.g. "apify~google-search-scraper" (tilde = slash in Apify URLs)
    actor_input: the JSON payload the actor expects (varies per actor)

    Returns: list of result dicts from the actor's dataset
    """
    token = settings.apify_api_token
    if not token:
        logger.warning("APIFY_API_TOKEN not set — returning empty results")
        return []

    headers = {"Content-Type": "application/json"}
    params  = {"token": token}

    dataset_id = None
    async with httpx.AsyncClient(timeout=30) as client:
        # Step 1: Start the actor run
        start_url = f"{APIFY_BASE}/acts/{actor_id}/runs"
        try:
            resp = await client.post(
                start_url, params=params, json=actor_input, headers=headers
            )
            resp.raise_for_status()
            run_data = resp.json()
            run_id   = run_data["data"]["id"]
            dataset_id = run_data["data"].get("defaultDatasetId", run_id)
            logger.info("Apify actor started", actor=actor_id, run_id=run_id, dataset_id=dataset_id)
        except Exception as e:
            logger.error("Failed to start Apify actor", actor=actor_id, error=str(e))
            return []

        # Step 2: Poll for completion (max APIFY_TIMEOUT_SECONDS)
        status_url = f"{APIFY_BASE}/acts/{actor_id}/runs/{run_id}"
        start_time = time.time()
        while True:
            await asyncio.sleep(3)   # poll every 3 seconds
            if time.time() - start_time > APIFY_TIMEOUT_SECONDS:
                logger.warning("Apify actor timed out", run_id=run_id)
                return []
            try:
                poll = await client.get(status_url, params=params)
                poll.raise_for_status()
                status = poll.json()["data"]["status"]
                if status == "SUCCEEDED":
                    break
                elif status in ("FAILED", "ABORTED", "TIMED-OUT"):
                    logger.error("Apify actor failed", status=status, run_id=run_id)
                    return []
                # status = "RUNNING" or "READY" — keep polling
            except Exception as e:
                logger.error("Error polling Apify run", error=str(e))
                return []

        # Step 3: Fetch dataset items
        target_id = dataset_id if dataset_id else run_id
        items_url = f"{APIFY_BASE}/datasets/{target_id}/items"
        try:
            items_resp = await client.get(items_url, params={**params, "format": "json"})
            items_resp.raise_for_status()
            items = items_resp.json()
            logger.info("Apify results fetched", actor=actor_id, count=len(items))
            return items
        except Exception as e:
            logger.error("Failed to fetch Apify results", error=str(e))
            return []


@tool
async def apify_google_search(query: str, max_results: int = 5) -> str:
    """
    Search Google for news and information about a company using Apify.

    Use for: company news, press releases, funding announcements, product launches.
    Input: a specific search query like "Freshworks funding 2024" or "Zoho new features"
    Returns: JSON string with search results including title, URL, snippet.

    Example: apify_google_search("PolicyBazaar product launch 2024", max_results=5)
    """
    try:
        actor_input = {
            "queries": query,
            "maxPagesPerQuery": 1,
            "resultsPerPage": max_results,
            "mobileResults": False,
            "languageCode": "en",
            "countryCode": "in",    # India-focused results
        }
        items = await _run_apify_actor("apify~google-search-scraper", actor_input)

        # Extract useful fields
        results = []
        for item in items[:max_results]:
            for organic in item.get("organicResults", [])[:max_results]:
                results.append({
                    "title":   organic.get("title", ""),
                    "url":     organic.get("url", ""),
                    "snippet": organic.get("description", ""),
                })

        if not results:
            return json.dumps({"error": "No results found", "query": query})
        return json.dumps({"results": results, "count": len(results), "query": query})

    except Exception as e:
        logger.error("apify_google_search failed", error=str(e))
        return json.dumps({"error": str(e), "query": query})


@tool
async def apify_g2_reviews(company_name: str, max_reviews: int = 5) -> str:
    """
    Scrape recent G2 customer reviews for a company using Apify.

    Use for: understanding customer sentiment, common complaints, praised features.
    Input: exact company name as it appears on G2 (e.g. "Freshworks", "Zoho CRM")
    Returns: JSON with recent reviews including rating, title, pros, cons.

    Example: apify_g2_reviews("Freshworks CRM", max_reviews=5)
    """
    try:
        actor_input = {
            "companyName": company_name,
            "maxReviews": max_reviews,
            "sortBy": "most_recent",
        }
        items = await _run_apify_actor("zhorex~g2-reviews-scraper", actor_input)

        reviews = []
        for item in items[:max_reviews]:
            reviews.append({
                "rating":     item.get("rating", 0),
                "title":      item.get("reviewTitle", ""),
                "pros":       item.get("reviewPros", ""),
                "cons":       item.get("reviewCons", ""),
                "reviewer":   item.get("reviewerTitle", ""),
                "date":       item.get("reviewDate", ""),
            })

        if not reviews:
            # Fallback: search for G2 reviews via Google
            return json.dumps({
                "note": "G2 scraper returned no results — try apify_google_search with 'site:g2.com {company}'",
                "company": company_name
            })
        return json.dumps({"reviews": reviews, "count": len(reviews), "company": company_name})

    except Exception as e:
        logger.error("apify_g2_reviews failed", error=str(e))
        return json.dumps({"error": str(e), "company": company_name})


@tool
async def apify_scrape_page(url: str) -> str:
    """
    Scrape the text content of any public webpage using Apify.

    Use for: company career pages, press/news pages, about pages, product pages.
    Input: full URL of the page to scrape
    Returns: cleaned text content of the page (first 3000 chars).

    Example: apify_scrape_page("https://freshworks.com/careers/")
    """
    try:
        actor_input = {
            "startUrls": [{"url": url}],
            "maxCrawlDepth": 0,           # just the one page, no following links
            "maxCrawlPages": 1,
            "pageFunction": """async function pageFunction(context) {
                const { page, request } = context;
                const title = await page.title();
                const text = await page.evaluate(() => document.body.innerText);
                return { url: request.url, title, text: text.slice(0, 3000) };
            }""",
        }
        items = await _run_apify_actor("apify~web-scraper", actor_input)

        if not items:
            return json.dumps({"error": "Could not scrape page", "url": url})

        item = items[0]
        return json.dumps({
            "url":   item.get("url", url),
            "title": item.get("title", ""),
            "text":  item.get("text", "")[:3000],
        })

    except Exception as e:
        logger.error("apify_scrape_page failed", error=str(e))
        return json.dumps({"error": str(e), "url": url})
