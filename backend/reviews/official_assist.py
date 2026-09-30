"""Browser-assisted capture for already identified official publisher pages."""
from __future__ import annotations

from contextlib import suppress
import json
import re
import time
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit
from urllib.request import Request, urlopen

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from .amazon_assist import (
    _browser_is_running,
    _browser_lock,
    _chrome_binary,
    _chromedriver_binary,
    _debug_port,
    _devtools_json,
    _launch_chrome_url,
    _normalize_search_query,
    _wait_for_browser,
)
from .browser_session import capture_tabs, remember_search


class OfficialAssistError(RuntimeError):
    pass


_OFFICIAL_IGNORED_HOSTS = (
    "google.", "amazon.", "jd.com", "bing.com", "baidu.com",
    "localhost", "127.0.0.1",
)


def _title_tokens(value: str) -> set[str]:
    ignored = {"the", "and", "of", "a", "an", "official", "publisher", "book", "books", "series"}
    return {
        token.casefold()
        for token in re.findall(r"[A-Za-z0-9]+", _normalize_search_query(value))
        if len(token) > 1 and token.casefold() not in ignored
    }


def _is_official_candidate_page(page: dict, expected_titles) -> bool:
    url = str(page.get("url") or "")
    parsed = urlsplit(url)
    host = parsed.netloc.casefold()
    if page.get("type") != "page" or parsed.scheme not in {"http", "https"}:
        return False
    if any(ignored in host for ignored in _OFFICIAL_IGNORED_HOSTS):
        return False
    expected_sets = [_title_tokens(title) for title in expected_titles if _title_tokens(title)]
    if not expected_sets:
        return True
    actual = _title_tokens(f"{page.get('title', '')} {unquote(parsed.path)}")
    return any(expected & actual for expected in expected_sets)


def _current_official_page(expected_titles):
    try:
        pages = _devtools_json("/json")
    except Exception as error:
        raise OfficialAssistError("无法读取官网辅助浏览器。") from error
    for page in capture_tabs("official", pages):
        if _is_official_candidate_page(page, expected_titles):
            return page
    raise OfficialAssistError("没有找到与当前审核项匹配的官网页面；请先从 Google 结果打开出版社或作者官网。")


def _google_search_page(query: str):
    try:
        pages = _devtools_json("/json")
    except Exception:
        return None
    for page in pages:
        parsed = urlsplit(page.get("url", ""))
        values = parse_qs(parsed.query).get("q", [])
        if page.get("type") == "page" and "google." in parsed.netloc.casefold() and values and values[0].casefold() == query.casefold():
            return page
    return None


def _open_search_in_running_browser(search_url: str) -> None:
    """Open the search in the debuggable Chrome, not a different Chrome window."""
    endpoint = f"http://127.0.0.1:{_debug_port()}"
    request = Request(f"{endpoint}/json/new?{quote(search_url, safe='')}", method="PUT")
    with urlopen(request, timeout=5) as response:
        page = json.load(response)
    if page.get("id"):
        with urlopen(f"{endpoint}/json/activate/{page['id']}", timeout=5):
            pass


def open_official_search(query: str) -> dict:
    """Open Google in the same reusable Chrome used by retailer capture."""
    normalized = _normalize_search_query(query)
    if not normalized:
        raise OfficialAssistError("当前审核对象没有可搜索的名称。")
    if not re.search(r"\b(?:official|publisher)\b", normalized, re.IGNORECASE):
        normalized = f"{normalized} official publisher"
    search_url = "https://www.google.com/search?" + urlencode({"q": normalized})
    binary = _chrome_binary()
    if not binary:
        raise OfficialAssistError("未找到 Google Chrome，无法启动官网辅助采集。")
    with _browser_lock:
        reused = _browser_is_running()
        try:
            if not reused:
                _launch_chrome_url(binary, search_url)
                _wait_for_browser()
            else:
                _open_search_in_running_browser(search_url)
            deadline = time.monotonic() + 12
            page = None
            while time.monotonic() < deadline:
                page = _google_search_page(normalized)
                if page:
                    break
                time.sleep(0.25)
            if not page:
                raise OfficialAssistError("搜索页未出现在官网采集浏览器中；请重试。此次未启动自动采集。")
            try:
                remember_search("official", page, _devtools_json("/json"))
            except Exception:
                pass
        except OfficialAssistError:
            raise
        except Exception as error:
            raise OfficialAssistError(f"官网搜索浏览器启动失败：{error}") from error
    return {
        "query": normalized,
        "search_url": search_url,
        "session_reused": reused,
        "current_url": (page or {}).get("url", search_url),
        "page_title": (page or {}).get("title", ""),
    }


