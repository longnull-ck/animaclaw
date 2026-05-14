"""
Anima — Evolution Engine（进化引擎）
进化 = 从每次处理问题的结果中提取"什么方法有效"，然后更新自己的行为模式
"""

from __future__ import annotations

import json
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable, Awaitable

from anima.models import Experience, ExperienceOutcome, Methodology, AnimaState

logger = logging.getLogger("anima.evolution")

MAX_EXPERIENCES = 1000


class EvolutionEngine:

    def __init__(self, data_dir: str | Path):
        self._exp_file    = Path(data_dir) / "experiences.json"
        self._method_file = Path(data_dir) / "methodologies.json"
        Path(data_dir).mkdir(parents=True, exist_ok=True)

    def initialize(self) -> None:
        if not self._exp_file.exists():
            self._save_exps([])
        if not self._method_file.exists():
            self._save_methods({})

    def record(self, action: str, method: str, outcome: ExperienceOutcome,
               skill_id: str | None = None, question_id: str | None = None,
               lesson: str | None = None) -> Experience:
        exp = Experience(id=str(uuid.uuid4()), action=action, method=method,
                         outcome=outcome, skill_id=skill_id, question_id=question_id, lesson=lesson)
        exps = self._load_exps()
        exps.append(exp)
        if len(exps) > MAX_EXPERIENCES:
            exps = exps[-MAX_EXPERIENCES:]
        self._save_exps(exps)
        return exp

    def apply_feedback(self, exp_id: str, satisfaction: float, comment: str = "") -> None:
        exps = self._load_exps()
        for exp in exps:
            if exp.id == exp_id:
                exp.owner_satisfaction = satisfaction
                if comment:
                    exp.lesson = (exp.lesson or "") + f" | 主人反馈：{comment}"
                break
        self._save_exps(exps)

    async def reflect(self, state: AnimaState,
                      brain_think_json: Callable[[str, str], Awaitable[dict]]) -> dict:
        exps = self._load_exps()
        recent = exps[-50:]
        if len(recent) < 3:
            return {"assessment": "经历太少，继续积累", "skill_gaps": [], "personality_adjustments": {}}

        success_count = sum(1 for e in recent if e.outcome == ExperienceOutcome.SUCCESS)
        fail_count    = sum(1 for e in recent if e.outcome == ExperienceOutcome.FAILURE)
        with_feedback = [e for e in recent if e.owner_satisfaction is not None]
        avg_sat = sum(e.owner_satisfaction for e in with_feedback) / len(with_feedback) if with_feedback else 0
        methods = self._load_methods()

        result = await brain_think_json(
            "你是一个自我反思的 AI 员工，正在进行工作复盘。用 JSON 回复。",
            f"""基于以下近期工作数据进行复盘：
- 最近经历：{len(recent)}，成功：{success_count}，失败：{fail_count}
- 主人平均满意度：{avg_sat:.0%}
- 已有方法论数：{len(methods)}
- 典型失败行动：{[e.action[:40] for e in recent if e.outcome == ExperienceOutcome.FAILURE][:5]}

请输出JSON：
{{
  "assessment": "总体评估",
  "skill_gaps": ["能力短板1"],
  "new_methodology": {{"scenario": "场景", "method": "方法", "effectiveness": 0.8, "conditions": "条件"}},
  "personality_adjustments": {{"proactivity_delta": 0.01, "risk_tolerance_delta": 0.0}}
}}"""
        )

        if nm := result.get("new_methodology"):
            if nm.get("scenario") and nm.get("method"):
                m = Methodology(id=str(uuid.uuid4()), scenario=nm["scenario"],
                                method=nm["method"], effectiveness=float(nm.get("effectiveness", 0.7)),
                                conditions=nm.get("conditions", ""))
                methods[m.id] = m
                self._save_methods(methods)
                logger.info(f"[Evolution] 提炼新方法论: {m.scenario[:40]}")

        return result

    def find_methodology(self, scenario: str) -> Methodology | None:
        methods = self._load_methods()
        if not methods:
            return None
        text = scenario.lower()
        tokens = text.split()
        best: tuple[Methodology, float] | None = None
        for m in methods.values():
            m_text = (m.scenario + " " + m.conditions).lower()
            hits = sum(1 for t in tokens if t in m_text)
            score = hits / max(len(tokens), 1) + m.effectiveness * 0.3
            if best is None or score > best[1]:
                best = (m, score)
        return best[0] if best and best[1] > 0.2 else None

    def stats(self) -> dict:
        exps = self._load_exps()
        methods = self._load_methods()
        with_feedback = [e for e in exps if e.owner_satisfaction is not None]
        avg_sat = sum(e.owner_satisfaction for e in with_feedback) / len(with_feedback) if with_feedback else 0.0
        success_rate = sum(1 for e in exps if e.outcome == ExperienceOutcome.SUCCESS) / len(exps) if exps else 0.0
        return {
            "total_experiences": len(exps),
            "success_rate": round(success_rate, 3),
            "avg_owner_satisfaction": round(avg_sat, 3),
            "methodology_count": len(methods),
        }

    def _load_exps(self) -> list[Experience]:
        if not self._exp_file.exists():
            return []
        raw = json.loads(self._exp_file.read_text(encoding="utf-8"))
        result = []
        for d in raw:
            d["outcome"] = ExperienceOutcome(d["outcome"])
            result.append(Experience(**d))
        return result

    def _save_exps(self, exps: list[Experience]) -> None:
        data = [{"id": e.id, "action": e.action, "method": e.method,
                 "outcome": e.outcome.value, "skill_id": e.skill_id,
                 "question_id": e.question_id, "owner_satisfaction": e.owner_satisfaction,
                 "lesson": e.lesson, "created_at": e.created_at} for e in exps]
        from anima.utils import atomic_write_json
        atomic_write_json(self._exp_file, data)

    def _load_methods(self) -> dict[str, Methodology]:
        if not self._method_file.exists():
            return {}
        raw = json.loads(self._method_file.read_text(encoding="utf-8"))
        return {mid: Methodology(**d) for mid, d in raw.items()}

    def _save_methods(self, methods: dict[str, Methodology]) -> None:
        data = {mid: {"id": m.id, "scenario": m.scenario, "method": m.method,
                      "effectiveness": m.effectiveness, "conditions": m.conditions,
                      "validation_count": m.validation_count, "updated_at": m.updated_at}
                for mid, m in methods.items()}
        from anima.utils import atomic_write_json
        atomic_write_json(self._method_file, data)
