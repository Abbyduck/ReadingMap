"""Keep explicit Capture actions scoped to the most recent provider search."""

_search_tabs: dict[str, tuple[str, set[str]]] = {}


def remember_search(provider: str, page: dict, pages: list[dict]) -> None:
    tab_id = page.get("id")
    if tab_id:
        _search_tabs[provider] = (tab_id, {row["id"] for row in pages if row.get("id")})


def capture_tabs(provider: str, pages: list[dict]) -> list[dict]:
    session = _search_tabs.get(provider)
    if not session:
        return pages
    search_id, known_ids = session
    return [page for page in pages if page.get("id") == search_id
            or page.get("openerId") == search_id
            or (page.get("id") and page["id"] not in known_ids)]
