"""Rendered-page capture and optional region selection in the existing monitored Chrome."""
from contextlib import suppress
from urllib.parse import urlsplit

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from .amazon_assist import (
    _browser_is_running, _browser_lock, _chrome_binary,
    _chromedriver_binary, _debug_port, _devtools_json,
)
from .structure_extractors import PageSnapshot

_SELECTION_JS = r"""
(function () {
  if (window.__readingMapSelectCleanup) window.__readingMapSelectCleanup();
  window.__readingMapRegion = null;
  let last = null;
  function suitable(el) {
    if (!(el instanceof Element)) return null;
    for (let i=0; el && i<7; i++, el=el.parentElement) {
      const links = el.querySelectorAll('a[href]');
      if (links.length >= 2 && links.length <= 200 && el.outerHTML.length <= 500000) return el;
    }
    return null;
  }
  function hover(e) {
    const current = suitable(e.target);
    if (!current || current === last) return;
    if (last) last.style.outline = last.dataset.rmOutline || '';
    last = current;
    current.dataset.rmOutline = current.style.outline || '';
    current.style.outline = '3px solid #3579bd';
  }
  function click(e) {
    const el = suitable(e.target);
    if (!el) return;
    e.preventDefault(); e.stopImmediatePropagation(); e.stopPropagation();
    window.__readingMapRegion = { html: el.outerHTML, url: location.href, title: document.title };
    cleanup();
  }
  function key(e) { if (e.key === 'Escape') cleanup(); }
  function cleanup() {
    document.removeEventListener('mousemove', hover, true);
    document.removeEventListener('click', click, true);
    document.removeEventListener('keydown', key, true);
    if (last) last.style.outline = last.dataset.rmOutline || '';
    window.__readingMapSelectCleanup = null;
  }
  document.addEventListener('mousemove', hover, true);
  document.addEventListener('click', click, true);
  document.addEventListener('keydown', key, true);
  window.__readingMapSelectCleanup = cleanup;
  return true;
})();
"""


def _connected_driver():
    if not _browser_is_running():
        raise ValueError("辅助 Chrome 尚未启动，请先搜索并打开目标页面")
    binary = _chrome_binary()
    chromedriver = _chromedriver_binary()
    if not binary or not chromedriver:
        raise ValueError("未找到 Chrome / ChromeDriver")
    options = Options()
    options.debugger_address = f"127.0.0.1:{_debug_port()}"
    options.binary_location = binary
    return webdriver.Chrome(service=Service(chromedriver), options=options)


def _target_url(expected_title: str) -> str:
    """Pick a recognizable current task page; never silently read an unrelated tab."""
    pages = _devtools_json("/json")
    keywords = [word.casefold() for word in expected_title.split() if len(word) >= 3][:4]
    allowed = []
    for row in pages:
        if row.get("type") != "page":
            continue
        url = row.get("url") or ""
        parsed = urlsplit(url)
        host = (parsed.hostname or "").casefold()
        if parsed.scheme not in {"http", "https"} or host in {"127.0.0.1", "localhost"}:
            continue
        if any(h in host for h in ("google.", "bing.", "baidu.")):
            continue
        title = (row.get("title") or "").casefold()
        haystack = title + " " + parsed.path.casefold().replace("-", " ")
        if keywords and not any(word in haystack for word in keywords):
            continue
        allowed.append(row)
    if not allowed:
        raise ValueError("没有找到与当前审核对象匹配的页面；请在辅助 Chrome 打开目标系列页面")
    if len(allowed) > 1:
        # DevTools target order is not a reliable active-tab indicator.
        raise ValueError("找到多个匹配页面，请先关闭或切走重复标签页，再采集结构")
    return allowed[0]["url"]


def _with_target(expected_title: str, callback):
    with _browser_lock:
        url = _target_url(expected_title)
        driver = _connected_driver()
        try:
            wanted = urlsplit(url)
            match = False
            for handle in driver.window_handles:
                driver.switch_to.window(handle)
                current = urlsplit(driver.current_url)
                if current.hostname == wanted.hostname and current.path.rstrip("/") == wanted.path.rstrip("/"):
                    match = True
                    break
            if not match:
                raise ValueError("辅助浏览器目标页已变化，请重新采集")
            return callback(driver)
        finally:
            with suppress(Exception):
                driver.service.stop()


def snapshot_current_page(expected_title: str) -> PageSnapshot:
    def snapshot(driver):
        html = driver.execute_script("return document.documentElement.outerHTML")
        return PageSnapshot(url=driver.current_url, title=driver.title, html=html)
    return _with_target(expected_title, snapshot)


def start_region_selection(expected_title: str) -> dict:
    def start(driver):
        driver.execute_script(_SELECTION_JS)
        return {"ready": True, "message": "请切换到辅助 Chrome，用鼠标点击书籍网格；按 Esc 取消"}
    return _with_target(expected_title, start)


def poll_region_selection(expected_title: str) -> dict:
    def poll(driver):
        data = driver.execute_script("return window.__readingMapRegion || null")
        if data:
            driver.execute_script("window.__readingMapRegion = null")
        return {"ready": bool(data), "region": data}
    return _with_target(expected_title, poll)
