"""
scripts/pipeline.py — 端到端流水线脚本

将所有服务串联成一条自动化链路:
  MonitorService (发现新代币)
       ↓
  SimulationService (Anvil 仿真买卖)
       ↓
  AnalysisService (风险评估)
       ↓
  生成 Markdown 审计报告 → 保存到 reports/ 目录

运行方式:
  cd /home/myx/web3开发/MemeScan
  python -m scripts.pipeline

退出方式:
  按 Ctrl+C，所有服务会优雅停止。
"""

import asyncio
import signal
from datetime import datetime
from pathlib import Path

from loguru import logger

from core.logging import setup_logging
from core.web3_provider import check_connection
from domain.models import AuditReport, Token
from services.analyzer import AnalysisService
from services.monitor import MonitorService
from services.simulator import SimulationService


# ── 报告输出目录 ──────────────────────────────────────────────────
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


# ── 待处理代币队列 ────────────────────────────────────────────────
#
# 为什么用队列而不是直接在回调里仿真？
#   MonitorService 的回调应该尽快返回，不能在里面阻塞太久。
#   如果仿真耗时 10 秒，而这期间又有新代币出现，轮询就会卡住。
#
#   解决: 回调只负责把代币"放进队列"，由另一个独立的协程从队列取出并处理。
#   这样 Monitor 可以持续轮询而不受仿真速度影响。
#
token_queue: asyncio.Queue[Token] = asyncio.Queue()


