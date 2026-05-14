# Anima — 全能型 AI 员工运行时

> 从零构建，不依赖任何 Agent 框架地基。

---

## 设计哲学

Anima 不是一个"绑定岗位"的助手，而是一个**自主学习、跨部门全能的 AI 员工**。  
她拥有：

| 能力 | 模块 |
|------|------|
| 长期记忆 | `memory/` |
| 自我身份 | `identity/` |
| 信任与权限 | `trust/` |
| 可扩展技能 | `skills/` |
| 驱动性问题 | `question/` |
| 自我进化 | `evolution/` |
| 自驱心智循环 | `loop/` |
| 多渠道通信 | `channels/` |

---

## 快速开始

```bash
# 1. 安装依赖
pip install -e ".[dev]"

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY 和 TELEGRAM_BOT_TOKEN

# 3. 启动
python run.py
```

---

## 项目结构

```
anima/
├── anima/
│   ├── models.py          # 全局数据模型
│   ├── brain.py           # 大脑核心（信号 → 思考 → 行动）
│   ├── memory/            # 记忆存储与管理
│   ├── identity/          # 身份引擎
│   ├── trust/             # 信任系统
│   ├── skills/            # 技能注册表
│   ├── question/          # 驱动性问题树
│   ├── evolution/         # 自我进化引擎
│   ├── loop/              # 心智循环（定时自驱动）
│   └── channels/          # 通信渠道（Telegram 等）
├── run.py                 # 启动入口
├── pyproject.toml
└── .env.example
```

---

## 扩展技能

```python
async def my_tool(args: dict) -> str:
    return f"执行结果: {args}"

skills.install(
    name="我的工具",
    description="做某件事",
    tool_name="my_tool",
    domains=["general"],
    handler=my_tool,
)
```

---

## 架构参考

- [Hermes Agent](https://github.com/nousresearch/hermes-agent) — 工具调用与推理范式
- [OpenHarness](https://github.com/HKUDS/OpenHarness) — Agent 评估与能力边界

---

## License

MIT
