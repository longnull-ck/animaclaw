"""
Anima — run.py
一个文件启动全部。永不停止，这才是真正的生命体。

用法：
  python run.py init        首次初始化员工身份
  python run.py start       启动 Anima（含心跳循环）
  python run.py status      查看当前状态
  python run.py chat        进入命令行对话模式
  python run.py feedback    给员工反馈（影响信任度）

环境变量（.env 文件）：
  DEEPSEEK_API_KEY      DeepSeek API Key（必填）
  TELEGRAM_BOT_TOKEN    Telegram Bot Token（可选）
  TELEGRAM_OWNER_ID     主人的 Telegram ID（可选）
  ANIMA_DATA_DIR        数据目录（默认：./data）
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("anima")

DATA_DIR = Path(os.getenv("ANIMA_DATA_DIR", "./data"))


class AnimaRuntime:

    def __init__(self):
        self._state_file = DATA_DIR / "state.json"
        self._setup_engines()

    def _setup_engines(self) -> None:
        from anima.brain import Brain
        from anima.memory.store import MemoryStore
        from anima.memory.manager import MemoryManager
        from anima.identity.engine import IdentityEngine
        from anima.trust.system import TrustSystem
        from anima.skills.registry import SkillRegistry
        from anima.question.tree import QuestionTree
        from anima.evolution.engine import EvolutionEngine
        from anima.loop.mind_loop import MindLoop

        DATA_DIR.mkdir(parents=True, exist_ok=True)

        self.brain    = Brain()
        self.identity = IdentityEngine(DATA_DIR)
        self.memory   = MemoryManager(MemoryStore(DATA_DIR / "memory.db"))
        self.trust    = TrustSystem(DATA_DIR)
        self.skills   = SkillRegistry(DATA_DIR)
        self.qtree    = QuestionTree(DATA_DIR)
        self.evo      = EvolutionEngine(DATA_DIR)

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
            raise RuntimeError("员工尚未初始化，请先运行: python run.py init")
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
            identity=identity,
            trust=trust,
            tick_count=raw.get("tick_count", 0),
            last_tick_at=raw.get("last_tick_at"),
        )

    async def _save_state(self, state) -> None:
        data = {
            "identity": {
                "id": state.identity.id,
                "name": state.identity.name,
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

    # ── 命令 ─────────────────────────────────────────────────

    async def cmd_init(self) -> None:
        print("\n🦾 欢迎使用 Anima — 全能型 AI 员工\n")
        name         = input("员工名字（默认 Anima）: ").strip() or "Anima"
        owner_name   = input("您的名字（主人）: ").strip() or "主人"
        company_desc = input("公司业务描述（一两句话）: ").strip()
        if not company_desc:
            print("❌ 公司描述不能为空")
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

        print(f"\n✅ {name} 已创建！")
        print(f"   信任等级：试用期（需要积累信任）")
        print(f"   SOUL.md 已生成：{DATA_DIR}/SOUL.md")
        print(f"\n运行 'python run.py start' 启动 Anima\n")

    async def cmd_start(self) -> None:
        # 环境配置校验
        from anima.config import require_config_or_exit
        config_result = require_config_or_exit()

        state = await self._load_state()
        name = state.identity.name
        print(f"\n🚀 {name} 启动中...\n")

        channels_started = []

        # ── Telegram 频道 ─────────────────────────────────────
        if os.getenv("TELEGRAM_BOT_TOKEN"):
            from anima.channels.telegram import TelegramChannel
            self._channel = TelegramChannel(
                owner_id="owner_001",
                inject_signal_fn=self.loop.inject_signal,
            )
            await self._channel.start()

            async def on_message(sender_id: str, text: str) -> None:
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
            channels_started.append("Telegram")
            print("✅ Telegram 频道已连接")

        # ── Discord 频道 ──────────────────────────────────────
        if os.getenv("DISCORD_BOT_TOKEN"):
            from anima.channels.discord import DiscordChannel
            self._discord_channel = DiscordChannel(
                token=os.getenv("DISCORD_BOT_TOKEN"),
                brain=self.brain,
                owner_user_id=os.getenv("DISCORD_OWNER_USER_ID", ""),
                guild_id=os.getenv("DISCORD_GUILD_ID"),
            )
            await self._discord_channel.start()
            channels_started.append("Discord")
            print("✅ Discord 频道已连接")

        # ── Slack 频道 ────────────────────────────────────────
        if os.getenv("SLACK_BOT_TOKEN") and os.getenv("SLACK_APP_TOKEN"):
            from anima.channels.slack import SlackChannel
            self._slack_channel = SlackChannel(
                bot_token=os.getenv("SLACK_BOT_TOKEN"),
                app_token=os.getenv("SLACK_APP_TOKEN"),
                brain=self.brain,
                owner_user_id=os.getenv("SLACK_OWNER_USER_ID", ""),
            )
            await self._slack_channel.start()
            channels_started.append("Slack")
            print("✅ Slack 频道已连接")

        if not channels_started:
            print("ℹ️  未配置任何消息频道，消息将输出到控制台")
        else:
            print(f"📡 已启动频道: {', '.join(channels_started)}")

        self.loop.start()
        print(f"✅ 心跳循环已启动（每5分钟感知一次）")
        print(f"\n{name} 已上线，永远在线为您服务。按 Ctrl+C 停止\n")

        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print(f"\n\n正在停止 {name}...")
            self.loop.stop()
            if self._channel:
                await self._channel.stop()
            if hasattr(self, '_discord_channel') and self._discord_channel:
                await self._discord_channel.stop()
            if hasattr(self, '_slack_channel') and self._slack_channel:
                await self._slack_channel.stop()
            print("已停止。再见！\n")

    async def cmd_status(self) -> None:
        state = await self._load_state()
        trust_s = self.trust.progress_summary()
        evo_s   = self.evo.stats()
        q_s     = self.qtree.stats()
        skills  = self.skills.get_active()
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
║  主人满意度  {evo_s['avg_owner_satisfaction']:.0%}
║  方法论数    {evo_s['methodology_count']}
╠══════════════════════════════════════╣
║  问题树
║    待处理    {q_s['pending']}
║    已解决    {q_s['resolved']}
║    总计      {q_s['total']}
║  心跳次数    {state.tick_count}
╚══════════════════════════════════════╝
""")

    async def cmd_chat(self) -> None:
        state = await self._load_state()
        name = state.identity.name
        print(f"\n💬 与 {name} 对话（输入 exit 退出）\n")
        history: list[dict] = []

        while True:
            try:
                user_input = input("你: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if user_input.lower() in ("exit", "quit", "q"):
                break
            if not user_input:
                continue

            history.append({"role": "user", "content": user_input})
            ctx = self.memory.build_context(
                identity_prompt=self.identity.build_identity_prompt(state.identity),
                recent_messages=history,
                query_hint=user_input,
            )
            system = self.memory.format_context_as_system_prompt(ctx)
            try:
                reply = await self.brain.think(system, user_input)
            except Exception as e:
                reply = f"[大脑调用失败: {e}]"
            history.append({"role": "assistant", "content": reply})
            print(f"\n{name}: {reply}\n")
            from anima.models import ExperienceOutcome
            self.evo.record(action=user_input, method="命令行对话", outcome=ExperienceOutcome.SUCCESS)

    async def cmd_doctor(self) -> None:
        """诊断命令：检查环境配置"""
        from anima.config import validate_config
        result = validate_config()
        if result["ok"]:
            print("✅ 所有检查通过，可以正常启动！")
        else:
            print("❌ 存在问题，请修复后再启动。")

    async def cmd_feedback(self) -> None:
        print("\n📝 给 Anima 反馈\n")
        satisfaction = float(input("满意度 (0-10): ").strip()) / 10
        comment = input("反馈内容（可选）: ").strip()
        reason = (
            "owner_explicit_trust" if satisfaction >= 0.9
            else "task_success" if satisfaction >= 0.6
            else "owner_frustrated"
        )
        state, level_changed, old_level = self.trust.adjust(reason, note=comment)
        self.memory.remember(
            content=f"主人反馈（满意度{int(satisfaction*100)}%）：{comment or '无说明'}",
            importance=0.7, tags=["feedback"],
        )
        print(f"\n✅ 已记录，信任分：{int(state.score*100)}")
        if level_changed:
            print(f"🎉 信任等级: {old_level.value} → {state.level.value}")
        print()


async def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "start"
    runtime = AnimaRuntime()
    commands = {
        "init": runtime.cmd_init,
        "start": runtime.cmd_start,
        "status": runtime.cmd_status,
        "chat": runtime.cmd_chat,
        "feedback": runtime.cmd_feedback,
        "doctor": runtime.cmd_doctor,
    }
    if cmd not in commands:
        print(f"未知命令: {cmd}\n可用命令: {', '.join(commands)}")
        sys.exit(1)
    await commands[cmd]()


if __name__ == "__main__":
    asyncio.run(main())