def official_browser_status(expected_query: str = "", alternate_titles=None) -> dict:
    """Report when the reviewer has navigated from Google to a matching site."""
    with _browser_lock:
        if not _browser_is_running():
            return {
                "provider": "official", "connected": False, "state": "disconnected",
                "current_url": "", "product_title": "", "product_id": "",
                "capture_ready": False, "message": "官网辅助浏览器未连接",
            }
        titles = [expected_query, *(alternate_titles or [])]
        try:
            page = _current_official_page(titles)
        except OfficialAssistError:
            page = None
        if page:
            return {
                "provider": "official", "connected": True, "state": "official_detail",
                "current_url": page.get("url", ""), "product_title": page.get("title", "").strip(),
                "product_id": "", "capture_ready": True,
                "message": "已识别官网页面，可点击 Capture 采集",
            }
        return {
            "provider": "official", "connected": True, "state": "search_results",
            "current_url": "", "product_title": "", "product_id": "",
            "capture_ready": False, "message": "Google 结果已就绪，请打开正确的出版社或作者官网",
        }


def _official_source(subject):
    links = subject.source_links.select_related("research_source").order_by("-research_source__fetched_at", "-pk")
    for link in links:
        source_type = link.research_source.source_type or ""
        if "official" in source_type or "publisher" in source_type:
            return link.research_source
    return None


def _meta_content(driver, selector: str) -> str:
    elements = driver.find_elements(By.CSS_SELECTOR, selector)
    return (elements[0].get_attribute("content") or "").strip() if elements else ""


def _simon_schuster_cover_url(source_url: str) -> str:
    """Derive the publisher CDN URL encoded by Simon & Schuster book pages."""
    parsed = urlsplit(source_url)
    if "simonandschuster." not in parsed.netloc.casefold():
        return ""
    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if len(parts) < 3 or parts[0].casefold() != "books":
        return ""
    isbn = parts[-1]
    if not re.fullmatch(r"\d{13}", isbn):
        return ""
    slug = re.sub(r"[^a-z0-9]+", "-", parts[1].casefold()).strip("-")
    return f"https://d28hgpri8am2if.cloudfront.net/book_images/onix/cvr{isbn}/{slug}-{isbn}_lg.jpg"


