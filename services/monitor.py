"""
services/monitor.py — 异步 PairCreated 事件监听器

通过 eth_getLogs 轮询 Uniswap V2 Factory 的 PairCreated 事件。
核心特性：
  - RPC 故障时的指数退避重连机制。
  - 通过 asyncio.Event 实现优雅关闭。
  - 基于回调的架构，用于新交易对的事件分发。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

from loguru import logger
from web3 import AsyncWeb3
from web3.types import LogReceipt

from core.config import get_settings
from core.web3_provider import get_async_web3
from domain.models import Token

# Uniswap V2 Factory — PairCreated(address indexed token0, address indexed token1, address pair, uint)
# ⚠️ .hex() 不带 0x 前缀，但 eth_getLogs 要求 topic 必须以 0x 开头
PAIR_CREATED_TOPIC = "0x" + AsyncWeb3.keccak(
    text="PairCreated(address,address,address,uint256)"
).hex()

# 新交易对回调函数的类型别名。
PairCreatedCallback = Callable[[Token], Coroutine[Any, Any, None]]


class MonitorService:
    """Uniswap V2 PairCreated 事件的异步监控器。

    用法::

        monitor = MonitorService(on_new_pair=my_callback)
        await monitor.start()   # 持续运行直到关闭
        await monitor.stop()
    """

    def __init__(self, on_new_pair: PairCreatedCallback | None = None) -> None:
        self._settings = get_settings()
        self._w3 = get_async_web3()
        self._shutdown_event = asyncio.Event()
        self._on_new_pair = on_new_pair
        self._last_block: int = 0
        self._reconnect_attempts: int = 0

    # ── 公共 API ────────────────────────────────────────────────

    async def start(self) -> None:
        """启动轮询循环。在调用 `stop()` 之前会持续阻塞。"""
        logger.info(
            "MonitorService 启动中",
            factory=self._settings.uniswap_v2_factory,
            poll_interval=self._settings.poll_interval_secs,
        )
        # 从当前链头初始化。
        try:
            self._last_block = await self._w3.eth.block_number
        except Exception as exc:
            logger.error("获取初始区块号失败: {}", exc)
            self._last_block = 0

        while not self._shutdown_event.is_set():
            try:
                await self._poll_events()
                self._reconnect_attempts = 0  # 成功后重置计数
            except Exception as exc:
                await self._handle_error(exc)

            # 可被关闭信号中断的休眠。
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self._settings.poll_interval_secs,
                )
            except asyncio.TimeoutError:
                pass  # 预期行为 — 继续轮询

        logger.info("MonitorService 已优雅停止")

    async def stop(self) -> None:
        """发出信号终止轮询循环。"""
        logger.info("MonitorService 收到关闭请求")
        self._shutdown_event.set()

    # ── 内部实现 ────────────────────────────────────────────────

    async def _poll_events(self) -> None:
        """获取自上次处理区块以来的新 PairCreated 日志。"""
        current_block = await self._w3.eth.block_number
        if current_block <= self._last_block:
            return

        # ⚡ 限制单次查询的区块范围
        # Alchemy 免费版限制: eth_getLogs 单次最多查 10 个区块。
        # 如果你升级了 Alchemy 套餐，可以把这个值改大（付费版支持 2000+）。
        MAX_BLOCK_RANGE = 10
        from_block = self._last_block + 1
        to_block = min(current_block, from_block + MAX_BLOCK_RANGE - 1)

        log_filter = {
            "fromBlock": from_block,
            "toBlock": to_block,
            "address": self._settings.uniswap_v2_factory,
            "topics": [PAIR_CREATED_TOPIC],
        }

        logs: list[LogReceipt] = await self._w3.eth.get_logs(log_filter)  # type: ignore[arg-type]

        for log_entry in logs:
            await self._process_log(log_entry)

        self._last_block = to_block
        if logs:
            logger.info(
                "已处理 {} 个新交易对，区块范围 {}-{}",
                len(logs),
                from_block,
                to_block,
            )

    async def _process_log(self, log_entry: LogReceipt) -> None:
        """解码 PairCreated 日志并触发回调。"""
        try:
            topics = log_entry.get("topics", [])
            data = log_entry.get("data", b"")

            # topic[1] = token0, topic[2] = token1（索引参数）
            token0 = "0x" + topics[1].hex()[-40:]
            token1 = "0x" + topics[2].hex()[-40:]
            # data = abi.encode(pair_address, pair_id)
            pair_address = "0x" + data.hex()[24:64] if isinstance(data, bytes) else "0x" + data[26:66]

            weth = self._settings.weth_address.lower()
            # 识别非 WETH 的代币。
            if token0.lower() == weth:
                target_token_address = token1
            elif token1.lower() == weth:
                target_token_address = token0
            else:
                logger.debug("交易对不含 WETH，跳过: {} / {}", token0, token1)
                return

            token = Token(
                address=target_token_address,
                pair_address=pair_address,
            )

            logger.info(
                "🆕 检测到新的 WETH 交易对: token={} pair={}",
                target_token_address,
                pair_address,
            )

            if self._on_new_pair:
                await self._on_new_pair(token)

        except (IndexError, ValueError) as exc:
            logger.warning("解码 PairCreated 日志失败: {}", exc)

    async def _handle_error(self, exc: Exception) -> None:
        """RPC 错误时的指数退避处理。"""
        self._reconnect_attempts += 1
        max_attempts = self._settings.max_reconnect_attempts
        base_delay = self._settings.reconnect_base_delay_secs

        if self._reconnect_attempts > max_attempts:
            logger.critical(
                "超过最大重连次数 ({})。正在关闭监控器。",
                max_attempts,
            )
            self._shutdown_event.set()
            return

        delay = min(base_delay * (2 ** (self._reconnect_attempts - 1)), 60.0)
        logger.warning(
            "RPC 错误 (第 {}/{} 次尝试): {}。将在 {:.1f} 秒后重试",
            self._reconnect_attempts,
            max_attempts,
            exc,
            delay,
        )
        await asyncio.sleep(delay)
