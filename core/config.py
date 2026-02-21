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
    llm_api_key: str = ""  # GLM / DeepSeek / OpenAI API Key
    llm_base_url: str = "https://open.bigmodel.cn/api/paas/v4/"  # 智谱 GLM
    llm_model: str = "glm-4-flash"  # 智谱 GLM 模型
    etherscan_api_key: str = ""
    bscscan_api_key: str = ""

    # ── Uniswap V2 Router ──────────────────────────────────────
    uniswap_v2_router: str = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"

    # ── BSC 链 (多链支持) ──────────────────────────────────────
    bsc_rpc_url: str = ""
    bsc_chain_id: int = 56
    bsc_factory: str = "0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73"
    bsc_weth: str = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"  # WBNB
    bsc_router: str = "0x10ED43C718714eb63d5aA57B78B54704E256024E"  # PancakeSwap

    # ── 路径 ────────────────────────────────────────────────────
    log_dir: Path = Path("./logs")

    # ── 税率阈值（规则引擎使用）──────────────────────────────────
    high_tax_threshold_pct: float = 10.0  # > 10% 视为可疑


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """返回应用级别的配置单例。"""
    return AppSettings()
