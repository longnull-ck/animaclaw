"""
Anima — Skills Registry（技能注册表）
老板不需要手动安装能力——AI 员工自己发现自己不会，然后自己去学。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from anima.models import Skill, SkillSource, SkillStatus, ExperienceOutcome

logger = logging.getLogger("anima.skills")

SKILL_CATALOG: list[dict] = [
    {"id": "web_search",       "name": "网络搜索",    "description": "搜索互联网获取最新信息",         "tool_name": "tool_web_search",    "domains": ["media","research","sales","operations"], "required_for": []},
    {"id": "web_read",         "name": "网页阅读",    "description": "抓取并阅读指定 URL 的网页内容",  "tool_name": "tool_web_read",      "domains": ["media","research","sales"],              "required_for": []},
    {"id": "file_read",        "name": "文件读取",    "description": "读取本地文件",                   "tool_name": "tool_file_read",     "domains": ["engineering","research","finance","hr","legal"], "required_for": ["engineering","finance","legal"]},
    {"id": "file_write",       "name": "文件写入",    "description": "创建或更新本地文件",             "tool_name": "tool_file_write",    "domains": ["engineering","media","operations"],      "required_for": ["engineering"]},
    {"id": "bash",             "name": "命令行执行",  "description": "执行系统命令和脚本",             "tool_name": "tool_bash",          "domains": ["engineering","operations","research"],   "required_for": ["engineering"]},
    {"id": "send_message",     "name": "发送消息",    "description": "通过已连接频道发送消息",         "tool_name": "tool_send_message",  "domains": ["sales","hr","customer_service"],         "required_for": []},
    {"id": "image_gen",        "name": "图片生成",    "description": "AI 生成配图、海报、封面图",      "tool_name": "tool_image_gen",     "domains": ["media"],                                 "required_for": []},
    {"id": "content_publish",  "name": "内容发布",    "description": "向小红书、微博等平台发布内容",   "tool_name": "tool_content_publish","domains": ["media"],                                "required_for": ["media"]},
    {"id": "sentiment_monitor","name": "舆情监控",    "description": "监控品牌相关的网络舆情",         "tool_name": "tool_sentiment",     "domains": ["media","customer_service"],              "required_for": []},
    {"id": "email",            "name": "邮件收发",    "description": "发送和读取邮件",                 "tool_name": "tool_email",         "domains": ["sales","hr","customer_service","legal"], "required_for": ["sales"]},
    {"id": "crm_update",       "name": "CRM 更新",    "description": "更新客户信息和跟进记录",         "tool_name": "tool_crm_update",    "domains": ["sales"],                                 "required_for": []},
    {"id": "spreadsheet",      "name": "表格处理",    "description": "读写 Excel/CSV 表格",            "tool_name": "tool_spreadsheet",   "domains": ["finance","operations","hr","research"],  "required_for": ["finance"]},
    {"id": "data_chart",       "name": "数据图表",    "description": "生成数据可视化图表",             "tool_name": "tool_data_chart",    "domains": ["finance","operations","research"],       "required_for": []},
    {"id": "deep_search",      "name": "深度搜索",    "description": "学术级深度搜索，适合研究场景",   "tool_name": "tool_deep_search",   "domains": ["research"],                              "required_for": ["research"]},
    {"id": "summarize",        "name": "文档摘要",    "description": "对长文档进行摘要提炼",           "tool_name": "tool_summarize",     "domains": ["research","hr","legal","operations"],    "required_for": []},
    {"id": "code_review",      "name": "代码审查",    "description": "审查代码质量，发现 bug",         "tool_name": "tool_code_review",   "domains": ["engineering"],                           "required_for": []},
    {"id": "browser_auto",     "name": "浏览器自动化","description": "自动化操作浏览器",              "tool_name": "tool_browser_auto",  "domains": ["engineering","operations","media"],      "required_for": []},
    {"id": "calendar",         "name": "日历管理",    "description": "查看、创建、更新日历事件",       "tool_name": "tool_calendar",      "domains": ["hr","operations","sales"],               "required_for": []},
    {"id": "ticket_manage",    "name": "工单管理",    "description": "创建、更新、关闭客服工单",       "tool_name": "tool_ticket_manage", "domains": ["customer_service"],                      "required_for": ["customer_service"]},
]

TASK_SKILL_KEYWORDS: list[tuple[list[str], str]] = [
    (["搜索","查找","查询","了解","最新","新闻"], "web_search"),
    (["网页","链接","url","网站","官网"], "web_read"),
    (["图片","配图","海报","设计","封面"], "image_gen"),
    (["小红书","微博","公众号","发布","推送"], "content_publish"),
    (["舆情","口碑","评论","监控"], "sentiment_monitor"),
    (["邮件","email","发邮件","邮箱"], "email"),
    (["excel","表格","csv","财务","报表"], "spreadsheet"),
    (["图表","可视化","折线","柱状"], "data_chart"),
    (["代码","开发","程序","bug","脚本"], "bash"),
    (["文件","读取","txt","pdf","docx"], "file_read"),
    (["写入","创建文件","保存"], "file_write"),
    (["学术","论文","深度研究","竞品"], "deep_search"),
    (["摘要","总结","提炼","会议记录"], "summarize"),
    (["日历","会议","提醒","安排"], "calendar"),
    (["工单","客服","投诉","售后"], "ticket_manage"),
    (["浏览器","自动化","截图","点击"], "browser_auto"),
    (["crm","客户跟进","销售阶段"], "crm_update"),
]


class SkillRegistry:

    def __init__(self, data_dir: str | Path):
        self._file = Path(data_dir) / "skills.json"
        Path(data_dir).mkdir(parents=True, exist_ok=True)

    def initialize(self) -> dict[str, Skill]:
        if self._file.exists():
            return self.load_all()
        self._save({})
        return {}

    def load_all(self) -> dict[str, Skill]:
        raw = json.loads(self._file.read_text(encoding="utf-8"))
        result: dict[str, Skill] = {}
        for sid, d in raw.items():
            d["source"] = SkillSource(d["source"])
            d["status"] = SkillStatus(d["status"])
            result[sid] = Skill(**d)
        return result

    def _save(self, skills: dict[str, Skill]) -> None:
        data = {}
        for sid, s in skills.items():
            data[sid] = {
                "id": s.id, "name": s.name, "description": s.description,
                "tool_name": s.tool_name, "domains": s.domains,
                "source": s.source.value, "status": s.status.value,
                "proficiency": s.proficiency, "success_rate": s.success_rate,
                "use_count": s.use_count, "preferred_method": s.preferred_method,
                "failure_cases": s.failure_cases,
                "installed_at": s.installed_at, "updated_at": s.updated_at,
            }
        from anima.utils import atomic_write_json
        atomic_write_json(self._file, data)

    def activate_domain(self, domain: str) -> list[Skill]:
        skills = self.load_all()
        installed: list[Skill] = []
        for spec in SKILL_CATALOG:
            if domain in spec.get("required_for", []) and spec["id"] not in skills:
                skill = self._from_spec(spec, SkillSource.DISCOVERED)
                skills[skill.id] = skill
                installed.append(skill)
                logger.info(f"[Skills] 自动安装: {skill.name}（领域: {domain}）")
        if installed:
            self._save(skills)
        return installed

    def discover_for_task(self, task_text: str) -> list[dict]:
        skills = self.load_all()
        text = task_text.lower()
        needed: list[dict] = []
        seen: set[str] = set()
        for keywords, skill_id in TASK_SKILL_KEYWORDS:
            if skill_id in skills or skill_id in seen:
                continue
            if any(kw in text for kw in keywords):
                spec = next((s for s in SKILL_CATALOG if s["id"] == skill_id), None)
                if spec:
                    needed.append(spec)
                    seen.add(skill_id)
        return needed

    def install(self, skill_id: str, source: SkillSource = SkillSource.DISCOVERED) -> Skill | None:
        spec = next((s for s in SKILL_CATALOG if s["id"] == skill_id), None)
        if not spec:
            return None
        skills = self.load_all()
        if skill_id in skills:
            return skills[skill_id]
        skill = self._from_spec(spec, source)
        skills[skill_id] = skill
        self._save(skills)
        logger.info(f"[Skills] 安装: {skill.name}")
        return skill

    def teach(self, name: str, description: str, tool_name: str,
              domains: list[str], preferred_method: str = "") -> Skill:
        skills = self.load_all()
        sid = f"taught_{int(datetime.utcnow().timestamp())}"
        skill = Skill(id=sid, name=name, description=description, tool_name=tool_name,
                      domains=domains, source=SkillSource.TAUGHT, status=SkillStatus.ACTIVE,
                      proficiency=0.5, success_rate=0.7, preferred_method=preferred_method)
        skills[sid] = skill
        self._save(skills)
        return skill

    def update_after_use(self, skill_id: str, outcome: ExperienceOutcome,
                         owner_satisfaction: float | None = None) -> None:
        skills = self.load_all()
        skill = skills.get(skill_id)
        if not skill:
            return
        skill.use_count += 1
        success_val = {"success": 1.0, "partial": 0.5, "failure": 0.0}[outcome.value]
        skill.success_rate = round(
            (skill.success_rate * (skill.use_count - 1) + success_val) / skill.use_count, 4)
        satisfaction_boost = (owner_satisfaction - 0.5) * 0.04 if owner_satisfaction is not None else 0
        base = {"success": 0.02, "partial": 0.005, "failure": -0.01}[outcome.value]
        skill.proficiency = round(min(1.0, max(0.0, skill.proficiency + base + satisfaction_boost)), 4)
        skill.updated_at = datetime.utcnow().isoformat()
        skills[skill_id] = skill
        self._save(skills)

    def get_active(self) -> list[Skill]:
        return [s for s in self.load_all().values() if s.status == SkillStatus.ACTIVE]

    def get_for_domain(self, domain: str) -> list[Skill]:
        return [s for s in self.load_all().values()
                if domain in s.domains and s.status == SkillStatus.ACTIVE]

    def _from_spec(self, spec: dict, source: SkillSource) -> Skill:
        return Skill(id=spec["id"], name=spec["name"], description=spec["description"],
                     tool_name=spec["tool_name"], domains=spec["domains"],
                     source=source, status=SkillStatus.ACTIVE, proficiency=0.3, success_rate=0.6)