async def on_new_pair(token: Token) -> None:
    """MonitorService 回调 — 将新代币放入处理队列。"""
    logger.info(
        "🆕 发现新代币: {} | 交易对: {}",
        token.address[:16] + "...",
        token.pair_address[:16] + "...",
    )
    await token_queue.put(token)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 流水线处理器 — 从队列取代币 → 仿真 → 分析 → 保存报告
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def pipeline_worker(shutdown_event: asyncio.Event) -> None:
    """持续从队列取出代币，依次执行仿真和分析。

    处理流程:
      1. 从队列取一个 Token
      2. 启动 Anvil → 仿真买卖 → 关闭 Anvil
      3. 把仿真结果交给 AnalysisService → 得到 AuditReport
      4. 生成 Markdown 报告 → 保存文件
      5. 回到步骤 1
    """
    analyzer = AnalysisService()
    REPORTS_DIR.mkdir(exist_ok=True)

    while not shutdown_event.is_set():
        try:
            # 带超时的队列等待 — 每 2 秒检查一次 shutdown 信号
            try:
                token = await asyncio.wait_for(token_queue.get(), timeout=2.0)
            except asyncio.TimeoutError:
                continue  # 队列为空，继续等待

            logger.info("⚙️ 开始处理: {}", token.address[:16] + "...")

            # ── 仿真 ──────────────────────────────────────────────
            try:
                async with SimulationService() as sim:
                    sim_result = await sim.simulate_buy_sell(token.address)
            except Exception as exc:
                logger.error("仿真失败: {} — {}", token.address[:16], exc)
                continue

            # ── 分析 ──────────────────────────────────────────────
            try:
                report = await analyzer.analyze(token, sim_result)
            except Exception as exc:
                logger.error("分析失败: {} — {}", token.address[:16], exc)
                continue

            # ── 生成 Markdown 报告 → 保存 ─────────────────────────
            md_content = generate_markdown_report(token, report)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}_{token.symbol}_{token.address[:10]}.md"
            filepath = REPORTS_DIR / filename
            filepath.write_text(md_content, encoding="utf-8")

            # ── 终端输出摘要 ──────────────────────────────────────
            risk_emoji = "🔴" if report.risk_score >= 60 else "🟡" if report.risk_score >= 30 else "🟢"
            logger.info(
                "\n"
                "╔══════════════════════════════════════════════════╗\n"
                "║  {} 审计完成: {} ({})                          \n"
                "║  风险评分: {:.0f}/100                             \n"
                "║  蜜罐: {}  买入税: {:.1f}%  卖出税: {:.1f}%      \n"
                "║  报告已保存: {}                                   \n"
                "╚══════════════════════════════════════════════════╝",
                risk_emoji,
                token.symbol,
                token.address[:10] + "...",
                report.risk_score,
                "🍯 是!" if sim_result.is_honeypot else "✅ 否",
                sim_result.buy_tax_pct,
                sim_result.sell_tax_pct,
                filepath.name,
            )

        except Exception as exc:
            logger.error("流水线异常: {}", exc)
            await asyncio.sleep(1.0)

    logger.info("流水线处理器已停止")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Markdown 报告生成
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_markdown_report(token: Token, report: AuditReport) -> str:
    """生成结构化的 Markdown 审计报告。"""
    sim = report.simulation
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 风险等级标签
    if report.risk_score >= 80:
        risk_level = "🔴 极高风险"
    elif report.risk_score >= 60:
        risk_level = "🟠 高风险"
    elif report.risk_score >= 30:
        risk_level = "🟡 中等风险"
    else:
        risk_level = "🟢 低风险"

    # 风险标签列表
    flags_list = ""
    if report.risk_flags:
        for flag in report.risk_flags:
            flags_list += f"- ⚠️ **{flag.value}**\n"
    else:
        flags_list = "- ✅ 未触发任何风险标签\n"

    # 蜜罐状态
    honeypot_status = "🍯 **是 — 该代币为蜜罐！购买后可能无法卖出！**" if sim.is_honeypot else "✅ 否"

    md = f"""# 🔍 代币审计报告 — {token.symbol}

> 生成时间: {now}
> 由 MemeScan (The Rug-Pull Radar) 自动生成

---

## 📌 基本信息

| 项目 | 值 |
|------|-----|
| **代币符号** | {token.symbol} |
| **代币地址** | `{token.address}` |
| **交易对地址** | `{token.pair_address}` |
| **所在链** | Ethereum Mainnet |

---

## 🎯 风险评估

| 项目 | 结果 |
|------|------|
| **风险评分** | **{report.risk_score:.0f} / 100** |
| **风险等级** | {risk_level} |
| **蜜罐检测** | {honeypot_status} |

### 触发的风险标签

{flags_list}
---

## 🧪 仿真结果

| 项目 | 结果 |
|------|------|
| **可买入** | {"✅ 是" if sim.can_buy else "❌ 否"} |
| **可卖出** | {"✅ 是" if sim.can_sell else "❌ 否"} |
| **买入税率** | {sim.buy_tax_pct:.2f}% |
| **卖出税率** | {sim.sell_tax_pct:.2f}% |
| **买入 Gas** | {sim.buy_gas:,} |
| **卖出 Gas** | {sim.sell_gas:,} |

"""

    if sim.revert_reason:
        md += f"""### Revert 原因

```
{sim.revert_reason}
```

"""

    md += f"""---

## 📝 分析摘要

{report.llm_summary}

---

## ⚙️ 仿真参数

- 仿真引擎: Foundry Anvil (主网分叉)
- 买入金额: 0.1 ETH
- DEX: Uniswap V2 Router
- 仿真时间: {now}

---

*本报告由 MemeScan 自动生成，仅供参考，不构成投资建议。*
"""

    return md

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 主函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def main() -> None:
    setup_logging()

    # 检查 RPC 连接
    logger.info("正在检查 RPC 连接...")
    if not await check_connection():
        logger.error("❌ RPC 连接失败！请检查 .env 中的 RPC_URL")
        return
    logger.info("✅ RPC 连接成功")

    # 创建报告目录
    REPORTS_DIR.mkdir(exist_ok=True)
    logger.info("📁 报告将保存到: {}", REPORTS_DIR)

    # 创建共享的 shutdown 事件
    shutdown_event = asyncio.Event()

    # 创建 MonitorService
    monitor = MonitorService(on_new_pair=on_new_pair)

    # 注册 Ctrl+C 信号处理
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            lambda: (
                asyncio.create_task(monitor.stop()),
                shutdown_event.set(),
            )
        )

    logger.info(
        "\n"
        "🚀 MemeScan 流水线已启动!\n"
        "   监控: Uniswap V2 PairCreated 事件\n"
        "   仿真: Anvil 分叉 + cast 买卖\n"
        "   分析: 规则引擎风险评估\n"
        "   报告: Markdown 格式保存到 reports/\n"
        "   按 Ctrl+C 停止\n"
    )

    # 并发启动: Monitor + Pipeline Worker
    # asyncio.gather 同时运行两个协程:
    #   - monitor.start(): 持续轮询新事件
    #   - pipeline_worker(): 持续处理队列中的代币
    await asyncio.gather(
        monitor.start(),
        pipeline_worker(shutdown_event),
    )

    logger.info("👋 MemeScan 流水线已停止")


if __name__ == "__main__":
    asyncio.run(main())
