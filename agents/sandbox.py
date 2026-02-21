"""
agents/sandbox.py — 沙盒仿真 Agent

封装 SimulationService，在 Anvil 分叉环境中执行买卖仿真。
V2 升级: 支持多额度仿真 + asyncio.Lock 防止端口冲突。
"""

from __future__ import annotations

import asyncio
from typing import Any

from agents.base import BaseAgent
from services.simulator import SimulationService
from domain.models import Token, SimulationResult


# 全局锁: 确保同一时间只有一个 Anvil 实例运行 (共享 8545 端口)
_anvil_lock = asyncio.Lock()


class SandboxAgent(BaseAgent):
    """沙盒仿真 Agent — 管理 Anvil 分叉，执行买卖仿真。

    自主决策:
      - 小额仿真通过后，可决定是否追加大额测试
      - 检测反鲸鱼机制 (小额能卖，大额不能卖)
    """

    name = "SandboxAgent"

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        """执行仿真。

        task keys:
          token: Token 对象
          amounts: list[str]  可选，ETH 金额列表，默认 ["0.1"]

        返回:
          simulation: SimulationResult (主要仿真结果)
          all_results: list[dict]  (多额度仿真结果)
        """
        token: Token = task["token"]
        amounts = task.get("amounts", ["0.1"])

        all_results = []
        primary_result = None

        for amount in amounts:
            self.log(f"仿真 {token.symbol or '???'} — 金额: {amount} ETH")
            result = await self._simulate_with_lock(token, amount)

            if result:
                all_results.append({
                    "amount_eth": amount,
                    "can_buy": result.can_buy,
                    "can_sell": result.can_sell,
                    "buy_tax_pct": result.buy_tax_pct,
                    "sell_tax_pct": result.sell_tax_pct,
                    "is_honeypot": result.is_honeypot,
                })
                if primary_result is None:
                    primary_result = result
            else:
                all_results.append({
                    "amount_eth": amount,
                    "error": "仿真失败",
                })

        return {
            "simulation": primary_result,
            "all_results": all_results,
        }

    async def decide(self, context: dict[str, Any]) -> str:
        """决策: 小额通过后是否需要大额测试。"""
        sim = context.get("simulation")
        if not sim:
            return "done"

        # 如果小额仿真通过了，可以追加大额测试检测反鲸鱼
        if sim.can_buy and sim.can_sell and sim.buy_tax_pct < 5:
            return "test_large_amount"

        return "done"

    async def _simulate_with_lock(
        self, token: Token, amount: str = "0.1"
    ) -> SimulationResult | None:
        """带锁的仿真 — 防止多个 Anvil 抢占同一端口。"""
        async with _anvil_lock:
            try:
                async with SimulationService() as sim:
                    return await sim.simulate_buy_sell(token, amount)
            except Exception as e:
                self.log_error(f"仿真失败: {e}")
                return None
