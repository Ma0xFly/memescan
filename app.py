"""
app.py — Streamlit 仪表盘入口（The Rug-Pull Radar）

在后台守护线程中运行 MonitorService（使用独立的 asyncio 事件循环），
同时 Streamlit 在主线程中管理 UI 渲染。

🔧 重要设计: 后台线程不能访问 st.session_state！
   因此用模块级列表 (_shared_reports, _shared_log) 作为线程间共享存储，
   主线程每次渲染时从共享列表同步到 session_state。

启动方式: `streamlit run app.py`
"""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
from loguru import logger

from core.config import get_settings
from core.db import init_db
from core.logging import setup_logging
from core.web3_provider import check_connection
from domain.models import AuditReport, Token
from services.analyzer import AnalysisService
from services.monitor import MonitorService
from services.simulator import SimulationService


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔧 线程安全的共享存储
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# 为什么不用 st.session_state？
#   Streamlit 的 session_state 绑定在主线程的 ScriptRunContext 上。
#   后台线程（MonitorService 的回调）无法访问它，会抛出:
#     "st.session_state has no attribute ... missing ScriptRunContext"
#
# 解决方案:
#   用模块级 Python 列表存数据（GIL 保证 append 是线程安全的），
#   主线程渲染时把新数据同步到 session_state 用于展示。
#

_shared_reports: list[AuditReport] = []   # 后台线程写入, 主线程读取
_shared_log: list[str] = []               # 后台线程写入, 主线程读取

REPORTS_DIR = Path(__file__).resolve().parent / "reports"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 页面配置
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

st.set_page_config(
    page_title="🔍 MemeScan — The Rug-Pull Radar",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 会话状态初始化
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if "reports" not in st.session_state:
    st.session_state.reports: list[AuditReport] = []
if "monitor_running" not in st.session_state:
    st.session_state.monitor_running: bool = False
if "monitor_thread" not in st.session_state:
    st.session_state.monitor_thread: threading.Thread | None = None
if "event_loop" not in st.session_state:
    st.session_state.event_loop: asyncio.AbstractEventLoop | None = None
if "scan_log" not in st.session_state:
    st.session_state.scan_log: list[str] = []
if "synced_count" not in st.session_state:
    st.session_state.synced_count: int = 0


def _sync_shared_to_session() -> bool:
    """将后台线程写入的共享数据同步到 session_state。

    返回: 是否有新数据需要刷新页面。
    """
    changed = False

    # 同步报告
    if len(_shared_reports) > st.session_state.synced_count:
        new_reports = _shared_reports[st.session_state.synced_count:]
        for r in new_reports:
            st.session_state.reports.insert(0, r)
        st.session_state.synced_count = len(_shared_reports)
        changed = True

    # 同步日志
    if len(_shared_log) > len(st.session_state.scan_log):
        st.session_state.scan_log = list(_shared_log)
        changed = True

    return changed


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 后台事件循环（用于运行异步服务）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _run_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """守护线程的目标函数。"""
    asyncio.set_event_loop(loop)
    loop.run_forever()


def get_or_create_loop() -> asyncio.AbstractEventLoop:
    """返回后台事件循环，如不存在则创建。"""
    if st.session_state.event_loop is None or st.session_state.event_loop.is_closed():
        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=_run_event_loop, args=(loop,), daemon=True)
        thread.start()
        st.session_state.event_loop = loop
        st.session_state.monitor_thread = thread
    return st.session_state.event_loop


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Markdown 报告保存
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _save_md_report(report: AuditReport) -> str:
    """保存审计报告为 Markdown 文件，返回文件名。"""
    from scripts.pipeline import generate_markdown_report
    REPORTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{report.token.symbol}_{report.token.address[:10]}.md"
    filepath = REPORTS_DIR / filename
    md = generate_markdown_report(report.token, report)
    filepath.write_text(md, encoding="utf-8")
    return filename


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 异步辅助函数（在后台线程执行，不能碰 session_state！）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _on_new_pair(token: Token) -> None:
    """MonitorService 检测到新交易对时触发的回调。

    ⚠️ 此函数在后台线程的事件循环中运行，所以只写入 _shared_*，
       不碰 st.session_state。
    """
    log_msg = f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] 新交易对: {token.symbol} — {token.address[:16]}…"
    _shared_log.append(log_msg)
    logger.info(log_msg)

    # 自动执行仿真和分析。
    try:
        async with SimulationService() as sim:
            result = await sim.simulate_buy_sell(token.address)

        analyzer = AnalysisService()
        report = await analyzer.analyze(token, result)

        # 写入共享列表（主线程会同步到 session_state）
        _shared_reports.append(report)

        # 同时保存 MD 报告到 reports/ 目录
        filename = _save_md_report(report)
        _shared_log.append(f"  📄 报告已保存: {filename}")
        logger.info("📄 报告已保存: {}", filename)
    except Exception as exc:
        error_msg = f"[错误] 代币 {token.address[:16]}… 仿真失败: {exc}"
        _shared_log.append(error_msg)
        logger.error(error_msg)


