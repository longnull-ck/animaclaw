"""
Anima — Identity Engine（身份引擎）
"""

from __future__ import annotations

import json
import uuid
import logging
from datetime import datetime
from pathlib import Path

from anima.models import Identity, Personality

logger = logging.getLogger("anima.identity")

DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "media":            ["小红书","微博","抖音","内容","文案","推广","传媒","公众号","视频","直播","品牌","营销"],
    "sales":            ["销售","客户","订单","报价","成交","跟进","crm","业绩","签约","谈判"],
    "finance":          ["财务","报销","发票","账期","利润","成本","预算","税务","核算","资金","对账"],
    "operations":       ["运营","流程","sop","效率","优化","数据","报表","复盘","kpi","okr"],
    "hr":               ["招聘","入职","离职","薪资","绩效","培训","考勤","人员","面试","员工"],
    "engineering":      ["代码","开发","bug","部署","接口","数据库","架构","测试","程序","服务器","api"],
    "research":         ["研究","分析","报告","竞品","调研","数据分析","洞察","趋势","市场调查"],
    "legal":            ["合同","法务","合规","知识产权","协议","条款","风险","版权","专利"],
    "logistics":        ["物流","仓储","供应链","发货","库存","采购","配送","仓库","货物"],
    "customer_service": ["客服","投诉","售后","用户反馈","退款","工单","满意度","服务"],
}

DEFAULT_CORE_VALUES = [
    "主动完成任务，遇到问题及时汇报",
    "保护公司信息安全，不泄露敏感数据",
    "诚实汇报结果，包括失败和不确定",
    "尊重主人的最终决策权",
    "不断学习，遇到不会的主动安装新能力",
]

DOMAIN_LABELS: dict[str, str] = {
    "media": "传媒/内容/营销", "sales": "销售/客户", "finance": "财务",
    "operations": "运营", "hr": "人力资源", "engineering": "技术研发",
    "research": "研究分析", "legal": "法务合规",
    "logistics": "物流供应链", "customer_service": "客户服务",
}


class IdentityEngine:

    def __init__(self, data_dir: str | Path):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._identity_file = self._data_dir / "identity.json"
        self._soul_file = self._data_dir / "SOUL.md"

    def initialize(self, name: str, owner_name: str, owner_id: str,
                   company_description: str, core_values: list[str] | None = None,
                   language: str = "zh-CN") -> Identity:
        if self._identity_file.exists():
            return self.load()

        identity = Identity(
            id=str(uuid.uuid4()), name=name, owner_id=owner_id,
            owner_name=owner_name, company_description=company_description,
            core_values=core_values or DEFAULT_CORE_VALUES,
            personality=Personality(language=language),
            active_domains=[],
        )
        self.save(identity)
        self._write_soul(identity)
        return identity

    def load(self) -> Identity:
        raw = json.loads(self._identity_file.read_text(encoding="utf-8"))
        p = raw.pop("personality", {})
        raw["personality"] = Personality(**p)
        return Identity(**raw)

    def save(self, identity: Identity) -> None:
        data = {
            "id": identity.id, "name": identity.name,
            "owner_id": identity.owner_id, "owner_name": identity.owner_name,
            "company_description": identity.company_description,
            "core_values": identity.core_values,
            "personality": {
                "proactivity": identity.personality.proactivity,
                "risk_tolerance": identity.personality.risk_tolerance,
                "language": identity.personality.language,
                "communication_style": identity.personality.communication_style,
            },
            "active_domains": identity.active_domains,
            "version": identity.version,
            "created_at": identity.created_at,
            "updated_at": identity.updated_at,
        }
        self._identity_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def infer_domains(self, identity: Identity, task_text: str) -> list[str]:
        text = task_text.lower()
        newly: list[str] = []
        for domain, keywords in DOMAIN_KEYWORDS.items():
            if domain not in identity.active_domains and any(kw.lower() in text for kw in keywords):
                identity.active_domains.append(domain)
                newly.append(domain)
        if newly:
            identity.updated_at = datetime.utcnow().isoformat()
            self.save(identity)
        return newly

    def update_personality(self, identity: Identity,
                           proactivity_delta: float = 0.0,
                           risk_tolerance_delta: float = 0.0) -> Identity:
        identity.personality.proactivity = min(1.0, max(0.0, identity.personality.proactivity + proactivity_delta))
        identity.personality.risk_tolerance = min(1.0, max(0.0, identity.personality.risk_tolerance + risk_tolerance_delta))
        identity.version += 1
        identity.updated_at = datetime.utcnow().isoformat()
        self.save(identity)
        self._write_soul(identity)
        return identity

    def build_identity_prompt(self, identity: Identity) -> str:
        domains_str = (
            "、".join(DOMAIN_LABELS.get(d, d) for d in identity.active_domains)
            if identity.active_domains else "尚未激活特定领域（按需自动扩展）"
        )
        risk_desc = ("敢于决断" if identity.personality.risk_tolerance > 0.6
                     else "谨慎决策" if identity.personality.risk_tolerance > 0.3
                     else "重要事项请示后执行")
        return f"""# 我是谁
我叫 {identity.name}，是 {identity.owner_name} 的 AI 员工。
我服务于：{identity.company_description}

# 我的能力范围
我是全能型员工，可承担公司所有部门的工作。
当前已激活领域：{domains_str}
遇到新领域任务时，我会主动学习并安装对应技能。

# 我的行为准则（永远不可违背）
{chr(10).join(f"{i+1}. {v}" for i, v in enumerate(identity.core_values))}

# 我的工作风格
- 主动程度：{int(identity.personality.proactivity * 100)}%
- 决策风格：{risk_desc}
- 工作语言：{identity.personality.language}

# 当前版本
v{identity.version}，持续学习进化中。""".strip()

    def _write_soul(self, identity: Identity) -> None:
        content = f"""# {identity.name} — SOUL.md

## 基本信息
- 姓名：{identity.name}
- 服务对象：{identity.owner_name}
- 公司业务：{identity.company_description}
- 版本：v{identity.version}

## 核心价值观
{chr(10).join(f"- {v}" for v in identity.core_values)}

## 已激活部门领域
{chr(10).join(f"- {DOMAIN_LABELS.get(d, d)}" for d in identity.active_domains) or "- 暂无（按需自动激活）"}

## 性格参数
- 主动程度：{int(identity.personality.proactivity * 100)}%
- 风险偏好：{int(identity.personality.risk_tolerance * 100)}%
"""
        self._soul_file.write_text(content, encoding="utf-8")
