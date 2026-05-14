"""
Anima — Web Search Tool
使用 DuckDuckGo HTML 搜索（无需 API Key）
"""

from __future__ import annotations

import logging
import httpx

logger = logging.getLogger("anima.tools.web_search")

DDGS_URL = "https://html.duckduckgo.com/html/"


async def tool_web_search(args: dict) -> str:
    """
    搜索互联网。
    args:
      query: str  搜索关键词
      max_results: int  最大结果数（默认5）
    """
    query = args.get("query", "")
    max_results = int(args.get("max_results", 5))

    if not query:
        return "[错误] 缺少搜索关键词 query"

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.post(
                DDGS_URL,
                data={"q": query, "b": ""},
                headers={"User-Agent": "Mozilla/5.0 (compatible; Anima/1.0)"},
            )
            resp.raise_for_status()
            html = resp.text

        # 简单解析 DuckDuckGo HTML 结果
        results = _parse_ddg_html(html, max_results)

        if not results:
            return f"搜索「{query}」未找到结果"

        output = f"搜索「{query}」的结果：\n\n"
        for i, r in enumerate(results, 1):
            output += f"{i}. {r['title']}\n   {r['url']}\n   {r['snippet']}\n\n"

        return output.strip()

    except Exception as e:
        logger.error(f"[web_search] 搜索失败: {e}")
        return f"[搜索失败] {e}"


def _parse_ddg_html(html: str, max_results: int) -> list[dict]:
    """从 DuckDuckGo HTML 中提取搜索结果"""
    results: list[dict] = []

    # 简单的标记解析（不依赖 BeautifulSoup）
    parts = html.split('class="result__a"')
    for part in parts[1:max_results + 1]:
        try:
            # 提取 URL
            href_start = part.find('href="') + 6
            href_end = part.find('"', href_start)
            url = part[href_start:href_end]

            # 提取标题
            title_start = part.find('>') + 1
            title_end = part.find('</a>')
            title = part[title_start:title_end].strip()
            # 清理 HTML 标签
            title = _strip_tags(title)

            # 提取摘要
            snippet = ""
            snippet_marker = 'class="result__snippet"'
            if snippet_marker in part:
                s_start = part.find('>', part.find(snippet_marker)) + 1
                s_end = part.find('</a>', s_start)
                if s_end == -1:
                    s_end = part.find('</span>', s_start)
                snippet = _strip_tags(part[s_start:s_end]).strip()

            if url and title:
                results.append({
                    "title": title[:100],
                    "url": url,
                    "snippet": snippet[:200],
                })
        except (IndexError, ValueError):
            continue

    return results


def _strip_tags(text: str) -> str:
    """移除 HTML 标签"""
    import re
    return re.sub(r'<[^>]+>', '', text).strip()
