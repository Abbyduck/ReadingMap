"""Human-guided Amazon browser session for one review item at a time."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
import json
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen

from django.conf import settings

from .browser_session import capture_tabs, remember_search


class AmazonAssistError(RuntimeError):
    pass


_browser_lock = threading.RLock()


def _normalize_search_query(value: str) -> str:
    title = " ".join(str(value or "").split())
    first_han = re.search(r"[\u3400-\u9fff]", title)
    if first_han and first_han.start() > 0:
        english_prefix = title[: first_han.start()].rstrip(" -/|·([（")
        if re.search(r"[A-Za-z]", english_prefix):
            return english_prefix
    return title


def _chrome_binary() -> str | None:
    chrome_for_testing = sorted(
        (settings.BASE_DIR.parent / "tmp").glob("chrome-*/chrome-win64/chrome.exe"),
        reverse=True,
    )
    candidates = [
        os.getenv("CHROME_BINARY_PATH"),
        shutil.which("chrome"),
        Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe",
        Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
        Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
        *chrome_for_testing,
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    return None


def _chromedriver_binary() -> str | None:
    candidates = [
        os.getenv("CHROMEDRIVER_PATH"),
        settings.BASE_DIR.parent / "tmp" / "chromedriver" / "chromedriver.exe",
        shutil.which("chromedriver"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    return None


def _profile_path() -> Path:
    return settings.BASE_DIR.parent / "tmp" / "amazon-research-chrome"


def _debug_port() -> int:
    return int(os.getenv("AMAZON_CHROME_DEBUG_PORT", "9225"))


def _devtools_json(path: str):
    with urlopen(f"http://127.0.0.1:{_debug_port()}{path}", timeout=2) as response:
        return json.load(response)


def _browser_is_running() -> bool:
    try:
        return bool(_devtools_json("/json/version").get("Browser"))
    except Exception:
        return False


def _launch_chrome_url(binary: str, url: str) -> None:
    profile = _profile_path()
    profile.mkdir(parents=True, exist_ok=True)
    creation_flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(
        [
            binary,
            "--remote-debugging-address=127.0.0.1",
            f"--remote-debugging-port={_debug_port()}",
            "--no-first-run",
            "--disable-notifications",
            "--start-maximized",
            f"--user-data-dir={profile}",
            url,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=creation_flags,
    )


def _wait_for_browser(timeout: float = 12) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _browser_is_running():
            return
        time.sleep(0.25)
    raise AmazonAssistError("Chrome 已启动，但本机采集通道没有就绪。")


def _matching_search_page(query: str):
    try:
        pages = _devtools_json("/json")
    except Exception:
        return None
    matches = []
    for page in pages:
        url = page.get("url", "")
        values = parse_qs(urlsplit(url).query).get("k", [])
        if page.get("type") == "page" and values and values[0].casefold() == query.casefold():
            matches.append(page)
    successful = [page for page in matches if not page.get("title", "").strip().lower().startswith("sorry")]
    return (successful or matches or [None])[0]


def _wait_for_search_page(query: str, timeout: float = 20):
    deadline = time.monotonic() + timeout
    last_match = None
    while time.monotonic() < deadline:
        match = _matching_search_page(query)
        if match:
            last_match = match
            title = match.get("title", "").strip()
            if title and not title.lower().startswith("sorry"):
                return match
        time.sleep(0.5)
    return last_match


def _asin_from_url(url: str) -> str | None:
    match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})(?:[/?]|$)", str(url or ""), re.IGNORECASE)
    return match.group(1).upper() if match else None


def _current_product_page():
    """Return Chrome's most recently active Amazon product tab."""
    try:
        pages = _devtools_json("/json")
    except Exception as error:
        raise AmazonAssistError("无法读取 Amazon 辅助浏览器。") from error
    for page in capture_tabs("amazon", pages):
        if page.get("type") == "page" and _asin_from_url(page.get("url", "")):
            return page
    raise AmazonAssistError("没有找到 Amazon 商品详情页；请先在搜索结果中打开正确商品。")


