"""
Remote MCP server for domain portfolio tools.

Transport: Streamable HTTP (deployable, network-accessible).
Data source: config.yaml — swap path + field mapping for a new client catalog.
"""

from __future__ import annotations

import os
import sys
from typing import Any

from dotenv import load_dotenv
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse

from auth import build_http_middleware
from catalog.loader import Catalog, CatalogError, load_catalog
from catalog.recommender import recommend_domains as run_recommendation
from catalog.search import get_record_details, search_records

load_dotenv()

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))
MCP_API_KEY = os.environ.get("MCP_API_KEY", "")

try:
    CATALOG: Catalog = load_catalog()
except CatalogError as exc:
    print(f"Failed to load catalog: {exc}", file=sys.stderr)
    sys.exit(1)

mcp = FastMCP(
    name="Claude Connector — Domain Portfolio",
    instructions=(
        "Tools for searching and recommending domains from a curated portfolio. "
        "Use search_domains for keyword lookup, get_domain_details for a single record, "
        "and recommend_domains for AI-matched suggestions from a business description."
    ),
)

HTTP_MIDDLEWARE = build_http_middleware(MCP_API_KEY)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(_request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "catalog_records": len(CATALOG.records),
            "record_type": CATALOG.record_type,
        }
    )


@mcp.custom_route("/", methods=["GET"])
async def root(_request: Request) -> PlainTextResponse:
    return PlainTextResponse(
        "Claude Connector MCP server. MCP endpoint: /mcp | Health: /health"
    )


@mcp.tool
def search_domains(query: str, category: str | None = None) -> dict[str, Any]:
    """Search the domain portfolio by keyword and optional category filter.

    Args:
        query: Keywords matched against domain name, category, and tags.
        category: Optional category filter (e.g. "Technology", "Marketing", "Fintech").

    Returns:
        Ranked list of matching domains with relevance scores.
    """
    if not query or not query.strip():
        return {
            "error": "invalid_query",
            "message": "Query must be a non-empty string.",
            "results": [],
        }
    return search_records(CATALOG, query=query, category=category)


@mcp.tool
def get_domain_details(domain: str) -> dict[str, Any]:
    """Return full metadata for a single domain in the portfolio.

    Args:
        domain: Exact domain name (e.g. "aidevelopers.org").

    Returns:
        Full record metadata, or a structured not-found response.
    """
    return get_record_details(CATALOG, domain=domain)


@mcp.tool
async def recommend_domains(business_idea: str) -> dict[str, Any]:
    """Recommend the top 3 portfolio domains for a free-text business description.

    Uses Claude to reason over category, tags, and brand fit across the full portfolio.

    Args:
        business_idea: Plain-language description of the business, product, or brand.

    Returns:
        Top 3 domain recommendations with brief justifications.
    """
    if not business_idea or not business_idea.strip():
        return {
            "error": "invalid_input",
            "message": "business_idea must be a non-empty string.",
            "recommendations": [],
        }
    return run_recommendation(CATALOG, business_idea=business_idea)


if __name__ == "__main__":
    print(f"Starting MCP server on {HOST}:{PORT} ({len(CATALOG.records)} records loaded)")
    if MCP_API_KEY:
        print("MCP_API_KEY is set — /mcp requires Authorization: Bearer <key>")
    else:
        print("MCP_API_KEY is not set — /mcp is open (set MCP_API_KEY in production)")
    mcp.run(transport="http", host=HOST, port=PORT, middleware=HTTP_MIDDLEWARE)
