"""
core/config.py — 应用配置单例

使用 pydantic-settings 从 .env 文件中加载环境变量，并进行严格的类型校验。
通过 `get_settings()` 获取全局唯一的配置实例。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """集中化、类型安全的应用配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── 链 & RPC ────────────────────────────────────────────────
    rpc_url: str = "https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY"
    chain_id: int = 1
    wss_url: str = ""  # 可选的 WebSocket 端点

    # ── Uniswap V2 ─────────────────────────────────────────────
    uniswap_v2_factory: str = "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f"
    weth_address: str = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"

    # ── Anvil / Foundry ────────────────────────────────────────
    anvil_port: int = 8545
    anvil_block_time: int = 0  # 0 = 即时出块
    simulation_timeout_secs: int = 30

    # ── 数据库 ──────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./memescan.db"

    # ── 监控 ────────────────────────────────────────────────────
    poll_interval_secs: float = 2.0
    max_reconnect_attempts: int = 10
    reconnect_base_delay_secs: float = 1.0

    # ── LLM / 分析 ─────────────────────────────────────────────
    openai_api_key: str = ""
    etherscan_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    # ── 路径 ────────────────────────────────────────────────────
    log_dir: Path = Path("./logs")

    # ── 税率阈值（规则引擎使用）──────────────────────────────────
    high_tax_threshold_pct: float = 10.0  # > 10% 视为可疑


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """返回应用级别的配置单例。"""
    return AppSettings()
