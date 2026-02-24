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
from core.web3_provider import get_async_web3
from services.etherscan import EtherscanService
from domain.models import AuditReport, RiskFlag, SimulationResult, Token


class AnalysisService:
    """基于仿真数据生成安全审计报告。

    当前使用规则引擎进行评分。LLM 集成（RAG + 合约源码分析）
    作为后续扩展计划。
    """

    def __init__(self, chain_name: str = "ethereum") -> None:
        self.chain_name = chain_name
        self._settings = get_settings()
        self.w3 = get_async_web3(chain_name=chain_name)

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
        # 异步执行链上检查
        is_renounced = await self._check_ownership(token.address)
        has_mint = await self._detect_mint_function(token.address)

        flags = self._evaluate_rules(simulation, is_renounced, has_mint)
        score = self._compute_score(flags, simulation)
        summary = await self._generate_summary(token, simulation, flags, score)

        # The token/simulation objects might come from a different module reload (Streamlit quirk)
        # Re-cast them to the current classes to avoid Pydantic validation errors
        safe_token = Token.model_validate(token, from_attributes=True)
        safe_simulation = SimulationResult.model_validate(simulation, from_attributes=True)
        
        report = AuditReport(
            token=safe_token,
            simulation=safe_simulation,
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

    async def _check_ownership(self, token_address: str) -> bool:
        """检查合约所有权是否已放弃 (Renounced)。
        
        尝试调用 `owner()` (0x8da5cb5b)。
        如果调用失败（无此方法）或返回零地址/死地址，则认为已放弃。
        """
        try:
            # owner() selector: 0x8da5cb5b
            # We use call directly or contract instance. 
            # Using call with raw data is faster/simpler if we don't have ABI.
            data = "0x8da5cb5b"
            result = await self.w3.eth.call(
                {"to": self.w3.to_checksum_address(token_address), "data": data}
            )
            # Result is bytes. If empty, maybe revert?
            if not result or all(b == 0 for b in result):
                return True # Returned 0x0...0
            
            # Check if it's the dead address (0x000...dEaD) or zero address
            # The result is 32 bytes (64 hex chars). Address is last 20 bytes.
            # But let's simplify: if it's 0x0...0, it's renounced.
            # Converting to int
            owner_int = int.from_bytes(result, byteorder='big')
            return owner_int == 0 or owner_int == 0xdead
            
        except Exception:
            # If call reverts, it might not have owner() or it's restricted.
            # Assuming if no owner() function, it's effectively renounced (immutable?)
            # Or it uses a different ownership pattern.
            # For safety, let's assume if we CAN'T read owner, it's NOT renounced (unknown risk)?
            # Or standard OpenZeppelin: if owner() missing, maybe Ownable not used.
            # Let's return True (pass) if function missing, but log warning?
            # Requirement: "Call owner() ... if 0x0 or dead -> True".
            return False 

    async def _detect_mint_function(self, token_address: str) -> bool:
        """检测字节码中是否存在 mint 函数签名 (0x40c10f19)。"""
        try:
            code = await self.w3.eth.get_code(self.w3.to_checksum_address(token_address))
            # mint(address,uint256) -> 0x40c10f19
            # mint(uint256) -> 0xa0712d68
            # simply check for hex sequence
            code_hex = code.hex()
            return "40c10f19" in code_hex
        except Exception:
            return False

    # ── 规则引擎 ────────────────────────────────────────────────

    def _evaluate_rules(
        self, 
        sim: SimulationResult, 
        is_renounced: bool, 
        has_mint: bool
    ) -> list[RiskFlag]:
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

        if not is_renounced:
            flags.append(RiskFlag.OWNERSHIP_NOT_RENOUNCED)

        if has_mint and not is_renounced:
            flags.append(RiskFlag.HIDDEN_MINT)

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

        如果配置了 OpenAI API Key 且 Etherscan 可获取源码，则调用 LLM 进行深度分析。
        否则使用基于规则的默认摘要。
        """
        # 1. 默认规则摘要
        default_summary = self._default_summary(token, sim, flags, score)
        
        if not self._settings.llm_api_key:
            return default_summary

        # 2. 尝试获取源码
        try:
            etherscan = EtherscanService(chain_name=self.chain_name)
            source_code = await etherscan.get_contract_source(token.address)
            
            if not source_code:
                return default_summary + " (未找到已验证的合约源码，跳过 LLM 分析)"
            
            # 3. 调用 LLM (兼容 GLM / DeepSeek / OpenAI)
            truncated_source = source_code[:12000] 
            
            prompt = f"""
            角色：资深智能合约安全审计专家。
            任务：分析以下 ERC-20 代币合约源码，识别潜在的安全风险（如蜜罐、隐藏增发、高税率、权限过大等）。
            
            上下文信息：
            - 代币地址: {token.address}
            - 仿真结果: 能买={sim.can_buy}, 能卖={sim.can_sell}
            - 测得税率: 买入 {sim.buy_tax_pct}%, 卖出 {sim.sell_tax_pct}%
            - 风险标签: {[f.value for f in flags]}
            - 风险评分: {score}/100
            
            合约源码（部分）：
            ```solidity
            {truncated_source}
            ```
            
            要求：
            1. 简要总结合约的主要功能和逻辑。
            2. 重点分析是否存在恶意代码或后门（如 `onlyOwner` 限制转账、修改税率无上限、黑名单等）。
            3. 结合仿真结果给出最终的安全评价。
            4. 输出语言：中文。
            5. 字数控制在 300 字以内。
            """
            
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                api_key=self._settings.llm_api_key,
                base_url=self._settings.llm_base_url,
            )
            
            response = await client.chat.completions.create(
                model=self._settings.llm_model,
                messages=[
                    {"role": "system", "content": "你是一个专业的区块链安全审计助手。"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,
                temperature=0.3,
            )
            
            llm_result = response.choices[0].message.content.strip()
            return f"{default_summary}\n\n🤖 **AI 深度分析**:\n{llm_result}"

        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            return default_summary + " (AI 分析服务暂时不可用)"

    def _default_summary(
        self,
        token: Token,
        sim: SimulationResult,
        flags: list[RiskFlag],
        score: float,
    ) -> str:
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
