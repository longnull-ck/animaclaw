"""
Anima — Knowledge Graph（知识图谱记忆系统）

人的记忆不是平铺列表，而是关联网络：
  "小红书" → 是什么（内容电商平台）
           → 怎么发（图文/视频）
           → 规则（不能硬广）
           → 我的经验（上次发XX效果好）
           → 关联：抖音、微博（同类平台）

核心设计：
  - 节点（KnowledgeNode）：一个概念/实体/经验
  - 边（KnowledgeEdge）：节点之间的关系
  - 层级：从一个概念出发，沿着关系逐层展开
  - 检索：不是搜关键词，而是"从A出发，沿关系走N步，收集路径上的知识"

关系类型：
  - IS_A: 是什么（小红书 IS_A 内容平台）
  - HAS_PROPERTY: 有什么属性/特征
  - HOW_TO: 怎么做（小红书 HOW_TO 发布内容）
  - RELATES_TO: 关联（小红书 RELATES_TO 抖音）
  - PART_OF: 属于（标题 PART_OF 笔记）
  - CAUSES: 导致（好标题 CAUSES 高点击）
  - EXPERIENCE: 经验（我上次 EXPERIENCE 发了XX）
  - RULE: 规则/限制（小红书 RULE 不能硬广）
  - EXAMPLE: 示例/案例

存储：SQLite（轻量但足够强大）
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("anima.memory.kg")


# ─── 数据模型 ─────────────────────────────────────────────────

class RelationType(str, Enum):
    IS_A = "is_a"                # 是什么
    HAS_PROPERTY = "has_property"  # 有什么特征
    HOW_TO = "how_to"            # 怎么做
    RELATES_TO = "relates_to"    # 关联
    PART_OF = "part_of"          # 属于/包含
    CAUSES = "causes"            # 导致/因果
    EXPERIENCE = "experience"    # 经验记录
    RULE = "rule"                # 规则/限制
    EXAMPLE = "example"          # 示例/案例
    DEPENDS_ON = "depends_on"    # 依赖
    OPPOSITE = "opposite"        # 对立/反义
    SEQUENCE = "sequence"        # 顺序（步骤1→步骤2）


@dataclass
class KnowledgeNode:
    id: str
    concept: str            # 核心概念名（如"小红书"）
    description: str = ""   # 详细描述
    category: str = ""      # 分类标签（platform, skill, person, product...）
    importance: float = 0.5
    access_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class KnowledgeEdge:
    id: str
    source_id: str          # 起始节点
    target_id: str          # 目标节点
    relation: RelationType  # 关系类型
    label: str = ""         # 关系的具体描述（如 "发布方式是"）
    weight: float = 1.0     # 关系强度（越大越重要）
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class KnowledgePath:
    """检索结果：从起点到终点的一条知识路径"""
    nodes: list[KnowledgeNode]
    edges: list[KnowledgeEdge]
    relevance_score: float = 0.0


# ─── 知识图谱引擎 ─────────────────────────────────────────────

class KnowledgeGraph:
    """
    知识图谱记忆系统。
    像人脑一样，通过关联检索知识。

    使用方式：
      kg.learn("小红书", "是什么", "内容电商平台，以种草笔记为主")
      kg.learn("小红书", "怎么发", "图文或视频，标题要有钩子")
      kg.learn("小红书", "关联", "抖音")

      # 检索时：
      context = kg.recall("小红书")
      # 返回：小红书的所有关联知识，按重要性排序
    """

    def __init__(self, db_path: str | Path):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS kg_nodes (
                    id           TEXT PRIMARY KEY,
                    concept      TEXT NOT NULL,
                    description  TEXT NOT NULL DEFAULT '',
                    category     TEXT NOT NULL DEFAULT '',
                    importance   REAL NOT NULL DEFAULT 0.5,
                    access_count INTEGER NOT NULL DEFAULT 0,
                    created_at   TEXT NOT NULL,
                    updated_at   TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_kg_nodes_concept
                    ON kg_nodes(concept);

                CREATE TABLE IF NOT EXISTS kg_edges (
                    id         TEXT PRIMARY KEY,
                    source_id  TEXT NOT NULL,
                    target_id  TEXT NOT NULL,
                    relation   TEXT NOT NULL,
                    label      TEXT NOT NULL DEFAULT '',
                    weight     REAL NOT NULL DEFAULT 1.0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (source_id) REFERENCES kg_nodes(id),
                    FOREIGN KEY (target_id) REFERENCES kg_nodes(id)
                );

                CREATE INDEX IF NOT EXISTS idx_kg_edges_source
                    ON kg_edges(source_id);
                CREATE INDEX IF NOT EXISTS idx_kg_edges_target
                    ON kg_edges(target_id);
                CREATE INDEX IF NOT EXISTS idx_kg_edges_relation
                    ON kg_edges(relation);
            """)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    # ─── 学习：写入知识 ──────────────────────────────────────

    def learn(
        self,
        concept: str,
        relation: str,
        target: str,
        *,
        label: str = "",
        weight: float = 1.0,
        source_category: str = "",
        target_category: str = "",
        target_description: str = "",
    ) -> tuple[KnowledgeNode, KnowledgeNode, KnowledgeEdge]:
        """
        学习一条知识（创建/更新节点和关系）。

        示例：
          kg.learn("小红书", "is_a", "内容电商平台")
          kg.learn("小红书", "how_to", "发布笔记", label="怎么发内容")
          kg.learn("小红书", "rule", "不能硬广")
          kg.learn("小红书", "relates_to", "抖音")

        Args:
            concept: 主概念
            relation: 关系类型（is_a, how_to, rule, relates_to, 等）
            target: 目标概念/知识
            label: 关系的描述标签
            weight: 关系强度
            source_category: 主概念的分类
            target_category: 目标概念的分类
            target_description: 目标节点的详细描述
        """
        # 解析关系类型
        try:
            rel = RelationType(relation)
        except ValueError:
            rel = RelationType.RELATES_TO  # 默认

        # 获取或创建源节点
        source_node = self._get_or_create_node(concept, category=source_category)

        # 获取或创建目标节点
        target_node = self._get_or_create_node(
            target, category=target_category, description=target_description
        )

        # 创建边（如果相同关系已存在，更新权重）
        edge = self._create_or_update_edge(
            source_node.id, target_node.id, rel, label, weight
        )

        return source_node, target_node, edge

    def learn_batch(self, concept: str, knowledge: list[dict]) -> None:
        """
        批量学习关于一个概念的多条知识。

        示例：
          kg.learn_batch("小红书", [
              {"relation": "is_a", "target": "内容电商平台"},
              {"relation": "how_to", "target": "发布笔记", "label": "图文或视频"},
              {"relation": "rule", "target": "不能硬广"},
              {"relation": "relates_to", "target": "抖音"},
          ])
        """
        for item in knowledge:
            self.learn(
                concept,
                item.get("relation", "relates_to"),
                item.get("target", ""),
                label=item.get("label", ""),
                weight=item.get("weight", 1.0),
                target_category=item.get("target_category", ""),
                target_description=item.get("target_description", ""),
            )

    # ─── 回忆：检索知识 ──────────────────────────────────────

    def recall(self, concept: str, max_depth: int = 2, max_results: int = 20) -> list[dict]:
        """
        回忆一个概念的所有关联知识。
        使用 spreading activation：激活从起点沿边权传播，超过阈值的节点被召回。
        边权随时间自动衰减（遗忘）。

        返回格式：
        [
            {
                "concept": "小红书",
                "relation": "is_a",
                "target": "内容电商平台",
                "label": "",
                "activation": 0.85,
                "weight": 1.0,
            },
            ...
        ]
        """
        node = self._find_node(concept)
        if not node:
            return []

        self._touch_node(node.id)

        # Spreading Activation
        activated = self._spread_activation(
            start_id=node.id,
            initial_energy=1.0,
            decay_factor=0.6,       # 每传播一步衰减 40%
            threshold=0.15,         # 激活低于此值的节点不召回
            max_steps=max_depth + 1,
        )

        # 将激活结果转为标准输出格式
        results: list[dict] = []
        for node_id, activation in activated.items():
            if node_id == node.id:
                continue  # 跳过起点自身

            target_node = self._get_node_by_id(node_id)
            if not target_node:
                continue

            # 找到连接到这个节点的边（从已激活的路径中）
            edge_info = self._find_connecting_edge(node.id, node_id, activated)
            relation = edge_info["relation"] if edge_info else "relates_to"
            label = edge_info["label"] if edge_info else ""
            weight = edge_info["weight"] if edge_info else 0.5

            results.append({
                "concept": concept,
                "relation": relation,
                "target": target_node.concept,
                "target_description": target_node.description,
                "label": label,
                "activation": round(activation, 3),
                "weight": weight,
            })

        # 按激活强度排序
        results.sort(key=lambda r: -r["activation"])
        return results[:max_results]

    def _spread_activation(
        self,
        start_id: str,
        initial_energy: float = 1.0,
        decay_factor: float = 0.6,
        threshold: float = 0.15,
        max_steps: int = 3,
    ) -> dict[str, float]:
        """
        扩散激活算法。

        从 start_id 出发，能量沿着边传播：
          - 每条边传递的能量 = 当前节点能量 × 边权(已衰减) × decay_factor
          - 如果一个节点从多个路径接收能量，取最大值（不累加，防止爆炸）
          - 低于 threshold 的激活不再传播

        返回: {node_id: activation_level} 所有被激活的节点
        """
        activations: dict[str, float] = {start_id: initial_energy}
        frontier: list[tuple[str, float, int]] = [(start_id, initial_energy, 0)]

        while frontier:
            current_id, current_energy, step = frontier.pop(0)

            if step >= max_steps:
                continue

            # 获取所有出边
            edges = self._get_outgoing_edges(current_id)
            for edge in edges:
                # 计算经过时间衰减后的边权
                effective_weight = self._decayed_weight(edge)
                # 传播的能量
                spread_energy = current_energy * effective_weight * decay_factor

                if spread_energy < threshold:
                    continue

                target_id = edge.target_id
                # 取最大激活值（不累加）
                if target_id not in activations or activations[target_id] < spread_energy:
                    activations[target_id] = spread_energy
                    frontier.append((target_id, spread_energy, step + 1))

            # 入边（反向传播，能量打折）
            in_edges = self._get_incoming_edges(current_id)
            for edge in in_edges:
                effective_weight = self._decayed_weight(edge) * 0.5  # 反向传播额外衰减
                spread_energy = current_energy * effective_weight * decay_factor

                if spread_energy < threshold:
                    continue

                source_id = edge.source_id
                if source_id not in activations or activations[source_id] < spread_energy:
                    activations[source_id] = spread_energy
                    frontier.append((source_id, spread_energy, step + 1))

        return activations

    def _decayed_weight(self, edge: KnowledgeEdge) -> float:
        """
        计算边的时间衰减权重。
        边创建越久，权重越低（模拟遗忘）。
        衰减公式: weight × exp(-λ × days_since_creation)
        λ = 0.01 意味着 ~100天后权重降到原来的 37%
        """
        import math
        try:
            created = datetime.fromisoformat(edge.created_at)
            days_elapsed = (datetime.utcnow() - created).total_seconds() / 86400.0
        except (ValueError, TypeError):
            days_elapsed = 0.0

        decay_lambda = 0.01  # 衰减速率
        decay_multiplier = math.exp(-decay_lambda * days_elapsed)
        return edge.weight * decay_multiplier

    def _find_connecting_edge(
        self, from_id: str, to_id: str, activated: dict[str, float]
    ) -> dict | None:
        """找到两个节点之间（可能经过中间节点）的最强连接边信息"""
        # 先检查直接边
        edges = self._get_outgoing_edges(from_id)
        for edge in edges:
            if edge.target_id == to_id:
                return {
                    "relation": edge.relation.value,
                    "label": edge.label,
                    "weight": edge.weight,
                }

        # 检查反向直接边
        in_edges = self._get_incoming_edges(from_id)
        for edge in in_edges:
            if edge.source_id == to_id:
                return {
                    "relation": f"reverse_{edge.relation.value}",
                    "label": edge.label,
                    "weight": edge.weight * 0.7,
                }

        # 间接连接：找到任意一条连接到 to_id 的边
        all_in = self._get_incoming_edges(to_id)
        for edge in all_in:
            if edge.source_id in activated:
                return {
                    "relation": edge.relation.value,
                    "label": edge.label,
                    "weight": edge.weight,
                }

        all_out = self._get_outgoing_edges(to_id)
        for edge in all_out:
            if edge.target_id in activated:
                return {
                    "relation": f"reverse_{edge.relation.value}",
                    "label": edge.label,
                    "weight": edge.weight * 0.7,
                }

        return None

    def recall_as_text(self, concept: str, max_depth: int = 2) -> str:
        """
        将回忆结果格式化为自然语言文本（用于注入到 system prompt）。

        示例输出：
          关于「小红书」的知识：
          - 是什么：内容电商平台
          - 怎么发：图文或视频，标题要有钩子
          - 规则：不能硬广
          - 关联：抖音、微博
          - 经验：上次发XX效果不错
        """
        results = self.recall(concept, max_depth=max_depth)
        if not results:
            return ""

        # 按关系类型分组
        groups: dict[str, list[str]] = {}
        relation_labels = {
            "is_a": "是什么",
            "has_property": "特征",
            "how_to": "怎么做",
            "relates_to": "关联",
            "part_of": "组成部分",
            "causes": "会导致",
            "experience": "我的经验",
            "rule": "规则/限制",
            "example": "示例",
            "depends_on": "依赖",
            "sequence": "步骤",
        }

        for r in results:
            rel = r["relation"].replace("reverse_", "被引用：")
            group_name = relation_labels.get(r["relation"], r["relation"])
            content = r["target"]
            if r["label"]:
                content = f"{r['label']}：{content}"
            if r["target_description"]:
                content += f"（{r['target_description']}）"
            groups.setdefault(group_name, []).append(content)

        lines = [f"关于「{concept}」的知识："]
        for group_name, items in groups.items():
            for item in items[:5]:  # 每组最多5条
                lines.append(f"  - {group_name}：{item}")

        return "\n".join(lines)

    # ─── 搜索：模糊匹配节点 ──────────────────────────────────

    def search_nodes(self, query: str, limit: int = 10) -> list[KnowledgeNode]:
        """模糊搜索节点（按概念名和描述）"""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM kg_nodes
                   WHERE concept LIKE ? OR description LIKE ?
                   ORDER BY importance DESC, access_count DESC
                   LIMIT ?""",
                (f"%{query}%", f"%{query}%", limit),
            ).fetchall()
        return [self._row_to_node(r) for r in rows]

    def find_related_concepts(self, concept: str) -> list[str]:
        """找到一个概念直接关联的所有概念"""
        node = self._find_node(concept)
        if not node:
            return []

        related = set()
        for edge in self._get_outgoing_edges(node.id):
            target = self._get_node_by_id(edge.target_id)
            if target:
                related.add(target.concept)
        for edge in self._get_incoming_edges(node.id):
            source = self._get_node_by_id(edge.source_id)
            if source:
                related.add(source.concept)

        return list(related)

    # ─── 删除 ───────────────────────────────────────────────

    def decay_all_edges(self, threshold: float = 0.1) -> int:
        """
        全图边权衰减（遗忘）。
        删除衰减后有效权重低于 threshold 的边。
        返回删除的边数。

        建议定期调用（如每天一次）。
        """
        import math
        removed = 0
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM kg_edges").fetchall()
            for row in rows:
                try:
                    created = datetime.fromisoformat(row["created_at"])
                    days = (datetime.utcnow() - created).total_seconds() / 86400.0
                except (ValueError, TypeError):
                    days = 0.0

                effective = row["weight"] * math.exp(-0.01 * days)
                if effective < threshold:
                    conn.execute("DELETE FROM kg_edges WHERE id=?", (row["id"],))
                    removed += 1

        # 清除孤立节点（没有任何边的节点）
        if removed:
            with self._conn() as conn:
                conn.execute("""
                    DELETE FROM kg_nodes WHERE id NOT IN (
                        SELECT source_id FROM kg_edges
                        UNION
                        SELECT target_id FROM kg_edges
                    )
                """)

        if removed:
            logger.info(f"[KG] 遗忘完成: 删除 {removed} 条弱关联边")
        return removed

    def reinforce_edge(self, concept: str, target: str, boost: float = 0.2) -> bool:
        """
        强化一条边（被回忆/使用时调用）。
        相当于"复习"——重置衰减起点，增加权重。
        """
        source_node = self._find_node(concept)
        target_node = self._find_node(target)
        if not source_node or not target_node:
            return False

        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM kg_edges WHERE source_id=? AND target_id=?",
                (source_node.id, target_node.id),
            ).fetchone()
            if row:
                new_weight = min(2.0, row["weight"] + boost)
                conn.execute(
                    "UPDATE kg_edges SET weight=?, created_at=? WHERE id=?",
                    (new_weight, datetime.utcnow().isoformat(), row["id"]),
                )
                return True
        return False

    def forget_concept(self, concept: str) -> bool:
        """删除一个概念及其所有关系"""
        node = self._find_node(concept)
        if not node:
            return False

        with self._conn() as conn:
            conn.execute("DELETE FROM kg_edges WHERE source_id=? OR target_id=?", (node.id, node.id))
            conn.execute("DELETE FROM kg_nodes WHERE id=?", (node.id,))
        return True

    # ─── 统计 ───────────────────────────────────────────────

    def stats(self) -> dict:
        with self._conn() as conn:
            nodes_count = conn.execute("SELECT COUNT(*) FROM kg_nodes").fetchone()[0]
            edges_count = conn.execute("SELECT COUNT(*) FROM kg_edges").fetchone()[0]
            categories = conn.execute(
                "SELECT category, COUNT(*) FROM kg_nodes WHERE category!='' GROUP BY category"
            ).fetchall()

        return {
            "nodes": nodes_count,
            "edges": edges_count,
            "categories": {r[0]: r[1] for r in categories},
        }

    # ─── 导出（用于调试和可视化） ────────────────────────────

    def export_all(self) -> dict:
        """导出整个图谱（用于可视化或调试）"""
        with self._conn() as conn:
            nodes = conn.execute("SELECT * FROM kg_nodes").fetchall()
            edges = conn.execute("SELECT * FROM kg_edges").fetchall()

        return {
            "nodes": [
                {"id": r["id"], "concept": r["concept"], "description": r["description"],
                 "category": r["category"], "importance": r["importance"]}
                for r in nodes
            ],
            "edges": [
                {"source": r["source_id"], "target": r["target_id"],
                 "relation": r["relation"], "label": r["label"], "weight": r["weight"]}
                for r in edges
            ],
        }

    # ─── 内部方法 ────────────────────────────────────────────

    def _get_or_create_node(
        self, concept: str, category: str = "", description: str = ""
    ) -> KnowledgeNode:
        """获取已存在的节点，或创建新节点"""
        existing = self._find_node(concept)
        if existing:
            # 如果提供了新信息，更新
            if (category and not existing.category) or (description and not existing.description):
                with self._conn() as conn:
                    updates = []
                    params = []
                    if category and not existing.category:
                        updates.append("category=?")
                        params.append(category)
                    if description and not existing.description:
                        updates.append("description=?")
                        params.append(description)
                    updates.append("updated_at=?")
                    params.append(datetime.utcnow().isoformat())
                    params.append(existing.id)
                    conn.execute(f"UPDATE kg_nodes SET {', '.join(updates)} WHERE id=?", params)
            return existing

        now = datetime.utcnow().isoformat()
        node = KnowledgeNode(
            id=str(uuid.uuid4())[:12],
            concept=concept,
            description=description,
            category=category,
            created_at=now,
            updated_at=now,
        )
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO kg_nodes VALUES (?,?,?,?,?,?,?,?)",
                (node.id, node.concept, node.description, node.category,
                 node.importance, node.access_count, node.created_at, node.updated_at),
            )
        return node

    def _find_node(self, concept: str) -> KnowledgeNode | None:
        """按概念名精确查找节点"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM kg_nodes WHERE concept=? COLLATE NOCASE",
                (concept,),
            ).fetchone()
        return self._row_to_node(row) if row else None

    def _get_node_by_id(self, node_id: str) -> KnowledgeNode | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM kg_nodes WHERE id=?", (node_id,)).fetchone()
        return self._row_to_node(row) if row else None

    def _touch_node(self, node_id: str) -> None:
        """记录节点被访问"""
        with self._conn() as conn:
            conn.execute(
                "UPDATE kg_nodes SET access_count=access_count+1, updated_at=? WHERE id=?",
                (datetime.utcnow().isoformat(), node_id),
            )

    def _create_or_update_edge(
        self, source_id: str, target_id: str, relation: RelationType,
        label: str, weight: float,
    ) -> KnowledgeEdge:
        """创建边，如果相同关系已存在则更新权重"""
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT * FROM kg_edges WHERE source_id=? AND target_id=? AND relation=?",
                (source_id, target_id, relation.value),
            ).fetchone()

            if existing:
                # 更新权重（取更高值）
                new_weight = max(existing["weight"], weight)
                new_label = label or existing["label"]
                conn.execute(
                    "UPDATE kg_edges SET weight=?, label=? WHERE id=?",
                    (new_weight, new_label, existing["id"]),
                )
                return KnowledgeEdge(
                    id=existing["id"], source_id=source_id, target_id=target_id,
                    relation=relation, label=new_label, weight=new_weight,
                    created_at=existing["created_at"],
                )

            edge = KnowledgeEdge(
                id=str(uuid.uuid4())[:12],
                source_id=source_id,
                target_id=target_id,
                relation=relation,
                label=label,
                weight=weight,
            )
            conn.execute(
                "INSERT INTO kg_edges VALUES (?,?,?,?,?,?,?)",
                (edge.id, edge.source_id, edge.target_id,
                 edge.relation.value, edge.label, edge.weight, edge.created_at),
            )
            return edge

    def _get_outgoing_edges(self, node_id: str) -> list[KnowledgeEdge]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM kg_edges WHERE source_id=? ORDER BY weight DESC",
                (node_id,),
            ).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def _get_incoming_edges(self, node_id: str) -> list[KnowledgeEdge]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM kg_edges WHERE target_id=? ORDER BY weight DESC",
                (node_id,),
            ).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def _row_to_node(self, row) -> KnowledgeNode:
        return KnowledgeNode(
            id=row["id"], concept=row["concept"],
            description=row["description"], category=row["category"],
            importance=row["importance"], access_count=row["access_count"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def _row_to_edge(self, row) -> KnowledgeEdge:
        return KnowledgeEdge(
            id=row["id"], source_id=row["source_id"], target_id=row["target_id"],
            relation=RelationType(row["relation"]),
            label=row["label"], weight=row["weight"],
            created_at=row["created_at"],
        )
