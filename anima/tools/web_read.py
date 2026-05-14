"""
Anima — Web Read Tool
抓取网页内容，提取正文文本
"""

from __future__ import annotations

import logging
import re
import httpx

logger = logging.getLogger("anima.tools.web_read")

MAX_CONTENT_LENGTH = 8000  # 最大返回字符数


async def tool_web_read(args: dict) -> str:
    """
    读取指定 URL 的网页内容。
    args:
      url: str  目标 URL
      max_length: int  最大返回长度（默认8000字符）
    """
    url = args.get("url", "")
    max_length = int(args.get("max_length", MAX_CONTENT_LENGTH))

    if not url:
        return "[错误] 缺少 url 参数"

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; Anima/1.0)"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")

        if "text/html" in content_type:
            text = _extract_text_from_html(resp.text)
        elif "application/json" in content_type:
            text = resp.text
        elif "text/" in content_type:
            text = resp.text
        else:
            return f"[不支持的内容类型] {content_type}"

        if len(text) > max_length:
            text = text[:max_length] + f"\n\n[已截断，原文共 {len(resp.text)} 字符]"

        return f"网页内容（{url}）：\n\n{text}"

    except httpx.HTTPStatusError as e:
        return f"[HTTP错误] {e.response.status_code}: {url}"
    except Exception as e:
        logger.error(f"[web_read] 抓取失败: {e}")
        return f"[抓取失败] {e}"


def _extract_text_from_html(html: str) -> str:
    """从 HTML 中提取正文文本（轻量实现，不依赖 BeautifulSoup）"""
    # 移除 script 和 style
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.S | re.I)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.S | re.I)
    # 移除 HTML 注释
    html = re.sub(r'<!--.*?-->', '', html, flags=re.S)
    # 移除 nav, header, footer
    html = re.sub(r'<(nav|header|footer)[^>]*>.*?</\1>', '', html, flags=re.S | re.I)
    # 把 br/p/div/li 转换为换行
    html = re.sub(r'<(br|p|div|li|h[1-6])[^>]*>', '\n', html, flags=re.I)
    # 移除所有 HTML 标签
    text = re.sub(r'<[^>]+>', '', html)
    # 清理多余空行
    text = re.sub(r'\n{3,}', '\n\n', text)
    # 清理多余空格
    text = re.sub(r'[ \t]+', ' ', text)
    # 去除首尾空白
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return '\n'.join(lines)
