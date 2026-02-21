"""
agents/auditor.py — 审计者 Agent

封装 AnalysisService + LLM，是 V2 的核心智能体。
具备自主决策能力: 根据初步检查结果决定是否追加 LLM 深度分析。

LLM 后端: 智谱 GLM (兼容 OpenAI API 格式)
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from agents.base import BaseAgent
from core.config import get_settings
from services.analyzer import AnalysisService
from services.etherscan import EtherscanService
from domain.models import AuditReport, RiskFlag, SimulationResult, Token


class AuditorAgent(BaseAgent):
    """审计者 Agent — 综合规则引擎 + LLM 做风险判断。

    双模式:
      standard     — 规则引擎评分 (快速)
      deep_analysis — 拉取源码 + LLM 分析 (精准但慢)

    自主决策:
      - 发现 HIDDEN_MINT 但评分不高 → 追加深度分析
      - 仿真正常但 ownership 未放弃 → 追加深度分析
    """

    name = "AuditorAgent"

    def __init__(self) -> None:
        self._analyzer = AnalysisService()
        self._etherscan = EtherscanService()
        self._settings = get_settings()
        self._llm_client = None

    def _get_llm_client(self):
        """懒加载 LLM 客户端。"""
        if self._llm_client is None and self._settings.llm_api_key:
            from openai import AsyncOpenAI
            self._llm_client = AsyncOpenAI(
                api_key=self._settings.llm_api_key,
                base_url=self._settings.llm_base_url,
            )
        return self._llm_client

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        """执行审计。

        task keys:
          token: Token 对象
          simulation: SimulationResult 对象
          mode: "standard" | "deep_analysis"  (默认 standard)

        返回:
          report: AuditReport
          llm_analysis: str | None  (深度分析结果)
          decision: str  (Agent 的决策)
        """
        token: Token = task["token"]
        simulation: SimulationResult = task["simulation"]
        mode = task.get("mode", "standard")

        # 标准审计: 规则引擎
        report = await self._analyzer.analyze(token, simulation)

        result = {
            "report": report,
            "llm_analysis": None,
            "decision": "standard_complete",
        }

        # 自主决策: 是否需要深度分析
        decision = await self.decide({
            "flags": [f.value for f in report.risk_flags],
            "score": report.risk_score,
            "can_sell": simulation.can_sell,
            "mode": mode,
        })

        result["decision"] = decision

        if decision == "need_deep_analysis" or mode == "deep_analysis":
            self.log("触发深度分析 — 正在获取合约源码并调用 LLM")
            llm_analysis = await self._deep_analyze(token, simulation, report)
            result["llm_analysis"] = llm_analysis

            # 将 LLM 分析追加到报告的 llm_summary
            if llm_analysis:
                enhanced_summary = (
                    f"{report.llm_summary}\n\n"
                    f"🤖 **AI 深度分析 (GLM)**:\n{llm_analysis}"
                )
                # 创建增强版报告
                result["report"] = AuditReport(
                    token=report.token,
                    simulation=report.simulation,
                    risk_score=report.risk_score,
                    risk_flags=report.risk_flags,
                    llm_summary=enhanced_summary,
                )

        return result

    async def decide(self, context: dict[str, Any]) -> str:
        """自主决策: 是否需要追加 LLM 深度分析。"""
        flags = context.get("flags", [])
        score = context.get("score", 0)
        can_sell = context.get("can_sell", True)
        mode = context.get("mode", "standard")

        # 如果明确要求深度分析
        if mode == "deep_analysis":
            return "need_deep_analysis"

        # 没有 LLM API Key → 无法做深度分析
        if not self._settings.llm_api_key:
            return "done"

        # 决策规则:
        # 1. 发现 HIDDEN_MINT 但评分不高 → 需要确认
        if "HIDDEN_MINT" in flags and score < 50:
            return "need_deep_analysis"

        # 2. 仿真正常但 ownership 未放弃 → 追加分析
        if can_sell and "OWNERSHIP_NOT_RENOUNCED" in flags:
            return "need_deep_analysis"

        # 3. 高风险但原因不明 → 追加分析
        if score >= 60 and "UNKNOWN_RISK" in flags:
            return "need_deep_analysis"

        return "done"

    async def _deep_analyze(
        self,
        token: Token,
        simulation: SimulationResult,
        report: AuditReport,
    ) -> str | None:
        """调用 LLM (GLM) 对合约源码进行深度分析。"""
        client = self._get_llm_client()
        if not client:
            self.log("未配置 LLM API Key，跳过深度分析")
            return None

        # 1. 尝试获取合约源码
        source_code = None
        try:
            source_code = await self._etherscan.get_contract_source(
                token.address
            )
        except Exception as e:
            self.log_error(f"获取源码失败: {e}")

        # 2. 构建 Prompt
        flags_str = ", ".join(f.value for f in report.risk_flags)

        if source_code:
            truncated = source_code[:8000]
            prompt = (
                "你是一名资深智能合约安全审计专家。\n"
                "请分析以下 ERC-20 代币合约源码，重点关注:\n"
                "1. 是否有隐藏的 mint/增发函数\n"
                "2. owner 是否有异常权限 (修改税率、暂停转账、黑名单)\n"
                "3. transfer 函数是否有隐藏逻辑\n"
                "4. 是否有可疑的 proxy/delegatecall\n\n"
                f"代币地址: {token.address}\n"
                f"仿真结果: 可买={simulation.can_buy}, 可卖={simulation.can_sell}\n"
                f"买入税: {simulation.buy_tax_pct:.1f}%, "
                f"卖出税: {simulation.sell_tax_pct:.1f}%\n"
                f"已触发标签: [{flags_str}]\n"
                f"风险评分: {report.risk_score:.1f}/100\n\n"
                f"合约源码 (节选):\n```solidity\n{truncated}\n```\n\n"
                "请用中文回答，300 字以内。"
            )
        else:
            prompt = (
                "你是一名资深智能合约安全审计专家。\n"
                "以下代币合约未开源，无法获取源码。请根据链上检查结果给出风险评估:\n\n"
                f"代币地址: {token.address}\n"
                f"代币符号: {token.symbol or '未知'}\n"
                f"仿真结果: 可买={simulation.can_buy}, 可卖={simulation.can_sell}\n"
                f"买入税: {simulation.buy_tax_pct:.1f}%, "
                f"卖出税: {simulation.sell_tax_pct:.1f}%\n"
                f"已触发标签: [{flags_str}]\n"
                f"风险评分: {report.risk_score:.1f}/100\n\n"
                "请用中文分析这些指标意味着什么风险，200 字以内。"
            )

        # 3. 调用 GLM API
        try:
            response = await client.chat.completions.create(
                model=self._settings.llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是 MemeScan AI 安全审计助手，专门分析 Memecoin 合约安全性。",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=500,
                temperature=0.3,
            )
            result = response.choices[0].message.content.strip()
            self.log(f"LLM 分析完成 ({len(result)} 字)")
            return result
        except Exception as e:
            self.log_error(f"LLM 调用失败: {e}")
            return f"AI 分析服务暂时不可用: {e}"
