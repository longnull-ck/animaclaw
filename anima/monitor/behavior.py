"""
Anima — Behavior Monitor（行为监控）

衔尾蛇的闭环核心：
  监控行为 → 发现模式 → 自动生成规则 → 规则改变行为 → 新模式 → 继续监控

设计原则：
  1. 纯统计驱动，不依赖 LLM 判断
  2. 模式检测是确定性的（计数 + 阈值），不是概率的
  3. 生成的规则直接插入 RuleEngine，立即生效
  4. 不需要人工干预

监控维度：
  - 重复失败模式：同一个 action 连续失败 N 次 → 生成熔断规则
  - 重复路径模式：每次 A 问题都走 B 工具 → 生成直通规则
  - 无效模式：某个动作成功率极低 → 生成抑制规则
  - 偏好模式：主人对某类回复满意度高 → 生成风格规则
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("anima.monitor")

# 模式检测阈值
REPEAT_FAIL_THRESHOLD = 3       # 同一 action 连续失败 N 次触发
SHORTCUT_THRESHOLD = 5          # 同一路径出现 N 次，生成直通规则
LOW_SUCCESS_THRESHOLD = 0.2     # 成功率低于 20% 触发抑制
MIN_SAMPLES_FOR_PATTERN = 5     # 至少 N 个样本才做模式判断
PREFERENCE_THRESHOLD = 0.8      # 满意度高于此值认为是偏好


@dataclass
class ActionRecord:
    """一次动作的完整记录"""
    id: str
    timestamp: str
    # 输入
    signal_type: str            # 信号类型
    question: str               # 处理的问题
    message: str = ""           # 原始消息（如果有）
    # 决策
    decision_source: str = ""   # "rule" | "llm" | "tool"
    rule_id: str | None = None  # 如果是规则触发的
    tool_used: str | None = None
    # 结果
    success: bool = True
    error: str | None = None
    owner_satisfaction: float | None = None  # 主人反馈
    # 上下文
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "signal_type": self.signal_type,
            "question": self.question,
            "message": self.message,
            "decision_source": self.decision_source,
            "rule_id": self.rule_id,
            "tool_used": self.tool_used,
            "success": self.success,
            "error": self.error,
            "owner_satisfaction": self.owner_satisfaction,
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ActionRecord":
        return cls(
            id=d["id"],
            timestamp=d["timestamp"],
            signal_type=d.get("signal_type", ""),
            question=d.get("question", ""),
            message=d.get("message", ""),
            decision_source=d.get("decision_source", ""),
            rule_id=d.get("rule_id"),
            tool_used=d.get("tool_used"),
            success=d.get("success", True),
            error=d.get("error"),
            owner_satisfaction=d.get("owner_satisfaction"),
            context=d.get("context", {}),
        )


@dataclass
class DetectedPattern:
    """检测到的行为模式"""
    pattern_type: str       # "repeat_fail" | "shortcut" | "low_success" | "preference"
    description: str
    evidence: dict[str, Any]
    suggested_rule: dict    # 生成规则的参数


class BehaviorMonitor:
    """
    行为监控器。

    使用：
      monitor = BehaviorMonitor(data_dir, rule_engine)
      monitor.initialize()

      # 每次动作完成后：
      monitor.record(action_record)

      # 定期（或每次 record 后）检查模式：
      patterns = monitor.analyze()
      # patterns 不为空 → 规则已自动插入 RuleEngine
    """

    def __init__(self, data_dir: str | Path, rule_engine):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self._data_dir / "action_log.json"
        self._patterns_file = self._data_dir / "detected_patterns.json"
        self._rule_engine = rule_engine
        self._records: list[ActionRecord] = []
        self._detected_patterns: list[DetectedPattern] = []
        # 内存中的快速统计缓存
        self._consecutive_fails: dict[str, int] = defaultdict(int)
        self._path_counter: Counter = Counter()  # (question_pattern → tool) 路径计数

    def initialize(self) -> None:
        """加载历史记录"""
        self._load_records()
        self._rebuild_caches()
        logger.info(f"[Monitor] 初始化完成: {len(self._records)} 条历史记录")

    # ─── 记录 ───────────────────────────────────────────────

    def record(self, rec: ActionRecord) -> list[DetectedPattern]:
        """
        记录一次动作，并立即检查是否产生新模式。
        返回新检测到的模式列表（可能为空）。
        """
        self._records.append(rec)
        self._update_caches(rec)
        self._save_records()

        # 每次记录后立即检查模式
        new_patterns = self._detect_patterns(rec)

        for pattern in new_patterns:
            self._apply_pattern(pattern)
            self._detected_patterns.append(pattern)

        if new_patterns:
            self._save_patterns()

        return new_patterns

    # ─── 分析（批量模式检测） ────────────────────────────────

    def analyze(self) -> list[DetectedPattern]:
        """
        全量分析历史记录，检测所有模式。
        通常在定期任务中调用（如每日复盘时）。
        """
        patterns: list[DetectedPattern] = []

        patterns.extend(self._detect_low_success_tools())
        patterns.extend(self._detect_shortcut_paths())
        patterns.extend(self._detect_preference_patterns())

        for pattern in patterns:
            if not self._pattern_already_handled(pattern):
                self._apply_pattern(pattern)
                self._detected_patterns.append(pattern)

        if patterns:
            self._save_patterns()

        return patterns

    # ─── 模式检测器 ──────────────────────────────────────────

    def _detect_patterns(self, latest: ActionRecord) -> list[DetectedPattern]:
        """基于最新记录做增量模式检测"""
        patterns: list[DetectedPattern] = []

        # 1. 重复失败检测
        fail_pattern = self._check_repeat_fail(latest)
        if fail_pattern:
            patterns.append(fail_pattern)

        # 2. 快捷路径检测
        shortcut_pattern = self._check_shortcut(latest)
        if shortcut_pattern:
            patterns.append(shortcut_pattern)

        return patterns

    def _check_repeat_fail(self, rec: ActionRecord) -> DetectedPattern | None:
        """检测：同一类问题连续失败"""
        if rec.success:
            # 成功了，重置计数
            key = self._normalize_question(rec.question)
            self._consecutive_fails[key] = 0
            return None

        key = self._normalize_question(rec.question)
        self._consecutive_fails[key] += 1
        count = self._consecutive_fails[key]

        if count >= REPEAT_FAIL_THRESHOLD:
            # 已经有对应规则了就不再生成
            rule_name = f"auto_suppress_{key[:30]}"
            if self._rule_already_exists(rule_name):
                return None

            return DetectedPattern(
                pattern_type="repeat_fail",
                description=f"问题「{rec.question[:40]}」连续失败 {count} 次",
                evidence={
                    "question_key": key,
                    "fail_count": count,
                    "last_error": rec.error,
                    "last_tool": rec.tool_used,
                },
                suggested_rule={
                    "name": rule_name,
                    "description": f"自动生成：「{key[:30]}」类问题连续失败 {count} 次，暂停自动处理",
                    "conditions": [
                        {"field": "question", "operator": "contains", "value": key[:40]},
                    ],
                    "action_type": "notify",
                    "action_params": {
                        "text": f"⚠️ 「{key[:30]}」类任务连续失败 {count} 次，已暂停。上次错误：{(rec.error or '未知')[:60]}",
                        "suppress_further": True,
                    },
                    "confidence": 0.7,
                },
            )
        return None

    def _check_shortcut(self, rec: ActionRecord) -> DetectedPattern | None:
        """检测：同一类问题总是用同一个工具解决"""
        if not rec.tool_used or not rec.success:
            return None

        key = self._normalize_question(rec.question)
        path_key = f"{key}→{rec.tool_used}"
        self._path_counter[path_key] += 1
        count = self._path_counter[path_key]

        if count >= SHORTCUT_THRESHOLD:
            rule_name = f"auto_shortcut_{key[:20]}_{rec.tool_used}"
            if self._rule_already_exists(rule_name):
                return None

            return DetectedPattern(
                pattern_type="shortcut",
                description=f"「{key[:30]}」类问题已 {count} 次使用 {rec.tool_used} 成功解决",
                evidence={
                    "question_key": key,
                    "tool": rec.tool_used,
                    "success_count": count,
                },
                suggested_rule={
                    "name": rule_name,
                    "description": f"自动生成：「{key[:30]}」类问题直通 {rec.tool_used}，跳过LLM判断",
                    "conditions": [
                        {"field": "question", "operator": "contains", "value": key[:40]},
                    ],
                    "action_type": "execute_tool",
                    "action_params": {
                        "tool_name": rec.tool_used,
                        "extract_query_from": "question",
                    },
                    "confidence": min(0.6 + count * 0.05, 0.95),
                },
            )
        return None

    def _detect_low_success_tools(self) -> list[DetectedPattern]:
        """检测：某个工具的成功率极低"""
        if len(self._records) < MIN_SAMPLES_FOR_PATTERN:
            return []

        tool_stats: dict[str, dict] = defaultdict(lambda: {"success": 0, "total": 0})
        for rec in self._records[-100:]:  # 只看最近100条
            if rec.tool_used:
                tool_stats[rec.tool_used]["total"] += 1
                if rec.success:
                    tool_stats[rec.tool_used]["success"] += 1

        patterns: list[DetectedPattern] = []
        for tool, stats in tool_stats.items():
            if stats["total"] < MIN_SAMPLES_FOR_PATTERN:
                continue
            success_rate = stats["success"] / stats["total"]
            if success_rate < LOW_SUCCESS_THRESHOLD:
                rule_name = f"auto_warn_low_success_{tool}"
                if self._rule_already_exists(rule_name):
                    continue

                patterns.append(DetectedPattern(
                    pattern_type="low_success",
                    description=f"工具 {tool} 成功率仅 {success_rate:.0%}（{stats['total']} 次调用）",
                    evidence={
                        "tool": tool,
                        "success_rate": success_rate,
                        "total_calls": stats["total"],
                    },
                    suggested_rule={
                        "name": rule_name,
                        "description": f"自动生成：工具 {tool} 成功率过低，使用前先通知主人确认",
                        "conditions": [
                            {"field": "tool_to_use", "operator": "equals", "value": tool},
                        ],
                        "action_type": "delegate_llm",
                        "action_params": {
                            "constraints": f"注意：工具 {tool} 近期成功率仅 {success_rate:.0%}，"
                                           f"请考虑替代方案或先确认参数正确。",
                        },
                        "confidence": 0.6,
                    },
                ))

        return patterns

    def _detect_preference_patterns(self) -> list[DetectedPattern]:
        """检测：主人对某类回复风格的偏好"""
        rated = [r for r in self._records if r.owner_satisfaction is not None]
        if len(rated) < MIN_SAMPLES_FOR_PATTERN:
            return []

        # 按 decision_source 分组统计满意度
        source_satisfaction: dict[str, list[float]] = defaultdict(list)
        for rec in rated[-50:]:
            source_satisfaction[rec.decision_source].append(rec.owner_satisfaction)

        patterns: list[DetectedPattern] = []
        for source, scores in source_satisfaction.items():
            if len(scores) < 3:
                continue
            avg = sum(scores) / len(scores)
            if avg >= PREFERENCE_THRESHOLD:
                rule_name = f"auto_prefer_{source}"
                if self._rule_already_exists(rule_name):
                    continue
                patterns.append(DetectedPattern(
                    pattern_type="preference",
                    description=f"主人对「{source}」类决策的满意度高达 {avg:.0%}",
                    evidence={
                        "decision_source": source,
                        "avg_satisfaction": avg,
                        "sample_count": len(scores),
                    },
                    suggested_rule={
                        "name": rule_name,
                        "description": f"自动生成：主人偏好 {source} 类决策方式",
                        "conditions": [],  # 偏好规则不直接触发，作为元数据存在
                        "action_type": "modify_state",
                        "action_params": {
                            "state_changes": {"preferred_decision_source": source},
                        },
                        "confidence": min(0.5 + avg * 0.4, 0.9),
                    },
                ))

        return patterns

    # ─── 应用模式 → 生成规则 ──────────────────────────────────

    def _apply_pattern(self, pattern: DetectedPattern) -> None:
        """将检测到的模式转为规则，插入规则引擎"""
        rule_spec = pattern.suggested_rule

        # 偏好规则条件为空时不插入规则引擎
        if not rule_spec.get("conditions"):
            logger.info(f"[Monitor] 检测到偏好模式: {pattern.description}（不生成规则）")
            return

        self._rule_engine.add_self_generated_rule(
            name=rule_spec["name"],
            description=rule_spec["description"],
            conditions=rule_spec["conditions"],
            action_type=rule_spec["action_type"],
            action_params=rule_spec["action_params"],
            confidence=rule_spec.get("confidence", 0.7),
        )

        logger.info(
            f"[Monitor] 模式 → 规则: {pattern.pattern_type} | "
            f"{pattern.description[:60]} → {rule_spec['name']}"
        )

    # ─── 工具方法 ────────────────────────────────────────────

    def _normalize_question(self, question: str) -> str:
        """
        将问题归一化为 key（用于模式匹配）。
        去掉细节，保留核心意图。
        """
        # 简单实现：取前30字符的关键词
        import re
        cleaned = re.sub(r'[^\w\s]', '', question[:60])
        words = cleaned.split()[:5]
        return "_".join(words) if words else "unknown"

    def _rule_already_exists(self, rule_name: str) -> bool:
        """检查同名规则是否已存在"""
        for rule in self._rule_engine.get_all_rules():
            if rule.name == rule_name:
                return True
        return False

    def _pattern_already_handled(self, pattern: DetectedPattern) -> bool:
        """检查这个模式是否已经被处理过"""
        rule_name = pattern.suggested_rule.get("name", "")
        return self._rule_already_exists(rule_name)

    def _update_caches(self, rec: ActionRecord) -> None:
        """更新内存缓存"""
        if rec.tool_used and rec.success:
            key = self._normalize_question(rec.question)
            path_key = f"{key}→{rec.tool_used}"
            self._path_counter[path_key] += 1

    def _rebuild_caches(self) -> None:
        """从历史记录重建缓存"""
        self._consecutive_fails.clear()
        self._path_counter.clear()

        for rec in self._records:
            if rec.tool_used and rec.success:
                key = self._normalize_question(rec.question)
                path_key = f"{key}→{rec.tool_used}"
                self._path_counter[path_key] += 1

        # 重建连续失败计数（只看最近的连续序列）
        recent_by_key: dict[str, list[bool]] = defaultdict(list)
        for rec in self._records[-50:]:
            key = self._normalize_question(rec.question)
            recent_by_key[key].append(rec.success)

        for key, results in recent_by_key.items():
            # 从最后往前数连续失败
            count = 0
            for success in reversed(results):
                if not success:
                    count += 1
                else:
                    break
            if count > 0:
                self._consecutive_fails[key] = count

    # ─── 统计 ───────────────────────────────────────────────

    def stats(self) -> dict:
        total = len(self._records)
        success = sum(1 for r in self._records if r.success)
        rule_triggered = sum(1 for r in self._records if r.decision_source == "rule")
        llm_triggered = sum(1 for r in self._records if r.decision_source == "llm")
        return {
            "total_records": total,
            "success_rate": round(success / total, 3) if total else 0.0,
            "rule_decisions": rule_triggered,
            "llm_decisions": llm_triggered,
            "rule_ratio": round(rule_triggered / total, 3) if total else 0.0,
            "patterns_detected": len(self._detected_patterns),
            "active_consecutive_fails": dict(self._consecutive_fails),
        }

    # ─── 持久化 ──────────────────────────────────────────────

    def _load_records(self) -> None:
        if not self._log_file.exists():
            self._records = []
            return
        try:
            data = json.loads(self._log_file.read_text(encoding="utf-8"))
            self._records = [ActionRecord.from_dict(d) for d in data]
            # 只保留最近 500 条
            if len(self._records) > 500:
                self._records = self._records[-500:]
        except Exception as e:
            logger.error(f"[Monitor] 加载记录失败: {e}")
            self._records = []

    def _save_records(self) -> None:
        # 只保留最近 500 条
        to_save = self._records[-500:]
        data = [r.to_dict() for r in to_save]
        self._log_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )

    def _save_patterns(self) -> None:
        data = [
            {
                "pattern_type": p.pattern_type,
                "description": p.description,
                "evidence": p.evidence,
                "suggested_rule_name": p.suggested_rule.get("name", ""),
            }
            for p in self._detected_patterns[-100:]  # 只保留最近100个
        ]
        self._patterns_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
