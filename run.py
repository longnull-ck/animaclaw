"""
Anima — run.py
统一启动入口。直接代理到 anima.cli 模块。

用法：
  python run.py init        首次初始化员工身份
  python run.py start       启动 Anima（含心跳循环）
  python run.py status      查看当前状态
  python run.py chat        进入命令行对话模式
  python run.py feedback    给员工反馈（影响信任度）
  python run.py doctor      检查配置和环境

环境变量（.env 文件）：
  DEEPSEEK_API_KEY      DeepSeek API Key（至少配一个）
  OPENAI_API_KEY        OpenAI API Key（可选）
  ANTHROPIC_API_KEY     Anthropic API Key（可选）
  GOOGLE_API_KEY        Google Gemini API Key（可选）
  OLLAMA_ENABLED        启用本地 Ollama（可选）
  TELEGRAM_BOT_TOKEN    Telegram Bot Token（可选）
  TELEGRAM_OWNER_CHAT_ID 主人的 Telegram Chat ID（可选）
  DISCORD_BOT_TOKEN     Discord Bot Token（可选）
  SLACK_BOT_TOKEN       Slack Bot Token（可选）
  SLACK_APP_TOKEN       Slack App Token（可选）
  ANIMA_DATA_DIR        数据目录（默认：./data）
"""

from anima.cli import main

if __name__ == "__main__":
    main()