def infer_official_entity_type(
    *,
    current_type: str | None,
    subject_title: str,
    source_url: str,
    page_title: str,
    description: str,
    page_signals: list[str] | None = None,
) -> dict:
    """Return a conservative Entity Type suggestion from publisher-page signals.

    This is intentionally publisher-neutral.  It does not turn every page that
    says "series" into a Series: product-line and reading-stage language wins
    when the page is chiefly organizing readers by age, ability, or level.
    """
    signals = [value for value in (page_signals or []) if value]
    corpus = " ".join((subject_title, page_title, description, *signals)).casefold()
    url = unquote(source_url).casefold()
    scores = {"book": 0, "animation": 0, "reading_system": 0, "series": 0, "level": 0, "set": 0}
    reasons: dict[str, list[str]] = {key: [] for key in scores}

    def add(entity_type: str, score: int, reason: str):
        scores[entity_type] += score
        reasons[entity_type].append(reason)

    if current_type in scores:
        add(current_type, 1, "保留当前 Research 类型作为弱先验")
    if re.search(r"\b(level|stage|step|band)\s*(?:[a-z]|\d+|one|two|three|four|five)\b", subject_title.casefold()):
        add("level", 9, "对象名称明确是 Level / Stage / Step / Band 层级")
    if re.search(r"\b(boxed\s+set|box\s+set|book\s+set|bundle)\b", corpus):
        add("set", 9, "官方页面明确把对象作为套装或组合销售")
    if re.search(r"\b(animated\s+(?:series|show)|animation|cartoon\s+series|television\s+series|tv\s+series)\b", corpus):
        add("animation", 9, "官方页面明确把对象标识为动画内容")
    if re.search(r"\b(episodes?|seasons?|watch\s+now)\b", corpus) and re.search(r"\b(animated|animation|cartoon|tv)\b", corpus):
        add("animation", 4, "页面以剧集或季度组织动画内容")
    if "/books/" in url and re.search(r"\b\d{13}\b", url):
        add("book", 12, "官方 URL 指向带 ISBN 的具体图书页")
    elif re.search(r"\bisbn(?:-1[03])?\b", corpus) and re.search(r"\b\d{10,13}\b", corpus):
        add("book", 7, "页面包含具体图书 ISBN")

    product_line_patterns = (
        r"\breading\s+(?:program|programme|scheme|system)\b",
        r"\b(?:reader|reading|product)\s+line\b",
        r"\bleveled\s+(?:reader|reading)\b",
        r"\breading\s+levels?\s+(?:for|designed|help|support)\b",
    )
    if any(re.search(pattern, corpus) for pattern in product_line_patterns):
        add("reading_system", 9, "官方定位强调阅读项目、阅读产品线或分级阅读产品线")
    if re.search(r"\b(levels?|stages?|steps?|bands?)\b", corpus) and re.search(
        r"\b(readers?|reading|ages?|grades?|independent|beginning|emerging|confident)\b", corpus
    ):
        add("reading_system", 5, "页面以阅读阶段、年龄或能力组织多个层级")
    if re.search(r"\b(?:ages?|grades?)\s+[pk\d]", corpus):
        add("reading_system", 2, "页面给出跨作品适用的年龄或年级定位")

    if re.search(r"\b(?:book\s+)?series\b", corpus):
        add("series", 3, "官方页面使用 Series 标识")
    if re.search(r"\bthis\s+series\s+is\s+part\s+of\b", corpus):
        add("series", 9, "官方描述明确当前对象是隶属于更大阅读产品线的系列")
    if re.search(r"\bseries\s+(?:about|featuring|follows)\b", corpus) or re.search(
        r"\b(?:same|beloved|favorite)\s+(?:characters?|world)\b", corpus
    ):
        add("series", 6, "官方描述表明作品共享角色、世界或持续作品身份")

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_type, best_score = ranked[0]
    runner_up = ranked[1][1]
    if best_score < 3 and current_type in scores:
        best_type = current_type
    confidence = min(0.98, max(0.55, 0.58 + best_score * 0.035 + max(0, best_score - runner_up) * 0.025))
    return {
        "value": best_type,
        "confidence": round(confidence, 2),
        "reason": "；".join(reasons[best_type]) or "页面信号不足，暂沿用当前 Research 建议，等待人工确认",
        "signals": signals[:12],
    }


def _page_structure_signals(driver) -> list[str]:
    selectors = (
        '[aria-label*="breadcrumb" i]',
        '[class*="breadcrumb" i]',
        ".bookDetails__seriesName",
        "h1",
        "h2",
        "nav a",
    )
    values = []
    for selector in selectors:
        for element in driver.find_elements(By.CSS_SELECTOR, selector):
            text = " ".join((element.text or "").split())
            if text and len(text) <= 180 and text not in values:
                values.append(text)
            if len(values) >= 24:
                return values
    return values


def _jsonld_nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _jsonld_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _jsonld_nodes(child)


def _schema_names(value) -> list[str]:
    rows = value if isinstance(value, list) else [value]
    names = []
    for row in rows:
        name = row.get("name") if isinstance(row, dict) else row
        name = " ".join(str(name or "").split())
        if name and name not in names:
            names.append(name)
    return names


def _schema_image(value) -> str:
    if isinstance(value, list):
        return next((_schema_image(row) for row in value if _schema_image(row)), "")
    if isinstance(value, dict):
        return str(value.get("url") or value.get("contentUrl") or "").strip()
    return str(value or "").strip()


