"""
services/simulator.py — Anvil 分叉仿真引擎

管理 Anvil 子进程的生命周期，并通过 Foundry 的 cast CLI 仿真买卖交易。
设计为异步上下文管理器，保证每次仿真后 Anvil 进程被正确清理。

用法::

    async with SimulationService() as sim:
        result = await sim.simulate_buy_sell("0xTokenAddress...")

Day 3-4 修改说明:
  - 🆕 用 cast send 替代 cast call，让交易真正上链到 Anvil
  - 🆕 买入后增加 approve 步骤，授权 Router 花费代币
  - 🆕 通过 getAmountsOut + 实际余额对比，精确计算买入/卖出税率
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

    # ── 常量定义 ──────────────────────────────────────────────────
    #
    # 为什么要把这些写成类常量而不是写死在函数里？
    # 因为如果以后要支持多链（BSC / Base），只需要改这些值。
    #

    # Uniswap V2 Router 合约地址 — 所有的买入/卖出操作都通过它中转
    UNISWAP_V2_ROUTER = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"

    # Anvil 默认生成的第一个测试账户 — 预充值 10000 ETH
    # 我们用它来模拟用户买卖行为
    ANVIL_SENDER = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"

    # 这个账户的私钥 — Anvil 的固定测试密钥，不是真实资产
    # cast send 需要私钥来签名交易
    ANVIL_PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"

    # 仿真买入金额: 0.1 ETH (单位: wei)
    # 不需要太大，只要能触发交易流程就行
    BUY_AMOUNT_WEI = "100000000000000000"

    def __init__(self) -> None:
        self._settings = get_settings()
        self._anvil_process: asyncio.subprocess.Process | None = None
        self._anvil_port: int = self._settings.anvil_port
        self._fork_url: str = self._settings.rpc_url

    # ── 上下文管理器 ────────────────────────────────────────────
    #
    # 什么是上下文管理器？
    #   async with SimulationService() as sim:
    #       ...  # sim 在这里可用
    #   # 离开 with 块后，Anvil 进程自动被终止
    #
    # 这保证了即使你的代码抛出异常，Anvil 也不会变成僵尸进程。
    #

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
            # 🆕 注意: 去掉了 --no-mining！
            # 原因: cast send 需要交易被"挖矿"确认。
            # Anvil 默认模式是 "auto-mine"：每收到一笔交易，立即出一个块。
            # 如果加了 --no-mining，交易会卡在 pending 状态，cast send 会超时。
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

        # 等待 Anvil 完成分叉并绑定端口（分叉需要从 RPC 拉取状态，可能需要几秒）
        await asyncio.sleep(3.0)

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

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 🆕 核心仿真流程 — 完全重写
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #
    # 旧版问题:
    #   用 cast call（只读模拟），状态不会改变，买入后实际没拿到代币。
    #
    # 新版流程:
    #   1. getAmountsOut   → 问 Router "0.1 ETH 能换多少代币？"（预期值）
    #   2. cast send 买入   → 真正把 ETH 换成代币（Anvil 链上状态改变）
    #   3. balanceOf       → 查你实际拿到多少代币
    #   4. 买入税 = (预期 - 实际) / 预期 × 100%
    #   5. cast send approve → 授权 Router 花你的代币
    #   6. getAmountsOut   → 问 Router "卖出这些代币能换多少 ETH？"
    #   7. cast send 卖出   → 真正卖出代币换回 ETH
    #   8. 卖出税 = (预期 ETH - 实际 ETH) / 预期 ETH × 100%
    #

    async def simulate_buy_sell(self, token_address: str) -> SimulationResult:
        """在 Anvil 分叉上仿真目标代币的完整买入→批准→卖出流程。

        参数:
            token_address: 待测试的 ERC-20 代币地址。

        返回:
            SimulationResult — 包含税率、蜜罐检测和 Gas 数据。
        """
        if self._anvil_process is None:
            raise AnvilProcessError("Anvil 未在运行。请先调用 fork_mainnet()。")

        rpc = f"http://127.0.0.1:{self._anvil_port}"
        weth = self._settings.weth_address
        router = self.UNISWAP_V2_ROUTER
        sender = self.ANVIL_SENDER
        pk = self.ANVIL_PRIVATE_KEY

        can_buy = False
        can_sell = False
        buy_gas = 0
        sell_gas = 0
        buy_tax_pct = 0.0
        sell_tax_pct = 0.0
        revert_reason: str | None = None
        error_message: str | None = None

        try:
            # ── 步骤 0: 查询代币元信息 ─────────────────────────────
            # 获取代币的符号（如 "SHIB"）和精度（如 18）
            # 用于后续日志输出更可读
            symbol = await self._get_token_symbol(rpc, token_address)
            decimals = await self._get_token_decimals(rpc, token_address)
            logger.info("🪙 代币: {} (精度: {})", symbol, decimals)

            # ── 步骤 1: 预测买入输出量 ─────────────────────────────
            #
            # getAmountsOut 是 Router 的只读函数。
            # 输入: 0.1 ETH + 路径 [WETH → Token]
            # 输出: [0.1 ETH, 预期代币数量]
            # 这个"预期数量"已经扣除了 Uniswap 的 0.3% 交易手续费，
            # 但还没有扣除代币本身的隐藏税。
            #
            expected_tokens = await self._get_amounts_out(
                rpc=rpc,
                router=router,
                amount_in=self.BUY_AMOUNT_WEI,
                path=f"[{weth},{token_address}]",
            )
            if expected_tokens is None or expected_tokens == 0:
                return SimulationResult(
                    token_address=token_address,
                    error_message="getAmountsOut 失败 — 可能没有流动性",
                )
            logger.info("📊 预期买入: {} {}", self._fmt_token(expected_tokens, decimals), symbol)

            # ── 步骤 2: 执行买入 ───────────────────────────────────
            #
            # 🆕 用 cast send 而不是 cast call！
            # cast send 会真正执行交易，改变 Anvil 链上状态。
            # 执行后，sender 账户会减少 0.1 ETH，增加代币。
            #
            buy_receipt = await self._cast_send(
                rpc=rpc,
                to=router,
                sig="swapExactETHForTokens(uint256,address[],address,uint256)",
                args=["0", f"[{weth},{token_address}]", sender, "9999999999"],
                sender=sender,
                private_key=pk,
                value=self.BUY_AMOUNT_WEI,
            )

            if not buy_receipt["success"]:
                revert_reason = buy_receipt.get("revert_reason", "买入 Revert")
                logger.warning("❌ 买入失败: {}", revert_reason)
                return SimulationResult(
                    token_address=token_address,
                    can_buy=False,
                    revert_reason=revert_reason,
                )

            can_buy = True
            buy_gas = buy_receipt.get("gas_used", 0)
            logger.info("✅ 买入成功 — Gas: {}", buy_gas)

            # ── 步骤 3: 查实际代币余额 → 算买入税 ──────────────────
            #
            # 如果代币有隐藏税，你实际拿到的量会比 getAmountsOut 预测的少。
            # 差值就是税。
            #
            actual_tokens = await self._get_token_balance(rpc, token_address, sender)
            logger.info("📊 实际收到: {} {} (预期: {})", self._fmt_token(actual_tokens, decimals), symbol, self._fmt_token(expected_tokens, decimals))

            if expected_tokens > 0 and actual_tokens >= 0:
                buy_tax_pct = max(0.0, (expected_tokens - actual_tokens) / expected_tokens * 100)
                logger.info("📊 买入税率: {:.2f}%", buy_tax_pct)

            # 如果一个代币都没拿到，也算蜜罐
            if actual_tokens == 0:
                return SimulationResult(
                    token_address=token_address,
                    can_buy=True,
                    can_sell=False,
                    is_honeypot=True,
                    buy_gas=buy_gas,
                    buy_tax_pct=100.0,
                    revert_reason="买入成功但余额为 0 — 100% 税率",
                )

            # ── 步骤 4: 🆕 Approve — 授权 Router 花费代币 ──────────
            #
            # 为什么需要 approve？
            #   ERC-20 标准规定: 别人（Router）要花你的代币，
            #   你必须先调用 approve(router, amount) 授权。
            #   如果不 approve，Router 调用 transferFrom 时会 Revert。
            #
            # 我们用 type(uint256).max 作为授权额度（"无限授权"）
            # 这在仿真环境中无所谓安全性，只要能通过就行。
            #
            max_uint256 = "115792089237316195423570985008687907853269984665640564039457584007913129639935"
            approve_receipt = await self._cast_send(
                rpc=rpc,
                to=token_address,
                sig="approve(address,uint256)",
                args=[router, max_uint256],
                sender=sender,
                private_key=pk,
            )

            if not approve_receipt["success"]:
                logger.warning("❌ Approve 失败: {}", approve_receipt.get("revert_reason"))
                return SimulationResult(
                    token_address=token_address,
                    can_buy=True,
                    can_sell=False,
                    is_honeypot=True,
                    buy_gas=buy_gas,
                    buy_tax_pct=buy_tax_pct,
                    revert_reason="Approve 被拒绝 — 可能是蜜罐",
                )

            logger.info("✅ Approve 成功")

            # ── 步骤 5: 预测卖出输出量 ─────────────────────────────
            expected_eth = await self._get_amounts_out(
                rpc=rpc,
                router=router,
                amount_in=str(actual_tokens),
                path=f"[{token_address},{weth}]",
            )
            logger.info("📊 预期卖出可得: {} ETH", self._fmt_eth(expected_eth))

            # ── 步骤 6: 记录卖出前 ETH 余额 ───────────────────────
            eth_before = await self._get_eth_balance(rpc, sender)

            # ── 步骤 7: 执行卖出 ───────────────────────────────────
            sell_receipt = await self._cast_send(
                rpc=rpc,
                to=router,
                sig="swapExactTokensForETH(uint256,uint256,address[],address,uint256)",
                args=[str(actual_tokens), "0", f"[{token_address},{weth}]", sender, "9999999999"],
                sender=sender,
                private_key=pk,
            )

            if not sell_receipt["success"]:
                revert_reason = sell_receipt.get("revert_reason", "卖出 Revert")
                logger.warning("❌ 卖出失败: {} — 🍯 蜜罐！", revert_reason)
                return SimulationResult(
                    token_address=token_address,
                    can_buy=True,
                    can_sell=False,
                    is_honeypot=True,
                    buy_gas=buy_gas,
                    buy_tax_pct=buy_tax_pct,
                    revert_reason=revert_reason,
                )

            can_sell = True
            sell_gas = sell_receipt.get("gas_used", 0)
            logger.info("✅ 卖出成功 — Gas: {}", sell_gas)

            # ── 步骤 8: 算卖出税率 ────────────────────────────────
            eth_after = await self._get_eth_balance(rpc, sender)
            # 实际收到的 ETH = 卖出后余额 - 卖出前余额（注意要加上 gas 消耗的 ETH）
            # 简化处理: 忽略 gas 费（在 Anvil 上 gas price 默认为 0）
            actual_eth_received = eth_after - eth_before

            if expected_eth and expected_eth > 0 and actual_eth_received >= 0:
                sell_tax_pct = max(0.0, (expected_eth - actual_eth_received) / expected_eth * 100)
                logger.info("📊 卖出税率: {:.2f}%", sell_tax_pct)

        except Exception as exc:
            error_message = str(exc)
            logger.error("代币 {} 仿真出错: {}", token_address, exc)

        is_honeypot = can_buy and not can_sell

        return SimulationResult(
            token_address=token_address,
            can_buy=can_buy,
            can_sell=can_sell,
            buy_tax_pct=min(buy_tax_pct, 100.0),  # 限制在 0-100 范围
            sell_tax_pct=min(sell_tax_pct, 100.0),
            buy_gas=buy_gas,
            sell_gas=sell_gas,
            is_honeypot=is_honeypot,
            revert_reason=revert_reason,
            error_message=error_message,
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 🆕 余额查询方法
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _get_token_balance(self, rpc: str, token: str, account: str) -> int:
        """查询某地址持有的 ERC-20 代币余额。

        原理: 调用代币合约的 balanceOf(address) 函数。
        这是 ERC-20 标准接口，所有代币都必须实现它。

        返回:
            代币余额（整数，单位是代币的最小精度，类似 ETH 的 wei）。
        """
        output = await self._cast_call_raw(
            rpc=rpc,
            to=token,
            sig="balanceOf(address)(uint256)",
            args=[account],
        )
        return self._parse_cast_uint(output, "代币余额")

    async def _get_token_symbol(self, rpc: str, token: str) -> str:
        """查询代币的符号名称（如 SHIB, PEPE）。"""
        output = await self._cast_call_raw(
            rpc=rpc, to=token, sig="symbol()(string)", args=[],
        )
        # cast 输出可能带引号，去掉
        cleaned = output.strip().strip('"')
        return cleaned if cleaned else "???"

    async def _get_token_decimals(self, rpc: str, token: str) -> int:
        """查询代币精度（大部分是 18，USDC/USDT 是 6）。"""
        output = await self._cast_call_raw(
            rpc=rpc, to=token, sig="decimals()(uint8)", args=[],
        )
        val = self._parse_cast_uint(output, "decimals")
        return val if val > 0 else 18  # 默认 18

    async def _get_eth_balance(self, rpc: str, account: str) -> int:
        """查询地址的 ETH 余额（单位: wei）。"""
        cast_bin = shutil.which("cast")
        if cast_bin is None:
            return 0

        process = await asyncio.create_subprocess_exec(
            cast_bin, "balance", "--rpc-url", rpc, account,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=10.0)
        try:
            return int(stdout.decode().strip())
        except (ValueError, TypeError):
            return 0

    async def _get_amounts_out(
        self, *, rpc: str, router: str, amount_in: str, path: str
    ) -> int | None:
        """调用 Router 的 getAmountsOut，获取预期输出量。

        什么是 getAmountsOut？
          Uniswap Router 的只读函数，根据 AMM 公式计算：
          "如果输入 X 个代币 A，经过路径 [A → B]，最终能得到多少个代币 B？"
          返回值已经包含了 Uniswap 的 0.3% 手续费扣除。

        参数:
            amount_in: 输入金额（wei 字符串）
            path: Uniswap 路径数组，如 "[WETH,Token]" 或 "[Token,WETH]"

        返回:
            路径最后一个代币的预期输出量，失败返回 None。
        """
        output = await self._cast_call_raw(
            rpc=rpc,
            to=router,
            sig="getAmountsOut(uint256,address[])(uint256[])",
            args=[amount_in, path],
        )
        try:
            # cast 输出格式示例:
            #   [100000000000000000 [1e17], 31142968847530135546317260 [3.114e25]]
            #
            # 解析策略:
            #   1. 按逗号分割得到每个元素
            #   2. 取最后一个元素（路径终点的输出量）
            #   3. 用 _parse_cast_uint 提取整数部分
            #
            # 去掉外层方括号
            inner = output.strip().strip("[]")
            # 按逗号分割
            parts = inner.split(",")
            if parts:
                last_part = parts[-1].strip()
                return self._parse_cast_uint(last_part, "getAmountsOut")
            return None
        except (ValueError, IndexError):
            logger.warning("解析 getAmountsOut 输出失败: {}", output)
            return None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 🆕 Cast 命令执行 — 分为 send 和 call 两种
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #
    # cast call vs cast send 的区别:
    #
    #   cast call  — "模拟执行"，不修改任何链上状态，用于查询（如 balanceOf）
    #   cast send  — "真正执行"，会发送一笔交易并修改链上状态（如 swap、approve）
    #
    # 类比:
    #   cast call = 在 Excel 里算"如果我买了会怎样" → 只是看看
    #   cast send = 真的点了"下单"按钮 → 钱花出去了，货进来了
    #

    async def _cast_send(
        self,
        *,
        rpc: str,
        to: str,
        sig: str,
        args: list[str],
        sender: str,
        private_key: str,
        value: str | None = None,
    ) -> dict[str, Any]:
        """执行 cast send — 发送真实交易到 Anvil 并返回交易回执。

        返回:
            字典: {success: bool, gas_used: int, revert_reason: str | None}
        """
        cast_bin = shutil.which("cast")
        if cast_bin is None:
            raise AnvilProcessError("在 PATH 中未找到 cast 二进制文件。")

        cmd: list[str] = [
            cast_bin, "send",
            "--rpc-url", rpc,
            "--private-key", private_key,
            "--json",  # 输出 JSON 格式的交易回执
            to,
            sig,
            *args,
        ]
        if value is not None:
            cmd.extend(["--value", value])

        logger.debug("执行 cast send: {} {} {}", to[:10], sig.split("(")[0], args)

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
            return {"success": False, "gas_used": 0, "revert_reason": "cast send 超时"}

        stdout = stdout_bytes.decode().strip()
        stderr = stderr_bytes.decode().strip()

        if process.returncode != 0:
            revert_reason = self._extract_revert_reason(stderr) or stderr[:256]
            return {"success": False, "gas_used": 0, "revert_reason": revert_reason}

        # 解析 cast send 的 JSON 交易回执
        # 关键字段:
        #   status: "0x1" = 成功, "0x0" = 失败（Revert）
        #   gasUsed: 实际消耗的 Gas
        gas_used = 0
        try:
            receipt = json.loads(stdout)
            if isinstance(receipt, dict):
                status = receipt.get("status", "0x0")
                gas_used = int(receipt.get("gasUsed", "0x0"), 16)

                if status != "0x1":
                    return {
                        "success": False,
                        "gas_used": gas_used,
                        "revert_reason": "交易 Revert（status=0x0）",
                    }
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("解析 cast send 回执失败: {}", exc)

        return {"success": True, "gas_used": gas_used, "revert_reason": None}

    async def _cast_call_raw(
        self,
        *,
        rpc: str,
        to: str,
        sig: str,
        args: list[str],
    ) -> str:
        """执行 cast call — 只读查询，返回原始输出字符串。

        与 _cast_send 不同，这个函数不需要私钥，
        因为它不会修改任何链上状态。
        """
        cast_bin = shutil.which("cast")
        if cast_bin is None:
            raise AnvilProcessError("在 PATH 中未找到 cast 二进制文件。")

        cmd: list[str] = [
            cast_bin, "call",
            "--rpc-url", rpc,
            to,
            sig,
            *args,
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=10.0,
            )
        except asyncio.TimeoutError:
            return ""

        if process.returncode != 0:
            stderr = stderr_bytes.decode().strip()
            logger.debug("cast call 失败: {}", stderr[:200])
            return ""

        return stdout_bytes.decode().strip()

    @staticmethod
    def _fmt_eth(wei: int | None) -> str:
        """将 wei 转为可读的 ETH 字符串。

        例: 99401320899255464 → '0.0994 ETH'
        """
        if wei is None:
            return "N/A"
        return f"{wei / 1e18:.6f}"

    @staticmethod
    def _fmt_token(amount: int, decimals: int = 18) -> str:
        """将代币原始数量转为可读字符串。

        大部分 ERC-20 代币精度为 18（和 ETH 一样）。
        例: 31142968847530135546317260 → '31,142,968.85'
        """
        readable = amount / (10 ** decimals)
        if readable >= 1_000_000:
            return f"{readable:,.2f}"
        elif readable >= 1:
            return f"{readable:,.4f}"
        else:
            return f"{readable:.8f}"

    def _parse_cast_uint(self, raw: str, label: str = "") -> int:
        """解析 cast 输出的整数值。

        cast 的输出格式可能是:
          "31142968847530135546317260 [3.114e25]"  ← 大数会附加科学计数法
          "0"                                      ← 普通数字
          "100000000000000000 [1e17]"               ← 带方括号

        解析策略: 取第一个空格前的部分，尝试转为 int。
        """
        try:
            cleaned = raw.strip()
            # 如果包含空格（如 "12345 [1.23e4]"），只取空格前的数字
            if " " in cleaned:
                cleaned = cleaned.split()[0]
            # 去掉可能残留的方括号、逗号
            cleaned = cleaned.strip("[], ")
            return int(cleaned)
        except (ValueError, TypeError):
            logger.warning("解析 {} 失败，原始值: {}", label, raw)
            return 0

    @staticmethod
    def _extract_revert_reason(stderr: str) -> str | None:
        """尝试从 cast 的 stderr 中提取可读的 Revert 原因。"""
        for line in stderr.splitlines():
            lower = line.lower()
            if "revert" in lower or "error" in lower:
                return line.strip()
        return None
