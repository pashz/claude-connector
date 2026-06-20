"""Claude-powered recommendations over the loaded catalog."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import anthropic

from catalog.loader import Catalog

CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")
MAX_TOKENS = 1024


def _portfolio_lines(catalog: Catalog) -> str:
    return "\n".join(
        f"- {record.id} | {record.category} | {', '.join(record.tags)}"
        for record in catalog.records
    )


def _build_system_prompt(catalog: Catalog) -> str:
    return f"""You are a domain portfolio advisor with access to {len(catalog.records)} curated domains.

When given a business idea:
1. Identify the niche, audience, and brand positioning
2. Select exactly the top 3 best-matching domains from the portfolio below
3. Return ONLY valid JSON (no markdown fences) in this shape:
{{
  "business_summary": "one sentence restatement of the idea",
  "recommendations": [
    {{"domain": "example.com", "rank": 1, "justification": "brief reason"}},
    {{"domain": "other.com", "rank": 2, "justification": "brief reason"}},
    {{"domain": "third.com", "rank": 3, "justification": "brief reason"}}
  ]
}}

Rules:
- Only recommend domains that appear in the portfolio
- Justifications must be one sentence each
- If nothing is a close match, pick the closest options and say so in the justification

PORTFOLIO:
{_portfolio_lines(catalog)}"""


def _parse_recommendation_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    return json.loads(cleaned)


def recommend_domains(catalog: Catalog, business_idea: str) -> dict[str, Any]:
    if not business_idea or not business_idea.strip():
        return {
            "error": "invalid_input",
            "message": "business_idea must be a non-empty string.",
            "recommendations": [],
        }

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "error": "missing_api_key",
            "message": "ANTHROPIC_API_KEY is not configured on the server.",
            "recommendations": [],
        }

    client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=MAX_TOKENS,
            system=_build_system_prompt(catalog),
            messages=[
                {
                    "role": "user",
                    "content": business_idea.strip(),
                }
            ],
        )
    except anthropic.APIError as exc:
        return {
            "error": "claude_api_error",
            "message": str(exc),
            "recommendations": [],
        }

    text_blocks = [
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ]
    raw_text = "\n".join(text_blocks).strip()

    if not raw_text:
        return {
            "error": "empty_response",
            "message": "Claude returned an empty response.",
            "recommendations": [],
        }

    try:
        parsed = _parse_recommendation_json(raw_text)
    except json.JSONDecodeError:
        return {
            "error": "parse_error",
            "message": "Could not parse Claude response as JSON.",
            "raw_response": raw_text,
            "recommendations": [],
        }

    recommendations = parsed.get("recommendations", [])
    validated: list[dict[str, Any]] = []

    for item in recommendations:
        if not isinstance(item, dict):
            continue
        domain = str(item.get("domain", "")).strip().lower()
        if domain not in catalog.records_by_id:
            continue
        record = catalog.records_by_id[domain]
        validated.append(
            {
                "domain": record.id,
                "rank": item.get("rank"),
                "justification": item.get("justification", ""),
                "category": record.category,
                "tags": record.tags,
            }
        )

    return {
        "business_summary": parsed.get("business_summary", ""),
        "recommendations": validated[:3],
        "model": CLAUDE_MODEL,
    }
