"""
Anima — 全局数据模型
所有模块共享这一份数据结构定义
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


@dataclass
class Personality:
    proactivity: float = 0.7
    risk_tolerance: float = 0.3
    language: str = "zh-CN"
    communication_style: str = "concise"


@dataclass
class Identity:
    id: str
    name: str
    owner_id: str
    owner_name: str
    company_description: str
    core_values: list[str]
    personality: Personality
    active_domains: list[str]
    version: int = 1
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class MemoryCategory(str, Enum):
    FACT = "fact"
    EXPERIENCE = "experience"
    PREFERENCE = "preference"
    IDENTITY = "identity"
    SKILL = "skill"


@dataclass
class MemoryEntry:
    id: str
    category: MemoryCategory
    content: str
    importance: float = 0.5
    access_count: int = 0
    permanent: bool = False
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_accessed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class MemorySearchResult:
    entry: MemoryEntry
    score: float


@dataclass
class HotContext:
    identity_prompt: str
    recent_messages: list[dict]
    injected_memories: list[MemorySearchResult]
    recent_summary: str = ""


class TrustLevel(str, Enum):
    PROBATION    = "probation"
    BASIC        = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED     = "advanced"
    FULL         = "full"


@dataclass
class TrustPermissions:
    auto_execute_routine: bool
    auto_message: bool
    auto_install_skill: bool
    require_approval: bool
    max_action_depth: int


@dataclass
class TrustEvent:
    delta: float
    reason: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class TrustState:
    score: float = 0.1
    level: TrustLevel = TrustLevel.PROBATION
    history: list[TrustEvent] = field(default_factory=list)
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class SkillStatus(str, Enum):
    ACTIVE     = "active"
    INSTALLING = "installing"
    FAILED     = "failed"
    DISABLED   = "disabled"


class SkillSource(str, Enum):
    BUILTIN    = "builtin"
    DISCOVERED = "discovered"
    TAUGHT     = "taught"


@dataclass
class Skill:
    id: str
    name: str
    description: str
    tool_name: str
    domains: list[str]
    source: SkillSource = SkillSource.BUILTIN
    status: SkillStatus = SkillStatus.ACTIVE
    proficiency: float = 0.3
    success_rate: float = 0.6
    use_count: int = 0
    preferred_method: str = ""
    failure_cases: list[str] = field(default_factory=list)
    installed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class QuestionStatus(str, Enum):
    PENDING     = "pending"
    IN_PROGRESS = "in_progress"
    RESOLVED    = "resolved"
    ABANDONED   = "abandoned"


class QuestionSource(str, Enum):
    INSTINCT        = "instinct"
    OWNER           = "owner"
    SELF_REFLECTION = "self_reflection"
    ENVIRONMENT     = "environment"


@dataclass
class QuestionNode:
    id: str
    question: str
    source: QuestionSource
    parent_id: str | None
    children_ids: list[str]
    priority: float
    depth: int
    status: QuestionStatus = QuestionStatus.PENDING
    resolution: str | None = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class ExperienceOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


@dataclass
class Experience:
    id: str
    action: str
    method: str
    outcome: ExperienceOutcome
    skill_id: str | None = None
    question_id: str | None = None
    owner_satisfaction: float | None = None
    lesson: str | None = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class Methodology:
    id: str
    scenario: str
    method: str
    effectiveness: float = 0.7
    conditions: str = ""
    validation_count: int = 1
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class SignalType(str, Enum):
    TIME        = "time"
    MESSAGE     = "message"
    DATA        = "data"
    ENVIRONMENT = "environment"
    INTERNAL    = "internal"


@dataclass
class Signal:
    type: SignalType
    payload: dict[str, Any]
    strength: float
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class AnimaState:
    identity: Identity
    trust: TrustState
    skills: dict[str, Skill] = field(default_factory=dict)
    methodologies: dict[str, Methodology] = field(default_factory=dict)
    experience_count: int = 0
    tick_count: int = 0
    last_tick_at: str | None = None
