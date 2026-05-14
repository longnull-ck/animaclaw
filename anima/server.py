"""
Anima — Server（Web + WebSocket 服务）
提供：
  1. WebSocket /ws — 实时推送思维流事件给前端
  2. HTTP API /api/* — 查询状态、记忆、问题树等
  3. 静态文件服务 — 托管前端 build 产物

前端连接 WebSocket 后：
  - 先收到历史事件回放（最近 50 条）
  - 然后实时接收所有新事件
  - 用户在 Web 界面上看到 Anima 每一步在干什么
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from aiohttp import web

from anima.events import get_event_bus, AnimaEvent

if TYPE_CHECKING:
    from anima.identity.engine import IdentityEngine
    from anima.memory.manager import MemoryManager
    from anima.trust.system import TrustSystem
    from anima.skills.registry import SkillRegistry
    from anima.question.tree import QuestionTree
    from anima.evolution.engine import EvolutionEngine
    from anima.providers.registry import ProviderRegistry

logger = logging.getLogger("anima.server")

STATIC_DIR = Path(__file__).parent.parent / "web" / "dist"


class AnimaServer:
    """
    Anima 的 Web 服务器。
    负责前端界面托管和实时数据推送。
    """

    def __init__(
        self,
        *,
        identity: "IdentityEngine",
        memory: "MemoryManager",
        trust: "TrustSystem",
        skills: "SkillRegistry",
        question_tree: "QuestionTree",
        evolution: "EvolutionEngine",
        providers: "ProviderRegistry",
        host: str = "0.0.0.0",
        port: int = 3210,
    ):
        self._identity = identity
        self._memory = memory
        self._trust = trust
        self._skills = skills
        self._qtree = question_tree
        self._evo = evolution
        self._providers = providers
        self._host = host
        self._port = port
        self._app = web.Application()
        self._ws_clients: list[web.WebSocketResponse] = []
        self._setup_routes()
        self._setup_event_forwarding()

    def _setup_routes(self) -> None:
        self._app.router.add_get("/ws", self._ws_handler)
        self._app.router.add_get("/api/status", self._api_status)
        self._app.router.add_get("/api/identity", self._api_identity)
        self._app.router.add_get("/api/trust", self._api_trust)
        self._app.router.add_get("/api/skills", self._api_skills)
        self._app.router.add_get("/api/questions", self._api_questions)
        self._app.router.add_get("/api/evolution", self._api_evolution)
        self._app.router.add_get("/api/memory/search", self._api_memory_search)
        self._app.router.add_get("/api/providers", self._api_providers)
        self._app.router.add_get("/api/events/history", self._api_events_history)

        # 静态文件服务（前端 build 产物）
        if STATIC_DIR.exists():
            self._app.router.add_static("/", STATIC_DIR, name="static")
        # SPA fallback
        self._app.router.add_get("/{path:.*}", self._spa_fallback)

    def _setup_event_forwarding(self) -> None:
        """把事件总线的事件转发给所有 WebSocket 客户端"""
        bus = get_event_bus()
        bus.subscribe(self._forward_event)

    async def _forward_event(self, event: AnimaEvent) -> None:
        """把事件推送给所有连接的 WebSocket 客户端"""
        if not self._ws_clients:
            return
        msg = event.to_json()
        dead: list[web.WebSocketResponse] = []
        for ws in self._ws_clients:
            try:
                await ws.send_str(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._ws_clients.remove(ws)

    # ── WebSocket 处理器 ──────────────────────────────────────

    async def _ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._ws_clients.append(ws)
        logger.info(f"[Server] WebSocket 客户端连接（当前 {len(self._ws_clients)} 个）")

        # 发送历史事件回放
        bus = get_event_bus()
        history = bus.get_history(50)
        await ws.send_str(json.dumps({
            "type": "history",
            "events": history,
        }, ensure_ascii=False))

        # 发送当前状态快照
        snapshot = self._build_snapshot()
        await ws.send_str(json.dumps({
            "type": "snapshot",
            "data": snapshot,
        }, ensure_ascii=False))

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    # 处理前端发来的命令
                    await self._handle_ws_command(ws, msg.data)
                elif msg.type == web.WSMsgType.ERROR:
                    break
        finally:
            self._ws_clients.remove(ws)
            logger.info(f"[Server] WebSocket 客户端断开（剩余 {len(self._ws_clients)} 个）")

        return ws

    async def _handle_ws_command(self, ws: web.WebSocketResponse, data: str) -> None:
        """处理前端通过 WebSocket 发来的命令"""
        try:
            cmd = json.loads(data)
            action = cmd.get("action")

            if action == "ping":
                await ws.send_str(json.dumps({"type": "pong"}))

            elif action == "get_snapshot":
                snapshot = self._build_snapshot()
                await ws.send_str(json.dumps({"type": "snapshot", "data": snapshot}, ensure_ascii=False))

        except json.JSONDecodeError:
            pass

    # ── HTTP API 路由 ─────────────────────────────────────────

    async def _api_status(self, request: web.Request) -> web.Response:
        return web.json_response(self._build_snapshot())

    async def _api_identity(self, request: web.Request) -> web.Response:
        try:
            identity = self._identity.load()
            return web.json_response({
                "name": identity.name,
                "owner_name": identity.owner_name,
                "company_description": identity.company_description,
                "active_domains": identity.active_domains,
                "core_values": identity.core_values,
                "personality": {
                    "proactivity": identity.personality.proactivity,
                    "risk_tolerance": identity.personality.risk_tolerance,
                    "communication_style": identity.personality.communication_style,
                    "language": identity.personality.language,
                },
                "version": identity.version,
                "created_at": identity.created_at,
            })
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def _api_trust(self, request: web.Request) -> web.Response:
        return web.json_response(self._trust.progress_summary())

    async def _api_skills(self, request: web.Request) -> web.Response:
        skills = self._skills.get_active()
        return web.json_response([
            {
                "id": s.id, "name": s.name, "description": s.description,
                "proficiency": s.proficiency, "success_rate": s.success_rate,
                "use_count": s.use_count, "domains": s.domains,
                "source": s.source.value,
            }
            for s in skills
        ])

    async def _api_questions(self, request: web.Request) -> web.Response:
        stats = self._qtree.stats()
        pending = self._qtree.all_pending(limit=10)
        return web.json_response({
            "stats": stats,
            "pending": [
                {"id": n.id, "question": n.question, "priority": n.priority,
                 "source": n.source.value, "depth": n.depth}
                for n in pending
            ],
        })

    async def _api_evolution(self, request: web.Request) -> web.Response:
        return web.json_response(self._evo.stats())

    async def _api_memory_search(self, request: web.Request) -> web.Response:
        query = request.query.get("q", "")
        if not query:
            return web.json_response([])
        results = self._memory.search(query, top_k=10)
        return web.json_response([
            {"content": e.content, "category": e.category.value,
             "importance": e.importance, "score": s}
            for e, s in results
        ])

    async def _api_providers(self, request: web.Request) -> web.Response:
        return web.json_response(self._providers.summary())

    async def _api_events_history(self, request: web.Request) -> web.Response:
        limit = int(request.query.get("limit", "50"))
        bus = get_event_bus()
        return web.json_response(bus.get_history(limit))

    async def _spa_fallback(self, request: web.Request) -> web.Response:
        """SPA fallback：所有未匹配路由返回 index.html"""
        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            return web.FileResponse(index_path)
        return web.Response(
            text="<h1>Anima Control Center</h1><p>前端未构建，请运行 cd web && npm run build</p>",
            content_type="text/html",
        )

    # ── 状态快照 ─────────────────────────────────────────────

    def _build_snapshot(self) -> dict:
        """构建完整状态快照（WebSocket 连接时发送）"""
        try:
            identity = self._identity.load()
            identity_data = {
                "name": identity.name,
                "owner_name": identity.owner_name,
                "company_description": identity.company_description,
                "active_domains": identity.active_domains,
                "version": identity.version,
                "personality": {
                    "proactivity": identity.personality.proactivity,
                    "risk_tolerance": identity.personality.risk_tolerance,
                },
            }
        except Exception:
            identity_data = None

        return {
            "identity": identity_data,
            "trust": self._trust.progress_summary(),
            "skills": [
                {"id": s.id, "name": s.name, "proficiency": s.proficiency,
                 "success_rate": s.success_rate, "use_count": s.use_count}
                for s in self._skills.get_active()
            ],
            "questions": self._qtree.stats(),
            "evolution": self._evo.stats(),
            "providers": self._providers.summary(),
            "ws_clients": len(self._ws_clients),
        }

    # ── 启动 ─────────────────────────────────────────────────

    async def start(self) -> None:
        runner = web.AppRunner(self._app)
        await runner.setup()
        site = web.TCPSite(runner, self._host, self._port)
        await site.start()
        logger.info(f"[Server] Anima 控制中心已启动: http://localhost:{self._port}")