def amazon_browser_status(expected_query: str = "") -> dict:
    """Describe the reusable Chrome session without attaching Selenium."""
    with _browser_lock:
        if not _browser_is_running():
            return {
                "provider": "amazon",
                "connected": False,
                "state": "disconnected",
                "current_url": "",
                "product_title": "",
                "product_id": "",
                "capture_ready": False,
                "message": "Amazon 辅助浏览器未连接",
            }
        try:
            pages = _devtools_json("/json")
        except Exception:
            return {
                "provider": "amazon",
                "connected": False,
                "state": "disconnected",
                "current_url": "",
                "product_title": "",
                "product_id": "",
                "capture_ready": False,
                "message": "无法读取 Amazon 辅助浏览器",
            }

        provider_pages = [
            page for page in capture_tabs("amazon", pages)
            if page.get("type") == "page" and "amazon." in urlsplit(page.get("url", "")).netloc.casefold()
        ]
        product_page = next((page for page in provider_pages if _asin_from_url(page.get("url", ""))), None)
        if product_page:
            message = "已识别商品详情页"
            capture_ready = True
            try:
                _assert_product_matches(expected_query, product_page)
            except AmazonAssistError as error:
                capture_ready = False
                message = str(error)
            return {
                "provider": "amazon",
                "connected": True,
                "state": "product_detail",
                "current_url": product_page.get("url", ""),
                "product_title": product_page.get("title", "").strip(),
                "product_id": _asin_from_url(product_page.get("url", "")) or "",
                "capture_ready": capture_ready,
                "message": message,
            }

        search_page = next((
            page for page in provider_pages
            if urlsplit(page.get("url", "")).path.startswith("/s")
        ), None)
        current = search_page or (provider_pages[0] if provider_pages else None)
        return {
            "provider": "amazon",
            "connected": True,
            "state": "search_results" if search_page else "unknown",
            "current_url": current.get("url", "") if current else "",
            "product_title": "",
            "product_id": "",
            "capture_ready": False,
            "message": "搜索结果已就绪，请打开正确商品" if search_page else "等待打开 Amazon 商品详情页",
        }


def _search_terms_from_product_url(url: str) -> str:
    values = parse_qs(urlsplit(str(url or "")).query).get("keywords", [])
    return values[0] if values else ""


def _title_tokens(value: str) -> set[str]:
    return {
        token.casefold()
        for token in re.findall(r"[A-Za-z0-9]+", _normalize_search_query(value))
        if len(token) > 1 and token.casefold() not in {"the", "and", "of", "a", "an"}
    }


def _assert_product_matches(expected_query: str, page: dict) -> None:
    expected = _title_tokens(expected_query)
    actual = _title_tokens(page.get("title", ""))
    originating_query = _search_terms_from_product_url(page.get("url", ""))
    origin = _title_tokens(originating_query)
    if expected and not (expected & actual or expected & origin):
        raise AmazonAssistError(
            f"当前商品“{page.get('title', '').strip()}”与审核项“{expected_query}”不匹配；"
            "请切回该审核项对应的 Amazon 商品页后再采集。"
        )


def _pick_largest_image(element) -> str:
    dynamic = element.get_attribute("data-a-dynamic-image") or ""
    try:
        candidates = json.loads(dynamic)
        if isinstance(candidates, dict) and candidates:
            return max(candidates.items(), key=lambda row: (row[1][0] * row[1][1]) if isinstance(row[1], list) and len(row[1]) > 1 else 0)[0]
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return element.get_attribute("data-old-hires") or element.get_attribute("src") or ""


def _first_text(driver, selectors: list[str]) -> str:
    from selenium.webdriver.common.by import By

    for selector in selectors:
        for element in driver.find_elements(By.CSS_SELECTOR, selector):
            value = " ".join(element.text.split())
            if value:
                return value
    return ""


def _all_text(driver, selector: str) -> list[str]:
    from selenium.webdriver.common.by import By

    values = []
    for element in driver.find_elements(By.CSS_SELECTOR, selector):
        value = " ".join(element.text.split())
        if value and value not in values:
            values.append(value)
    return values


