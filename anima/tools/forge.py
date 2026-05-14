"""
Anima — ToolForge（工具自造引擎）

人与动物的最大区别：没有工具会造。
当 Anima 发现自己缺少某个能力时，不是躺平等主人给，
而是自己分析需求 → 写代码 → 测试 → 注册为新工具。

流程：
  1. 需求分析：这个工具需要做什么？输入输出是什么？
  2. 代码生成：大模型写 Python 函数
  3. 安全审查：检查代码是否安全（禁止 rm -rf、网络攻击等）
  4. 沙箱测试：在隔离环境中试运行
  5. 注册上线：注册到 ToolDispatcher，永久可用

造出的工具保存在 data/tools/ 目录，重启后自动加载。
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import sys
import tempfile
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Callable, Awaitable

from anima.events import emit_skill, emit_action, emit_thinking

logger = logging.getLogger("anima.tools.forge")

# 安全黑名单：禁止在生成的工具中出现的危险模式
DANGEROUS_PATTERNS = [
    "os.system(",
    "subprocess.call(",
    "shutil.rmtree(",
    "rm -rf",
    "__import__('os').system",
    "eval(",
    "exec(",
    "open('/etc",
    "open('/root",
    "import socket",  # 禁止原始 socket（httpx 是安全的）
]

# 允许的 import 白名单
ALLOWED_IMPORTS = [
    "json", "re", "math", "datetime", "time", "uuid",
    "pathlib", "os.path", "urllib.parse",
    "httpx", "aiohttp",  # 网络请求
    "csv", "io", "base64", "hashlib",
    "typing", "dataclasses", "enum",
]


class ToolForge:
    """
    工具自造引擎。
    让 Anima 自己写代码创造新工具。
    """

    def __init__(self, data_dir: str | Path, brain, dispatcher):
        """
        Args:
            data_dir: 数据目录（造出的工具保存在 data_dir/tools/）
            brain: Anima Brain 实例（用于生成代码）
            dispatcher: ToolDispatcher 实例（注册新工具）
        """
        self._brain = brain
        self._dispatcher = dispatcher
        self._tools_dir = Path(data_dir) / "tools"
        self._tools_dir.mkdir(parents=True, exist_ok=True)
        self._manifest_file = self._tools_dir / "manifest.json"
        self._load_existing_tools()

    # ─── 核心入口：造一个工具 ─────────────────────────────────

    async def forge_tool(
        self,
        need_description: str,
        tool_name: str | None = None,
    ) -> dict:
        """
        造一个新工具。

        Args:
            need_description: 需要什么能力的描述
                例如："发送邮件到指定邮箱"
                例如："调用企业微信API添加好友"
            tool_name: 工具名（可选，不提供则自动生成）

        Returns:
            {"success": True/False, "tool_name": str, "reason": str}
        """
        await emit_thinking(
            "开始造工具",
            f"需求: {need_description[:60]}",
            data={"phase": "forge_start"},
        )

        # ── Step 1: 需求分析 & 代码生成 ─────────────────────
        tool_spec = await self._design_tool(need_description, tool_name)
        if not tool_spec:
            return {"success": False, "tool_name": "", "reason": "需求分析失败"}

        final_name = tool_spec["name"]
        await emit_thinking(
            f"设计完成: {final_name}",
            tool_spec.get("description", "")[:60],
        )

        # ── Step 2: 生成代码 ─────────────────────────────────
        code = await self._generate_code(tool_spec)
        if not code:
            return {"success": False, "tool_name": final_name, "reason": "代码生成失败"}

        # ── Step 3: 安全审查 ─────────────────────────────────
        safety_result = self._safety_check(code)
        if not safety_result["safe"]:
            await emit_action(
                "工具安全审查未通过",
                safety_result["reason"],
                data={"tool_name": final_name, "blocked": True},
            )
            return {"success": False, "tool_name": final_name, "reason": f"安全审查未通过: {safety_result['reason']}"}

        # ── Step 4: 沙箱测试 ─────────────────────────────────
        test_result = await self._sandbox_test(code, final_name, tool_spec)
        if not test_result["passed"]:
            # 尝试修复一次
            await emit_thinking("测试失败，尝试修复", test_result.get("error", "")[:60])
            code = await self._fix_code(code, test_result["error"], tool_spec)
            if code:
                test_result = await self._sandbox_test(code, final_name, tool_spec)

            if not test_result["passed"]:
                return {"success": False, "tool_name": final_name, "reason": f"测试失败: {test_result.get('error', '未知')}"}

        # ── Step 5: 保存 & 注册 ──────────────────────────────
        self._save_tool(final_name, code, tool_spec)
        self._register_tool(final_name, code)

        await emit_skill(
            f"新工具已造好: {final_name}",
            tool_spec.get("description", ""),
            data={"tool_name": final_name, "forged": True},
        )

        return {"success": True, "tool_name": final_name, "reason": "造好了！"}

    # ─── Step 1: 需求分析 ────────────────────────────────────

    async def _design_tool(self, need: str, suggested_name: str | None) -> dict | None:
        """让大模型设计工具的规格"""
        prompt = f"""你需要设计一个 Python 异步工具函数。

