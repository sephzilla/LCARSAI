"""Small opt-in web lookup used only when the user explicitly requests a search."""
from __future__ import annotations

from html.parser import HTMLParser
import re
import urllib.parse
import urllib.request


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "svg"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "svg") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            value = " ".join(data.split())
            if value:
                self.parts.append(value)


def search_web(query: str, limit: int = 5) -> list[dict[str, str]]:
    """Fetch DuckDuckGo HTML results for an explicitly requested web search."""
    query = query.strip()
    if not query:
        return []
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    req = urllib.request.Request(url, headers={"User-Agent": "Computer-LCARS-AI/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            html = response.read(2_000_000).decode("utf-8", errors="replace")
    except Exception as exc:
        raise RuntimeError(f"Web lookup failed: {exc}") from exc
    # Parse only result anchors and their nearby snippets; don't execute page content.
    anchors = re.findall(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.I | re.S
    )
    snippets = re.findall(
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>|<div[^>]+class="result__snippet"[^>]*>(.*?)</div>',
        html, re.I | re.S
    )
    results = []
    for index, (href, title_html) in enumerate(anchors[:limit]):
        title_parser = _TextParser()
        title_parser.feed(title_html)
        title = " ".join(title_parser.parts).strip()
        snippet = ""
        if index < len(snippets):
            snippet_parser = _TextParser()
            snippet_parser.feed(" ".join(snippets[index]))
            snippet = " ".join(snippet_parser.parts).strip()
        if href.startswith("//"):
            href = "https:" + href
        if title and href.startswith("http"):
            results.append({"title": title, "url": href, "snippet": snippet})
    return results
