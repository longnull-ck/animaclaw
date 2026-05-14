"""
Anima — Task Template Store（任务模板库）

每当 Anima 成功完成一个任务，自动提取模式生成可复用模板。
下次遇到类似任务时，直接套用模板加速执行。

核心能力：
  - 从完成的任务中自动提炼模板
  - 基于语义相似度匹配模板
  - 模板随使用次数增加自动优化
  - 支持用户手动教导新模板
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anima.task_processor import GenericTask

logger = logging.getLogger("anima.task_templates")


class TaskTemplateStore:
    """
    任务模板库。
    从成功完成的任务中自动生成模板，加速未来类似任务的处理。
    """

    def __init__(self, data_dir: str | Path, brain=None):
        self._file = Path(data_dir) / "task_templates.json"
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        self._brain = brain  # 用于语义匹配

    # ─── 模板匹配 ────────────────────────────────────────────

    def find_matching(self, task_description: str) -> dict | None:
        """
        查找与任务描述最匹配的模板。
        使用关键词匹配 + 使用次数加权。
        """
        templates = self._load()
        if not templates:
            return None

        text = task_description.lower()
        best_match: tuple[dict, float] | None = None

        for tmpl in templates.values():
            # 关键词匹配得分
            keywords = tmpl.get("keywords", [])
            if not keywords:
                continue

            hits = sum(1 for kw in keywords if kw.lower() in text)
            if hits == 0:
                continue

            # 得分 = 命中率 × 使用次数加成 × 成功率加成
            keyword_score = hits / len(keywords)
            usage_bonus = min(tmpl.get("use_count", 0) / 10, 0.3)  # 最多 +0.3
            success_bonus = tmpl.get("avg_quality", 0.7) * 0.2
            score = keyword_score + usage_bonus + success_bonus

            if best_match is None or score > best_match[1]:
                best_match = (tmpl, score)

        # 只有分数超过阈值才返回
        if best_match and best_match[1] >= 0.3:
            logger.info(f"[Templates] 匹配模板: {best_match[0]['name']} (score={best_match[1]:.2f})")
            return best_match[0]

        return None

    # ─── 从完成的任务生成模板 ─────────────────────────────────

    def generate_from_task(self, task: "GenericTask") -> dict | None:
        """
        从一个成功完成的任务中自动提炼模板。
        只有质量分 >= 0.6 的任务才会生成模板。
        """
        if task.quality_score < 0.6:
            return None

        # 提取关键词（从任务描述中提取名词和动词）
        keywords = self._extract_keywords(task.description)
        if len(keywords) < 2:
            return None

        # 提取步骤模板
        step_templates = []
        for step in task.decomposed_steps:
            if step.status == "done":
                step_templates.append({
                    "description_pattern": step.description,
                    "required_skills": step.required_skills,
                    "acceptance_criteria": step.acceptance_criteria,
                    "tool_used": step.tool_used,
                })

        if not step_templates:
            return None

        # 生成模板名称
        name = task.description[:40]
        if len(task.description) > 40:
            name += "..."

        template = {
            "id": str(uuid.uuid4())[:8],
            "name": name,
            "description": task.description,
            "keywords": keywords,
            "steps": step_templates,
            "avg_quality": task.quality_score,
            "use_count": 1,
            "corrections_avg": task.corrections_made,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "source_task_id": task.id,
        }

        # 保存
        templates = self._load()
        templates[template["id"]] = template
        self._save(templates)

        logger.info(f"[Templates] 新模板: {name}")
        return template

    # ─── 更新模板（每次使用后优化） ─────────────────────────

    def update_after_use(self, template_id: str, quality_score: float) -> None:
        """
        模板被使用后，更新使用次数和平均质量。
        模板会越用越精准。
        """
        templates = self._load()
        tmpl = templates.get(template_id)
        if not tmpl:
            return

        tmpl["use_count"] = tmpl.get("use_count", 0) + 1
        # 移动平均质量分
        old_avg = tmpl.get("avg_quality", 0.7)
        count = tmpl["use_count"]
        tmpl["avg_quality"] = round((old_avg * (count - 1) + quality_score) / count, 4)
        tmpl["updated_at"] = datetime.utcnow().isoformat()

        templates[template_id] = tmpl
        self._save(templates)

    # ─── 手动教导模板 ────────────────────────────────────────

    def teach_template(
        self,
        name: str,
        description: str,
        keywords: list[str],
        steps: list[dict],
    ) -> dict:
        """
        手动教给 Anima 一个任务模板。
        用于你想固化某种处理方式时。
        """
        template = {
            "id": str(uuid.uuid4())[:8],
            "name": name,
            "description": description,
            "keywords": keywords,
            "steps": steps,
            "avg_quality": 0.8,
            "use_count": 0,
            "corrections_avg": 0,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "source_task_id": None,
            "taught": True,
        }

        templates = self._load()
        templates[template["id"]] = template
        self._save(templates)

        logger.info(f"[Templates] 手动教导模板: {name}")
        return template

    # ─── 获取所有模板 ────────────────────────────────────────

    def list_all(self) -> list[dict]:
        """列出所有模板（按使用次数排序）"""
        templates = self._load()
        sorted_templates = sorted(
            templates.values(),
            key=lambda t: t.get("use_count", 0),
            reverse=True,
        )
        return sorted_templates

    def stats(self) -> dict:
        """模板库统计"""
        templates = self._load()
        if not templates:
            return {"total": 0, "taught": 0, "auto_generated": 0, "total_uses": 0}

        taught = sum(1 for t in templates.values() if t.get("taught"))
        total_uses = sum(t.get("use_count", 0) for t in templates.values())

        return {
            "total": len(templates),
            "taught": taught,
            "auto_generated": len(templates) - taught,
            "total_uses": total_uses,
        }

    # ─── 删除模板 ────────────────────────────────────────────

    def delete(self, template_id: str) -> bool:
        templates = self._load()
        if template_id in templates:
            del templates[template_id]
            self._save(templates)
            return True
        return False

    # ─── 内部方法 ────────────────────────────────────────────

    def _extract_keywords(self, text: str) -> list[str]:
        """
        从任务描述中提取关键词。
        简单实现：按标点和空格分词，过滤停用词，取高频词。
        """
        import re

        # 中文分词（简单按标点分割）
        segments = re.split(r'[，。！？、；：""''（）\s,.\-!?;:\'\"()\[\]{}<>]+', text)
        # 过滤太短或太长的
        words = [w.strip() for w in segments if 2 <= len(w.strip()) <= 10]

        # 去重保持顺序
        seen = set()
        unique = []
        for w in words:
            if w not in seen:
                seen.add(w)
                unique.append(w)

        return unique[:10]  # 最多 10 个关键词

    def _load(self) -> dict[str, dict]:
        if not self._file.exists():
            return {}
        try:
            return json.loads(self._file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            return {}

    def _save(self, templates: dict[str, dict]) -> None:
        self._file.write_text(
            json.dumps(templates, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
