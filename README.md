# Anima — 全能型 AI 员工运行时

> 从零构建，不依赖任何 Agent 框架地基。永不停止，这才是真正的生命体。

---

## 设计哲学

Anima 不是一个"绑定岗位"的助手，而是一个**自主学习、跨部门全能的 AI 员工**。

| 能力 | 模块 | 说明 |
|------|------|------|
| 长期记忆 | `memory/` | 分类存储、重要性衰减、语义检索 |
| 自我身份 | `identity/` | 人格参数、核心价值观、多领域激活 |
| 信任与权限 | `trust/` | 5 级信任体系，逐步解锁自主能力 |
| 可扩展技能 | `skills/` | 按需安装、熟练度追踪、自动发现 |
| 驱动性问题 | `question/` | 问题树驱动行动，优先级排序 |
| 自我进化 | `evolution/` | 经验积累、方法论提炼、每日复盘 |
| 自驱心智循环 | `loop/` | 感知→思考→行动，永不停歇 |
| 多渠道通信 | `channels/` | Telegram / Discord / Slack / Web |
| 工具执行 | `tools/` | Web搜索、文件操作、Bash、表格 |
| 多模型支持 | `providers/` | DeepSeek/OpenAI/Claude/Gemini/Ollama |
| Web 控制中心 | `web/` | 实时思维流、对话、状态可视化 |

---

## 快速开始

### 方式一：一行命令安装（推荐）

```bash
curl -fsSL https://raw.githubusercontent.com/longnull-ck/animaclaw/main/install.sh | bash
```

脚本自动完成：检测环境 → 安装依赖 → 交互式配置（API Key、频道等）→ 就绪。
全程不需要手动编辑任何配置文件。

### 方式二：手动安装

```bash
# 1. 克隆
git clone https://github.com/longnull-ck/animaclaw.git
cd animaclaw

# 2. 安装
pip install -e ".[all]"

# 3. 交互式配置（自动写入 .env，不用手动编辑）
anima init

# 4. 启动
anima start
```

### 方式三：Docker 部署

```bash
git clone https://github.com/longnull-ck/animaclaw.git
cd animaclaw
anima init              # 交互式配置，自动生成 .env
make build && make up   # 构建并启动
make logs               # 查看日志
```

更多 Docker 命令：

| 命令 | 说明 |
|------|------|
| `make up` | 后台启动 |
| `make down` | 停止 |
| `make restart` | 重启 |
| `make logs` | 实时日志 |
| `make status` | 查看状态 |
| `make shell` | 进入容器 |
| `make clean` | 清理（含数据） |

### 方式三：开发环境（热重载）

```bash
docker compose -f docker-compose.dev.yml up
```

前端开发服务器在 `http://localhost:5173`，后端在 `http://localhost:3210`。

---

## 环境变量配置

### 模型 Provider（至少配置一个）

| 变量 | 说明 | 示例 |
|------|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key | `sk-...` |
| `OPENAI_API_KEY` | OpenAI API Key | `sk-...` |
| `ANTHROPIC_API_KEY` | Anthropic API Key | `sk-ant-...` |
| `GOOGLE_API_KEY` | Google Gemini API Key | `AI...` |
| `OLLAMA_ENABLED` | 启用本地 Ollama | `true` |

系统会自动检测所有配置的 Provider，首选第一个，失败自动切换到下一个。

### Telegram 频道（可选）

| 变量 | 说明 |
|------|------|
| `TELEGRAM_BOT_TOKEN` | 从 @BotFather 获取 |
| `TELEGRAM_OWNER_CHAT_ID` | 你的 Chat ID |

### Discord 频道（可选）

| 变量 | 说明 |
|------|------|
| `DISCORD_BOT_TOKEN` | Discord Bot Token |
| `DISCORD_OWNER_USER_ID` | 你的 Discord User ID |
| `DISCORD_GUILD_ID` | 限定 Guild（留空=所有） |

