"""
Anima — Summarize Tool
使用大模型对长文本进行摘要提炼。

支持场景：
  - 长文档摘要
  - 会议纪要提炼
  - 文章要点总结
  - 多源信息合并总结
"""

from __future__ import annotations

import logging

logger = logging.getLogger("anima.tools.summarize")


async def tool_summarize(args: dict) -> str:
    """
    对文本进行摘要提炼。

    args:
      text: str          待摘要的文本（必填）
      style: str         摘要风格：bullet（要点列表）、paragraph（段落）、oneliner（一句话）
                         默认 bullet
      max_length: int    摘要最大字数（默认 300）
      language: str      输出语言（默认 zh，可选 en）
      focus: str         聚焦主题（可选，如"技术方案"、"行动项"）
    """
    text = args.get("text", "")
    style = args.get("style", "bullet")
    max_length = int(args.get("max_length", 300))
    language = args.get("language", "zh")
    focus = args.get("focus", "")

    if not text:
        return "[错误] 缺少待摘要的文本 text"

    if len(text) < 50:
        return f"文本太短（{len(text)}字），无需摘要：{text}"

    # 本地快速摘要（不依赖外部 Brain 实例）
    # 实际使用时由 TaskProcessor 通过 LLM 调用，这里提供兜底逻辑
    try:
        summary = _local_extractive_summary(text, max_length, style, focus)
        return summary
    except Exception as e:
        logger.error(f"[summarize] 摘要失败: {e}")
        return f"[摘要失败] {e}"


def _local_extractive_summary(text: str, max_length: int, style: str, focus: str) -> str:
    """
    本地抽取式摘要（不依赖大模型）。
    按句子重要性排序，抽取最重要的句子。
    """
    import re

    # 分句
    sentences = re.split(r'[。！？\n]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 5]

    if not sentences:
        return text[:max_length]

    # 简单评分：句子位置 + 长度 + 关键词匹配
    scored: list[tuple[float, str]] = []
    total = len(sentences)

    for i, sent in enumerate(sentences):
        score = 0.0
        # 位置加分：开头和结尾的句子更重要
        if i < 3:
            score += 2.0 - (i * 0.5)
        if i >= total - 2:
            score += 1.0
        # 长度加分：适中长度的句子更可能包含信息
        if 20 <= len(sent) <= 100:
            score += 1.0
        # 包含数字/数据
        if re.search(r'\d+', sent):
            score += 0.5
        # 关键词匹配
        if focus and focus in sent:
            score += 3.0
        # 包含关键标志词
        key_indicators = ["重要", "关键", "总结", "结论", "因此", "所以", "建议", "目标", "结果"]
        for kw in key_indicators:
            if kw in sent:
                score += 0.5
                break

        scored.append((score, sent))

    # 按得分排序，取前N句
    scored.sort(key=lambda x: x[0], reverse=True)

    # 组装摘要
    selected: list[str] = []
    current_length = 0

    for _, sent in scored:
        if current_length + len(sent) > max_length:
            break
        selected.append(sent)
        current_length += len(sent)

    if not selected:
        selected = [scored[0][1][:max_length]]

    # 格式化输出
    if style == "bullet":
        return "\n".join(f"- {s}" for s in selected)
    elif style == "oneliner":
        return selected[0] if selected else ""
    else:  # paragraph
        return "。".join(selected) + "。"
