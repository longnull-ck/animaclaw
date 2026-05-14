"""
Anima — Trust System（信任度系统）
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from anima.models import TrustState, TrustLevel, TrustEvent, TrustPermissions

logger = logging.getLogger("anima.trust")

LEVEL_THRESHOLDS = [
    (TrustLevel.PROBATION,    0.0,  0.2),
    (TrustLevel.BASIC,        0.2,  0.4),
    (TrustLevel.INTERMEDIATE, 0.4,  0.6),
    (TrustLevel.ADVANCED,     0.6,  0.8),
    (TrustLevel.FULL,         0.8,  1.01),
]

LEVEL_PERMISSIONS: dict[TrustLevel, TrustPermissions] = {
    TrustLevel.PROBATION:    TrustPermissions(False, False, False, True,  0),
    TrustLevel.BASIC:        TrustPermissions(True,  False, False, True,  1),
    TrustLevel.INTERMEDIATE: TrustPermissions(True,  True,  False, True,  2),
    TrustLevel.ADVANCED:     TrustPermissions(True,  True,  True,  False, 4),
    TrustLevel.FULL:         TrustPermissions(True,  True,  True,  False, 99),
}

TRUST_DELTAS = {
    "task_success":         +0.01,
    "owner_explicit_trust": +0.05,
    "proactive_helpful":    +0.02,
    "skill_installed":      +0.01,
    "week_no_issues":       +0.02,
    "minor_mistake":        -0.02,
    "major_mistake":        -0.08,
    "owner_frustrated":     -0.03,
}

LEVEL_LABELS = {
    TrustLevel.PROBATION:    "试用期（需要审批）",
    TrustLevel.BASIC:        "基础信任（常规任务自主）",
    TrustLevel.INTERMEDIATE: "中级信任（可主动沟通）",
    TrustLevel.ADVANCED:     "高级信任（高度自主）",
    TrustLevel.FULL:         "完全信任（只汇报结果）",
}


def score_to_level(score: float) -> TrustLevel:
    for level, lo, _ in reversed(LEVEL_THRESHOLDS):
        if score >= lo:
            return level
    return TrustLevel.PROBATION


class TrustSystem:

    def __init__(self, data_dir: str | Path):
        self._file = Path(data_dir) / "trust.json"
        Path(data_dir).mkdir(parents=True, exist_ok=True)

    def initialize(self) -> TrustState:
        if self._file.exists():
            return self.load()
        state = TrustState()
        self.save(state)
        return state

    def load(self) -> TrustState:
        raw = json.loads(self._file.read_text(encoding="utf-8"))
        raw["level"] = TrustLevel(raw["level"])
        from anima.models import safe_init
        raw["history"] = [safe_init(TrustEvent, e) for e in raw.get("history", [])]
        return safe_init(TrustState, raw)

    def save(self, state: TrustState) -> None:
        from anima.utils import atomic_write_json
        data = {
            "score": state.score, "level": state.level.value,
            "history": [{"delta": e.delta, "reason": e.reason, "timestamp": e.timestamp}
                        for e in state.history],
            "updated_at": state.updated_at,
        }
        atomic_write_json(self._file, data)

    def adjust(self, reason_key: str, custom_delta: float | None = None,
               note: str = "") -> tuple[TrustState, bool, TrustLevel]:
        state = self.load()
        old_level = state.level
        delta = custom_delta if custom_delta is not None else TRUST_DELTAS.get(reason_key, 0.0)
        state.score = round(min(1.0, max(0.0, state.score + delta)), 4)
        state.level = score_to_level(state.score)
        state.updated_at = datetime.utcnow().isoformat()
        state.history.append(TrustEvent(delta=delta, reason=note or reason_key))
        if len(state.history) > 500:
            state.history = state.history[-500:]
        self.save(state)
        return state, state.level != old_level, old_level

    def get_permissions(self) -> TrustPermissions:
        state = self.load()
        return LEVEL_PERMISSIONS[state.level]

    def progress_summary(self) -> dict:
        state = self.load()
        current = next(t for t in LEVEL_THRESHOLDS if t[0] == state.level)
        next_t = next((t for t in LEVEL_THRESHOLDS if t[1] > current[1] and t[0] != state.level), None)
        return {
            "score": int(state.score * 100),
            "level": state.level.value,
            "label": LEVEL_LABELS[state.level],
            "next_level": next_t[0].value if next_t else None,
            "points_to_next": int((current[2] - state.score) * 100) if next_t else 0,
        }
