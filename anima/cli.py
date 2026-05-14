"""
Anima — CLI 入口
安装后通过 `anima` 命令直接调用，和 OpenClaw 的 `openclaw gateway` 一样简洁。

用法：
  anima start       启动全部（gateway + web + 心跳循环）
  anima init        初始化员工身份
  anima status      查看当前状态
  anima chat        进入命令行对话
  anima feedback    给员工反馈
  anima doctor      检查配置和环境
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# ── 加载 .env ────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── 日志 ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("anima")

DATA_DIR = Path(os.getenv("ANIMA_DATA_DIR", "./data"))


# ─────────────────────────────────────────────────────────────
# 运行时
# ─────────────────────────────────────────────────────────────

class AnimaRuntime:

    def __init__(self):
        self._state_file = DATA_DIR / "state.json"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._setup()

    def _setup(self) -> None:
        from anima.brain import Brain
        from anima.memory.store import MemoryStore
        from anima.memory.manager import MemoryManager
        from anima.identity.engine import IdentityEngine
        from anima.trust.system import TrustSystem
        from anima.skills.registry import SkillRegistry
        from anima.question.tree import QuestionTree
        from anima.evolution.engine import EvolutionEngine
        from anima.loop.mind_loop import MindLoop
        from anima.providers.registry import get_provider_registry

        self.providers = get_provider_registry()
        self.brain     = Brain()
        self.identity  = IdentityEngine(DATA_DIR)
        self.memory    = MemoryManager(MemoryStore(DATA_DIR / "memory.db"))
        self.trust     = TrustSystem(DATA_DIR)
        self.skills    = SkillRegistry(DATA_DIR)
        self.qtree     = QuestionTree(DATA_DIR)
        self.evo       = EvolutionEngine(DATA_DIR)

        self.loop = MindLoop(
            identity_engine=self.identity,
            memory_manager=self.memory,
            trust_system=self.trust,
            skill_registry=self.skills,
            question_tree=self.qtree,
            evolution_engine=self.evo,
            brain=self.brain,
            get_state=self._load_state,
            save_state=self._save_state,
            notify_owner=self._notify,
        )
        self._channel = None

    async def _load_state(self):
        if not self._state_file.exists():
            raise RuntimeError("员工尚未初始化，请先运行: anima init")
        raw = json.loads(self._state_file.read_text(encoding="utf-8"))
        from anima.models import (
            AnimaState, TrustLevel, TrustEvent, TrustState, Personality, Identity
        )
        p = raw["identity"].pop("personality")
        raw["identity"]["personality"] = Personality(**p)
        identity = Identity(**raw["identity"])
        ts = raw["trust"]
        ts["level"] = TrustLevel(ts["level"])
        ts["history"] = [TrustEvent(**e) for e in ts.get("history", [])]
        trust = TrustState(**ts)
        return AnimaState(
            identity=identity, trust=trust,
            tick_count=raw.get("tick_count", 0),
            last_tick_at=raw.get("last_tick_at"),
        )

    async def _save_state(self, state) -> None:
        data = {
            "identity": {
                "id": state.identity.id, "name": state.identity.name,
                "owner_id": state.identity.owner_id,
                "owner_name": state.identity.owner_name,
                "company_description": state.identity.company_description,
                "core_values": state.identity.core_values,
                "personality": {
                    "proactivity": state.identity.personality.proactivity,
                    "risk_tolerance": state.identity.personality.risk_tolerance,
                    "language": state.identity.personality.language,
                    "communication_style": state.identity.personality.communication_style,
                },
                "active_domains": state.identity.active_domains,
                "version": state.identity.version,
                "created_at": state.identity.created_at,
                "updated_at": state.identity.updated_at,
            },
            "trust": {
                "score": state.trust.score,
                "level": state.trust.level.value,
                "history": [
                    {"delta": e.delta, "reason": e.reason, "timestamp": e.timestamp}
                    for e in state.trust.history[-20:]
                ],
                "updated_at": state.trust.updated_at,
            },
            "tick_count": state.tick_count,
            "last_tick_at": state.last_tick_at,
        }
        self._state_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    async def _notify(self, text: str) -> None:
        if self._channel:
            await self._channel.send(text)
        else:
            print(f"\n🔔 Anima: {text}\n")

    # ─────────────────────────────────────────────────────────
    # 命令：anima start（核心命令，启动全部）
    # ─────────────────────────────────────────────────────────

    async def cmd_start(self, port: int = 3210, verbose: bool = False) -> None:
        """启动 Anima Gateway（心跳 + Web 控制中心 + 频道）"""
        from anima.events import emit_system
        from anima.server import AnimaServer

        state = await self._load_state()
        name = state.identity.name

        print(f"""
