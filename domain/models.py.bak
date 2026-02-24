"""
domain/models.py — Pydantic V2 领域模型

严格、不可变的数据契约，用于应用边界。
这些模型用于校验、序列化和服务间通信。
它们不是 ORM 模型（ORM 模型见 db_models.py）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 风险标签枚举
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class RiskFlag(str, Enum):
    """分析过程中检测到的分类风险指标。"""

    HONEYPOT = "HONEYPOT"
    HIGH_BUY_TAX = "HIGH_BUY_TAX"
    HIGH_SELL_TAX = "HIGH_SELL_TAX"
    CANNOT_SELL = "CANNOT_SELL"
    OWNERSHIP_NOT_RENOUNCED = "OWNERSHIP_NOT_RENOUNCED"
    HIDDEN_MINT = "HIDDEN_MINT"
    PROXY_CONTRACT = "PROXY_CONTRACT"
    BLACKLIST_FUNCTION = "BLACKLIST_FUNCTION"
    TRANSFER_PAUSABLE = "TRANSFER_PAUSABLE"
    ANTI_WHALE_LIMIT = "ANTI_WHALE_LIMIT"
    UNKNOWN_RISK = "UNKNOWN_RISK"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Token 代币模型
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class Token(BaseModel):
    """表示一个新发现的 ERC-20 代币。"""

    address: str = Field(..., description="校验和格式的 ERC-20 合约地址")
    name: str = Field(default="UNKNOWN", max_length=128)
    symbol: str = Field(default="???", max_length=32)
    decimals: int = Field(default=18, ge=0, le=24)
    pair_address: str = Field(..., description="DEX 流动性交易对地址")
    deployer: str = Field(default="", description="合约部署者地址")
    total_supply: Optional[str] = Field(default=None, description="原始总供应量")
    liquidity_eth: Optional[float] = Field(default=None, description="ETH 流动性池规模")
    holder_count: Optional[int] = Field(default=None, description="持币地址数")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("address", "pair_address", "deployer", mode="before")
    @classmethod
    def normalise_address(cls, v: str) -> str:
        """将地址统一存储为小写十六进制格式，保证一致性。"""
        if isinstance(v, str) and v:
            return v.strip().lower()
        return v

    model_config = {"frozen": True}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SimulationResult 仿真结果模型
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SimulationResult(BaseModel):
    """Anvil 分叉买卖仿真的输出结果。"""

    token_address: str
    can_buy: bool = False
    can_sell: bool = False
    buy_tax_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    sell_tax_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    buy_gas: int = Field(default=0, ge=0)
    sell_gas: int = Field(default=0, ge=0)
    is_honeypot: bool = False
    revert_reason: Optional[str] = None
    error_message: Optional[str] = None
    simulated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("token_address", mode="before")
    @classmethod
    def normalise_address(cls, v: str) -> str:
        return v.strip().lower() if isinstance(v, str) else v

    model_config = {"frozen": True}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AuditReport 审计报告模型
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AuditReport(BaseModel):
    """代币的最终安全审计报告。"""

    token: Token
    simulation: SimulationResult
    risk_score: float = Field(default=0.0, ge=0.0, le=100.0, description="0=安全, 100=跑路")
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    llm_summary: str = Field(default="", description="LLM 生成的分析叙述")
    audited_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_dangerous(self) -> bool:
        """快速检查：评分 ≥ 70 或存在任何关键风险标签。"""
        critical = {RiskFlag.HONEYPOT, RiskFlag.CANNOT_SELL, RiskFlag.HIDDEN_MINT}
        return self.risk_score >= 70.0 or bool(critical & set(self.risk_flags))

    model_config = {"frozen": True}
