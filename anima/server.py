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
import os
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

# ── API 认证 ──────────────────────────────────────────────────

API_TOKEN = os.getenv("ANIMA_API_TOKEN", "")


def _check_auth(request: web.Request) -> bool:
    """
    检查请求是否携带正确的认证 Token。
    如果 ANIMA_API_TOKEN 未设置（空字符串），则跳过认证（本地开发模式）。
    """
    if not API_TOKEN:
        return True

    # 支持 Bearer Token 和 query param 两种方式
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:] == API_TOKEN

    # query param fallback（方便 WebSocket 连接）
    token_param = request.query.get("token", "")
    if token_param:
        return token_param == API_TOKEN

    return False


@web.middleware
async def auth_middleware(request: web.Request, handler):
    """
    API 认证中间件。
    保护 /api/* 和 /ws 端点。静态文件不需要认证。
    """
    path = request.path

    # 静态文件和 SPA fallback 不需要认证
    if not (path.startswith("/api/") or path == "/ws"):
        return await handler(request)

    if not _check_auth(request):
        return web.json_response(
            {"error": "Unauthorized. Set ANIMA_API_TOKEN or provide Bearer token."},
            status=401,
        )

    return await handler(request)


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
        brain=None,
        mind_loop=None,
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
        self._brain = brain
        self._mind_loop = mind_loop
        self._host = host
        self._port = port
        self._app = web.Application(middlewares=[auth_middleware])
        self._ws_clients: list[web.WebSocketResponse] = []
        self._chat_history: list[dict] = []   # WebChat 对话历史
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

        # Per-client rate limiter state
        import time
        rate_state = {"tokens": 10.0, "last_refill": time.monotonic()}

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
                    # Rate limiting: token bucket (10 msg/s, burst 20)
                    now = time.monotonic()
                    elapsed = now - rate_state["last_refill"]
                    rate_state["tokens"] = min(20.0, rate_state["tokens"] + elapsed * 10.0)
                    rate_state["last_refill"] = now

                    if rate_state["tokens"] < 1.0:
                        await ws.send_str(json.dumps({
                            "type": "error",
                            "message": "Rate limit exceeded. Please slow down.",
                        }))
                        continue

                    rate_state["tokens"] -= 1.0
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

            elif action == "chat":
                # ── WebChat：用户在浏览器里直接对话 ────────────
                text = cmd.get("text", "").strip()
                if not text:
                    return
                await self._handle_chat(ws, text)

            elif action == "chat_stream":
                # ── WebChat 流式：逐 token 返回 ───────────────
                text = cmd.get("text", "").strip()
                if not text:
                    return
                await self._handle_chat_stream(ws, text)

            elif action == "feedback":
                # ── 快捷反馈（👍👎）─────────────────────────────
                satisfaction = float(cmd.get("satisfaction", 0.7))
                comment = cmd.get("comment", "")
                await self._handle_feedback(ws, satisfaction, comment)

            elif action == "task":
                # ── 通用任务处理：用户下达任务 ─────────────────
                text = cmd.get("text", "").strip()
                if not text:
                    return
                await self._handle_task(ws, text)

        except json.JSONDecodeError:
            pass

    # ── WebChat 对话处理 ──────────────────────────────────────

    async def _handle_chat(self, ws: web.WebSocketResponse, text: str) -> None:
        """
        WebChat 频道：用户在浏览器里发消息，Anima 思考后回复。
        全过程通过事件总线广播，前端思维流实时可见。

        智能路由：如果消息看起来是一个任务（而非闲聊/提问），
        自动转交给通用任务处理器。
        """
        from anima.events import emit_message, emit_thinking, emit_action
        from anima.models import ExperienceOutcome, Signal, SignalType

        await emit_message("收到用户消息", text[:60])

        # ── 智能路由：判断是否为任务 ─────────────────────────
        is_task = await self._detect_task_intent(text)
        if is_task:
            await self._handle_task(ws, text)
            return

        # 同时注入信号到 MindLoop（让问题树也感知到）
        if self._mind_loop:
            self._mind_loop.inject_signal(Signal(
                type=SignalType.MESSAGE,
                payload={"content": text, "source": "webchat"},
                strength=0.9,
            ))

        try:
            # 构建上下文
            identity = self._identity.load()
            ctx = self._memory.build_context(
                identity_prompt=self._identity.build_identity_prompt(identity),
                recent_messages=self._chat_history[-10:] + [{"role": "user", "content": text}],
                query_hint=text,
            )
            system_prompt = self._memory.format_context_as_system_prompt(ctx)

            await emit_thinking("正在思考回复...", text[:40])

            # 调用大脑
            reply = await self._brain.think(system_prompt, text)

            await emit_action("回复用户", reply[:80])

            # 记录对话历史
            self._chat_history.append({"role": "user", "content": text})
            self._chat_history.append({"role": "assistant", "content": reply})
            if len(self._chat_history) > 40:
                self._chat_history = self._chat_history[-40:]

            # 记录经历
            self._evo.record(action=text, method="WebChat对话", outcome=ExperienceOutcome.SUCCESS)

            # 发送回复给前端
            await ws.send_str(json.dumps({
                "type": "chat_reply",
                "text": reply,
                "model": self._brain.active_model if hasattr(self._brain, 'active_model') else "unknown",
            }, ensure_ascii=False))

        except Exception as e:
            logger.error(f"[Server] chat 处理失败: {e}")
            await ws.send_str(json.dumps({
                "type": "chat_reply",
                "text": f"[处理失败: {e}]",
                "error": True,
            }, ensure_ascii=False))

    async def _handle_chat_stream(self, ws: web.WebSocketResponse, text: str) -> None:
        """WebChat 流式对话：逐 token 返回，前端实时显示打字效果"""
        from anima.events import emit_message, emit_thinking

        await emit_message("收到用户消息（流式）", text[:60])

        try:
            identity = self._identity.load()
            ctx = self._memory.build_context(
                identity_prompt=self._identity.build_identity_prompt(identity),
                recent_messages=self._chat_history[-10:] + [{"role": "user", "content": text}],
                query_hint=text,
            )
            system_prompt = self._memory.format_context_as_system_prompt(ctx)

            await emit_thinking("正在流式回复...", text[:40])

            # 流式标记开始
            await ws.send_str(json.dumps({"type": "chat_stream_start"}, ensure_ascii=False))

            full_reply = ""
            async for chunk in self._brain.think_stream(system_prompt, text):
                full_reply += chunk
                await ws.send_str(json.dumps({
                    "type": "chat_stream_chunk",
                    "text": chunk,
                }, ensure_ascii=False))

            # 流式标记结束
            await ws.send_str(json.dumps({"type": "chat_stream_end"}, ensure_ascii=False))

            # 记录对话历史
            self._chat_history.append({"role": "user", "content": text})
            self._chat_history.append({"role": "assistant", "content": full_reply})
            if len(self._chat_history) > 40:
                self._chat_history = self._chat_history[-40:]

            from anima.models import ExperienceOutcome
            self._evo.record(action=text, method="WebChat流式对话", outcome=ExperienceOutcome.SUCCESS)

        except Exception as e:
            logger.error(f"[Server] chat_stream 处理失败: {e}")
            await ws.send_str(json.dumps({
                "type": "chat_stream_end",
                "error": str(e),
            }, ensure_ascii=False))

    async def _handle_feedback(self, ws: web.WebSocketResponse, satisfaction: float, comment: str) -> None:
        """处理前端发来的快捷反馈"""
        from anima.events import emit_trust

        reason = (
            "owner_explicit_trust" if satisfaction >= 0.9
            else "task_success" if satisfaction >= 0.6
            else "owner_frustrated"
        )
        state, level_changed, old_level = self._trust.adjust(reason, note=comment)
        self._memory.remember(
            content=f"主人反馈（满意度{int(satisfaction*100)}%）：{comment or '无说明'}",
            importance=0.7, tags=["feedback"],
        )

        await emit_trust(
            f"信任度变化: {int(state.score*100)}分",
            f"{'升级!' if level_changed else ''} {comment}" if comment else "",
        )

        await ws.send_str(json.dumps({
            "type": "feedback_result",
            "score": int(state.score * 100),
            "level": state.level.value,
            "level_changed": level_changed,
        }, ensure_ascii=False))

    # ── 通用任务处理 ─────────────────────────────────────────

    # ── 任务意图检测 ────────────────────────────────────────

    async def _detect_task_intent(self, text: str) -> bool:
        """
        判断用户消息是"任务指令"还是"闲聊/提问"。
        任务指令 → 走通用任务处理器
        闲聊/提问 → 走普通对话

        判断依据（快速规则，不调用大模型）：
        - 包含动作词（帮我、给我、做一下、处理、联系、发送、生成、整理...）
        - 长度超过 20 字且包含具体对象
        - 包含明确的指令语气
        """
        # 快速关键词检测（避免每次都调用大模型）
        task_indicators = [
            "帮我", "帮忙", "请你", "麻烦你",
            "做一下", "处理一下", "搞定", "完成",
            "联系", "跟进", "发送", "生成", "整理", "分析",
            "写一", "做个", "搜一下", "查一下", "找一下",
            "把这", "把那", "给我", "给他",
            "发一封", "写一篇", "做一份",
        ]

        text_lower = text.lower()

        # 明确的任务指示词
        if any(kw in text_lower for kw in task_indicators):
            # 但要排除太短的（"帮我看看这个对吗"不是任务）
            if len(text) >= 15:
                return True

        # 如果消息很长（>50字）且有具体细节，大概率是任务
        if len(text) > 50 and any(kw in text_lower for kw in ["电话", "微信", "邮件", "客户", "文件", "表格", "数据"]):
            return True

        return False

    # ── 通用任务处理 ─────────────────────────────────────────

    async def _handle_task(self, ws: web.WebSocketResponse, text: str) -> None:
        """
        通用任务处理入口。
        用户在 WebChat 中下达任务，自动走 6 步闭环。
        实时通过事件总线广播进度（前端思维流可见）。
        """
        # 通知前端：任务已接收，开始处理
        await ws.send_str(json.dumps({
            "type": "task_started",
            "text": f"收到任务，开始处理: {text[:60]}...",
        }, ensure_ascii=False))

        try:
            # 使用 MindLoop 的任务处理器
            if self._mind_loop:
                task = await self._mind_loop.process_task(text)
            else:
                # 降级：直接实例化处理器
                from anima.task_processor import UniversalTaskProcessor
                from anima.task_templates import TaskTemplateStore
                from anima.tools.dispatcher import get_dispatcher
                from pathlib import Path
                import os

                data_dir = Path(os.getenv("ANIMA_DATA_DIR", "./data"))
                processor = UniversalTaskProcessor(
                    brain=self._brain,
                    skill_registry=self._skills,
                    tool_dispatcher=get_dispatcher(),
                    evolution_engine=self._evo,
                    memory_manager=self._memory,
                    identity_engine=self._identity,
                    template_store=TaskTemplateStore(data_dir),
                )
                task = await processor.process_task(text)

            # 发送最终结果
            await ws.send_str(json.dumps({
                "type": "task_completed",
                "task_id": task.id,
                "status": task.status.value,
                "quality_score": int(task.quality_score * 100),
                "result": task.final_result,
                "steps_count": len(task.decomposed_steps),
                "corrections": task.corrections_made,
            }, ensure_ascii=False))

        except Exception as e:
            logger.error(f"[Server] task 处理失败: {e}")
            await ws.send_str(json.dumps({
                "type": "task_completed",
                "status": "failed",
                "result": f"任务处理失败: {e}",
                "error": True,
            }, ensure_ascii=False))

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

        try:
            trust_data = self._trust.progress_summary()
        except Exception:
            trust_data = {"score": 0, "level": "probation", "label": "未初始化", "next_level": None, "points_to_next": 0}

        try:
            skills_data = [
                {"id": s.id, "name": s.name, "proficiency": s.proficiency,
                 "success_rate": s.success_rate, "use_count": s.use_count}
                for s in self._skills.get_active()
            ]
        except Exception:
            skills_data = []

        try:
            questions_data = self._qtree.stats()
        except Exception:
            questions_data = {"pending": 0, "resolved": 0, "total": 0}

        try:
            evolution_data = self._evo.stats()
        except Exception:
            evolution_data = {"total_experiences": 0, "success_rate": 0, "methodology_count": 0}

        try:
            providers_data = self._providers.summary()
        except Exception:
            providers_data = {"total_providers": 0, "enabled": 0, "active": None, "providers": []}

        return {
            "identity": identity_data,
            "trust": trust_data,
            "skills": skills_data,
            "questions": questions_data,
            "evolution": evolution_data,
            "providers": providers_data,
            "ws_clients": len(self._ws_clients),
        }

    # ── 启动 ─────────────────────────────────────────────────

    async def start(self) -> None:
        runner = web.AppRunner(self._app)
        await runner.setup()
        site = web.TCPSite(runner, self._host, self._port)
        await site.start()
        logger.info(f"[Server] Anima 控制中心已启动: http://localhost:{self._port}")
