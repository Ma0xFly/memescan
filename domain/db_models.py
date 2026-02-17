"""
domain/db_models.py — SQLAlchemy 2.0 ORM 模型

映射到 Pydantic 领域模型的持久化类，用于数据库存储。
使用 core.db 中的声明式基类 Base。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base


class TokenRecord(Base):
    """已发现代币的持久化记录。"""

    __tablename__ = "tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    address: Mapped[str] = mapped_column(String(42), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), default="UNKNOWN")
    symbol: Mapped[str] = mapped_column(String(32), default="???")
    decimals: Mapped[int] = mapped_column(Integer, default=18)
    pair_address: Mapped[str] = mapped_column(String(42), index=True, nullable=False)
    deployer: Mapped[str] = mapped_column(String(42), default="")
    total_supply: Mapped[str | None] = mapped_column(String(78), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<TokenRecord {self.symbol} ({self.address[:10]}…)>"


class SimulationRecord(Base):
    """买卖仿真的持久化记录。"""

    __tablename__ = "simulations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_address: Mapped[str] = mapped_column(String(42), index=True, nullable=False)
    can_buy: Mapped[bool] = mapped_column(Boolean, default=False)
    can_sell: Mapped[bool] = mapped_column(Boolean, default=False)
    buy_tax_pct: Mapped[float] = mapped_column(Float, default=0.0)
    sell_tax_pct: Mapped[float] = mapped_column(Float, default=0.0)
    buy_gas: Mapped[int] = mapped_column(Integer, default=0)
    sell_gas: Mapped[int] = mapped_column(Integer, default=0)
    is_honeypot: Mapped[bool] = mapped_column(Boolean, default=False)
    revert_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    simulated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<SimulationRecord token={self.token_address[:10]}… honeypot={self.is_honeypot}>"


class AuditRecord(Base):
    """已完成的审计报告持久化记录。"""

    __tablename__ = "audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_address: Mapped[str] = mapped_column(String(42), index=True, nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    risk_flags_json: Mapped[str] = mapped_column(Text, default="[]")
    llm_summary: Mapped[str] = mapped_column(Text, default="")
    audited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<AuditRecord token={self.token_address[:10]}… score={self.risk_score}>"