**Discord Bot 创建步骤：**
1. 前往 [Discord Developer Portal](https://discord.com/developers/applications)
2. 创建 Application → Bot → 复制 Token
3. 开启 Privileged Intents：`MESSAGE CONTENT`、`SERVER MEMBERS`
4. 生成 OAuth2 URL，权限选择 `Send Messages`、`Read Message History`
5. 邀请 Bot 到你的服务器

**使用方式：** DM 直接对话 / 在频道中 @Bot

### Slack 频道（可选）

| 变量 | 说明 |
|------|------|
| `SLACK_BOT_TOKEN` | Bot User OAuth Token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | App-Level Token (`xapp-...`) |
| `SLACK_OWNER_USER_ID` | 你的 Slack User ID |

**Slack App 创建步骤：**
1. 前往 [Slack API](https://api.slack.com/apps) 创建 App
2. OAuth & Permissions → Bot Token Scopes：
   - `chat:write` — 发送消息
   - `app_mentions:read` — 读取 @提及
   - `im:history` — 读取 DM 历史
   - `im:read` — 读取 DM
3. Event Subscriptions → Subscribe to bot events：
   - `message.im` — DM 消息
   - `app_mention` — @提及
4. Socket Mode → 开启并生成 App-Level Token
5. Install to Workspace

**使用方式：** DM 直接对话 / 在频道中 @Anima

---

## 项目结构

```
animaclaw/
├── anima/
│   ├── models.py           # 全局数据模型
│   ├── brain.py            # 大脑（多模型调用、JSON输出、流式）
│   ├── events.py           # 事件总线（透明化的核心）
│   ├── server.py           # Web 服务器（API + WebSocket + 静态）
│   ├── cli.py              # 命令行接口
│   ├── memory/             # 记忆存储与管理
│   │   ├── store.py        #   SQLite 持久化
│   │   └── manager.py      #   上下文构建、检索、衰减
│   ├── identity/           # 身份引擎
│   │   └── engine.py       #   人格、领域、身份 prompt
│   ├── trust/              # 信任系统
│   │   └── system.py       #   5级信任、权限映射
│   ├── skills/             # 技能注册表
│   │   └── registry.py     #   安装、发现、熟练度
│   ├── question/           # 驱动性问题树
│   │   └── tree.py         #   优先级队列、子问题衍生
│   ├── evolution/          # 自我进化引擎
│   │   └── engine.py       #   经验记录、方法论提炼
│   ├── loop/               # 心智循环
│   │   └── mind_loop.py    #   感知→思考→行动循环
│   ├── channels/           # 通信渠道
│   │   ├── base.py         #   渠道基类
│   │   ├── telegram.py     #   Telegram 适配器
│   │   ├── discord.py      #   Discord 适配器
│   │   └── slack.py        #   Slack 适配器
│   ├── providers/          # 模型提供商
│   │   └── registry.py     #   多 Provider 管理、failover
│   └── tools/              # 工具执行层
│       ├── dispatcher.py   #   统一调度器
│       ├── web_search.py   #   网络搜索
│       ├── web_read.py     #   网页读取
│       ├── file_ops.py     #   文件操作
│       ├── bash.py         #   Shell 命令
│       └── spreadsheet.py  #   表格处理
├── web/                    # 前端控制中心（React + Vite）
│   └── src/
│       ├── App.tsx         #   主布局（响应式）
│       ├── hooks/useAnima.ts  #  WebSocket 连接
│       └── components/     #   UI 组件
├── run.py                  # 统一启动入口
├── Dockerfile              # 生产镜像（多阶段构建）
├── Dockerfile.dev          # 开发镜像（热重载）
├── docker-compose.yml      # 生产部署
├── docker-compose.dev.yml  # 开发环境
├── Makefile                # 快捷命令
└── pyproject.toml          # Python 项目配置
```

---

## 命令行

```bash
python run.py init       # 初始化员工身份（交互式）
python run.py start      # 启动 Anima（心跳循环 + 所有配置频道）
python run.py status     # 查看当前状态
python run.py chat       # 命令行对话模式
python run.py feedback   # 给员工反馈（影响信任度）
```

---

## Web 控制中心

启动后访问 `http://localhost:3210`：

- **思维流** — 实时查看 Anima 的每一步思考、行动、记忆操作
- **对话面板** — 直接和 Anima 对话（支持流式输出）
- **员工档案** — 身份、信任度、技能、性格参数
- **底部面板** — 问题树、记忆库、进化日志、模型状态

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/status` | 完整状态快照 |
| GET | `/api/identity` | 身份信息 |
| GET | `/api/trust` | 信任进度 |
| GET | `/api/skills` | 已安装技能 |
| GET | `/api/questions` | 问题树状态 |
| GET | `/api/evolution` | 进化统计 |
| GET | `/api/memory/search?q=` | 记忆检索 |
| GET | `/api/providers` | Provider 状态 |
| GET | `/api/events/history` | 历史事件 |
| WS | `/ws` | WebSocket 实时推送 |

---

## 扩展技能

```python
from anima.tools.dispatcher import get_dispatcher

async def my_tool(args: dict) -> str:
    """自定义工具"""
    return f"执行结果: {args}"

# 注册到调度器
dispatcher = get_dispatcher()
dispatcher.register("my_tool", my_tool)
```

---

## 信任等级体系

| 等级 | 分数 | 解锁能力 |
|------|------|----------|
| 试用期 | 0-20 | 仅响应指令，需确认 |
| 基础 | 20-40 | 自动执行日常任务 |
| 中级 | 40-65 | 主动推送、自动安装技能 |
| 高级 | 65-85 | 跨领域决策、资源调配 |
| 完全信任 | 85-100 | 全自主运行 |

信任通过：完成任务、主人正面反馈、持续无事故 来提升。

---

## 架构参考

- [Hermes Agent](https://github.com/nousresearch/hermes-agent) — 工具调用与推理范式
- [OpenHarness](https://github.com/HKUDS/OpenHarness) — Agent 评估与能力边界

---

## License

MIT
