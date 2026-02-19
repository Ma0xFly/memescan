"""
scripts/test_simulator.py — SimulationService 仿真测试脚本

用一个真实的代币地址来测试仿真引擎的完整流程:
  1. 启动 Anvil (fork 主网)
  2. 执行: getAmountsOut → 买入 → 查余额 → approve → 卖出 → 算税率
  3. 打印结构化的 SimulationResult

运行方式:
  cd /home/myx/web3开发/MemeScan
  python -m scripts.test_simulator

⚠️ 注意: 需要 Foundry (anvil + cast) 已安装，且 .env 中配置了真实 RPC URL。
   Anvil 会从主网 Fork，首次启动可能需要 10-30 秒。
"""

import asyncio

from loguru import logger

from core.logging import setup_logging
from services.simulator import SimulationService


# ── 测试用的代币地址 ──────────────────────────────────────────────
#
# 你可以在 https://etherscan.io 上找到任何代币的合约地址。
# 下面用的是 SHIB（柴犬币）— 一个典型的正常 ERC-20 代币。
# 它可以正常买入和卖出，不是蜜罐。
#
# 如果你想测试蜜罐检测，可以把这个地址换成一个已知的蜜罐代币。
#

# SHIB — 正常代币，应该 can_buy=True, can_sell=True, is_honeypot=False
TEST_TOKEN_SHIB = "0x95aD61b0a150d79219dCF64E1E6Cc01f0B64C4cE"

# PEPE — 另一个正常 Memecoin
TEST_TOKEN_PEPE = "0x6982508145454Ce325dDbE47a25d4ec3d2311933"


async def test_one_token(token_address: str, label: str) -> None:
    """对一个代币运行完整仿真并打印结果。"""
    logger.info("=" * 60)
    logger.info("🧪 开始测试: {} ({})", label, token_address[:16] + "...")
    logger.info("=" * 60)

    # async with 保证仿真结束后 Anvil 被自动清理
    async with SimulationService() as sim:
        result = await sim.simulate_buy_sell(token_address)

    # 打印结果
    logger.info("\n📋 仿真结果:")
    logger.info("  代币地址:   {}", result.token_address)
    logger.info("  可买入:     {}", "✅ 是" if result.can_buy else "❌ 否")
    logger.info("  可卖出:     {}", "✅ 是" if result.can_sell else "❌ 否")
    logger.info("  蜜罐:       {}", "🍯 是!" if result.is_honeypot else "✅ 不是")
    logger.info("  买入 Gas:   {:,}", result.buy_gas)
    logger.info("  卖出 Gas:   {:,}", result.sell_gas)
    logger.info("  买入税率:   {:.2f}%", result.buy_tax_pct)
    logger.info("  卖出税率:   {:.2f}%", result.sell_tax_pct)
    if result.revert_reason:
        logger.info("  Revert:     {}", result.revert_reason)
    if result.error_message:
        logger.info("  错误:       {}", result.error_message)


async def main() -> None:
    setup_logging()

    # 测试一个正常代币 — 应该能买卖
    await test_one_token(TEST_TOKEN_SHIB, "SHIB (正常代币)")

    # 如果你想连续测试多个代币，取消下面这行的注释:
    # await test_one_token(TEST_TOKEN_PEPE, "PEPE (正常代币)")


if __name__ == "__main__":
    asyncio.run(main())
