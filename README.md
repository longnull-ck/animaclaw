# 🦾 Anima — 你的全能 AI 员工

<p align="center">
  <strong>永不停止，这才是真正的生命体。</strong>
</p>

<p align="center">
  <a href="https://github.com/longnull-ck/animaclaw/actions/workflows/ci.yml?branch=main"><img src="https://img.shields.io/github/actions/workflow/status/longnull-ck/animaclaw/ci.yml?branch=main&style=for-the-badge" alt="CI"></a>
  <a href="https://github.com/longnull-ck/animaclaw/releases"><img src="https://img.shields.io/github/v/release/longnull-ck/animaclaw?include_prereleases&style=for-the-badge" alt="Release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="MIT License"></a>
  <a href="https://github.com/longnull-ck/animaclaw"><img src="https://img.shields.io/github/stars/longnull-ck/animaclaw?style=for-the-badge" alt="Stars"></a>
</p>

**Anima** 是一个运行在你自己机器上的 AI 员工。她有身份、有记忆、会自我进化。你给她任务，她会主动思考、行动、汇报，像真正的员工一样成长。

不是聊天机器人。不是 Copilot。是一个**会自己干活的员工**。

---

## 为什么选择 Anima？

- 🧠 **有记忆** — 记住所有对话和任务，不需要重复解释
- 🎭 **有身份** — 可定制的性格、价值观、工作风格
- 📈 **会成长** — 信任体系 + 经验积累，越用越强
- 🔄 **永不停止** — 心智循环持续运行，主动发现问题和机会
- 🔌 **多渠道** — Telegram / Discord / Slack / Web 控制中心
- 🤖 **多模型** — DeepSeek / OpenAI / Claude / Gemini / Ollama，自动切换
- 🛠️ **会用工具** — 搜索网页、读写文件、执行命令、处理表格
- 🔒 **本地运行** — 数据全在你手上，不依赖任何云服务

---

## 快速安装

### macOS / Linux

```bash
curl -fsSL https://raw.githubusercontent.com/longnull-ck/animaclaw/main/install.sh | bash
```

### Windows（PowerShell）

```powershell
irm https://raw.githubusercontent.com/longnull-ck/animaclaw/main/install.ps1 | iex
```

### 手动安装（所有平台）

```bash
git clone https://github.com/longnull-ck/animaclaw.git
cd animaclaw
pip install -e ".[all]"
python run.py init       # 交互式配置
python run.py start      # 启动
```

安装脚本自动完成：检测环境 → 安装依赖 → 交互式配置 → 就绪。  
全程不需要手动编辑任何配置文件。

> **要求：** Python 3.11+，至少一个 AI 模型的 API Key

---

## 30 秒上手

```bash
# 1. 初始化（设置名字、公司、API Key）
python run.py init

# 2. 启动（Web 控制中心 + 心智循环 + 消息频道）
python run.py start

# 3. 打开浏览器
# http://localhost:3210
```

就这样。Anima 已经在工作了。

---

## 连接消息频道

配置对应环境变量即可自动连接，全部可选：

| 频道 | 需要的环境变量 |
|------|---------------|
| Telegram | `TELEGRAM_BOT_TOKEN` + `TELEGRAM_OWNER_CHAT_ID` |
| Discord | `DISCORD_BOT_TOKEN` + `DISCORD_OWNER_USER_ID` |
| Slack | `SLACK_BOT_TOKEN` + `SLACK_APP_TOKEN` |
| Web | 默认启动，无需配置 |

频道设置详情见 [频道配置指南](docs/channels.md)。

---

## 支持的模型

| Provider | 环境变量 | 说明 |
|----------|----------|------|
| DeepSeek | `DEEPSEEK_API_KEY` | 推荐，性价比最高 |
| OpenAI | `OPENAI_API_KEY` | GPT-4o / GPT-4 |
| Anthropic | `ANTHROPIC_API_KEY` | Claude 3.5 / Claude 4 |
| Google | `GOOGLE_API_KEY` | Gemini Pro |
| Ollama | `OLLAMA_ENABLED=true` | 本地模型，完全离线 |

