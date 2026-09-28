"""Human-guided JD.com browser session for one review item at a time."""
from __future__ import annotations

import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen

from django.conf import settings

from .amazon_assist import (
    _browser_is_running,
    _browser_lock,
    _chrome_binary,
    _chromedriver_binary,
    _debug_port,
    _devtools_json,
    _first_text,
    _launch_chrome_url,
    _wait_for_browser,
)


class JdAssistError(RuntimeError):
    pass


def _normalize_jd_query(value: str) -> str:
    return " ".join(str(value or "").split())


def _jd_sku_from_url(url: str) -> str | None:
    value = str(url or "")
    for pattern in (r"//item\.jd\.com/(\d+)\.html", r"//item\.m\.jd\.com/product/(\d+)\.html"):
        match = re.search(pattern, value, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _matching_search_page(query: str):
    try:
        pages = _devtools_json("/json")
    except Exception:
        return None
    for page in pages:
        if page.get("type") != "page":
            continue
        url = page.get("url", "")
        values = parse_qs(urlsplit(url).query).get("keyword", [])
        if "search.jd.com" in urlsplit(url).netloc and values and values[0].casefold() == query.casefold():
            return page
    return None


def _wait_for_search_page(query: str, timeout: float = 20):
    deadline = time.monotonic() + timeout
    last_match = None
    while time.monotonic() < deadline:
        match = _matching_search_page(query)
        if match:
            last_match = match
            if match.get("title", "").strip():
                return match
        time.sleep(0.5)
    return last_match


def _current_jd_product_page():
    try:
        pages = _devtools_json("/json")
    except Exception as error:
        raise JdAssistError("无法读取京东辅助浏览器。") from error
    for page in pages:
        if page.get("type") == "page" and _jd_sku_from_url(page.get("url", "")):
            return page
    raise JdAssistError("没有找到京东商品详情页；请先在搜索结果中打开正确商品。")


def jd_browser_status(expected_query: str = "", alternate_titles=None) -> dict:
    """Describe the shared Chrome session for the JD workflow."""
    with _browser_lock:
        if not _browser_is_running():
            return {
                "provider": "jd", "connected": False, "state": "disconnected",
                "current_url": "", "product_title": "", "product_id": "",
                "capture_ready": False, "message": "京东辅助浏览器未连接",
            }
        try:
            pages = _devtools_json("/json")
        except Exception:
            return {
                "provider": "jd", "connected": False, "state": "disconnected",
                "current_url": "", "product_title": "", "product_id": "",
                "capture_ready": False, "message": "无法读取京东辅助浏览器",
            }

        provider_pages = [
            page for page in pages
            if page.get("type") == "page" and urlsplit(page.get("url", "")).netloc.casefold().endswith("jd.com")
        ]
        product_page = next((page for page in provider_pages if _jd_sku_from_url(page.get("url", ""))), None)
        if product_page:
            message = "已识别商品详情页"
            capture_ready = True
            try:
                _assert_jd_product_matches(expected_query, product_page, alternate_titles)
            except JdAssistError as error:
                capture_ready = False
                message = str(error)
            return {
                "provider": "jd", "connected": True, "state": "product_detail",
                "current_url": product_page.get("url", ""),
                "product_title": product_page.get("title", "").strip(),
                "product_id": _jd_sku_from_url(product_page.get("url", "")) or "",
                "capture_ready": capture_ready, "message": message,
            }

        search_page = next((
            page for page in provider_pages
            if urlsplit(page.get("url", "")).netloc.casefold() == "search.jd.com"
        ), None)
        current = search_page or (provider_pages[0] if provider_pages else None)
        return {
            "provider": "jd", "connected": True,
            "state": "search_results" if search_page else "unknown",
            "current_url": current.get("url", "") if current else "",
            "product_title": "", "product_id": "", "capture_ready": False,
            "message": "搜索结果已就绪，请打开正确商品" if search_page else "等待打开京东商品详情页",
        }


def _match_fragments(value: str) -> set[str]:
    compact = _normalize_jd_query(value)
    fragments = {
        token.casefold()
        for token in re.findall(r"[A-Za-z0-9]+", compact)
        if len(token) > 1 and token.casefold() not in {"the", "and", "of", "a", "an"}
    }
    fragments.update(part for part in re.findall(r"[\u3400-\u9fff]{2,}", compact))
    return fragments


def _fuzzy_han_match(expected_title: str, actual_title: str) -> bool:
    actual = "".join(re.findall(r"[\u3400-\u9fff]", actual_title))
    for fragment in re.findall(r"[\u3400-\u9fff]{4,}", expected_title):
        if fragment in actual:
            return True
        minimum = max(4, len(fragment) - 1)
        maximum = min(len(actual), len(fragment) + 1)
        for size in range(minimum, maximum + 1):
            for start in range(0, len(actual) - size + 1):
                if SequenceMatcher(None, fragment, actual[start:start + size]).ratio() >= 0.82:
                    return True
    return False


def _assert_jd_product_matches(expected_query: str, page: dict, alternate_titles=None) -> None:
    titles = [expected_query, *(alternate_titles or [])]
    expected = set().union(*(_match_fragments(title) for title in titles if title))
    actual_title = page.get("title", "")
    actual = _match_fragments(actual_title)
    normalized_actual = re.sub(r"\s+", "", actual_title).casefold()
    exact_match = any(fragment in actual or fragment.casefold() in normalized_actual for fragment in expected)
    fuzzy_match = any(_fuzzy_han_match(title, actual_title) for title in titles if title)
    if expected and not (exact_match or fuzzy_match):
        raise JdAssistError(
            f"当前商品“{actual_title.strip()}”与审核项“{expected_query}”不匹配；"
            "请切回该审核项对应的京东商品页后再采集。"
        )


def _absolute_image_url(value: str) -> str:
    url = str(value or "").strip()
    if not url or url.startswith("data:"):
        return ""
    if url.startswith("//"):
        url = "https:" + url
    if not url.startswith(("http://", "https://")):
        return ""
    url = url.replace("/n5/", "/n1/")
    url = re.sub(r"/s\d+x\d+_jfs/", "/jfs/", url, flags=re.IGNORECASE)
    return re.sub(r"(\.(?:jpe?g|png))\.avif(?=\?|$)", r"\1", url, flags=re.IGNORECASE)


def _image_url(element) -> str:
    for attribute in ("data-origin", "data-url", "data-lazy-img", "data-lazyload", "src"):
        url = _absolute_image_url(element.get_attribute(attribute) or "")
        if url:
            return url
    return ""


def _image_identity(url: str) -> str:
    """Return a stable identity across JD thumbnail/CDN size variants."""
    path = urlsplit(str(url or "")).path.casefold()
    jfs_index = path.find("/jfs/")
    if jfs_index >= 0:
        path = path[jfs_index:]
    return re.sub(r"\.avif$", "", path)


def _gallery_image_urls(driver, cover_url: str) -> list[str]:
    """Collect current and legacy JD gallery images in visible gallery order."""
    from selenium.webdriver.common.by import By

    selectors = (
        ".image-carousel-content .item img.image",
        ".image-carousel-content img",
        "#spec-list img",
        ".spec-items img",
        "#J-detail-content img",
        "#detail .detail-content img",
    )
    urls = []
    seen = {_image_identity(cover_url)} if cover_url else set()
    for selector in selectors:
        for image in driver.find_elements(By.CSS_SELECTOR, selector):
            url = _image_url(image)
            identity = _image_identity(url)
            if url and identity and identity not in seen:
                seen.add(identity)
                urls.append(url)
    return urls


def _product_detail_rows(driver) -> dict[str, str]:
    from selenium.webdriver.common.by import By

    rows: dict[str, str] = {}
    for selector in ("#detail .p-parameter-list li", "ul.parameter2 li", ".parameter2 li"):
        for element in driver.find_elements(By.CSS_SELECTOR, selector):
            line = " ".join((element.get_attribute("title") or element.text or "").split())
            parts = re.split(r"\s*[:：]\s*", line, maxsplit=1)
            if len(parts) == 2 and parts[0] and parts[1]:
                rows.setdefault(parts[0].strip(), parts[1].strip())
    for block in driver.find_elements(By.CSS_SELECTOR, ".Ptable-item"):
        keys = [" ".join(element.text.split()).strip(" :：") for element in block.find_elements(By.CSS_SELECTOR, "dt")]
        values = [" ".join(element.text.split()) for element in block.find_elements(By.CSS_SELECTOR, "dd")]
        for key, value in zip(keys, values):
            if key and value:
                rows.setdefault(key, value)
    return rows


def _detail_value(rows: dict[str, str], *needles: str) -> str:
    for key, value in rows.items():
        folded = key.casefold().replace(" ", "")
        if any(needle.casefold().replace(" ", "") in folded for needle in needles):
            return value
    return ""


def _clean_jd_page_title(value: str) -> str:
    title = " ".join(str(value or "").split())
    title = re.sub(r"\s*【行情\s*报价\s*价格\s*评测】\s*-?\s*京东\s*$", "", title)
    return re.sub(r"\s*-\s*京东\s*$", "", title).strip()


def _included_titles_from_text(value: str) -> list[str]:
    lines = [" ".join(line.split()) for line in str(value or "").splitlines()]
    start = next((index for index, line in enumerate(lines) if re.fullmatch(r"\d+册目录", line)), None)
    if start is None:
        return []
    titles = []
    for line in lines[start + 1:]:
        if line in {"作者简介", "内页展示", "售后保障"}:
            break
        match = re.match(r"^\s*\d+[.、]\s*(.+?)\s*[;；]?\s*$", line)
        if match and match.group(1):
            titles.append(match.group(1).strip())
    return titles


def _book_detail_element(driver):
    """Return the smallest rich-description container used by the current JD page."""
    from selenium.webdriver.common.by import By

    candidates = []
    for element in driver.find_elements(By.XPATH, "//*[contains(normalize-space(.), '图书信息')]"):
        text = "\n".join(line.strip() for line in (element.text or "").splitlines() if line.strip())
        if "图书信息" in text and ("作者简介" in text or "内页展示" in text):
            candidates.append((len(text), element))
    return min(candidates, key=lambda item: item[0])[1] if candidates else None


def _capture_with_selenium(page: dict) -> dict:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By

    driver_path = _chromedriver_binary()
    if not driver_path:
        raise JdAssistError("未找到 ChromeDriver，无法读取当前京东商品页。")
    options = Options()
    options.debugger_address = f"127.0.0.1:{_debug_port()}"
    binary = _chrome_binary()
    if binary:
        options.binary_location = binary
    driver = None
    try:
        driver = webdriver.Chrome(service=Service(driver_path), options=options)
        target_sku = _jd_sku_from_url(page.get("url", ""))
        for handle in driver.window_handles:
            driver.switch_to.window(handle)
            if _jd_sku_from_url(driver.current_url) == target_sku:
                break
        if _jd_sku_from_url(driver.current_url) != target_sku:
            raise JdAssistError("ChromeDriver 已连接，但没有找到刚才选中的京东商品标签页。")

        title = _first_text(
            driver,
            [".sku-title-name", ".sku-name", ".itemInfo-wrap .sku-name", "#itemName"],
        ) or _clean_jd_page_title(driver.title)
        if not title:
            raise JdAssistError("京东商品页尚未加载完成，未读到商品标题。")
        _assert_jd_product_matches(
            page.get("expected_query", ""),
            {"title": title},
            page.get("alternate_titles") or [],
        )
        rows = _product_detail_rows(driver)
        for element in driver.find_elements(By.CSS_SELECTOR, ".item"):
            labels = element.find_elements(By.CSS_SELECTOR, ".label .text")
            values = element.find_elements(By.CSS_SELECTOR, ".value .text")
            if labels and values:
                key = " ".join(labels[0].text.split()).strip(" :：")
                value = " ".join((values[0].get_attribute("title") or values[0].text or "").split())
                if key and value:
                    rows.setdefault(key, value)
        description = _first_text(driver, [".book-detail-content", "#J-detail-content", "#detail .detail-content"])
        detail_element = _book_detail_element(driver)
        if not description and detail_element is not None:
            description = detail_element.text.strip()
        if len(description) > 5000:
            description = description[:5000].rstrip() + "…"

        cover_url = ""
        for selector in ("#spec-img", "#preview .jqzoom img", ".preview-wrap img"):
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                cover_url = _image_url(elements[0])
                if cover_url:
                    break
        image_urls = _gallery_image_urls(driver, cover_url)
        seen_image_ids = {_image_identity(url) for url in [cover_url, *image_urls] if url}
        if detail_element is not None:
            for image in detail_element.find_elements(By.CSS_SELECTOR, "img"):
                url = _image_url(image)
                identity = _image_identity(url)
                if url and identity and identity not in seen_image_ids:
                    seen_image_ids.add(identity)
                    image_urls.append(url)

        isbn_values = []
        for value in (_detail_value(rows, "ISBN"), _detail_value(rows, "书号")):
            for match in re.findall(r"(?:97[89])?\d{9}[\dX]", re.sub(r"[^0-9X]", "", value.upper())):
                if match not in isbn_values:
                    isbn_values.append(match)
        page_count_text = _detail_value(rows, "页数", "页码")
        page_count_match = re.search(r"\d+", page_count_text.replace(",", ""))
        extra_lines = []
        for label, value in (
            ("京东好评率", _first_text(driver, [".percent-con", ".comment-percent"])),
            ("包装", _detail_value(rows, "包装")),
            ("开本", _detail_value(rows, "开本")),
            ("商品尺寸", _detail_value(rows, "商品尺寸", "尺寸")),
            ("重量", _detail_value(rows, "重量")),
        ):
            if value:
                extra_lines.append(f"{label}：{value}")
        facts = {
            "author": _detail_value(rows, "作者", "著者"),
            "illustrator": _detail_value(rows, "绘者", "插画作者", "插画", "绘图"),
            "description": description,
            "publisher": _detail_value(rows, "出版社"),
            "publication_date": _detail_value(rows, "出版时间", "出版日期"),
            "language": _detail_value(rows, "正文语种", "正文语言", "语种", "语言"),
            "reading_age": _detail_value(rows, "适用年龄", "年龄"),
            "retailer_category": _detail_value(rows, "童书类型"),
            "page_count": int(page_count_match.group()) if page_count_match else None,
            "isbns": isbn_values,
            "included_titles": _included_titles_from_text(description),
            "extra_info": "\n".join(extra_lines),
        }
        return {
            "sku": target_sku or "",
            "title": title,
            "source_url": f"https://item.jd.com/{target_sku}.html",
            "current_url": driver.current_url,
            "image_urls": {"cover": cover_url, "details": image_urls[:15]},
            "facts": {key: value for key, value in facts.items() if value not in (None, "", [], {})},
        }
    except JdAssistError:
        raise
    except Exception as error:
        raise JdAssistError(f"读取京东商品页失败：{error}") from error
    finally:
        if driver is not None:
            try:
                driver.service.stop()
            except Exception:
                pass


def _asset_directory(sku: str) -> Path:
    return settings.BASE_DIR.parent / "research_data" / "jd" / sku


def _download_assets(capture: dict) -> list[dict]:
    urls = []
    cover = (capture.get("image_urls") or {}).get("cover")
    if cover:
        urls.append((cover, "cover"))
    urls.extend((url, "detail") for url in (capture.get("image_urls") or {}).get("details") or [])
    if not urls:
        return []
    target = _asset_directory(capture["sku"])
    target.mkdir(parents=True, exist_ok=True)
    saved = []
    seen = set()
    for index, (url, role) in enumerate(urls[:16]):
        if url in seen:
            continue
        seen.add(url)
        local_path = None
        try:
            request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": capture["source_url"]})
            with urlopen(request, timeout=15) as response:
                content = response.read()
                content_type = response.headers.get_content_type()
            if not content or not content_type.startswith("image/"):
                continue
            extension = {"image/png": ".png", "image/webp": ".webp", "image/avif": ".avif", "image/gif": ".gif"}.get(content_type, ".jpg")
            name = ("cover" if role == "cover" else f"detail-{index:02d}") + extension
            path = target / name
            path.write_bytes(content)
            local_path = path.relative_to(settings.BASE_DIR.parent).as_posix()
        except Exception:
            pass
        saved.append({"source_url": url, "local_path": local_path, "role": role, "selected": True})
    return saved


def capture_jd_product(expected_query: str, alternate_titles=None) -> dict:
    with _browser_lock:
        if not _browser_is_running():
            raise JdAssistError("商品辅助浏览器没有运行，请先点击“搜索京东”。")
        page = _current_jd_product_page()
        page["expected_query"] = _normalize_jd_query(expected_query)
        page["alternate_titles"] = [
            _normalize_jd_query(title)
            for title in (alternate_titles or [])
            if _normalize_jd_query(title) and _normalize_jd_query(title) != page["expected_query"]
        ]
        _assert_jd_product_matches(page["expected_query"], page, page["alternate_titles"])
        capture = _capture_with_selenium(page)
        capture["downloaded_assets"] = _download_assets(capture)
        capture["facts"]["product_images"] = capture["downloaded_assets"]
        return capture


def open_jd_search(query: str) -> dict:
    normalized = _normalize_jd_query(query)
    if not normalized:
        raise JdAssistError("当前审核对象没有可搜索的名称。")
    search_url = "https://search.jd.com/Search?" + urlencode({"keyword": normalized, "enc": "utf-8"})
    binary = _chrome_binary()
    if not binary:
        raise JdAssistError("未找到 Google Chrome，无法启动京东辅助采集。")
    with _browser_lock:
        reused = _browser_is_running()
        try:
            if not reused:
                _launch_chrome_url(binary, "https://www.jd.com/")
                _wait_for_browser()
                time.sleep(2)
            _launch_chrome_url(binary, search_url)
            page = _wait_for_search_page(normalized)
        except Exception as error:
            if isinstance(error, JdAssistError):
                raise
            raise JdAssistError(f"京东浏览器启动失败：{error}") from error
        if not page:
            raise JdAssistError("Chrome 已打开，但没有找到对应的京东搜索标签页。")
    return {
        "query": normalized,
        "search_url": search_url,
        "session_reused": reused,
        "current_url": page.get("url", search_url),
        "page_title": page.get("title", ""),
    }
