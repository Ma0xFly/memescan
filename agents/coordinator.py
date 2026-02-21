"""
agents/coordinator.py — 协调者 Agent

多智能体系统的编排中心。接收新代币事件，调度各 Agent 协作完成审计。
核心特点: 自主决策 — 根据中间结果决定是否追加深度检查。

使用流程:
    coordinator = CoordinatorAgent()
    result = await coordinator.run({"token": token})
    report = result["report"]  # AuditReport
"""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from agents.sandbox import SandboxAgent
from agents.auditor import AuditorAgent
from agents.reporter import ReporterAgent
from domain.models import Token


class CoordinatorAgent(BaseAgent):
    """协调者 Agent — 编排 Sandbox → Auditor → Reporter 流程。

    自主决策:
      1. 仿真失败 → 标记高风险，跳过 LLM 分析
      2. 规则引擎发现可疑 → 追加 LLM 深度分析
      3. 一切正常 → 直接出报告
    """

    name = "CoordinatorAgent"

    def __init__(self) -> None:
        self.sandbox = SandboxAgent()
        self.auditor = AuditorAgent()
        self.reporter = ReporterAgent()

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        """完整审计流程: 仿真 → 审计 → 报告。

        task keys:
          token: Token 对象

        返回:
          report: AuditReport
          md_content: str
          file_path: str
          decisions: list[str]  (Agent 决策链路记录)
        """
        token: Token = task["token"]
        decisions: list[str] = []

        self.log(f"开始审计代币: {token.symbol or '???'} ({token.address[:10]}…)")

        # ── Step 1: 沙盒仿真 ────────────────────────────────
        self.log("Step 1/3 — 沙盒仿真")
        sandbox_result = await self.sandbox.run({"token": token})
        simulation = sandbox_result.get("simulation")

        if simulation is None:
            # 仿真完全失败 — 创建一个空的仿真结果
            self.log("仿真失败 — 跳过后续分析")
            decisions.append("simulation_failed → skip_deep_analysis")
            from domain.models import SimulationResult
            simulation = SimulationResult(
                can_buy=False,
                can_sell=False,
                buy_tax_pct=0.0,
                sell_tax_pct=0.0,
                buy_gas=0,
                sell_gas=0,
                is_honeypot=False,
            )

        # ── Step 2: 审计分析 ────────────────────────────────
        self.log("Step 2/3 — 审计分析")
        audit_result = await self.auditor.run({
            "token": token,
            "simulation": simulation,
        })
        report = audit_result["report"]
        decisions.append(f"auditor_decision: {audit_result['decision']}")

        if audit_result.get("llm_analysis"):
            decisions.append("llm_deep_analysis_completed")

        # ── Step 3: 生成报告 ────────────────────────────────
        self.log("Step 3/3 — 生成报告")
        reporter_result = await self.reporter.run({"report": report})

        self.log(
            f"审计完成 — 评分: {report.risk_score:.0f}/100, "
            f"标签: {[f.value for f in report.risk_flags]}, "
            f"决策链: {decisions}"
        )

        return {
            "report": report,
            "md_content": reporter_result["md_content"],
            "file_path": reporter_result["file_path"],
            "decisions": decisions,
        }

    async def decide(self, context: dict[str, Any]) -> str:
        """协调者的全局决策 (目前委托给 AuditorAgent)。"""
        return "delegate_to_auditor"
