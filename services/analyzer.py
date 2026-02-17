"""
services/analyzer.py — 规则引擎 + LLM 分析服务

通过可配置的风险规则评估仿真结果，生成 AuditReport。
可选的 LLM 叙述摘要作为补充。

规则引擎同步执行（纯计算），LLM 调用异步执行（HTTP）。
两者均由 `analyze()` 方法统一编排。
"""

from __future__ import annotations

from loguru import logger

from core.config import get_settings
from domain.models import AuditReport, RiskFlag, SimulationResult, Token


class AnalysisService:
    """基于仿真数据生成安全审计报告。

    当前使用规则引擎进行评分。LLM 集成（RAG + 合约源码分析）
    作为后续扩展计划。
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    async def analyze(
        self, token: Token, simulation: SimulationResult
    ) -> AuditReport:
        """执行完整的分析流水线并返回结构化报告。

        参数:
            token: 已发现的代币元数据。
            simulation: 买卖仿真结果。

        返回:
            包含风险评分、标签和可选 LLM 叙述的 AuditReport。
        """
        flags = self._evaluate_rules(simulation)
        score = self._compute_score(flags, simulation)
        summary = await self._generate_summary(token, simulation, flags, score)

        report = AuditReport(
            token=token,
            simulation=simulation,
            risk_score=score,
            risk_flags=flags,
            llm_summary=summary,
        )

        logger.info(
            "审计完成: {} — 评分={:.1f}, 标签={}",
            token.address[:10],
            score,
            [f.value for f in flags],
        )
        return report

    # ── 规则引擎 ────────────────────────────────────────────────

    def _evaluate_rules(self, sim: SimulationResult) -> list[RiskFlag]:
        """将确定性风险规则应用于仿真结果。"""
        flags: list[RiskFlag] = []

        # 蜜罐检测
        if sim.is_honeypot:
            flags.append(RiskFlag.HONEYPOT)

        if sim.can_buy and not sim.can_sell:
            flags.append(RiskFlag.CANNOT_SELL)

        # 税率分析
        threshold = self._settings.high_tax_threshold_pct
        if sim.buy_tax_pct > threshold:
            flags.append(RiskFlag.HIGH_BUY_TAX)
        if sim.sell_tax_pct > threshold:
            flags.append(RiskFlag.HIGH_SELL_TAX)

        # Gas 异常（极高的 Gas 通常意味着链上陷阱）
        if sim.buy_gas > 500_000:
            flags.append(RiskFlag.UNKNOWN_RISK)

        return flags

    def _compute_score(
        self, flags: list[RiskFlag], sim: SimulationResult
    ) -> float:
        """根据标签和原始指标计算 0-100 的风险评分。

        评分权重（越高越危险）：
          - HONEYPOT / CANNOT_SELL → 40 分
          - HIGH_*_TAX → 15 分
          - HIDDEN_MINT → 25 分
          - 其他标签 → 10 分
        """
        weight_map: dict[RiskFlag, float] = {
            RiskFlag.HONEYPOT: 40.0,
            RiskFlag.CANNOT_SELL: 40.0,
            RiskFlag.HIGH_BUY_TAX: 15.0,
            RiskFlag.HIGH_SELL_TAX: 15.0,
            RiskFlag.HIDDEN_MINT: 25.0,
            RiskFlag.OWNERSHIP_NOT_RENOUNCED: 10.0,
            RiskFlag.PROXY_CONTRACT: 10.0,
            RiskFlag.BLACKLIST_FUNCTION: 10.0,
            RiskFlag.TRANSFER_PAUSABLE: 10.0,
            RiskFlag.ANTI_WHALE_LIMIT: 5.0,
            RiskFlag.UNKNOWN_RISK: 10.0,
        }

        raw = sum(weight_map.get(f, 5.0) for f in flags)

        # 附加分：如果仿真连买入都无法完成，则属于最高风险。
        if not sim.can_buy:
            raw += 30.0

        return min(raw, 100.0)

    # ── LLM 集成（占位实现）─────────────────────────────────────

    async def _generate_summary(
        self,
        token: Token,
        sim: SimulationResult,
        flags: list[RiskFlag],
        score: float,
    ) -> str:
        """生成人类可读的分析摘要。

        TODO: 替换为基于 RAG 的 LLM 流水线：
          1. 从 Etherscan 获取已验证的合约源码。
          2. 对源码进行分块和向量化。
          3. 结合仿真上下文 + 源码块查询 LLM。
        """
        if not flags:
            return (
                f"代币 {token.symbol} ({token.address[:10]}…) 通过了基本仿真检查。"
                f"未检测到关键风险。风险评分: {score:.1f}/100。"
            )

        flag_labels = ", ".join(f.value for f in flags)
        honeypot_warning = ""
        if RiskFlag.HONEYPOT in flags or RiskFlag.CANNOT_SELL in flags:
            honeypot_warning = (
                " ⚠️ 严重警告: 该代币具有蜜罐特征 —— "
                "用户购买后可能无法卖出。"
            )

        return (
            f"代币 {token.symbol} ({token.address[:10]}…) 触发标签: [{flag_labels}]。"
            f"风险评分: {score:.1f}/100。{honeypot_warning} "
            f"买入税: {sim.buy_tax_pct:.1f}%，卖出税: {sim.sell_tax_pct:.1f}%。"
            f"买入 Gas: {sim.buy_gas}，卖出 Gas: {sim.sell_gas}。"
        )
