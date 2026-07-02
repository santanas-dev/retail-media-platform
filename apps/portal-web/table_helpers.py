"""
UI.2.3 — Tables Modernization: pagination, search, table helpers.

SSR-friendly pagination: no JS, query params (page, page_size, q),
template-side slicing for backends without server pagination.

Usage:
    from table_helpers import paginate, search_items, table_context

    items = [...]  # Full list from backend
    ctx = table_context(request, items, search_fields=["username","email"])
    # ctx = {items, page, page_size, total, total_pages, has_prev, has_next,
    #         start_idx, end_idx, query, search_fields, ...}
"""

from typing import Any, Optional, List, Dict, Callable


# ══════════════════════════════════════════════════════════════════════
# Pagination
# ══════════════════════════════════════════════════════════════════════

DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20
ALLOWED_PAGE_SIZES = {20, 50, 100}


def parse_int(value: Any, default: int) -> int:
    """Parse an int from query string, with safe fallback."""
    try:
        val = int(str(value))
        return val
    except (ValueError, TypeError):
        return default


def paginate(
    items: list,
    page: int = DEFAULT_PAGE,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict:
    """Slice a list into a page. Returns metadata dict for template.

    Args:
        items: Full list of items.
        page: 1-indexed page number.
        page_size: Items per page.

    Returns:
        {
            "items": sliced list,
            "page": page (clamped),
            "page_size": page_size,
            "total": total item count,
            "total_pages": total pages,
            "has_prev": bool,
            "has_next": bool,
            "start_idx": 1-indexed start,
            "end_idx": 1-indexed end,
        }
    """
    if page < 1:
        page = DEFAULT_PAGE
    if page_size not in ALLOWED_PAGE_SIZES:
        page_size = DEFAULT_PAGE_SIZE

    total = len(items)
    total_pages = max(1, (total + page_size - 1) // page_size)

    if page > total_pages:
        page = total_pages

    start = (page - 1) * page_size
    end = start + page_size
    sliced = items[start:end]

    start_idx = start + 1 if total > 0 else 0
    end_idx = min(start + len(sliced), total)

    return {
        "rows": sliced,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "start_idx": start_idx,
        "end_idx": end_idx,
    }


# ══════════════════════════════════════════════════════════════════════
# Search
# ══════════════════════════════════════════════════════════════════════

def search_items(
    items: list,
    query: str,
    search_fields: list,
    item_getter: Optional[Callable] = None,
) -> list:
    """Filter items by case-insensitive substring search.

    Args:
        items: List of items (dicts or objects).
        query: Search string. Empty = return all.
        search_fields: List of field names or dot-paths to search.
        item_getter: Optional function to extract searchable text from item.

    Returns:
        Filtered list.
    """
    if not query or not query.strip():
        return items

    q = query.strip().lower()

    def _matches(item):
        if item_getter:
            text = item_getter(item)
            return q in text.lower()

        # Search dict/object fields
        for field in search_fields:
            val = _get_field(item, field)
            if val and q in str(val).lower():
                return True
        return False

    return [item for item in items if _matches(item)]


def _get_field(item: Any, field: str) -> Optional[str]:
    """Get a field from dict or object, supporting dot-paths."""
    parts = field.split(".")
    current = item
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif hasattr(current, part):
            current = getattr(current, part, None)
        else:
            return None
        if current is None:
            return None
    return str(current) if current is not None else None


# ══════════════════════════════════════════════════════════════════════
# Table context builder — search + paginate in one call
# ══════════════════════════════════════════════════════════════════════

def table_context(
    request: Any,
    items: list,
    search_fields: Optional[list] = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    search_param: str = "q",
    page_param: str = "page",
    size_param: str = "page_size",
) -> dict:
    """Build a full table context: search → paginate → metadata.

    Args:
        request: FastAPI Request (for query params).
        items: Full list of items.
        search_fields: Fields to search in.
        page_size: Items per page.

    Returns:
        Paginate result + query, search_fields, page_size, page_sizes list.
    """
    if search_fields is None:
        search_fields = []

    # Parse query params
    query_str = request.query_params.get(search_param, "").strip()
    page = parse_int(request.query_params.get(page_param), DEFAULT_PAGE)
    ps = parse_int(request.query_params.get(size_param), page_size)
    if ps not in ALLOWED_PAGE_SIZES:
        ps = page_size

    # Search
    filtered = search_items(items, query_str, search_fields)

    # Paginate
    result = paginate(filtered, page=page, page_size=ps)

    # Add extra context for templates
    result["query"] = query_str
    result["search_fields"] = search_fields
    result["page_sizes"] = sorted(ALLOWED_PAGE_SIZES)
    result["search_param"] = search_param
    result["page_param"] = page_param
    result["size_param"] = size_param

    return result


# ══════════════════════════════════════════════════════════════════════
# Query string builder — preserve existing params while changing one
# ══════════════════════════════════════════════════════════════════════

def build_query_params(
    request: Any,
    updates: dict,
    page_param: str = "page",
    search_param: str = "q",
    size_param: str = "page_size",
) -> str:
    """Build a query string preserving current params, overriding with updates.

    Args:
        request: FastAPI Request.
        updates: Dict of param overrides (e.g. {"page": "2"}).
               Pass None value to remove a param.
        page_param: Name of the page query param.
        search_param: Name of the search query param.
        size_param: Name of the size query param.

    Returns:
        Query string like "?page=2&q=admin&page_size=20"
    """
    params = {}

    # Preserve existing table params
    for key in (page_param, search_param, size_param):
        val = request.query_params.get(key, "")
        if val:
            params[key] = val

    # Apply updates
    for key, val in updates.items():
        if val is None:
            params.pop(key, None)
        else:
            params[key] = str(val)

    # Build query string from non-empty params
    parts = []
    for key, val in sorted(params.items()):
        # Remove page param when it's page 1 (clean URL)
        if key == page_param and val == "1":
            continue
        if val:
            parts.append(f"{key}={val}")
    if parts:
        return "?" + "&".join(parts)
    return ""