def _product_detail_rows(driver) -> dict[str, str]:
    from selenium.webdriver.common.by import By

    rows: dict[str, str] = {}
    selectors = [
        "#detailBullets_feature_div li",
        "#productDetails_detailBullets_sections1 tr",
        "#productDetails_techSpec_section_1 tr",
        "#productDetails_db_sections tr",
        "#productDetails_feature_div tr",
    ]
    for selector in selectors:
        for element in driver.find_elements(By.CSS_SELECTOR, selector):
            cells = [" ".join(cell.text.split()) for cell in element.find_elements(By.CSS_SELECTOR, "th, td, span") if cell.text.strip()]
            if len(cells) >= 2:
                key, value = cells[0].strip(" :：\u200e"), cells[-1].strip()
            else:
                line = " ".join(element.text.split())
                parts = re.split(r"\s*[:：]\s*", line, maxsplit=1)
                if len(parts) != 2:
                    continue
                key, value = parts[0].strip(" \u200e"), parts[1].strip()
            if key and value and key.casefold() != value.casefold():
                rows.setdefault(key, value)
    return rows


def _detail_value(rows: dict[str, str], *needles: str) -> str:
    for key, value in rows.items():
        folded = key.casefold().replace(" ", "")
        if any(needle.casefold().replace(" ", "") in folded for needle in needles):
            return value
    return ""


