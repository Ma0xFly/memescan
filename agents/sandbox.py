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
                    result = await sim.simulate_buy_sell(token, amount)
                    if result and not result.is_honeypot:
                        result = await self._try_rug_pull_replay(sim, token, result)
                    return result
            except Exception as e:
                self.log_error(f"仿真失败: {e}")
                return None

    async def _try_rug_pull_replay(
        self, sim: SimulationService, token: Token, base_result: SimulationResult
    ) -> SimulationResult:
        """尝试扮演项目方恶意提权并重放跑路攻击。"""
        # 我们优先读取合约的 owner
        owner_address = await sim._cast_call_raw(
            rpc=f"http://127.0.0.1:{sim._anvil_port}",
            to=token.address,
            sig="owner()(address)",
            args=[]
        )
        
        # 解析 cast_call_raw 返回的地址
        if owner_address and "0x" in owner_address:
            # 取最后 40 位
            owner_address = "0x" + owner_address[-40:]
            if owner_address == "0x0000000000000000000000000000000000000000":
                owner_address = token.deployer
        else:
            owner_address = token.deployer

        if not owner_address or owner_address == "0x0000000000000000000000000000000000000000":
            return base_result

        self.log(f"⚔️ [攻防演练] 锁定 Owner 权限: {owner_address[:10]}...")
        
        success = await sim.impersonate_account(owner_address)
        if not success:
            self.log("⚠️ [提权失败] 无法接管该账户。")
            return base_result
            
        self.log("✅ [成功] 已在沙盒中提权为 Owner！")

        attack_payloads = [
            {"sig": "setBlacklist(address,bool)", "args": [SimulationService.ANVIL_SENDER, "true"], "desc": "拉黑买家"},
            {"sig": "blacklistAddress(address,bool)", "args": [SimulationService.ANVIL_SENDER, "true"], "desc": "拉黑买家"},
            {"sig": "setTaxFeePercent(uint256)", "args": ["99"], "desc": "修改税率为99%"},
            {"sig": "setTax(uint256)", "args": ["99"], "desc": "修改税率为99%"},
            {"sig": "setFees(uint256,uint256)", "args": ["99", "99"], "desc": "修改买卖税率为99%"},
            {"sig": "pauseTrading()", "args": [], "desc": "暂停交易"},
        ]

        rug_success = False
        
        for payload in attack_payloads:
            self.log(f"😈 [执行] 尝试调用 {payload['sig']}")
            receipt = await sim.cast_send_unlocked(
                to=token.address,
                sig=payload["sig"],
                args=payload["args"],
                sender=owner_address
            )
            
            if receipt["success"]:
                # 验证是否成功阻断交易
                verify_result = await sim.simulate_buy_sell(token, "0.01")
                
                if verify_result.is_honeypot or verify_result.sell_tax_pct > 90:
                    self.log(f"🔴 [实锤] 用户已无法卖出筹码！🚨 判定为蜜罐！")
                    rug_success = True
                    
                    return base_result.model_copy(update={
                        "is_honeypot": True,
                        "revert_reason": f"Rug-Pull 演练实锤: {payload['desc']}",
                        "rug_pull_replayed": True,
                        "rug_pull_method": payload["sig"],
                        "rug_pull_success": True
                    })

        if not rug_success:
            self.log("🛡️ [演练结束] 尝试了常见恶意后门，暂未攻破。")
            return base_result.model_copy(update={"rug_pull_replayed": True})

        return base_result
