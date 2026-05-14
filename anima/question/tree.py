"""
Anima — Question Tree（问题树引擎）
需求 → 根问题 → 子问题（无穷但有序）
优先级 = 紧急度 × 重要度 × 相关度
"""

from __future__ import annotations

import json
import uuid
import logging
from datetime import datetime
from pathlib import Path

from anima.models import QuestionNode, QuestionStatus, QuestionSource

logger = logging.getLogger("anima.question")

MAX_DEPTH = 5
MAX_PENDING_PER_DEPTH = 10


class QuestionTree:

    def __init__(self, data_dir: str | Path):
        self._file = Path(data_dir) / "questions.json"
        Path(data_dir).mkdir(parents=True, exist_ok=True)

    def initialize(self) -> None:
        if not self._file.exists():
            self._save({})

    def _load(self) -> dict[str, QuestionNode]:
        if not self._file.exists():
            return {}
        raw = json.loads(self._file.read_text(encoding="utf-8"))
        nodes: dict[str, QuestionNode] = {}
        for nid, d in raw.items():
            d["source"] = QuestionSource(d["source"])
            d["status"] = QuestionStatus(d["status"])
            nodes[nid] = QuestionNode(**d)
        return nodes

    def _save(self, nodes: dict[str, QuestionNode]) -> None:
        data = {}
        for nid, n in nodes.items():
            data[nid] = {
                "id": n.id, "question": n.question, "source": n.source.value,
                "parent_id": n.parent_id, "children_ids": n.children_ids,
                "priority": n.priority, "depth": n.depth, "status": n.status.value,
                "resolution": n.resolution, "created_at": n.created_at, "updated_at": n.updated_at,
            }
        self._file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def add_root(self, question: str, source: QuestionSource, priority: float = 0.5) -> QuestionNode:
        nodes = self._load()
        node = self._make(question, source, None, 0, priority)
        nodes[node.id] = node
        self._save(nodes)
        return node

    def add_child(self, parent_id: str, question: str, priority: float | None = None) -> QuestionNode | None:
        nodes = self._load()
        parent = nodes.get(parent_id)
        if not parent or parent.depth >= MAX_DEPTH:
            return None
        child = self._make(question, QuestionSource.SELF_REFLECTION, parent_id,
                           parent.depth + 1, priority if priority is not None else parent.priority * 0.85)
        nodes[child.id] = child
        parent.children_ids.append(child.id)
        parent.updated_at = datetime.utcnow().isoformat()
        self._prune(nodes, parent.depth + 1)
        self._save(nodes)
        return child

    def start(self, node_id: str) -> None:
        self._update(node_id, status=QuestionStatus.IN_PROGRESS)

    def resolve(self, node_id: str, resolution: str) -> None:
        self._update(node_id, status=QuestionStatus.RESOLVED, resolution=resolution)

    def abandon(self, node_id: str, reason: str) -> None:
        self._update(node_id, status=QuestionStatus.ABANDONED, resolution=f"放弃：{reason}")

    def boost(self, node_id: str, delta: float) -> None:
        nodes = self._load()
        node = nodes.get(node_id)
        if node:
            node.priority = round(min(1.0, node.priority + delta), 4)
            node.updated_at = datetime.utcnow().isoformat()
            self._save(nodes)

    def next_pending(self) -> QuestionNode | None:
        nodes = self._load()
        pending = [n for n in nodes.values() if n.status == QuestionStatus.PENDING]
        return max(pending, key=lambda n: n.priority) if pending else None

    def all_pending(self, limit: int = 20) -> list[QuestionNode]:
        nodes = self._load()
        pending = [n for n in nodes.values() if n.status == QuestionStatus.PENDING]
        return sorted(pending, key=lambda n: n.priority, reverse=True)[:limit]

    def stats(self) -> dict:
        nodes = list(self._load().values())
        return {
            "total": len(nodes),
            "pending": sum(1 for n in nodes if n.status == QuestionStatus.PENDING),
            "in_progress": sum(1 for n in nodes if n.status == QuestionStatus.IN_PROGRESS),
            "resolved": sum(1 for n in nodes if n.status == QuestionStatus.RESOLVED),
            "abandoned": sum(1 for n in nodes if n.status == QuestionStatus.ABANDONED),
        }

    def _make(self, question, source, parent_id, depth, priority) -> QuestionNode:
        return QuestionNode(id=str(uuid.uuid4()), question=question, source=source,
                            parent_id=parent_id, children_ids=[],
                            priority=round(min(1.0, max(0.0, priority)), 4), depth=depth)

    def _update(self, node_id: str, **kwargs) -> None:
        nodes = self._load()
        node = nodes.get(node_id)
        if not node:
            return
        for k, v in kwargs.items():
            setattr(node, k, v)
        node.updated_at = datetime.utcnow().isoformat()
        self._save(nodes)

    def _prune(self, nodes: dict[str, QuestionNode], depth: int) -> None:
        pending = [n for n in nodes.values() if n.depth == depth and n.status == QuestionStatus.PENDING]
        if len(pending) <= MAX_PENDING_PER_DEPTH:
            return
        for n in sorted(pending, key=lambda n: n.priority)[: len(pending) - MAX_PENDING_PER_DEPTH]:
            nodes[n.id].status = QuestionStatus.ABANDONED
            nodes[n.id].resolution = "优先级过低，自动淘汰"
            nodes[n.id].updated_at = datetime.utcnow().isoformat()
