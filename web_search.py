from __future__ import annotations

import html
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse
from urllib.request import Request, urlopen
from typing import Any


class _SearchParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._href = ""
        self._text: list[str] = []
        self._in_result = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        href = attrs.get("href", "")
        if tag == "a" and (href.startswith("http") or href.startswith("/l/") or href.startswith("//")):
            if href.startswith("//"):
                href = "https:" + href
            parsed_href = urlparse(href)
            if parsed_href.path.startswith("/l/"):
                target = parse_qs(parsed_href.query).get("uddg", [""])[0]
                href = unquote(target) if target else urljoin("https://duckduckgo.com", href)
            if not href.startswith("http"):
                return
            self._href = href
            self._text = []
            self._in_result = True

    def handle_data(self, data):
        if self._in_result:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._in_result:
            title = " ".join("".join(self._text).split())
            href = html.unescape(self._href)
            if title and not any(item["url"] == href for item in self.results):
                self.results.append({"title": title[:240], "url": href})
            self._href = ""
            self._text = []
            self._in_result = False


def search_web(query: str, limit: int = 5) -> dict[str, Any]:
    query = " ".join((query or "").split())
    if not query:
        return {"ok": False, "error": "query is required", "results": []}
    limit = max(1, min(int(limit), 10))
    url = "https://html.duckduckgo.com/html/?q=" + quote(query)
    request = Request(url, headers={"User-Agent": "genagent/1.0"})
    try:
        with urlopen(request, timeout=12) as response:
            body = response.read(2 * 1024 * 1024).decode("utf-8", errors="replace")
    except Exception as exc:
        return {"ok": False, "error": f"web search failed: {type(exc).__name__}", "results": []}
    parser = _SearchParser()
    parser.feed(body)
    results = parser.results[:limit]
    return {"ok": True, "query": query, "results": results, "source": "DuckDuckGo HTML results"}
