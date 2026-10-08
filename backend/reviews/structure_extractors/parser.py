"""Publisher-independent Structure discovery. This module never accesses Catalog or Selenium."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urldefrag

from bs4 import BeautifulSoup, Tag

_COUNT = re.compile(r"(?:\(|（)?\s*(\d{1,4})\s*(?:Titles?|Books?|Volumes?|册|本|种)\s*(?:\)|）)?", re.I)
_BAD_SECTIONS = ("you might also like", "related books", "other series", "recommended for you",
                 "people also bought", "猜你喜欢", "相关推荐", "其他系列", "更多推荐")
_BAD_LINKS = ("/cart", "/account", "/search", "/login", "/privacy", "/terms",
              "/collections/all", "/categories/", "/authors/", "/social/")
_BOOK_URL = re.compile(r"/(?:books?/|titles?/|products?/|book/|product/|works?/)", re.I)


@dataclass(frozen=True)
class PageSnapshot:
    url: str
    title: str
    html: str


def _plain(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def _absolute(base: str, value: str | None) -> str | None:
    if not value or value.startswith(("data:", "javascript:", "mailto:", "#")):
        return None
    result, _ = urldefrag(urljoin(base or "https://invalid.example/", value))
    return result if urlsplit(result).scheme in {"http", "https"} else None


def _image_url(node: Tag, base: str) -> str | None:
    image = node.find("img")
    if image is None:
        return None
    for attr in ("data-src", "data-original", "data-lazy-src", "src"):
        found = _absolute(base, image.get(attr))
        if found:
            return found
    srcset = image.get("srcset", "")
    return _absolute(base, srcset.split(",")[0].strip().split(" ")[0] if srcset else "")


def _url_ok(url: str, base: str) -> bool:
    dest = urlsplit(url)
    origin = urlsplit(base)
    if not dest.hostname or dest.hostname != origin.hostname:
        return False
    path = dest.path.lower().rstrip("/")
    if not path or path == origin.path.lower().rstrip("/"):
        return False
    if any(token in path for token in _BAD_LINKS):
        return False
    return True


def _item_from_node(node: Tag, base: str, source: str) -> dict | None:
    choices = []
    for anchor in node.find_all("a", href=True):
        url = _absolute(base, anchor.get("href"))
        if not url or not _url_ok(url, base):
            continue
        title = _plain(anchor.get_text(" ", strip=True))
        image = anchor.find("img")
        if not title and image:
            title = _plain(image.get("alt") or image.get("title"))
        if not title or len(title) > 180 or title.casefold() in {"view", "more", "details", "buy", "shop", "read more", "learn more"}:
            continue
        choices.append((bool(_BOOK_URL.search(urlsplit(url).path)), len(title), title, url))
    if not choices:
        return None
    choices.sort(key=lambda x: (-int(x[0]), -x[1]))
    _, _, title, url = choices[0]
    return {"title": title, "url": url, "image": _image_url(node, base),
            "position": None, "source_kind": source, "confidence": 0.7}


def _flatten_schemas(value: object):
    if isinstance(value, list):
        for row in value:
            yield from _flatten_schemas(row)
    if not isinstance(value, dict):
        return
    yield value
    for key in ("@graph", "mainEntity", "itemListElement"):
        if key in value:
            yield from _flatten_schemas(value[key])


def _ld_members(html: BeautifulSoup, url: str) -> tuple[list[dict], int | None] | None:
    for script in html.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except (ValueError, TypeError):
            continue
        for entity in _flatten_schemas(data):
            kinds = entity.get("@type") or []
            kinds = [kinds] if isinstance(kinds, str) else kinds
            if "BreadcrumbList" in kinds:
                continue
            if not any(kind in {"ItemList", "BookSeries", "CollectionPage"} for kind in kinds):
                continue
            entries = entity.get("itemListElement") or entity.get("hasPart") or []
            if isinstance(entries, dict):
                entries = [entries]
            members = []
            for n, row in enumerate(entries, 1):
                if not isinstance(row, dict):
                    continue
                target = row.get("item") if isinstance(row.get("item"), dict) else row
                title = _plain(row.get("name") or target.get("name"))
                link = _absolute(url, row.get("url") or target.get("url") or target.get("@id"))
                if not title or not link or not _url_ok(link, url):
                    continue
                pos = row.get("position")
                pos = int(pos) if str(pos).isdigit() else None
                image = target.get("image")
                if isinstance(image, dict):
                    image = image.get("url")
                if isinstance(image, list):
                    image = next((x for x in image if isinstance(x, str)), None)
                members.append({"title": title, "url": link, "image": _absolute(url, image),
                                "position": pos, "source_kind": "browser", "confidence": 0.98})
            if len(members) >= 2:
                count = entity.get("numberOfItems")
                count = int(count) if str(count).isdigit() else None
                return members, count
    return None


def _nearby_heading(node: Tag) -> tuple[str, int | None, bool]:
    heading = node.find_previous(["h1", "h2", "h3", "h4"])
    if not heading:
        return "", None, False
    label = _plain(heading.get_text(" ", strip=True))
    match = _COUNT.search(label)
    count = int(match.group(1)) if match else None
    is_bad = any(x in label.casefold() for x in _BAD_SECTIONS)
    return label, count, is_bad


def _dom_groups(soup: BeautifulSoup, base: str) -> list[dict]:
    groups = []
    # Analyze sibling sets, rather than CSS class names. Cards may be div, li or article.
    for parent in soup.find_all(["section", "ul", "ol", "div", "main", "article"]):
        if parent.find_parent(["nav", "footer", "header"]) or parent.name in {"nav", "footer"}:
            continue
        children = [x for x in parent.find_all(recursive=False) if isinstance(x, Tag)]
        if not 2 <= len(children) <= 120:
            continue
        members = []
        for child in children:
            member = _item_from_node(child, base, "browser")
            if member is not None:
                members.append(member)
        # Require distinct item URLs. One card may have multiple anchors to the same work.
        unique = {m["url"]: m for m in members}
        members = list(unique.values())
        if len(members) < 2:
            continue
        label, declared, bad = _nearby_heading(parent)
        shape = [child.name for child in children]
        repeat = max(shape.count(name) for name in set(shape)) / len(shape)
        book_urls = sum(bool(_BOOK_URL.search(urlsplit(m["url"]).path)) for m in members)
        images = sum(bool(m.get("image")) for m in members)
        score = 0.22 + 0.20 * repeat + 0.20 * book_urls / len(members)
        score += 0.12 * images / len(members)
        score += 0.12 if re.search(r"series|titles|books|level|stage|套装|系列|册|本", label, re.I) else 0
        score += 0.16 if declared is not None and declared == len(members) else 0
        score -= 0.38 if bad else 0
        score -= 0.14 if len(members) * 2 < len(children) else 0
        score = min(0.99, max(0, round(score, 3)))
        groups.append({"members": members, "title": label, "declared_count": declared,
                       "confidence": score, "bad_section": bad})
    return sorted(groups, key=lambda g: (g["confidence"], len(g["members"])), reverse=True)


def _dedupe(items: list[dict]) -> list[dict]:
    result = []
    urls = set()
    titles_without_urls = set()
    for row in items:
        url = row.get("url")
        key = url.casefold() if url else _plain(row.get("title")).casefold()
        if not key or (key in urls if url else key in titles_without_urls):
            continue
        (urls if url else titles_without_urls).add(key)
        result.append(row)
    return result


def extract_structure(snapshot: PageSnapshot, *, html_fragment: str | None = None) -> dict:
    base = snapshot.url
    html = BeautifulSoup(html_fragment if html_fragment is not None else snapshot.html, "html.parser")
    if html_fragment is None:
        ld = _ld_members(html, base)
        if ld:
            members, declared = ld
            members = _dedupe(members)
            return {"members": members, "group": {"title": snapshot.title, "declared_count": declared},
                    "declared_count": declared, "diagnostics": {
                        "strategy": "json_ld", "candidate_group_count": 1, "candidate_link_count": len(members),
                        "accepted_member_count": len(members), "confidence": 0.98, "messages": []}}
    groups = _dom_groups(html, base)
    winner = groups[0] if groups else None
    # A confident candidate group is shown for human review, never auto-committed.
    members = _dedupe(winner["members"]) if winner and winner["confidence"] >= 0.40 else []
    declared = winner["declared_count"] if winner else None
    return {"members": members, "group": {k: winner[k] for k in ("title", "declared_count")} if winner else None,
            "declared_count": declared, "diagnostics": {
                "strategy": "selected_dom" if html_fragment is not None else "generic_dom",
                "candidate_group_count": len(groups),
                "candidate_link_count": len(winner["members"]) if winner else 0,
                "accepted_member_count": len(members),
                "confidence": winner["confidence"] if winner else 0,
                "messages": [] if members else ["未可靠识别成员列表，请尝试选择网页区域、粘贴 HTML 或 URL 列表。"]}}


def extract_url_list(urls: list[str]) -> dict:
    if not 1 <= len(urls) <= 500:
        raise ValueError("请提供 1–500 条 URL")
    members = []
    for url in urls:
        url = url.strip()
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
            raise ValueError("链接必须是有效的 http(s) URL")
        label = parsed.path.rstrip("/").split("/")[-1].replace("-", " ").replace("_", " ")
        members.append({"title": _plain(label) or parsed.hostname, "url": url, "image": None,
                        "position": None, "source_kind": "url_list", "confidence": 0.4})
    members = _dedupe(members)
    return {"members": members, "group": None, "declared_count": None,
            "diagnostics": {"strategy": "url_list", "candidate_group_count": 1,
                            "candidate_link_count": len(urls), "accepted_member_count": len(members),
                            "confidence": 0.4, "messages": ["链接标题来自 URL，请确认或修改后再暂存。"]}}