╔══════════════════════════════════════════════════╗
║                                                  ║
║   🦾 Anima Gateway — {name:16s}          ║
║                                                  ║
╠══════════════════════════════════════════════════╣
║   控制中心: http://localhost:{port:<5d}              ║
║   WebSocket: ws://localhost:{port:<5d}/ws             ║
║   心跳循环: 每 5 分钟                             ║
║   模型:     {str(self.providers.active.name if self.providers.active else '未配置'):<20s}      ║
╚══════════════════════════════════════════════════╝
""")

        # 启动 Web 服务器（含 WebSocket）
        server = AnimaServer(
            identity=self.identity,
            memory=self.memory,
            trust=self.trust,
            skills=self.skills,
            question_tree=self.qtree,
            evolution=self.evo,
            providers=self.providers,
            port=port,
        )
        await server.start()

        # 启动 Telegram 频道（如果配置了）
        if os.getenv("TELEGRAM_BOT_TOKEN"):
            from anima.channels.telegram import TelegramChannel
            self._channel = TelegramChannel(
                owner_id="owner_001",
                inject_signal_fn=self.loop.inject_signal,
            )
            await self._channel.start()

            async def on_message(sender_id: str, text: str) -> None:
                from anima.events import emit_message
                await emit_message("收到主人消息", text[:60])
                ctx = self.memory.build_context(
                    identity_prompt=self.identity.build_identity_prompt(state.identity),
                    recent_messages=[{"role": "user", "content": text}],
                    query_hint=text,
                )
                system = self.memory.format_context_as_system_prompt(ctx)
                reply = await self.brain.think(system, text)
                await self._channel.send(reply)
                from anima.models import ExperienceOutcome
                self.evo.record(action=text, method="即时对话", outcome=ExperienceOutcome.SUCCESS)

            self._channel.on_message(on_message)
            print("  ✅ Telegram 频道已连接")

        # 启动心跳循环
        self.loop.start()
        print("  ✅ 心跳循环已启动")
        await emit_system("Anima Gateway 启动", f"端口: {port}")

        print(f"\n  {name} 已上线。按 Ctrl+C 停止。\n")

        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print(f"\n  正在停止 {name}...")
            self.loop.stop()
            if self._channel:
                await self._channel.stop()
            print("  已停止。再见！\n")

    # ─────────────────────────────────────────────────────────
    # 命令：anima init
    # ─────────────────────────────────────────────────────────

    async def cmd_init(self) -> None:
        print("\n🦾 Anima — 全能型 AI 员工初始化\n")
        name         = input("  员工名字（默认 Anima）: ").strip() or "Anima"
        owner_name   = input("  您的名字（主人）: ").strip() or "主人"
        company_desc = input("  公司业务描述（一两句话）: ").strip()
        if not company_desc:
            print("  ❌ 公司描述不能为空")
            return

        identity = self.identity.initialize(
            name=name, owner_name=owner_name,
            owner_id="owner_001", company_description=company_desc,
        )
        trust = self.trust.initialize()
        self.skills.initialize()
        self.qtree.initialize()
        self.evo.initialize()

        from anima.models import AnimaState
        await self._save_state(AnimaState(identity=identity, trust=trust))
        self.memory.remember_permanent(
            f"我叫 {name}，服务于 {owner_name}。公司：{company_desc}",
            tags=["identity", "core"],
        )

        print(f"""
  ✅ {name} 已创建！

  信任等级: 试用期（需要积累信任）
  SOUL.md:  {DATA_DIR}/SOUL.md

  下一步运行:
    anima start
""")

    # ─────────────────────────────────────────────────────────
    # 命令：anima status
    # ─────────────────────────────────────────────────────────

    async def cmd_status(self) -> None:
        state = await self._load_state()
        trust_s = self.trust.progress_summary()
        evo_s = self.evo.stats()
        q_s = self.qtree.stats()
        skills = self.skills.get_active()
        from anima.identity.engine import DOMAIN_LABELS
        domains = "、".join(DOMAIN_LABELS.get(d, d) for d in state.identity.active_domains) or "暂无"

        print(f"""