def _official_capture_from_driver(driver, subject, source_url: str, source_type: str = "publisher_official") -> dict:
    title = driver.title.strip()
    if not title or "blocked" in title.casefold() or "attention required" in title.casefold():
        raise OfficialAssistError("官网页面未正常加载")
    if "scholastic.com" in urlsplit(source_url).netloc.casefold():
        with suppress(Exception):
            WebDriverWait(driver, 12).until(lambda active: (
                len(active.find_elements(By.CSS_SELECTOR, ".bookDetails__title")) >= 2
                and any((element.text or "").strip() for element in active.find_elements(By.CSS_SELECTOR, ".bookDetails__description"))
            ))
    description = _meta_content(driver, 'meta[property="og:description"]') or _meta_content(driver, 'meta[name="description"]')
    cover = _meta_content(driver, 'meta[property="og:image"]') or _meta_content(driver, 'meta[name="twitter:image"]')

    def first_text(*selectors):
        for selector in selectors:
            for element in driver.find_elements(By.CSS_SELECTOR, selector):
                value = " ".join((element.text or "").split())
                if value:
                    return value
        return ""

    description = description or first_text(
        ".bookDetails__description", "[class*='bookDescription']",
        "main [class*='description']:not([class*='footer'])",
        "article [class*='description']:not([class*='footer'])",
    )
    if not cover:
        images = driver.find_elements(By.CSS_SELECTOR, ".bookDetails__image, main img, article img")
        cover = (images[0].get_attribute("src") or "").strip() if images else ""
    schemas = []
    for element in driver.find_elements(By.CSS_SELECTOR, 'script[type="application/ld+json"]'):
        raw = element.get_attribute("textContent") or element.get_attribute("innerHTML") or ""
        try:
            schemas.extend(_jsonld_nodes(json.loads(raw)))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    preferred = []
    for row in schemas:
        schema_type = row.get("@type")
        types = schema_type if isinstance(schema_type, list) else [schema_type]
        if any(str(value or "").casefold() in {"book", "product", "creativework", "bookseries", "collectionpage"} for value in types):
            preferred.append(row)
    candidates = [*preferred, *schemas]

    def first(*keys):
        for row in candidates:
            for key in keys:
                value = row.get(key)
                if value not in (None, "", [], {}):
                    return value
        return None

    description = str(first("description") or description or "").strip()
    cover = _schema_image(first("image", "thumbnailUrl")) or cover or _simon_schuster_cover_url(source_url)
    facts = {}
    authors = _schema_names(first("author", "creator"))
    illustrators = _schema_names(first("illustrator"))
    publishers = _schema_names(first("publisher", "brand"))
    if authors:
        facts["author"] = ", ".join(authors)
    if illustrators:
        facts["illustrator"] = ", ".join(illustrators)
    if publishers:
        facts["publisher"] = ", ".join(publishers)
    body_text = ""
    with suppress(Exception):
        body_text = driver.find_element(By.TAG_NAME, "body").text or ""
    if not authors:
        author_match = re.search(r"\bAuthor\s*:\s*([^;\n]+)", body_text, re.IGNORECASE)
        if author_match and author_match.group(1).strip():
            facts["author"] = author_match.group(1).strip()
    if not illustrators:
        illustrator_match = re.search(r"\bIllustrator\s*:\s*([^;\n]+)", body_text, re.IGNORECASE)
        if illustrator_match and illustrator_match.group(1).strip():
            facts["illustrator"] = illustrator_match.group(1).strip()
    official_age = first_text(".bookDetails__age", "[class*='recommendedAge']", "[class*='ageRange']")
    if official_age and re.search(r"\d", official_age):
        facts["official_age"] = official_age
    official_genre = first_text(".bookDetails__genre", "[class*='genreValue']")
    if official_genre:
        facts["official_genre"] = official_genre
    if description:
        facts["description"] = description
    if cover:
        facts["cover"] = cover
        facts["product_images"] = [{"source_url": cover, "role": "cover", "selected": True}]
    isbn_values = first("isbn", "isbn13", "isbn10")
    if isbn_values:
        values = isbn_values if isinstance(isbn_values, list) else [isbn_values]
        normalized = []
        for value in values:
            token = re.sub(r"[^0-9X]", "", str(value).upper())
            if token and token not in normalized:
                normalized.append(token)
        if normalized:
            facts["isbns"] = normalized
    page_count = first("numberOfPages")
    match = re.search(r"\d+", str(page_count or ""))
    if match:
        facts["page_count"] = int(match.group())
    publication_date = first("datePublished", "releaseDate")
    if publication_date:
        facts["publication_date"] = str(publication_date)
    language = first("inLanguage")
    if language:
        facts["language"] = str(language)
    series_names = _schema_names(first("isPartOf"))
    if series_names:
        facts["series_name"] = series_names[0]
    page_signals = _page_structure_signals(driver)
    if page_signals:
        facts["official_page_signals"] = page_signals
    capture = {
        "source_url": source_url,
        "source_title": title,
        "source_type": source_type,
        "facts": facts,
        "entity_type_suggestion": infer_official_entity_type(
            current_type=subject.proposed_entity_type,
            subject_title=subject.proposed_display_title or "",
            source_url=source_url,
            page_title=title,
            description=description,
            page_signals=page_signals,
        ),
    }
    boxes = driver.find_elements(By.CSS_SELECTOR, ".bookDetails")
    if subject.proposed_entity_type in {"reading_system", "series", "level", "set", "franchise"} and len(boxes) >= 2:
        members = []
        for position, box in enumerate(boxes, 1):
            title_elements = box.find_elements(By.CSS_SELECTOR, ".bookDetails__title")
            member_title = " ".join((title_elements[0].text or "").split()) if title_elements else ""
            if not member_title or any(row["display_title"].casefold() == member_title.casefold() for row in members):
                continue
            member_facts = {}
            image_elements = box.find_elements(By.CSS_SELECTOR, ".bookDetails__image")
            member_cover = (image_elements[0].get_attribute("src") or "").strip() if image_elements else ""
            if member_cover:
                member_facts["cover"] = member_cover
                member_facts["product_images"] = [{"source_url": member_cover, "role": "cover", "selected": True}]
            author_elements = box.find_elements(By.CSS_SELECTOR, ".bookDetails__contributors--author")
            member_author = " ".join((author_elements[0].text or "").split()) if author_elements else ""
            member_author = re.sub(r"^Author\s*:\s*|;\s*$", "", member_author, flags=re.IGNORECASE).strip()
            if member_author:
                member_facts["author"] = member_author
            illustrator_elements = box.find_elements(By.CSS_SELECTOR, ".bookDetails__contributors--illustrator")
            member_illustrator = " ".join((illustrator_elements[0].text or "").split()) if illustrator_elements else ""
            member_illustrator = re.sub(r"^Illustrator\s*:\s*|;\s*$", "", member_illustrator, flags=re.IGNORECASE).strip()
            if member_illustrator:
                member_facts["illustrator"] = member_illustrator
            member_url = source_url
            for anchor in box.find_elements(By.CSS_SELECTOR, "a[href]"):
                href = (anchor.get_attribute("href") or "").strip()
                if "scholastic.com" in urlsplit(href).netloc.casefold() and "/books/" in urlsplit(href).path:
                    member_url = href
                    break
            isbn_match = re.search(r"\b(97[89]\d{10})\b", f"{member_url} {member_cover}")
            if isbn_match:
                member_facts["isbns"] = [isbn_match.group(1)]
            members.append({
                "display_title": member_title, "entity_type": "book", "position": position,
                "source_url": member_url, "source_title": f"{member_title} | Scholastic",
                "source_type": source_type, "facts": member_facts,
            })
        if len(members) >= 2:
            capture["members"] = members
    acorn_match = re.search(r"part of Scholastic(?:'s|’s) early reader line,\s*([^,.]+)", description, re.IGNORECASE)
    if acorn_match:
        parent_title = acorn_match.group(1).strip()
        capture["parents"] = [{
            "display_title": parent_title, "entity_type": "reading_system", "position": 1,
            "source_url": source_url, "source_title": f"{parent_title} | Scholastic",
            "source_type": source_type,
            "facts": {"publisher": "Scholastic", "description": f"Scholastic early reader line {parent_title}."},
        }]
    return capture


