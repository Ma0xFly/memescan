"""
services/simulator.py — Anvil 分叉仿真引擎

管理 Anvil 子进程的生命周期，并通过 Foundry 的 `cast` CLI 执行买卖仿真。
设计为异步上下文管理器。

用法::

    async with SimulationService() as sim:
        result = await sim.simulate_buy_sell("0xTokenAddress...")
"""

from __future__ import annotations

import asyncio
import json
import shutil
from typing import Any

from loguru import logger

from core.config import get_settings
from domain.models import SimulationResult


class AnvilProcessError(Exception):
    """当 Anvil 启动失败或无响应时抛出此异常。"""


class SimulationService:
    """管理 Anvil 分叉并通过 cast 运行买卖仿真。

    实现异步上下文管理器以实现干净的生命周期管理。
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._anvil_process: asyncio.subprocess.Process | None = None
        self._anvil_port: int = self._settings.anvil_port
        self._fork_url: str = self._settings.rpc_url

    # ── 上下文管理器 ────────────────────────────────────────────

    async def __aenter__(self) -> SimulationService:
        await self.fork_mainnet()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.kill_anvil()

    # ── Anvil 生命周期管理 ──────────────────────────────────────

    async def fork_mainnet(self, block: int | None = None) -> None:
        """启动一个从主网分叉的 Anvil 进程。

        参数:
            block: 可选的分叉起始区块号。None 表示使用最新区块。

        异常:
            AnvilProcessError: 当 Anvil 二进制文件未找到或启动失败时抛出。
        """
        if self._anvil_process is not None:
            logger.warning("Anvil 已在运行，正在终止先前的实例")
            await self.kill_anvil()

        anvil_bin = shutil.which("anvil")
        if anvil_bin is None:
            raise AnvilProcessError(
                "在 PATH 中未找到 anvil 二进制文件。请安装 Foundry: https://getfoundry.sh"
            )

        cmd: list[str] = [
            anvil_bin,
            "--fork-url", self._fork_url,
            "--port", str(self._anvil_port),
            "--no-mining",  # 手动出块以保证仿真确定性
            "--silent",
        ]
        if block is not None:
            cmd.extend(["--fork-block-number", str(block)])
        if self._settings.anvil_block_time > 0:
            cmd.extend(["--block-time", str(self._settings.anvil_block_time)])

        logger.info("正在启动 Anvil: {}", " ".join(cmd))

        self._anvil_process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # 短暂等待 Anvil 绑定端口。
        await asyncio.sleep(2.0)

        if self._anvil_process.returncode is not None:
            stderr = (await self._anvil_process.stderr.read()).decode() if self._anvil_process.stderr else ""
            raise AnvilProcessError(f"Anvil 立即退出: {stderr}")

        logger.info("Anvil 已成功在端口 {} 上完成分叉", self._anvil_port)

    async def kill_anvil(self) -> None:
        """终止被管理的 Anvil 进程。"""
        if self._anvil_process is None:
            return

        try:
            self._anvil_process.terminate()
            await asyncio.wait_for(self._anvil_process.wait(), timeout=5.0)
            logger.info("Anvil 进程已正常终止")
        except asyncio.TimeoutError:
            logger.warning("Anvil 未在规定时间内退出，正在强制终止")
            self._anvil_process.kill()
            await self._anvil_process.wait()
        finally:
            self._anvil_process = None

    # ── 仿真执行 ────────────────────────────────────────────────

    async def simulate_buy_sell(self, token_address: str) -> SimulationResult:
        """在 Anvil 分叉上仿真目标代币的买入和卖出操作。

        步骤:
          1. cast call — 仿真 swapExactETHForTokens（买入）
          2. cast call — 仿真 swapExactTokensForETH（卖出）
          3. 从 JSON 输出中解析 Gas 用量和 Revert 原因

        参数:
            token_address: 待测试的 ERC-20 代币地址（校验和格式）。

        返回:
            包含税率估算和蜜罐检测结果的 SimulationResult。
        """
        if self._anvil_process is None:
            raise AnvilProcessError("Anvil 未在运行。请先调用 fork_mainnet()。")

        rpc_endpoint = f"http://127.0.0.1:{self._anvil_port}"
        weth = self._settings.weth_address

        # Uniswap V2 Router
        router = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
        # 默认发送者 — Anvil 的第一个预充值账户
        sender = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
        # 买入金额: 0.1 ETH
        buy_value = "100000000000000000"  # 0.1 ETH（单位: wei）

        can_buy = False
        can_sell = False
        buy_gas = 0
        sell_gas = 0
        buy_tax_pct = 0.0
        sell_tax_pct = 0.0
        revert_reason: str | None = None
        error_message: str | None = None

        try:
            # ── 步骤 1: 仿真买入 ─────────────────────────────────
            buy_result = await self._cast_call(
                rpc_endpoint=rpc_endpoint,
                to=router,
                sig="swapExactETHForTokens(uint256,address[],address,uint256)",
                args=["0", f"[{weth},{token_address}]", sender, "9999999999"],
                value=buy_value,
                sender=sender,
            )

            if buy_result.get("success"):
                can_buy = True
                buy_gas = buy_result.get("gas_used", 0)
                logger.info("✅ 买入仿真成功 — Gas: {}", buy_gas)
            else:
                revert_reason = buy_result.get("revert_reason", "买入时发生未知 Revert")
                logger.warning("❌ 买入仿真 Revert: {}", revert_reason)

            # ── 步骤 2: 仿真卖出（仅在买入成功时执行）────────────
            if can_buy:
                sell_result = await self._cast_call(
                    rpc_endpoint=rpc_endpoint,
                    to=router,
                    sig="swapExactTokensForETH(uint256,uint256,address[],address,uint256)",
                    args=["1000000000000000000", "0", f"[{token_address},{weth}]", sender, "9999999999"],
                    sender=sender,
                )

                if sell_result.get("success"):
                    can_sell = True
                    sell_gas = sell_result.get("gas_used", 0)
                    logger.info("✅ 卖出仿真成功 — Gas: {}", sell_gas)
                else:
                    revert_reason = sell_result.get("revert_reason", "卖出时发生未知 Revert")
                    logger.warning("❌ 卖出仿真 Revert: {}", revert_reason)

        except Exception as exc:
            error_message = str(exc)
            logger.error("代币 {} 仿真出错: {}", token_address, exc)

        is_honeypot = can_buy and not can_sell

        return SimulationResult(
            token_address=token_address,
            can_buy=can_buy,
            can_sell=can_sell,
            buy_tax_pct=buy_tax_pct,
            sell_tax_pct=sell_tax_pct,
            buy_gas=buy_gas,
            sell_gas=sell_gas,
            is_honeypot=is_honeypot,
            revert_reason=revert_reason,
            error_message=error_message,
        )

    # ── Cast 命令执行 ────────────────────────────────────────────

    async def _cast_call(
        self,
        *,
        rpc_endpoint: str,
        to: str,
        sig: str,
        args: list[str],
        sender: str,
        value: str | None = None,
    ) -> dict[str, Any]:
        """执行 `cast call` 命令并解析 JSON 输出。

        返回:
            包含以下键的字典: success (bool), gas_used (int), revert_reason (str | None)
        """
        cast_bin = shutil.which("cast")
        if cast_bin is None:
            raise AnvilProcessError("在 PATH 中未找到 cast 二进制文件。")

        cmd: list[str] = [
            cast_bin, "call",
            "--rpc-url", rpc_endpoint,
            "--from", sender,
            "--json",
            to,
            sig,
            *args,
        ]
        if value is not None:
            cmd.extend(["--value", value])

        logger.debug("执行命令: {}", " ".join(cmd))

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=float(self._settings.simulation_timeout_secs),
            )
        except asyncio.TimeoutError:
            return {"success": False, "gas_used": 0, "revert_reason": "仿真超时"}

        stdout = stdout_bytes.decode().strip()
        stderr = stderr_bytes.decode().strip()

        if process.returncode != 0:
            revert_reason = self._extract_revert_reason(stderr) or stderr[:256]
            return {"success": False, "gas_used": 0, "revert_reason": revert_reason}

        # 解析 cast 的 JSON 输出。
        gas_used = 0
        try:
            data = json.loads(stdout)
            if isinstance(data, dict):
                gas_used = int(data.get("gasUsed", data.get("gas", 0)))
        except (json.JSONDecodeError, ValueError):
            pass  # 非 JSON 输出 — 如果返回码为 0 仍视为成功

        return {"success": True, "gas_used": gas_used, "revert_reason": None}

    @staticmethod
    def _extract_revert_reason(stderr: str) -> str | None:
        """尝试从 cast 的 stderr 中提取可读的 Revert 原因。"""
        for line in stderr.splitlines():
            lower = line.lower()
            if "revert" in lower or "error" in lower:
                return line.strip()
        return None