def _gallery_image_urls(driver, cover_url: str) -> list[str]:
    """Read the large image behind every Amazon gallery thumbnail.

    This follows the working flow in the older ``crawl amazon`` script: open the
    image popover, click each ``ivImage_*`` thumbnail, then read ``ivLargeImage``.
    Only the resulting image URLs are retained; the page itself is not archived.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    urls = []
    try:
        containers = driver.find_elements(By.CSS_SELECTOR, "#main-image-container, #imageBlock")
        if not containers:
            return urls
        driver.execute_script("arguments[0].click()", containers[0])
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[id^='ivImage_'], #ivLargeImage"))
        )
        thumbnails = driver.find_elements(By.CSS_SELECTOR, "[id^='ivImage_']")[:16]
        if not thumbnails:
            thumbnails = [None]
        for thumbnail in thumbnails:
            try:
                if thumbnail is not None:
                    thumb_id = thumbnail.get_attribute("id")
                    if thumb_id:
                        WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.ID, thumb_id)))
                    driver.execute_script("arguments[0].click()", thumbnail)
                WebDriverWait(driver, 8).until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, "#ivLargeImage img, .ivLargeImage img"))
                )
                large = driver.find_elements(By.CSS_SELECTOR, "#ivLargeImage img, .ivLargeImage img")
                if large:
                    url = large[0].get_attribute("src") or ""
                    if url and url != cover_url and url not in urls:
                        urls.append(url)
            except Exception:
                continue
    except Exception:
        pass
    finally:
        try:
            close = driver.find_elements(By.CSS_SELECTOR, ".ivClose, #ivClose")
            if close:
                driver.execute_script("arguments[0].click()", close[0])
        except Exception:
            pass
    return urls


def _canonical_product_url(url: str, asin: str) -> str:
    host = urlsplit(url).netloc or "www.amazon.com"
    return f"https://{host}/dp/{asin}"


def _member_titles_from_product_title(title: str) -> list[str]:
    """Extract explicitly enumerated boxed-set members from an Amazon title."""
    if ":" not in title:
        return []
    prefix, remainder = title.split(":", 1)
    if not re.search(r"\b(?:boxed set|collection|set)\b", prefix, re.IGNORECASE):
        return []
    values = []
    for part in remainder.split(";"):
        value = " ".join(part.strip(" ;").split())
        if value and value not in values:
            values.append(value)
    return values if len(values) >= 2 else []


def _capture_with_selenium(page: dict) -> dict:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By

    driver_path = _chromedriver_binary()
    if not driver_path:
        raise AmazonAssistError("未找到 ChromeDriver，无法读取当前商品页。")
    options = Options()
    options.debugger_address = f"127.0.0.1:{_debug_port()}"
    binary = _chrome_binary()
    if binary:
        options.binary_location = binary
    driver = None
    try:
        driver = webdriver.Chrome(service=Service(driver_path), options=options)
        target_asin = _asin_from_url(page.get("url", ""))
        for handle in driver.window_handles:
            driver.switch_to.window(handle)
            if _asin_from_url(driver.current_url) == target_asin:
                break
        if _asin_from_url(driver.current_url) != target_asin:
            raise AmazonAssistError("ChromeDriver 已连接，但没有找到刚才选中的商品标签页。")

        title = _first_text(driver, ["#productTitle", "#title"])
        if not title:
            raise AmazonAssistError("商品页尚未加载完成，未读到商品标题。")
        rows = _product_detail_rows(driver)
        authors = []
        illustrators = []
        contributor_rows = driver.find_elements(By.CSS_SELECTOR, "#bylineInfo .author")
        for contributor in contributor_rows:
            names = [
                " ".join(element.text.split())
                for element in contributor.find_elements(By.CSS_SELECTOR, "a.contributorName, a")
                if " ".join(element.text.split())
            ]
            role_text = " ".join((contributor.text or "").split())
            target = illustrators if re.search(r"\b(?:illustrator|illustrated by)\b|插画|绘者", role_text, re.IGNORECASE) else authors
            for name in names:
                if name not in target:
                    target.append(name)
        if not contributor_rows:
            authors = _all_text(driver, "#bylineInfo .author a, #bylineInfo a.contributorName, .author a")
        description = _first_text(driver, [
            "#bookDescription_feature_div", "#productDescription", "#editorialReviews_feature_div",
            "#aplus_feature_div",
        ])

        cover_url = ""
        landing = driver.find_elements(By.CSS_SELECTOR, "#landingImage, #imgBlkFront")
        if landing:
            cover_url = _pick_largest_image(landing[0])
        image_urls = []
        for image in driver.find_elements(By.CSS_SELECTOR, "#altImages img, #imageBlock img"):
            url = _pick_largest_image(image)
            if url and url not in image_urls and url != cover_url:
                image_urls.append(url)
        for url in _gallery_image_urls(driver, cover_url):
            if url not in image_urls:
                image_urls.append(url)

        series = []
        for link in driver.find_elements(By.CSS_SELECTOR, "#seriesBulletWidget_feature_div a, a[href*='/series/'], a[href*='series']"):
            name = " ".join(link.text.split())
            href = link.get_attribute("href") or ""
            if name and href and not any(row["url"] == href for row in series):
                series.append({"name": name, "url": href})

        asin = target_asin or ""
        isbn_values = []
        for value in (_detail_value(rows, "ISBN-10"), _detail_value(rows, "ISBN-13")):
            normalized = re.sub(r"[^0-9X]", "", value.upper())
            if normalized and normalized not in isbn_values:
                isbn_values.append(normalized)
        page_count_text = _detail_value(rows, "Print length", "Paperback", "Hardcover", "页数")
        page_count_match = re.search(r"\d+", page_count_text.replace(",", ""))
        rating = ""
        rating_elements = driver.find_elements(By.CSS_SELECTOR, "#acrPopover, [data-hook='rating-out-of-text']")
        if rating_elements:
            rating = rating_elements[0].get_attribute("title") or " ".join(rating_elements[0].text.split())
        rating_count = _first_text(driver, ["#acrCustomerReviewText", "[data-hook='total-review-count']"])
        dimensions = _detail_value(rows, "Dimensions", "尺寸")
        sales_rank = _detail_value(rows, "Best Sellers Rank", "Best Seller Rank", "销量排名", "热销商品排名")
        extra_lines = []
        for label, value in [
            ("Amazon 评分", rating),
            ("Amazon 评价数", rating_count),
            ("Amazon 销量排名", sales_rank),
            ("商品尺寸", dimensions),
        ]:
            if value:
                extra_lines.append(f"{label}：{value}")
        facts = {
            "author": ", ".join(authors),
            "illustrator": ", ".join(illustrators) or _detail_value(rows, "Illustrator", "Illustrated by", "插画", "绘者"),
            "description": description,
            "publisher": _detail_value(rows, "Publisher", "出版社"),
            "publication_date": _detail_value(rows, "Publication date", "出版日期"),
            "language": _detail_value(rows, "Language", "语言"),
            "reading_age": _detail_value(rows, "Reading age", "阅读年龄"),
            "page_count": int(page_count_match.group()) if page_count_match else None,
            "isbns": isbn_values,
            "extra_info": "\n".join(extra_lines),
            "series": series,
            "included_titles": _member_titles_from_product_title(title),
        }
        return {
            "asin": asin,
            "title": title,
            "source_url": _canonical_product_url(driver.current_url, asin),
            "current_url": driver.current_url,
            "image_urls": {"cover": cover_url, "details": image_urls},
            "facts": {key: value for key, value in facts.items() if value not in (None, "", [], {})},
        }
    except AmazonAssistError:
        raise
    except Exception as error:
        raise AmazonAssistError(f"读取 Amazon 商品页失败：{error}") from error
    finally:
        # Do not call quit(): this is an attached, reusable user-controlled Chrome.
        if driver is not None:
            try:
                driver.service.stop()
            except Exception:
                pass


def _asset_directory(asin: str) -> Path:
    return settings.BASE_DIR.parent / "research_data" / "amazon" / asin


def _download_assets(capture: dict) -> list[dict]:
    urls = []
    cover = (capture.get("image_urls") or {}).get("cover")
    if cover:
        urls.append((cover, "cover"))
    urls.extend((url, "detail") for url in (capture.get("image_urls") or {}).get("details") or [])
    if not urls:
        return []
    target = _asset_directory(capture["asin"])
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
            extension = {"image/png": ".png", "image/webp": ".webp"}.get(content_type, ".jpg")
            name = ("cover" if role == "cover" else f"detail-{index:02d}") + extension
            path = target / name
            path.write_bytes(content)
            local_path = path.relative_to(settings.BASE_DIR.parent).as_posix()
        except Exception:
            pass
        saved.append({
            "source_url": url,
            "local_path": local_path,
            "role": role,
            "selected": True,
        })
    return saved


def capture_amazon_product(expected_query: str) -> dict:
    """Read and download assets from the product the human selected in Chrome."""
    with _browser_lock:
        if not _browser_is_running():
            raise AmazonAssistError("Amazon 辅助浏览器没有运行，请先点击“搜索 Amazon”。")
        page = _current_product_page()
        _assert_product_matches(expected_query, page)
        capture = _capture_with_selenium(page)
        capture["downloaded_assets"] = _download_assets(capture)
        capture["facts"]["product_images"] = capture["downloaded_assets"]
        return capture


def open_amazon_search(query: str) -> dict:
    """Open a human-controlled Amazon search in a reusable debug-enabled Chrome."""
    normalized = _normalize_search_query(query)
    if not normalized:
        raise AmazonAssistError("当前审核对象没有可搜索的名称。")
    search_url = "https://www.amazon.com/s?" + urlencode({"i": "stripbooks", "k": normalized})
    binary = _chrome_binary()
    if not binary:
        raise AmazonAssistError("未找到 Google Chrome，无法启动 Amazon 辅助采集。")

    with _browser_lock:
        reused = _browser_is_running()
        try:
            if not reused:
                _launch_chrome_url(binary, "https://www.amazon.com/")
                _wait_for_browser()
                time.sleep(4)
            _launch_chrome_url(binary, search_url)
            page = _wait_for_search_page(normalized)
            if not page or page.get("title", "").strip().lower().startswith("sorry"):
                _launch_chrome_url(binary, "https://www.amazon.com/")
                time.sleep(4)
                _launch_chrome_url(binary, search_url)
                page = _wait_for_search_page(normalized)
        except AmazonAssistError:
            raise
        except Exception as error:
            raise AmazonAssistError(f"Amazon 浏览器启动失败：{error}") from error
        if not page:
            raise AmazonAssistError("Chrome 已打开，但没有找到对应的 Amazon 搜索标签页。")
        if page.get("title", "").strip().lower().startswith("sorry"):
            raise AmazonAssistError("Amazon 返回了错误页；请在辅助 Chrome 中刷新后重试。")
        try:
            remember_search("amazon", page, _devtools_json("/json"))
        except Exception:
            pass
    return {
        "query": normalized,
        "search_url": search_url,
        "session_reused": reused,
        "current_url": page.get("url", search_url),
        "page_title": page.get("title", ""),
    }
