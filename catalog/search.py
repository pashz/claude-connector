"""Keyword search and record lookup — no external API calls."""

from __future__ import annotations

from typing import Any

from catalog.loader import Catalog, CatalogRecord


def _record_to_result(record: CatalogRecord, score: int) -> dict[str, Any]:
    return {
        "domain": record.id,
        "category": record.category,
        "tags": record.tags,
        "score": score,
        **{k: v for k, v in record.metadata.items() if k not in ("domain", "category", "tags")},
    }


def search_records(
    catalog: Catalog,
    query: str,
    category: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    if not query or not query.strip():
        return {
            "error": "invalid_query",
            "message": "Query must be a non-empty string.",
            "results": [],
        }

    query_lower = query.strip().lower()
    category_filter = category.strip().lower() if category else None

    scored: list[tuple[int, CatalogRecord]] = []
    for record in catalog.records:
        if category_filter and record.category.lower() != category_filter:
            continue

        score = 0
        if query_lower in record.id:
            score += 3
        if query_lower in record.category.lower():
            score += 2
        for tag in record.tags:
            if query_lower in tag.lower():
                score += 1

        if score > 0:
            scored.append((score, record))

    scored.sort(key=lambda item: item[0], reverse=True)
    results = [_record_to_result(record, score) for score, record in scored[:limit]]

    return {
        "query": query,
        "category": category,
        "count": len(results),
        "results": results,
    }


def get_record_details(catalog: Catalog, domain: str) -> dict[str, Any]:
    if not domain or not domain.strip():
        return {
            "error": "invalid_input",
            "message": "Domain must be a non-empty string.",
            "found": False,
        }

    lookup = domain.strip().lower()
    record = catalog.records_by_id.get(lookup)

    if record is None:
        return {
            "error": "not_found",
            "message": f"No record found for '{domain.strip()}'.",
            "domain": domain.strip(),
            "found": False,
        }

    return {
        "found": True,
        "domain": record.id,
        "category": record.category,
        "tags": record.tags,
        "details": record.metadata,
    }
