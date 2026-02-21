"""
core/db.py — 异步 SQLAlchemy 2.0 数据库引擎 & 会话工厂

提供连接池、异步会话工厂，以及用于依赖注入的上下文管理器。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from core.config import get_settings


from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import select
from sqlalchemy.orm import DeclarativeBase

from core.config import get_settings
from domain.models import Token, SimulationResult, AuditReport

class Base(DeclarativeBase):
    """所有 ORM 模型的声明式基类。"""
    pass

class Repository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_token(self, token: Token) -> None:
        from domain.db_models import TokenRecord
        
        stmt = select(TokenRecord).where(TokenRecord.address == token.address)
        result = await self.session.execute(stmt)
        record = result.scalar_one_or_none()
        
        if record:
            record.name = token.name
            record.symbol = token.symbol
            record.decimals = token.decimals
            record.pair_address = token.pair_address
            record.deployer = token.deployer
            record.total_supply = token.total_supply
            record.liquidity_eth = token.liquidity_eth
            record.holder_count = token.holder_count
        else:
            record = TokenRecord(
                address=token.address,
                name=token.name,
                symbol=token.symbol,
                decimals=token.decimals,
                pair_address=token.pair_address,
                deployer=token.deployer,
                total_supply=token.total_supply,
                liquidity_eth=token.liquidity_eth,
                holder_count=token.holder_count,
            )
            self.session.add(record)
        await self.session.flush()

    async def save_simulation(self, sim: SimulationResult) -> None:
        from domain.db_models import SimulationRecord
        
        record = SimulationRecord(
            token_address=sim.token_address,
            can_buy=sim.can_buy,
            can_sell=sim.can_sell,
            buy_tax_pct=sim.buy_tax_pct,
            sell_tax_pct=sim.sell_tax_pct,
            buy_gas=sim.buy_gas,
            sell_gas=sim.sell_gas,
            is_honeypot=sim.is_honeypot,
            revert_reason=sim.revert_reason,
            error_message=sim.error_message,
            simulated_at=sim.simulated_at,
        )
        self.session.add(record)
        await self.session.flush()

    async def save_audit(self, report: AuditReport) -> None:
        from domain.db_models import AuditRecord
        import json
        
        record = AuditRecord(
            token_address=report.token.address,
            risk_score=report.risk_score,
            risk_flags_json=json.dumps([f.value for f in report.risk_flags]),
            llm_summary=report.llm_summary,
            audited_at=report.audited_at,
        )
        self.session.add(record)
        await self.session.flush()

    async def get_token_history(self, address: str, limit: int = 10):
        pass




def _build_engine():
    """根据当前配置构建异步引擎。"""
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
    )


# 模块级别的单例（延迟引用）。
_engine = _build_engine()
_session_factory = async_sessionmaker(
    bind=_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """生成一个异步会话并保证资源清理。

    用法::

        async with get_session() as session:
            result = await session.execute(...)
    """
    session = _session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def init_db() -> None:
    """创建所有 ORM 模型定义的数据表。

    在应用启动时调用一次。
    """
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def shutdown_db() -> None:
    """优雅地释放引擎连接池。"""
    await _engine.dispose()
