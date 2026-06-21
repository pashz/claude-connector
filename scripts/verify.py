#!/usr/bin/env python3
"""Run benchmark checks against catalog logic and (optionally) a live MCP server."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from catalog.loader import load_catalog
from catalog.recommender import recommend_domains
from catalog.search import get_record_details, search_records

PASS = 0
FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}" + (f" — {detail}" if detail else ""))


def test_catalog_logic() -> None:
    print("\n=== Catalog logic (offline) ===")
    catalog = load_catalog()

    check("Catalog loads 412 domains", len(catalog.records) == 412)

    queries = [
        ("fintech", None),
        ("marketing", "Marketing"),
        ("ai", "Technology"),
    ]
    for query, category in queries:
        result = search_records(catalog, query, category)
        ok = result["count"] > 0 and len(result["results"]) > 0
        check(f"search_domains('{query}', category={category!r}) returns results", ok, str(result.get("count")))

    valid = get_record_details(catalog, "aidevelopers.org")
    check("get_domain_details valid domain", valid.get("found") is True, valid.get("domain", ""))

    missing = get_record_details(catalog, "this-domain-does-not-exist.xyz")
    check(
        "get_domain_details not found",
        missing.get("found") is False and missing.get("error") == "not_found",
    )

    empty = search_records(catalog, "   ")
    check("search_domains empty query", empty.get("error") == "invalid_query")

    sample_config = ROOT / "config.sample.yaml"
    os.environ["DATA_CONFIG"] = str(sample_config)
    sample = load_catalog(sample_config)
    sample_search = search_records(sample, "fintech")
    check("Sample catalog swap loads and searches", sample_search["count"] > 0)
    os.environ.pop("DATA_CONFIG", None)


def test_recommendations() -> None:
    print("\n=== recommend_domains (requires ANTHROPIC_API_KEY) ===")
    catalog = load_catalog()

    if os.environ.get("ANTHROPIC_API_KEY"):
        ideas = [
            "A fintech startup for crypto payment processing",
            "An online store selling vintage teak furniture",
        ]
        for idea in ideas:
            result = recommend_domains(catalog, idea)
            ok = (
                not result.get("error")
                and len(result.get("recommendations", [])) >= 1
                and all(r.get("justification") for r in result["recommendations"])
            )
            domains = [r["domain"] for r in result.get("recommendations", [])]
            detail = result.get("message", "") if result.get("error") else str(domains)
            usage = result.get("usage", {})
            if usage:
                detail += f" | cache_read={usage.get('cache_read_input_tokens', 0)}"
            check(f"recommend_domains({idea[:40]}...)", ok, detail)
    else:
        print("  SKIP  No ANTHROPIC_API_KEY — running mock parser test instead")
        from unittest.mock import MagicMock, patch

        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                type="text",
                text='{"business_summary":"Fintech payments","recommendations":[{"domain":"aidevelopers.org","rank":1,"justification":"Tech brand fit."},{"domain":"antiqueteak.com","rank":2,"justification":"Fallback pick."},{"domain":"affiliatetutorial.com","rank":3,"justification":"Marketing angle."}]}',
            )
        ]

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("catalog.recommender.anthropic.Anthropic") as mock_cls:
                mock_cls.return_value.messages.create.return_value = mock_response
                result = recommend_domains(catalog, "fintech startup")
                ok = len(result.get("recommendations", [])) == 3 and not result.get("error")
                check("recommend_domains mock pipeline", ok, str(result.get("recommendations", [])))


async def test_mcp_auth(base_url: str = "http://127.0.0.1:8000") -> None:
    print("\n=== MCP auth enforcement (live server) ===")
    api_key = os.environ.get("MCP_API_KEY", "")
    if not api_key:
        print("  SKIP  MCP_API_KEY not set — auth enforcement disabled")
        return

    try:
        import httpx
    except ImportError:
        print("  SKIP  httpx not available")
        return

    headers = {"Accept": "application/json, text/event-stream"}
    async with httpx.AsyncClient(base_url=base_url) as client:
        no_auth = await client.post("/mcp", headers=headers)
        check("Missing bearer returns 401", no_auth.status_code == 401, str(no_auth.status_code))

        bad_auth = await client.post(
            "/mcp",
            headers={**headers, "Authorization": "Bearer wrong-key"},
        )
        check("Wrong bearer returns 401", bad_auth.status_code == 401, str(bad_auth.status_code))

        health = await client.get("/health")
        check("Health check stays open without auth", health.status_code == 200, str(health.status_code))


async def test_mcp_client(base_url: str = "http://127.0.0.1:8000/mcp") -> None:
    print("\n=== MCP client (live server) ===")
    try:
        from fastmcp import Client
    except ImportError:
        print("  SKIP  fastmcp Client not available")
        return

    api_key = os.environ.get("MCP_API_KEY") or None
    client_auth = api_key if api_key else None

    try:
        async with Client(base_url, auth=client_auth) as client:
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}
            check("MCP list_tools", {"search_domains", "get_domain_details", "recommend_domains"}.issubset(tool_names))

            search = await client.call_tool("search_domains", {"query": "marketing"})
            search_text = search.content[0].text if search.content else ""
            check("MCP search_domains call", "results" in search_text)

            details = await client.call_tool("get_domain_details", {"domain": "aidevelopers.org"})
            details_text = details.content[0].text if details.content else ""
            check("MCP get_domain_details call", "found" in details_text)
    except Exception as exc:
        check("MCP client connection", False, str(exc))


def main() -> None:
    print("Claude Connector — benchmark verification")
    test_catalog_logic()
    test_recommendations()
    asyncio.run(test_mcp_auth())
    asyncio.run(test_mcp_client())

    print(f"\n=== Summary: {PASS} passed, {FAIL} failed ===")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
