"""Tools package — exports all tools available to agents."""
from tools.search_tool import web_search
from tools.retriever_tool import retrieve_from_memory
from tools.file_tool import read_file, write_file
from tools.apify_tool import apify_google_search, apify_g2_reviews, apify_scrape_page
from tools.crunchbase_tool import crunchbase_company_info, crunchbase_recent_funding
from tools.slack_tool import send_slack_digest

# General-purpose tools (original project)
ALL_TOOLS = [web_search, retrieve_from_memory, read_file, write_file]

# Competitive Intelligence tools (extension)
CI_TOOLS = [
    apify_google_search,
    apify_g2_reviews,
    apify_scrape_page,
    crunchbase_company_info,
    crunchbase_recent_funding,
    send_slack_digest,
]

# Full tool set — agents get all tools
ALL_TOOLS_EXTENDED = ALL_TOOLS + CI_TOOLS

__all__ = [
    "web_search", "retrieve_from_memory", "read_file", "write_file",
    "apify_google_search", "apify_g2_reviews", "apify_scrape_page",
    "crunchbase_company_info", "crunchbase_recent_funding", "send_slack_digest",
    "ALL_TOOLS", "CI_TOOLS", "ALL_TOOLS_EXTENDED",
]
