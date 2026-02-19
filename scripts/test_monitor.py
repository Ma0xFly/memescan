"""
scripts/test_monitor.py — MonitorService 独立测试脚本

这个脚本的作用：
  在终端直接运行 MonitorService，观察它能不能捕获以太坊上新创建的交易对。
  不依赖 Streamlit，纯命令行输出，方便调试。

运行方式:
  cd /MemeScan
  python -m scripts.test_monitor

退出方式:
  按 Ctrl+C，MonitorService 会优雅停止。
"""

import asyncio
import signal

from loguru import logger

# ── 导入我们自己写的模块 ──────────────────────────────────────────
# setup_logging: 初始化日志系统（彩色终端输出 + 文件记录）
from core.logging import setup_logging
# check_connection: 验证 RPC 节点是否可用
from core.web3_provider import check_connection
# Token: 代币的数据模型（地址、符号、交易对地址等）
from domain.models import Token
# MonitorService: 我们的核心 — 事件监听器
from services.monitor import MonitorService


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 回调函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# 什么是回调（Callback）？
#   MonitorService 在监听到新交易对时，不直接处理业务逻辑，
#   而是调用一个你预先"注册"进去的函数。
#   这样做的好处是：MonitorService 不需要知道"检测到新代币后要干什么"，
#   它只负责"发现"，具体怎么处理由你的回调函数决定。
#
#   以后接入仿真引擎时，只需要把这个回调替换成仿真逻辑即可，
#   MonitorService 本身代码完全不用改。
#

async def on_new_pair(token: Token) -> None:
    """MonitorService 检测到新的 WETH 交易对时，会自动调用这个函数。

    参数:
        token: 包含新代币信息的 Token 对象
              - token.address:      代币的合约地址
              - token.pair_address:  Uniswap 交易对的合约地址
              - token.symbol:        代币符号（目前默认为 "???"，因为还没实现查询）
    """
    # 先简单打印出来，确认解码正确就行
    logger.info(
        "\n"
        "🚨 ═══════════════════════════════════════════════\n"
        "   新代币发现!\n"
        "   代币地址: {}\n"
        "   交易对:   {}\n"
        "   符号:     {}\n"
        "═══════════════════════════════════════════════════",
        token.address,
        token.pair_address,
        token.symbol,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 主函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def main() -> None:
    # ── 第 1 步: 初始化日志 ─────────────────────────────────────
    # 这会配置 loguru，让日志输出彩色格式到终端，同时写入 logs/ 目录
    setup_logging()

    # ── 第 2 步: 检查 RPC 连接 ──────────────────────────────────
    # 在启动监控之前，先确认能连上以太坊节点
    # 如果连不上，就没必要启动监控了
    logger.info("正在检查 RPC 连接...")
    if not await check_connection():
        logger.error("❌ RPC 连接失败！请检查 .env 中的 RPC_URL 是否正确")
        return  # 直接退出，不启动监控
    logger.info("✅ RPC 连接成功")

    # ── 第 3 步: 创建 MonitorService 实例 ───────────────────────
    # 把我们定义的回调函数 on_new_pair 传进去
    # 当 MonitorService 发现新的 WETH 交易对时，就会自动调用它
    monitor = MonitorService(on_new_pair=on_new_pair)

    # ── 第 4 步: 注册 Ctrl+C 信号处理 ──────────────────────────
    # 问题: MonitorService.start() 是一个死循环（while not shutdown），
    #       如果你直接按 Ctrl+C，Python 会抛出 KeyboardInterrupt，
    #       可能在中间状态退出，不够优雅。
    #
    # 解决: 用 signal 模块拦截 Ctrl+C 信号，
    #       收到信号后调用 monitor.stop()，
    #       它会设置 shutdown_event，让循环在下一轮自然退出。
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.create_task(monitor.stop())
        )

    # ── 第 5 步: 启动监控 ──────────────────────────────────────
    # 这一行会阻塞，直到 monitor.stop() 被调用
    # 在此期间，MonitorService 会每 2 秒轮询一次新事件
    logger.info(
        "🔍 开始监控 PairCreated 事件...\n"
        "   轮询间隔: 每 2 秒\n"
        "   监控目标: Uniswap V2 Factory\n"
        "   按 Ctrl+C 停止"
    )
    await monitor.start()

    # 如果走到这里，说明 monitor.stop() 已被调用
    logger.info("👋 监控已停止，程序退出")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 入口
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# if __name__ == "__main__" 的意思是：
#   只有当这个文件被"直接运行"时才执行下面的代码。
#   如果是被其他文件 import 的，就不会执行。
#
# asyncio.run(main()) 的意思是：
#   启动一个 asyncio 事件循环，运行 main() 协程。
#   我们的 MonitorService 是异步的（async），必须在事件循环中运行。
#

if __name__ == "__main__":
    asyncio.run(main())
