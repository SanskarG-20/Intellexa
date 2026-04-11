"""
rag_service.py — Smart Retrieval-Augmented Generation
Fetches live web data to bridge the 2023 knowledge cutoff.

Search Priority:
  1. SerpAPI  (if SERPAPI_API_KEY is configured)
  2. DuckDuckGo HTML scrape  (free fallback, no key required)
"""
import json
import re
import httpx
import datetime
import urllib.parse
from typing import List, Dict, Any
from app.core.config import settings


class RAGService:
    """
    Production RAG Service wired into the Intellexa intelligence pipeline.
    Accepts a `needs_search` flag from the Autopsy Service to avoid keyword matching.
    Provides a free DuckDuckGo fallback so it works without any API key.
    """

    REALTIME_KEYWORDS = {
        "current",
        "latest",
        "today",
        "now",
        "president",
        "who is",
        "recent",
        "breaking",
        "live",
        "update",
    }

    REALTIME_TOPIC_KEYWORDS = {
        "politics",
        "election",
        "senate",
        "congress",
        "government",
        "sports",
        "match",
        "score",
        "league",
        "news",
        "headline",
    }

    @classmethod
    def is_realtime_query(cls, query: str) -> bool:
        text = " ".join(str(query or "").split()).lower()
        if not text:
            return False

        has_realtime_keyword = any(keyword in text for keyword in cls.REALTIME_KEYWORDS)
        has_topic_keyword = any(keyword in text for keyword in cls.REALTIME_TOPIC_KEYWORDS)
        has_recent_year = bool(re.search(r"\b20(2[4-9]|[3-9][0-9])\b", text))

        return has_realtime_keyword or has_topic_keyword or has_recent_year

    @classmethod
    def isRealtimeQuery(cls, query: str) -> bool:
        """
        Compatibility alias matching requested naming.
        """
        return cls.is_realtime_query(query)

    # ──────────────────────────────────────────────
    # 1. SerpAPI (paid, best quality)
    # ──────────────────────────────────────────────
    @staticmethod
    async def _search_serpapi(query: str) -> List[Dict[str, str]]:
        api_key = settings.SERPAPI_API_KEY.strip()
        if not api_key or api_key in ("your_key_here", ""):
            return []

        print(f"[RAG][SerpAPI] Searching: '{query}'")
        params = {
            "q": query,
            "api_key": api_key,
            "engine": "google",
            "num": 5,
        }
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                resp = await client.get("https://serpapi.com/search.json", params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("organic_results", [])
                    cleaned = [
                        {"title": r.get("title", ""), "snippet": r.get("snippet", "")}
                        for r in results if r.get("snippet")
                    ]
                    print(f"[RAG][SerpAPI] {len(cleaned)} results.")
                    return cleaned[:4]
                print(f"[RAG][SerpAPI] Error {resp.status_code}")
        except Exception as e:
            print(f"[RAG][SerpAPI] Exception: {e}")
        return []

    # ──────────────────────────────────────────────
    # 2. DuckDuckGo HTML scrape (free, no key)
    # ──────────────────────────────────────────────
    @staticmethod
    async def _search_duckduckgo(query: str) -> List[Dict[str, str]]:
        """
        Scrapes DuckDuckGo search result HTML to extract titles and snippets.
        This is the reliable fallback when no API keys are available.
        """
        print(f"[RAG][DuckDuckGo] Searching: '{query}'")
        encoded = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"

        try:
            async with httpx.AsyncClient(
                timeout=12.0,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/122.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html",
                },
                follow_redirects=True,
            ) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    print(f"[RAG][DuckDuckGo] HTTP {resp.status_code}")
                    return []

                html = resp.text

                # Extract result snippets from DDG HTML structure
                # DDG HTML results look like: <a class="result__snippet">...</a>
                snippet_pattern = re.compile(
                    r'class="result__snippet"[^>]*>(.*?)</a>', re.DOTALL
                )
                title_pattern = re.compile(
                    r'class="result__a"[^>]*>(.*?)</a>', re.DOTALL
                )

                titles = [
                    re.sub(r"<[^>]+>", "", t).strip()
                    for t in title_pattern.findall(html)
                ]
                snippets = [
                    re.sub(r"<[^>]+>", "", s).strip()
                    for s in snippet_pattern.findall(html)
                ]

                results = []
                for title, snippet in zip(titles, snippets):
                    if snippet and len(snippet) > 20:
                        results.append({"title": title or "Search Result", "snippet": snippet})
                    if len(results) >= 4:
                        break

                print(f"[RAG][DuckDuckGo] {len(results)} results parsed.")
                return results

        except Exception as e:
            print(f"[RAG][DuckDuckGo] Exception: {e}")
        return []

    # ──────────────────────────────────────────────
    # 3. Main Search Dispatcher
    # ──────────────────────────────────────────────
    @classmethod
    async def search_web(cls, query: str) -> List[Dict[str, str]]:
        """
        Routes the search request to the best available engine.
        Priority: SerpAPI → DuckDuckGo HTML
        """
        results = await cls._search_serpapi(query)
        if results:
            return results

        results = await cls._search_duckduckgo(query)
        if results:
            return results

        print("[RAG] All search engines returned empty results.")
        return []

    # ──────────────────────────────────────────────
    # 4. Context Formatter for LLM Injection
    # ──────────────────────────────────────────────
    @staticmethod
    def construct_rag_context(web_data: List[Dict[str, str]]) -> str:
        """
        Formats live web data into a structured block
        ready to be injected into the LLM system prompt.
        """
        if not web_data:
            return ""

        now = datetime.datetime.now().strftime("%A, %d %B %Y, %I:%M %p IST")
        lines = [
            "Context:",
            "Latest verified information:",
            f"(Fetched: {now})",
            "",
        ]
        for i, item in enumerate(web_data, start=1):
            title = " ".join(str(item.get("title", "")).split()) or "Search Result"
            snippet = " ".join(str(item.get("snippet", "")).split())
            lines.append(f"{i}. {title} — {snippet}")

        lines.extend(
            [
                "",
                "Based ONLY on the above information, answer the question.",
                "Do NOT use prior knowledge.",
            ]
        )

        return "\n".join(lines)


rag_service = RAGService()