╔══════════════════════════════════════╗
║  🦾 {state.identity.name} — 状态报告
╠══════════════════════════════════════╣
║  版本        v{state.identity.version}
║  信任等级    {trust_s['label']}
║  信任分数    {trust_s['score']}分
║  激活领域    {domains}
╠══════════════════════════════════════╣
║  已安装技能  {len(skills)} 个
║  经历总数    {evo_s['total_experiences']}
║  成功率      {evo_s['success_rate']:.0%}
║  方法论数    {evo_s['methodology_count']}
╠══════════════════════════════════════╣
║  问题树: 待处理 {q_s['pending']} / 已解决 {q_s['resolved']} / 总计 {q_s['total']}
║  心跳次数    {state.tick_count}
╚══════════════════════════════════════╝
""")

    # ─────────────────────────────────────────────────────────
    # 命令：anima chat
    # ─────────────────────────────────────────────────────────

    async def cmd_chat(self) -> None:
        state = await self._load_state()
        name = state.identity.name
        print(f"\n  💬 与 {name} 对话（输入 exit 退出）\n")
        history: list[dict] = []
        while True:
            try:
                user_input = input("  你: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if user_input.lower() in ("exit", "quit", "q"):
                break
            if not user_input:
                continue
            history.append({"role": "user", "content": user_input})
            ctx = self.memory.build_context(
                identity_prompt=self.identity.build_identity_prompt(state.identity),
                recent_messages=history, query_hint=user_input,
            )
            system = self.memory.format_context_as_system_prompt(ctx)
            try:
                reply = await self.brain.think(system, user_input)
            except Exception as e:
                reply = f"[调用失败: {e}]"
            history.append({"role": "assistant", "content": reply})
            print(f"\n  {name}: {reply}\n")
            from anima.models import ExperienceOutcome
            self.evo.record(action=user_input, method="命令行对话", outcome=ExperienceOutcome.SUCCESS)

    # ─────────────────────────────────────────────────────────
    # 命令：anima doctor
    # ─────────────────────────────────────────────────────────

    async def cmd_doctor(self) -> None:
        print("\n  🩺 Anima Doctor — 环境检查\n")
        checks = []

        # 检查数据目录
        checks.append(("数据目录", DATA_DIR.exists(), str(DATA_DIR)))

        # 检查身份文件
        identity_exists = (DATA_DIR / "identity.json").exists()
        checks.append(("员工身份", identity_exists, "已初始化" if identity_exists else "未初始化，运行 anima init"))

        # 检查 Provider
        from anima.providers.registry import get_provider_registry
        registry = get_provider_registry()
        has_provider = len(registry.enabled_providers) > 0
        provider_names = ", ".join(p.name for p in registry.enabled_providers)
        checks.append(("模型 Provider", has_provider, provider_names or "无！请配置 DEEPSEEK_API_KEY"))

        # 检查 Telegram
        has_tg = bool(os.getenv("TELEGRAM_BOT_TOKEN"))
        checks.append(("Telegram", has_tg, "已配置" if has_tg else "未配置（可选）"))

        # 输出结果
        for name, ok, detail in checks:
            icon = "✅" if ok else "❌"
            print(f"  {icon} {name:16s} {detail}")

        all_ok = all(ok for _, ok, _ in checks[:3])  # 前3个是必须的
        print(f"\n  {'✅ 一切正常，可以启动！' if all_ok else '❌ 有问题需要修复'}\n")

    # ─────────────────────────────────────────────────────────
    # 命令：anima feedback
    # ─────────────────────────────────────────────────────────

    async def cmd_feedback(self) -> None:
        print("\n  📝 给 Anima 反馈\n")
        satisfaction = float(input("  满意度 (0-10): ").strip()) / 10
        comment = input("  反馈内容（可选）: ").strip()
        reason = (
            "owner_explicit_trust" if satisfaction >= 0.9
            else "task_success" if satisfaction >= 0.6
            else "owner_frustrated"
        )
        state, level_changed, old_level = self.trust.adjust(reason, note=comment)
        self.memory.remember(content=f"主人反馈（满意度{int(satisfaction*100)}%）：{comment or '无说明'}",
                             importance=0.7, tags=["feedback"])
        print(f"\n  ✅ 已记录，信任分：{int(state.score*100)}")
        if level_changed:
            print(f"  🎉 信任等级: {old_level.value} → {state.level.value}")
        print()


# ─────────────────────────────────────────────────────────────
# CLI 入口函数（pyproject.toml [project.scripts] 指向这里）
# ─────────────────────────────────────────────────────────────

def main() -> None:
    args = sys.argv[1:]
    cmd = args[0] if args else "start"

    # 解析 --port 和 --verbose 参数
    port = 3210
    verbose = False
    for i, arg in enumerate(args):
        if arg == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
        if arg == "--verbose":
            verbose = True

    runtime = AnimaRuntime()

    commands = {
        "start":    lambda: runtime.cmd_start(port=port, verbose=verbose),
        "init":     runtime.cmd_init,
        "status":   runtime.cmd_status,
        "chat":     runtime.cmd_chat,
        "feedback": runtime.cmd_feedback,
        "doctor":   runtime.cmd_doctor,
    }

    if cmd in ("--help", "-h", "help"):
        print("""
🦾 Anima — 全能型 AI 员工

用法:
  anima start [--port 3210] [--verbose]   启动 Gateway（全部服务）
  anima init                              初始化员工身份
  anima status                            查看当前状态
  anima chat                              命令行对话
  anima feedback                          给员工反馈
  anima doctor                            检查配置和环境
  anima --help                            显示此帮助
""")
        return

    if cmd not in commands:
        print(f"  未知命令: {cmd}")
        print(f"  可用命令: {', '.join(commands)}")
        print(f"  运行 anima --help 查看帮助")
        sys.exit(1)

    asyncio.run(commands[cmd]())


if __name__ == "__main__":
    main()
