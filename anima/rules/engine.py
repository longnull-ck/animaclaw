"""
Anima — Rule Engine（规则引擎）

不是建议，是法律。
规则引擎是框架层的决策核心：匹配条件 → 直接 dispatch 行为，不经过 LLM。

设计原则：
  1. 规则是代码级的 if-then，不是交给 LLM 的文本提示
  2. 三层优先级：CODE_RULE > SELF_GENERATED > INITIAL
  3. 匹配后直接返回 Action，调用方执行——LLM 无权否决
  4. 自生规则由行为监控产生，持久化存储，可被更高优先级覆盖

执行流程：
  signal 进入 → engine.evaluate(signal_context) →
    如果命中规则 → 返回 RuleAction（直接执行的指令）
    如果没命中   → 返回 None（交给 LLM 兜底）
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("anima.rules")


# ─── 优先级 ──────────────────────────────────────────────────

class RulePriority(IntEnum):
    """
    越高越优先。相同优先级按创建时间（后创建覆盖先创建）。
    """
    INITIAL = 10          # 初始规则（启动时加载的默认行为）
    SELF_GENERATED = 50   # 自生规则（行为监控自动产生）
    CODE_RULE = 90        # 代码规则（硬编码，不可被自生规则覆盖）


# ─── 条件匹配器 ──────────────────────────────────────────────

@dataclass
class Condition:
    """
    规则的触发条件。支持多种匹配方式。

    field: 要检查的上下文字段名（如 "message", "signal_type", "action"）
    operator: 匹配方式
      - "contains": field 包含 value 子串
      - "equals": field == value
      - "regex": field 匹配正则
      - "in": value 是列表，field 在列表中
      - "gt" / "lt": 数值比较
      - "exists": field 存在且非空
    value: 比较值
    """
    field: str
    operator: str
    value: Any = None

    def matches(self, context: dict) -> bool:
        """检查 context 是否满足此条件"""
        actual = context.get(self.field)

        if self.operator == "exists":
            return actual is not None and actual != ""

        if actual is None:
            return False

        if self.operator == "contains":
            return str(self.value).lower() in str(actual).lower()

        if self.operator == "equals":
            return str(actual).lower() == str(self.value).lower()

        if self.operator == "regex":
            try:
                return bool(re.search(str(self.value), str(actual), re.IGNORECASE))
            except re.error:
                return False

        if self.operator == "in":
            if isinstance(self.value, list):
                return str(actual).lower() in [str(v).lower() for v in self.value]
            return False

        if self.operator == "gt":
            try:
                return float(actual) > float(self.value)
            except (ValueError, TypeError):
                return False

        if self.operator == "lt":
            try:
                return float(actual) < float(self.value)
            except (ValueError, TypeError):
                return False

        return False


# ─── 规则动作 ──────────────────────────────────────────────

@dataclass
class RuleAction:
    """
    规则匹配后要执行的动作。
    这是给调用方的硬指令，不是"建议"。

    action_type:
      - "execute_tool": 直接调用工具（tool_name + args）
      - "respond": 直接回复（不经过 LLM 思考）
      - "delegate_llm": 仍交给 LLM，但注入强制约束
      - "suppress": 吞掉信号，不做任何处理
      - "notify": 通知主人
      - "modify_state": 修改内部状态参数
      - "chain": 链式执行多个动作
    """
    action_type: str
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def tool_name(self) -> str | None:
        return self.params.get("tool_name")

    @property
    def tool_args(self) -> dict:
        return self.params.get("tool_args", {})

    @property
    def response_text(self) -> str:
        return self.params.get("text", "")

    @property
    def llm_constraints(self) -> str:
        return self.params.get("constraints", "")

    @property
    def state_changes(self) -> dict:
        return self.params.get("state_changes", {})


# ─── 规则 ───────────────────────────────────────────────────

@dataclass
class Rule:
    """
    一条规则 = 条件组 + 动作 + 元数据。
    所有条件必须同时满足（AND 逻辑）。
    """
    id: str
    name: str
    description: str
    conditions: list[Condition]
    action: RuleAction
    priority: RulePriority
    enabled: bool = True
    fire_count: int = 0
    last_fired_at: str | None = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    # 来源追踪
    source: str = "code"  # "code" | "self_generated" | "initial"
    # 自生规则的置信度（0-1，低于阈值会被清除）
    confidence: float = 1.0

    def evaluate(self, context: dict) -> RuleAction | None:
        """
        评估此规则是否被触发。
        返回 RuleAction 如果所有条件满足，否则 None。
        """
        if not self.enabled:
            return None

        if not self.conditions:
            return None

        for cond in self.conditions:
            if not cond.matches(context):
                return None

        # 所有条件满足 → 触发
        self.fire_count += 1
        self.last_fired_at = datetime.utcnow().isoformat()
        return self.action


# ─── 规则引擎 ────────────────────────────────────────────────

class RuleEngine:
    """
    规则引擎。框架的决策核心。

    使用：
      engine = RuleEngine(data_dir="./data/rules")
      engine.load()

      # 处理信号时：
      action = engine.evaluate({"message": "搜一下XXX", "signal_type": "message"})
      if action:
          # 直接执行，不问 LLM
          execute(action)
      else:
          # 没有匹配规则，交给 LLM
          llm_response = brain.think(...)
    """

    def __init__(self, data_dir: str | Path):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._rules_file = self._data_dir / "rules.json"
        self._rules: list[Rule] = []
        # 预编译的代码规则（不存储，每次启动注册）
        self._code_rules: list[Rule] = []

    def initialize(self) -> None:
        """加载持久化规则 + 注册内置代码规则"""
        self._load_persistent_rules()
        self._register_builtin_code_rules()
        self._sort_rules()
        logger.info(
            f"[RuleEngine] 初始化完成: {len(self._code_rules)} 代码规则, "
            f"{len(self._rules)} 持久化规则"
        )

    # ─── 核心：评估 ──────────────────────────────────────────

    def evaluate(self, context: dict) -> RuleAction | None:
        """
        用 context 评估所有规则。
        返回最高优先级的匹配规则的 Action，或 None。

        context 是一个 dict，可能包含：
          - message: 用户消息内容
          - signal_type: 信号类型 (time, message, internal, ...)
          - action: 当前正在执行的动作
          - question: 当前问题
          - error_count: 连续错误次数
          - last_tool: 上次使用的工具
          - domain: 当前领域
          - ... 任何上下文字段
        """
        # 代码规则优先级最高，先检查
        for rule in self._code_rules:
            action = rule.evaluate(context)
            if action:
                logger.info(f"[RuleEngine] 命中代码规则: {rule.name}")
                self._record_fire(rule)
                return action

        # 然后按优先级检查持久化规则
        for rule in self._rules:
            action = rule.evaluate(context)
            if action:
                logger.info(f"[RuleEngine] 命中规则: {rule.name} (优先级={rule.priority})")
                self._record_fire(rule)
                return action

        return None

    # ─── 添加规则 ─────────────────────────────────────────────

    def add_code_rule(self, rule: Rule) -> None:
        """注册代码级规则（不持久化，每次启动注册）"""
        rule.priority = RulePriority.CODE_RULE
        rule.source = "code"
        self._code_rules.append(rule)
        self._sort_rules()

    def add_rule(self, rule: Rule) -> None:
        """添加持久化规则（自生规则或初始规则）"""
        # 检查是否有相同 name 的规则，如果有则覆盖
        self._rules = [r for r in self._rules if r.name != rule.name]
        self._rules.append(rule)
        self._sort_rules()
        self._save_persistent_rules()

    def add_self_generated_rule(
        self,
        name: str,
        description: str,
        conditions: list[dict],
        action_type: str,
        action_params: dict,
        confidence: float = 0.7,
    ) -> Rule:
        """
        行为监控调用此方法插入自生规则。

        Args:
            name: 规则名称（唯一标识）
            description: 为什么生成这条规则
            conditions: [{"field": "...", "operator": "...", "value": "..."}]
            action_type: "execute_tool" | "respond" | "suppress" | ...
            action_params: 动作参数
            confidence: 置信度（低于 0.3 会被自动清除）
        """
        rule = Rule(
            id=str(uuid.uuid4())[:12],
            name=name,
            description=description,
            conditions=[Condition(**c) for c in conditions],
            action=RuleAction(action_type=action_type, params=action_params),
            priority=RulePriority.SELF_GENERATED,
            source="self_generated",
            confidence=confidence,
        )
        self.add_rule(rule)
        logger.info(f"[RuleEngine] 新自生规则: {name} (置信度={confidence:.0%})")
        return rule

    # ─── 规则管理 ─────────────────────────────────────────────

    def remove_rule(self, rule_id: str) -> bool:
        """删除规则"""
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.id != rule_id]
        if len(self._rules) < before:
            self._save_persistent_rules()
            return True
        return False

    def disable_rule(self, rule_id: str) -> bool:
        """禁用规则（不删除）"""
        for r in self._rules:
            if r.id == rule_id:
                r.enabled = False
                self._save_persistent_rules()
                return True
        return False

    def decay_confidence(self, amount: float = 0.05) -> int:
        """
        降低所有自生规则的置信度。
        长期未触发的规则会被自动清除。
        返回清除的规则数。
        """
        removed = 0
        surviving: list[Rule] = []
        for r in self._rules:
            if r.source == "self_generated":
                r.confidence -= amount
                if r.confidence <= 0.3:
                    logger.info(f"[RuleEngine] 清除低置信度规则: {r.name} ({r.confidence:.0%})")
                    removed += 1
                    continue
            surviving.append(r)

        if removed:
            self._rules = surviving
            self._save_persistent_rules()
        return removed

    def boost_confidence(self, rule_id: str, amount: float = 0.1) -> None:
        """规则被验证有效时，提升置信度"""
        for r in self._rules:
            if r.id == rule_id:
                r.confidence = min(1.0, r.confidence + amount)
                self._save_persistent_rules()
                break

    def get_all_rules(self) -> list[Rule]:
        """返回所有规则（代码规则 + 持久化规则），按优先级排序"""
        return self._code_rules + self._rules

    def stats(self) -> dict:
        """规则引擎统计"""
        all_rules = self.get_all_rules()
        return {
            "total_rules": len(all_rules),
            "code_rules": len(self._code_rules),
            "self_generated": sum(1 for r in self._rules if r.source == "self_generated"),
            "initial_rules": sum(1 for r in self._rules if r.source == "initial"),
            "total_fires": sum(r.fire_count for r in all_rules),
            "enabled": sum(1 for r in all_rules if r.enabled),
            "disabled": sum(1 for r in all_rules if not r.enabled),
        }

    # ─── 内置代码规则 ─────────────────────────────────────────

    def _register_builtin_code_rules(self) -> None:
        """
        注册硬编码的代码规则。
        这些规则优先级最高，不可被自生规则覆盖。
        """

        # 规则1: 用户说"搜一下" → 强制调用 web_search
        self.add_code_rule(Rule(
            id="code_search_trigger",
            name="搜索触发",
            description="用户明确要求搜索时，直接调用搜索工具，不让LLM犹豫",
            conditions=[
                Condition(field="message", operator="regex", value=r"搜[一]?[下索]|search|查[一]?下|帮我[找查搜]"),
            ],
            action=RuleAction(
                action_type="execute_tool",
                params={"tool_name": "web_search", "extract_query_from": "message"},
            ),
            priority=RulePriority.CODE_RULE,
        ))

        # 规则2: 用户说"记住" → 强制写入记忆
        self.add_code_rule(Rule(
            id="code_memory_trigger",
            name="记忆触发",
            description="用户明确要求记住某事时，直接写入长期记忆",
            conditions=[
                Condition(field="message", operator="regex", value=r"记住|记一下|别忘了|remember"),
            ],
            action=RuleAction(
                action_type="execute_tool",
                params={"tool_name": "memory_store", "extract_content_from": "message"},
            ),
            priority=RulePriority.CODE_RULE,
        ))

        # 规则3: 连续错误超过3次 → 停止当前动作，通知主人
        self.add_code_rule(Rule(
            id="code_error_circuit_breaker",
            name="错误熔断",
            description="连续失败超过阈值时，停止自动执行，防止无限重试",
            conditions=[
                Condition(field="consecutive_errors", operator="gt", value=3),
            ],
            action=RuleAction(
                action_type="notify",
                params={"text": "连续执行失败，已暂停自动操作。请检查后手动恢复。",
                         "suppress_further": True},
            ),
            priority=RulePriority.CODE_RULE,
        ))

        # 规则4: 深夜时段（22:00-07:00）→ 不主动通知
        self.add_code_rule(Rule(
            id="code_quiet_hours",
            name="静默时段",
            description="深夜不主动打扰主人",
            conditions=[
                Condition(field="is_quiet_hours", operator="equals", value=True),
                Condition(field="signal_type", operator="equals", value="internal"),
            ],
            action=RuleAction(
                action_type="suppress",
                params={"reason": "quiet_hours"},
            ),
            priority=RulePriority.CODE_RULE,
        ))

    # ─── 持久化 ──────────────────────────────────────────────

    def _load_persistent_rules(self) -> None:
        """从文件加载持久化规则"""
        if not self._rules_file.exists():
            self._rules = []
            return

        try:
            data = json.loads(self._rules_file.read_text(encoding="utf-8"))
            self._rules = []
            for d in data:
                conditions = [Condition(**c) for c in d.get("conditions", [])]
                action = RuleAction(
                    action_type=d["action"]["action_type"],
                    params=d["action"].get("params", {}),
                )
                rule = Rule(
                    id=d["id"],
                    name=d["name"],
                    description=d.get("description", ""),
                    conditions=conditions,
                    action=action,
                    priority=RulePriority(d.get("priority", RulePriority.INITIAL)),
                    enabled=d.get("enabled", True),
                    fire_count=d.get("fire_count", 0),
                    last_fired_at=d.get("last_fired_at"),
                    created_at=d.get("created_at", datetime.utcnow().isoformat()),
                    source=d.get("source", "initial"),
                    confidence=d.get("confidence", 1.0),
                )
                self._rules.append(rule)
        except Exception as e:
            logger.error(f"[RuleEngine] 加载规则失败: {e}")
            self._rules = []

    def _save_persistent_rules(self) -> None:
        """保存持久化规则到文件"""
        data = []
        for r in self._rules:
            data.append({
                "id": r.id,
                "name": r.name,
                "description": r.description,
                "conditions": [
                    {"field": c.field, "operator": c.operator, "value": c.value}
                    for c in r.conditions
                ],
                "action": {
                    "action_type": r.action.action_type,
                    "params": r.action.params,
                },
                "priority": int(r.priority),
                "enabled": r.enabled,
                "fire_count": r.fire_count,
                "last_fired_at": r.last_fired_at,
                "created_at": r.created_at,
                "source": r.source,
                "confidence": r.confidence,
            })

        self._rules_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _sort_rules(self) -> None:
        """按优先级降序排列（高优先级先匹配）"""
        self._code_rules.sort(key=lambda r: -r.priority)
        self._rules.sort(key=lambda r: (-r.priority, r.created_at))

    def _record_fire(self, rule: Rule) -> None:
        """记录规则触发（用于统计和置信度管理）"""
        if rule.source == "self_generated":
            # 自生规则每次触发时，提升一点置信度
            rule.confidence = min(1.0, rule.confidence + 0.02)
        # 持久化规则的 fire_count 已在 evaluate() 中更新
        if rule in self._rules:
            self._save_persistent_rules()
