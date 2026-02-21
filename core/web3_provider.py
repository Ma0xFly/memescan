"""
core/web3_provider.py — 异步 Web3 Provider 单例

管理一个通过 AsyncHTTPProvider 连接的 AsyncWeb3 实例。
包含轻量级的连接健康检查工具函数。
"""

from __future__ import annotations

from functools import lru_cache

from web3 import AsyncWeb3
from web3.providers import AsyncHTTPProvider

from core.config import get_settings


@lru_cache(maxsize=2)
def get_async_web3(chain_name: str = "ethereum") -> AsyncWeb3:
    """返回一个缓存的 AsyncWeb3 实例。

    使用 AsyncHTTPProvider 实现非阻塞的 JSON-RPC 调用。
    支持多链。
    """
    settings = get_settings()
    rpc_url = settings.rpc_url if chain_name == "ethereum" else settings.bsc_rpc_url
    
    provider = AsyncHTTPProvider(
        endpoint_uri=rpc_url,
        request_kwargs={"timeout": 30},
    )
    return AsyncWeb3(provider)


async def check_connection(chain_name: str = "ethereum") -> bool:
    """验证 Web3 Provider 是否连通且可响应。

    返回:
        如果节点响应 eth_blockNumber 则返回 True，否则返回 False。
    """
    try:
        w3 = get_async_web3(chain_name)
        block = await w3.eth.block_number
        return block > 0
    except Exception:
        return False
