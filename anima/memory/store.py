"""
Anima — Memory Store（记忆存储层）
基于 SQLite，实现三层记忆架构：
  L1 热记忆：运行时组装，不持久化
  L2 温记忆：对话摘要，warm_memory 表
  L3 冷记忆：关键事实/经验/偏好，cold_memory 表（FTS5 全文检索）
"""

from __future__ import annotations

import sqlite3
import uuid
import json
import logging
from datetime import datetime
from pathlib import Path

from anima.models import MemoryEntry, MemoryCategory

logger = logging.getLogger("anima.memory.store")


class WarmEntry:
    __slots__ = ("id", "summary", "key_points", "domains",
                 "period_start", "period_end", "created_at")

    def __init__(self, id, summary, key_points, domains,
                 period_start, period_end, created_at):
        self.id = id
        self.summary = summary
        self.key_points = key_points
        self.domains = domains
        self.period_start = period_start
        self.period_end = period_end
        self.created_at = created_at


class MemoryStore:

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS warm_memory (
                    id           TEXT PRIMARY KEY,
                    summary      TEXT NOT NULL,
                    key_points   TEXT NOT NULL,
                    domains      TEXT NOT NULL,
                    period_start TEXT NOT NULL,
                    period_end   TEXT NOT NULL,
                    created_at   TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS cold_memory (
                    id               TEXT PRIMARY KEY,
                    category         TEXT NOT NULL,
                    content          TEXT NOT NULL,
                    importance       REAL NOT NULL DEFAULT 0.5,
                    access_count     INTEGER NOT NULL DEFAULT 0,
                    permanent        INTEGER NOT NULL DEFAULT 0,
                    tags             TEXT NOT NULL DEFAULT '[]',
                    created_at       TEXT NOT NULL,
                    last_accessed_at TEXT NOT NULL
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS cold_memory_fts
                USING fts5(content, tags, content='cold_memory', content_rowid='rowid');

                CREATE TRIGGER IF NOT EXISTS cold_memory_ai
                AFTER INSERT ON cold_memory BEGIN
                    INSERT INTO cold_memory_fts(rowid, content, tags)
                    VALUES (new.rowid, new.content, new.tags);
                END;

                CREATE TRIGGER IF NOT EXISTS cold_memory_ad
                AFTER DELETE ON cold_memory BEGIN
                    INSERT INTO cold_memory_fts(cold_memory_fts, rowid, content, tags)
                    VALUES ('delete', old.rowid, old.content, old.tags);
                END;

                CREATE TRIGGER IF NOT EXISTS cold_memory_au
                AFTER UPDATE ON cold_memory BEGIN
                    INSERT INTO cold_memory_fts(cold_memory_fts, rowid, content, tags)
                    VALUES ('delete', old.rowid, old.content, old.tags);
                    INSERT INTO cold_memory_fts(rowid, content, tags)
                    VALUES (new.rowid, new.content, new.tags);
                END;
            """)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    # ── L2 温记忆 ─────────────────────────────────────────────

    def append_warm(self, summary, key_points, domains, period_start, period_end) -> WarmEntry:
        entry = WarmEntry(
            id=str(uuid.uuid4()), summary=summary, key_points=key_points,
            domains=domains, period_start=period_start, period_end=period_end,
            created_at=datetime.utcnow().isoformat(),
        )
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO warm_memory VALUES (?,?,?,?,?,?,?)",
                (entry.id, entry.summary,
                 json.dumps(entry.key_points, ensure_ascii=False),
                 json.dumps(entry.domains, ensure_ascii=False),
                 entry.period_start, entry.period_end, entry.created_at),
            )
        self._trim_warm(200)
        return entry

    def get_recent_warm(self, n: int = 5) -> list[WarmEntry]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM warm_memory ORDER BY created_at DESC LIMIT ?", (n,)
            ).fetchall()
        return [self._row_to_warm(r) for r in reversed(rows)]

    def _trim_warm(self, max_rows: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM warm_memory WHERE id NOT IN "
                "(SELECT id FROM warm_memory ORDER BY created_at DESC LIMIT ?)",
                (max_rows,),
            )

    def _row_to_warm(self, row) -> WarmEntry:
        return WarmEntry(
            id=row["id"], summary=row["summary"],
            key_points=json.loads(row["key_points"]),
            domains=json.loads(row["domains"]),
            period_start=row["period_start"],
            period_end=row["period_end"],
            created_at=row["created_at"],
        )

    # ── L3 冷记忆 ─────────────────────────────────────────────

    def add_cold(self, content, category: MemoryCategory,
                 importance=0.5, tags=None, permanent=False) -> MemoryEntry:
        now = datetime.utcnow().isoformat()
        entry = MemoryEntry(
            id=str(uuid.uuid4()), category=category, content=content,
            importance=importance, access_count=0, permanent=permanent,
            tags=tags or [], created_at=now, last_accessed_at=now,
        )
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO cold_memory VALUES (?,?,?,?,?,?,?,?,?)",
                (entry.id, entry.category.value, entry.content, entry.importance,
                 0, int(permanent), json.dumps(entry.tags, ensure_ascii=False), now, now),
            )
        return entry

    def touch(self, entry_id: str) -> None:
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.execute(
                "UPDATE cold_memory SET access_count=access_count+1, last_accessed_at=? WHERE id=?",
                (now, entry_id),
            )

    def get_permanent(self) -> list[MemoryEntry]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM cold_memory WHERE permanent=1 ORDER BY importance DESC"
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def search(self, query: str, top_k: int = 6) -> list[tuple[MemoryEntry, float]]:
        if not query.strip():
            return []
        fts_results: list[tuple[str, float]] = []
        try:
            with self._conn() as conn:
                rows = conn.execute(
                    "SELECT c.*, fts.rank FROM cold_memory_fts fts "
                    "JOIN cold_memory c ON c.rowid=fts.rowid "
                    "WHERE cold_memory_fts MATCH ? ORDER BY fts.rank LIMIT ?",
                    (self._fts_query(query), top_k * 2),
                ).fetchall()
            fts_results = [(r["id"], abs(r["rank"])) for r in rows]
        except sqlite3.OperationalError as e:
            logger.warning(f"[MemoryStore] FTS 失败: {e}")

        # FTS5 unicode61 tokenizer 对中文/混合文本分词不佳，
        # 如果 FTS 没有结果，回退到 LIKE 模糊匹配
        if not fts_results:
            fts_results = self._fallback_like_search(query, top_k * 2)

        if not fts_results:
            return []

        ids = [r[0] for r in fts_results]
        rank_map = {r[0]: r[1] for r in fts_results}
        placeholders = ",".join("?" * len(ids))
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM cold_memory WHERE id IN ({placeholders})", ids
            ).fetchall()
        entries = {r["id"]: self._row_to_entry(r) for r in rows}

        scored: list[tuple[MemoryEntry, float]] = []
        for eid, fts_rank in fts_results:
            if eid not in entries:
                continue
            e = entries[eid]
            score = (min(fts_rank / 10.0, 1.0) * 0.5
                     + e.importance * 0.35
                     + min(e.access_count / 20.0, 1.0) * 0.15)
            scored.append((e, round(score, 4)))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def _fallback_like_search(self, query: str, limit: int) -> list[tuple[str, float]]:
        """FTS 无结果时使用 LIKE 回退搜索（支持中文子串匹配）"""
        results: list[tuple[str, float]] = []
        try:
            with self._conn() as conn:
                rows = conn.execute(
                    "SELECT id, importance FROM cold_memory "
                    "WHERE content LIKE ? OR tags LIKE ? "
                    "ORDER BY importance DESC LIMIT ?",
                    (f"%{query}%", f"%{query}%", limit),
                ).fetchall()
            # 给 LIKE 结果一个合理的伪 rank（基于 importance）
            results = [(r["id"], r["importance"] * 5.0) for r in rows]
        except Exception as e:
            logger.warning(f"[MemoryStore] LIKE fallback 失败: {e}")
        return results

    def decay_stale(self) -> int:
        now = datetime.utcnow()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, importance, last_accessed_at FROM cold_memory WHERE permanent=0"
            ).fetchall()
            decayed = 0
            for row in rows:
                days = (now - datetime.fromisoformat(row["last_accessed_at"])).days
                if days > 30:
                    decay = min((days - 30) * 0.01, 0.5)
                    conn.execute(
                        "UPDATE cold_memory SET importance=? WHERE id=?",
                        (max(row["importance"] - decay, 0.05), row["id"]),
                    )
                    decayed += 1
        return decayed

    def _row_to_entry(self, row) -> MemoryEntry:
        return MemoryEntry(
            id=row["id"], category=MemoryCategory(row["category"]),
            content=row["content"], importance=row["importance"],
            access_count=row["access_count"], permanent=bool(row["permanent"]),
            tags=json.loads(row["tags"]),
            created_at=row["created_at"], last_accessed_at=row["last_accessed_at"],
        )

    @staticmethod
    def _fts_query(text: str) -> str:
        clean = text.replace('"', '').replace("'", "").replace("*", "")
        tokens = clean.split()
        if not tokens:
            return '""'
        return " OR ".join(f'"{t}"' for t in tokens[:10])