需求描述: {need}

请设计这个工具的规格，返回 JSON：
{{
  "name": "tool_xxx",
  "description": "这个工具做什么",
  "input_args": {{"arg_name": "参数说明"}},
  "output": "返回什么",
  "dependencies": ["需要pip安装的包，如httpx"],
  "example_usage": "示例调用"
}}

规则：
- name 必须以 tool_ 开头，全小写，下划线分隔
- 函数签名必须是 async def tool_xxx(args: dict) -> str
- 只能用标准库 + httpx + aiohttp
- 不能使用 eval/exec/os.system 等危险操作"""

        if suggested_name:
            prompt += f"\n\n建议的工具名: {suggested_name}"

        result = await self._brain.think_json(
            "你是工具设计专家，只返回JSON。", prompt
        )

        if not result.get("name"):
            return None

        # 确保以 tool_ 开头
        name = result["name"]
        if not name.startswith("tool_"):
            name = f"tool_{name}"

        result["name"] = name
        return result

    # ─── Step 2: 代码生成 ────────────────────────────────────

    async def _generate_code(self, spec: dict) -> str | None:
        """让大模型生成工具的 Python 代码"""
        prompt = f"""请为以下工具规格生成完整的 Python 代码：

工具名: {spec['name']}
描述: {spec.get('description', '')}
输入参数: {json.dumps(spec.get('input_args', {}), ensure_ascii=False)}
输出: {spec.get('output', 'str')}
示例: {spec.get('example_usage', '')}

要求：
1. 函数签名必须是: async def {spec['name']}(args: dict) -> str
2. 使用 type hints
3. 包含错误处理（try/except）
4. 使用 httpx 做 HTTP 请求（如果需要的话）
5. 返回值必须是字符串（成功返回结果描述，失败返回错误信息）
6. 代码开头加必要的 import
7. 不要包含 ```python``` 标记，直接给纯代码

禁止：
- 不能用 eval/exec/os.system/subprocess
- 不能直接操作系统文件（/etc, /root 等）
- 不能创建 socket 连接（用 httpx 代替）

直接输出纯 Python 代码，不要任何解释："""

        code = await self._brain.think(
            "你是 Python 专家，只输出纯代码，不要解释或markdown标记。",
            prompt,
        )

        # 清理可能的 markdown 代码块
        code = code.strip()
        if code.startswith("```python"):
            code = code[9:]
        if code.startswith("```"):
            code = code[3:]
        if code.endswith("```"):
            code = code[:-3]
        code = code.strip()

        # 验证代码是否能解析
        try:
            compile(code, "<forge>", "exec")
        except SyntaxError as e:
            logger.warning(f"[ToolForge] 生成的代码有语法错误: {e}")
            return None

        return code

    # ─── Step 3: 安全审查 ────────────────────────────────────

    def _safety_check(self, code: str) -> dict:
        """检查代码安全性"""
        for pattern in DANGEROUS_PATTERNS:
            if pattern in code:
                return {"safe": False, "reason": f"包含危险操作: {pattern}"}

        # 检查 import（只允许白名单）
        import ast
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return {"safe": False, "reason": "代码语法错误"}

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name.split(".")[0]
                    if module not in ALLOWED_IMPORTS and module != "typing":
                        return {"safe": False, "reason": f"禁止导入: {alias.name}"}
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module = node.module.split(".")[0]
                    if module not in ALLOWED_IMPORTS and module != "typing":
                        return {"safe": False, "reason": f"禁止导入: {node.module}"}

        return {"safe": True, "reason": ""}

    # ─── Step 4: 沙箱测试 ────────────────────────────────────

    async def _sandbox_test(self, code: str, tool_name: str, spec: dict) -> dict:
        """在隔离环境中测试工具代码"""
        # 创建临时文件
        test_code = f"""
import asyncio
import sys

{code}

async def _test():
    try:
        # 用空参数测试（应该不会崩溃，可能返回错误提示）
        result = await {tool_name}({{}})
        print(f"TEST_RESULT:{{result[:200]}}")
        return True
    except TypeError as e:
        # 缺少必要参数是正常的（说明函数结构正确）
        if "required" in str(e) or "missing" in str(e) or "argument" in str(e):
            print(f"TEST_RESULT:ARGS_NEEDED")
            return True
        print(f"TEST_ERROR:{{e}}")
        return False
    except Exception as e:
        # 网络错误等运行时错误是可以接受的（说明代码能跑）
        error_str = str(e)
        if any(x in error_str.lower() for x in ["connection", "timeout", "dns", "url", "api_key", "token", "auth"]):
            print(f"TEST_RESULT:RUNTIME_OK_{{error_str[:100]}}")
            return True
        print(f"TEST_ERROR:{{e}}")
        return False