配置多个 Provider 时，自动 failover：首选失败 → 自动切换下一个。

---

## 信任体系

Anima 不会一上来就有所有权限。她需要赢得信任：

| 等级 | 能力 |
|------|------|
| 🟡 试用期 | 只响应指令，执行前需确认 |
| 🟢 基础 | 自动执行日常任务 |
| 🔵 中级 | 主动推送发现、自动学习新技能 |
| 🟣 高级 | 跨领域决策、资源调配 |
| 🔴 完全信任 | 全自主运行 |

通过：完成任务 ✓ · 正面反馈 ✓ · 持续无事故 ✓ 来提升信任。

---

## 命令行

```bash
python run.py init       # 初始化身份
python run.py start      # 启动（Web + 频道 + 心智循环）
python run.py status     # 查看状态报告
python run.py chat       # 命令行对话
python run.py feedback   # 给反馈（影响信任度）
python run.py doctor     # 诊断环境配置
```

---

## Web 控制中心

启动后访问 `http://localhost:3210`：

- **思维流** — 实时看到 Anima 在想什么、在做什么
- **对话** — 直接和她说话（流式输出）
- **员工档案** — 身份、信任度、技能、性格
- **监控面板** — 问题树、记忆库、进化日志

---

## Docker 部署

```bash
git clone https://github.com/longnull-ck/animaclaw.git
cd animaclaw
python run.py init          # 交互式配置
make build && make up       # 构建并启动
```

| 命令 | 说明 |
|------|------|
| `make up` | 启动 |
| `make down` | 停止 |
| `make logs` | 查看日志 |
| `make restart` | 重启 |

---

## 从零构建，不依赖任何 Agent 框架

Anima 没有用 LangChain、AutoGen、CrewAI 或任何框架。  
每一行代码都是为 **"一个有生命的 AI 员工"** 这个目标从零写的。

<details>
<summary>📁 项目结构（点击展开）</summary>

```
animaclaw/
├── anima/
│   ├── brain.py            # 大脑（多模型、流式、JSON 输出）
│   ├── memory/             # 长期记忆（SQLite + 知识图谱）
│   ├── identity/           # 身份引擎（人格 + 价值观）
│   ├── trust/              # 信任系统（5 级权限）
│   ├── skills/             # 技能注册表（按需安装）
│   ├── question/           # 问题树（驱动行动）
│   ├── evolution/          # 进化引擎（经验 + 方法论）
│   ├── loop/               # 心智循环（感知→思考→行动）
│   ├── channels/           # 通信渠道适配器
│   ├── providers/          # 模型 Provider 管理
│   ├── tools/              # 工具层（搜索/文件/命令/表格）
│   └── server.py           # Web 服务器（API + WebSocket）
├── web/                    # 前端（React + Vite + Tailwind）
├── run.py                  # 统一入口
├── install.sh              # Linux/macOS 安装脚本
├── install.ps1             # Windows 安装脚本
└── pyproject.toml          # Python 项目配置
```

</details>

<details>
<summary>🔌 API 端点（点击展开）</summary>

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/status` | 完整状态 |
| GET | `/api/identity` | 身份信息 |
| GET | `/api/trust` | 信任进度 |
| GET | `/api/skills` | 已安装技能 |
| GET | `/api/questions` | 问题树 |
| GET | `/api/evolution` | 进化统计 |
| GET | `/api/memory/search?q=` | 记忆检索 |
| GET | `/api/providers` | Provider 状态 |
| WS | `/ws` | 实时推送 |

</details>

---

## 架构灵感

- [OpenClaw](https://github.com/openclaw/openclaw) — 个人 AI 助手的产品形态
- [Hermes Agent](https://github.com/nousresearch/hermes-agent) — 工具调用与推理
- [OpenHarness](https://github.com/HKUDS/OpenHarness) — Agent 评估

---

## License

MIT — 随便用，随便改。