def capture_current_official(subject, expected_query: str, alternate_titles=None) -> dict:
    """Capture the matching official page selected by the reviewer in Chrome."""
    with _browser_lock:
        if not _browser_is_running():
            raise OfficialAssistError("官网辅助浏览器没有运行，请先点击“搜索官方资料”。")
        page = _current_official_page([expected_query, *(alternate_titles or [])])
        driver_path = _chromedriver_binary()
        binary = _chrome_binary()
        if not driver_path or not binary:
            raise OfficialAssistError("未找到 Chrome 或 ChromeDriver，无法读取官网页面。")
        options = Options()
        options.debugger_address = f"127.0.0.1:{_debug_port()}"
        options.binary_location = binary
        driver = None
        try:
            driver = webdriver.Chrome(service=Service(driver_path), options=options)
            target = urlsplit(page.get("url", ""))
            for handle in driver.window_handles:
                driver.switch_to.window(handle)
                current = urlsplit(driver.current_url)
                if current.netloc.casefold() == target.netloc.casefold() and current.path.rstrip("/") == target.path.rstrip("/"):
                    break
            current = urlsplit(driver.current_url)
            if current.netloc.casefold() != target.netloc.casefold() or current.path.rstrip("/") != target.path.rstrip("/"):
                raise OfficialAssistError("ChromeDriver 已连接，但没有找到刚才打开的官网标签页。")
            WebDriverWait(driver, 20).until(
                lambda active: active.execute_script("return document.readyState") in {"interactive", "complete"}
            )
            return _official_capture_from_driver(driver, subject, driver.current_url)
        except OfficialAssistError:
            raise
        except Exception as error:
            raise OfficialAssistError(f"读取官网页面失败：{error}") from error
        finally:
            if driver is not None:
                with suppress(Exception):
                    driver.service.stop()


