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


class Base(DeclarativeBase):
    """所有 ORM 模型的声明式基类。"""
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