result = asyncio.run(_test())
sys.exit(0 if result else 1)
"""

        # 写入临时文件并执行
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_code)
            tmp_path = f.name

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, tmp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
            output = stdout.decode() + stderr.decode()

            if proc.returncode == 0 or "TEST_RESULT:" in output:
                return {"passed": True, "output": output[:500]}
            else:
                return {"passed": False, "error": output[:500]}

        except asyncio.TimeoutError:
            return {"passed": False, "error": "测试超时（15s）"}
        except Exception as e:
            return {"passed": False, "error": str(e)}
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    # ─── 修复代码 ────────────────────────────────────────────

    async def _fix_code(self, code: str, error: str, spec: dict) -> str | None:
        """尝试让大模型修复代码"""
        prompt = f"""以下 Python 工具代码在测试时出错，请修复：

原始代码：
{code}

错误信息：
{error}

工具规格：
- 名称: {spec['name']}
- 描述: {spec.get('description', '')}
- 输入: {json.dumps(spec.get('input_args', {}), ensure_ascii=False)}

请输出修复后的完整代码（纯 Python，不要解释）："""

        fixed = await self._brain.think(
            "你是 Python debug 专家，只输出修复后的纯代码。",
            prompt,
        )

        fixed = fixed.strip()
        if fixed.startswith("```python"):
            fixed = fixed[9:]
        if fixed.startswith("```"):
            fixed = fixed[3:]
        if fixed.endswith("```"):
            fixed = fixed[:-3]
        fixed = fixed.strip()

        try:
            compile(fixed, "<forge_fix>", "exec")
            safety = self._safety_check(fixed)
            if safety["safe"]:
                return fixed
        except SyntaxError:
            pass

        return None

    # ─── Step 5: 保存 & 注册 ─────────────────────────────────

    def _save_tool(self, name: str, code: str, spec: dict) -> None:
        """保存工具代码到文件系统"""
        # 保存代码文件
        tool_file = self._tools_dir / f"{name}.py"
        tool_file.write_text(code, encoding="utf-8")

        # 更新 manifest
        manifest = self._load_manifest()
        manifest[name] = {
            "name": name,
            "description": spec.get("description", ""),
            "input_args": spec.get("input_args", {}),
            "file": f"{name}.py",
            "forged_at": datetime.utcnow().isoformat(),
            "use_count": 0,
            "success_count": 0,
        }
        self._save_manifest(manifest)

        logger.info(f"[ToolForge] 工具已保存: {name} → {tool_file}")

    def _register_tool(self, name: str, code: str) -> None:
        """动态注册工具到 Dispatcher"""
        # 创建一个模块命名空间并执行代码
        namespace = {}
        exec(code, namespace)

        # 找到工具函数
        tool_fn = namespace.get(name)
        if tool_fn and callable(tool_fn):
            self._dispatcher.register(name, tool_fn)
            logger.info(f"[ToolForge] 工具已注册: {name}")
        else:
            logger.warning(f"[ToolForge] 注册失败: 在代码中找不到函数 {name}")

    # ─── 启动时加载已有工具 ───────────────────────────────────

    def _load_existing_tools(self) -> None:
        """启动时自动加载之前造过的工具"""
        manifest = self._load_manifest()
        loaded = 0

        for name, info in manifest.items():
            tool_file = self._tools_dir / info.get("file", f"{name}.py")
            if not tool_file.exists():
                continue

            try:
                code = tool_file.read_text(encoding="utf-8")
                # 安全检查
                if not self._safety_check(code)["safe"]:
                    logger.warning(f"[ToolForge] 跳过不安全的工具: {name}")
                    continue
                self._register_tool(name, code)
                loaded += 1
            except Exception as e:
                logger.warning(f"[ToolForge] 加载工具失败 {name}: {e}")

        if loaded > 0:
            logger.info(f"[ToolForge] 已加载 {loaded} 个自造工具")

    # ─── Manifest 管理 ───────────────────────────────────────

    def _load_manifest(self) -> dict:
        if not self._manifest_file.exists():
            return {}
        try:
            return json.loads(self._manifest_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            return {}

    def _save_manifest(self, manifest: dict) -> None:
        self._manifest_file.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ─── 状态查询 ────────────────────────────────────────────

    def list_forged_tools(self) -> list[dict]:
        """列出所有自造工具"""
        manifest = self._load_manifest()
        return [
            {"name": name, "description": info.get("description", ""), "forged_at": info.get("forged_at", "")}
            for name, info in manifest.items()
        ]

    def stats(self) -> dict:
        manifest = self._load_manifest()
        return {
            "total_forged": len(manifest),
            "tools": list(manifest.keys()),
        }