def capture_official_subjects(subjects) -> tuple[dict[int, dict], dict[int, str]]:
    """Capture cover/basic metadata from each subject's verified official URL.

    A fresh temporary tab is used for every subject so the user's existing
    Amazon/JD tabs and login session remain untouched.
    """
    targets = []
    errors: dict[int, str] = {}
    for subject in subjects:
        source = _official_source(subject)
        if source is None:
            errors[subject.pk] = "没有已确认的官网来源链接"
        else:
            targets.append((subject, source))
    if not targets:
        return {}, errors

    driver_path = _chromedriver_binary()
    binary = _chrome_binary()
    if not driver_path or not binary:
        raise OfficialAssistError("未找到 Chrome 或 ChromeDriver，无法采集官网页面")

    with _browser_lock:
        if not _browser_is_running():
            _launch_chrome_url(binary, targets[0][1].source_url)
            _wait_for_browser()
        options = Options()
        options.debugger_address = f"127.0.0.1:{_debug_port()}"
        options.binary_location = binary
        driver = webdriver.Chrome(service=Service(driver_path), options=options)
        original_handle = driver.current_window_handle
        captures: dict[int, dict] = {}
        try:
            for subject, source in targets:
                opened_handle = None
                fallback_cover = _simon_schuster_cover_url(source.source_url)
                try:
                    driver.switch_to.new_window("tab")
                    opened_handle = driver.current_window_handle
                    driver.get(source.source_url)
                    WebDriverWait(driver, 20).until(
                        lambda current: current.execute_script("return document.readyState") in {"interactive", "complete"}
                    )
                    captures[subject.pk] = _official_capture_from_driver(
                        driver, subject, source.source_url, source.source_type or "publisher_official",
                    )
                except Exception as error:
                    if fallback_cover:
                        captures[subject.pk] = {
                            "source_url": source.source_url,
                            "source_title": source.source_title or "官方出版社页面",
                            "source_type": source.source_type or "publisher_official",
                            "facts": {
                                "cover": fallback_cover,
                                "product_images": [{"source_url": fallback_cover, "role": "cover", "selected": True}],
                            },
                        }
                    else:
                        errors[subject.pk] = str(error) or type(error).__name__
                finally:
                    if opened_handle is not None:
                        with suppress(Exception):
                            driver.close()
                    with suppress(Exception):
                        driver.switch_to.window(original_handle)
        finally:
            with suppress(Exception):
                driver.service.stop()
    return captures, errors