async def _manual_scan(token_address: str) -> AuditReport | None:
    """对手动输入的代币地址执行一次性仿真 + 分析。"""
    token = Token(address=token_address, pair_address="0x" + "0" * 40)
    try:
        async with SimulationService() as sim:
            result = await sim.simulate_buy_sell(token_address)
        analyzer = AnalysisService()
        report = await analyzer.analyze(token, result)
        if report:
            _save_md_report(report)
        return report
    except Exception as exc:
        logger.error("手动扫描失败: {}", exc)
        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# UI 布局
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def render_sidebar() -> None:
    """侧边栏：控制面板和状态显示。"""
    settings = get_settings()

    st.sidebar.title("⚙️ 控制面板")
    st.sidebar.markdown("---")

    # 连接状态
    loop = get_or_create_loop()
    future = asyncio.run_coroutine_threadsafe(check_connection(), loop)
    try:
        connected = future.result(timeout=5)
    except Exception:
        connected = False

    if connected:
        st.sidebar.success("🟢 RPC 已连接")
    else:
        st.sidebar.error("🔴 RPC 连接断开")

    st.sidebar.caption(f"RPC: `{settings.rpc_url[:40]}…`")
    st.sidebar.caption(f"链 ID: `{settings.chain_id}`")

    st.sidebar.markdown("---")

    # 监控控制
    st.sidebar.subheader("🔎 实时监控")
    if not st.session_state.monitor_running:
        if st.sidebar.button("▶️ 启动监控", use_container_width=True):
            monitor = MonitorService(on_new_pair=_on_new_pair)
            asyncio.run_coroutine_threadsafe(monitor.start(), loop)
            st.session_state.monitor_running = True
            st.rerun()
    else:
        st.sidebar.info("监控运行中…")
        if st.sidebar.button("⏹️ 停止监控", use_container_width=True):
            st.session_state.monitor_running = False
            st.rerun()

    st.sidebar.markdown("---")

    # 手动扫描
    st.sidebar.subheader("🎯 手动扫描")
    manual_addr = st.sidebar.text_input(
        "代币地址",
        placeholder="0x…",
        key="manual_address",
    )
    if st.sidebar.button("🔬 扫描代币", use_container_width=True) and manual_addr:
        with st.sidebar.status("扫描中…", expanded=True):
            future = asyncio.run_coroutine_threadsafe(
                _manual_scan(manual_addr), loop
            )
            try:
                report = future.result(timeout=60)
                if report:
                    st.session_state.reports.insert(0, report)
                    st.sidebar.success("扫描完成！报告已保存到 reports/ 目录")
                else:
                    st.sidebar.error("扫描失败 — 请查看日志。")
            except Exception as exc:
                st.sidebar.error(f"错误: {exc}")
        st.rerun()


def render_main() -> None:
    """主内容区域：审计报告仪表盘。"""
    st.title("🔍 MemeScan — The Rug-Pull Radar")
    st.caption("基于 Anvil 分叉仿真的实时 Memecoin 安全扫描")

    # ── 指标概览行 ──────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    reports = st.session_state.reports

    total = len(reports)
    honeypots = sum(1 for r in reports if r.simulation.is_honeypot)
    dangerous = sum(1 for r in reports if r.is_dangerous)
    safe = total - dangerous

    col1.metric("📊 已扫描总数", total)
    col2.metric("🍯 蜜罐", honeypots)
    col3.metric("⚠️ 高风险", dangerous)
    col4.metric("✅ 低风险", safe)

    st.markdown("---")

    # ── 审计报告列表 ────────────────────────────────────────────
    if reports:
        st.subheader("📋 审计报告")
        for idx, report in enumerate(reports):
            severity = "🔴" if report.is_dangerous else "🟡" if report.risk_score > 30 else "🟢"
            with st.expander(
                f"{severity} {report.token.symbol} — 评分: {report.risk_score:.0f}/100 | {report.token.address[:20]}…",
                expanded=(idx == 0),
            ):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**代币信息**")
                    st.text(f"地址:     {report.token.address}")
                    st.text(f"符号:     {report.token.symbol}")
                    st.text(f"交易对:   {report.token.pair_address}")
                with c2:
                    st.markdown("**仿真结果**")
                    st.text(f"可买入:   {'✅' if report.simulation.can_buy else '❌'}")
                    st.text(f"可卖出:   {'✅' if report.simulation.can_sell else '❌'}")
                    st.text(f"蜜罐:     {'🍯 是' if report.simulation.is_honeypot else '否'}")
                    st.text(f"买入 Gas: {report.simulation.buy_gas:,}")
                    st.text(f"卖出 Gas: {report.simulation.sell_gas:,}")
                    st.text(f"买入税:   {report.simulation.buy_tax_pct:.1f}%")
                    st.text(f"卖出税:   {report.simulation.sell_tax_pct:.1f}%")

                if report.risk_flags:
                    flags_str = " | ".join(f"🚩 {f.value}" for f in report.risk_flags)
                    st.warning(f"**风险标签:** {flags_str}")

                if report.simulation.revert_reason:
                    st.error(f"**Revert 原因:** {report.simulation.revert_reason}")

                if report.llm_summary:
                    st.info(f"**分析摘要:** {report.llm_summary}")
    else:
        st.info(
            "暂无报告。请从侧边栏启动实时监控或执行手动扫描。"
        )

    # ── 实时日志 ────────────────────────────────────────────────
    if st.session_state.scan_log:
        st.markdown("---")
        st.subheader("📜 事件日志")
        log_text = "\n".join(st.session_state.scan_log[-50:])
        st.code(log_text, language="text")

    # ── 同步后台监控数据（仅在有新数据时刷新页面）──────────────
    if st.session_state.monitor_running:
        if _sync_shared_to_session():
            st.rerun()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 主入口
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main() -> None:
    """应用入口函数。"""
    setup_logging()

    # 初始化数据库表（通过后台事件循环执行）。
    loop = get_or_create_loop()
    asyncio.run_coroutine_threadsafe(init_db(), loop)

    # 同步后台数据到 session_state
    _sync_shared_to_session()

    render_sidebar()
    render_main()


if __name__ == "__main__":
    main()
else:
    # Streamlit 在每次交互时会重新执行脚本。
    main()
