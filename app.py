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
from agents.coordinator import CoordinatorAgent
from agents.scanner import ScannerAgent
from agents.reporter import ReporterAgent


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

_shared_reports: list[dict] = []   # 后台线程写入, 主线程读取
_shared_log: list[str] = []               # 后台线程写入, 主线程读取


def _ui_log_sink(message) -> None:
    """Loguru 自定义 sink：将 Agent/Service 的关键日志推送到前端事件日志。

    只捕获来自 agents.* 和 services.* 模块的 INFO 级别日志,
    让用户在前端能实时看到扫描进度，而不是以为卡住了。
    """
    record = message.record
    module = record["name"]  # e.g. "agents.base", "services.simulator"

    # 只捕获 agent 和 service 的 INFO/WARNING 级别消息
    if record["level"].no < 20:  # DEBUG 级别跳过
        return
    if not (module.startswith("agents.") or module.startswith("services.")):
        return

    # 格式化为简洁的前端显示
    time_str = record["time"].strftime("%H:%M:%S")
    text = str(record["message"]).strip()
    _shared_log.append(f"[{time_str}] {text}")


# 注册 sink（只注册一次，避免重复）
from loguru import logger as _loguru_logger
_loguru_logger.add(_ui_log_sink, level="INFO", enqueue=False)

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
    st.session_state.reports: list[dict] = []
if "monitor_running" not in st.session_state:
    st.session_state.monitor_running: bool = False
if "monitor_thread" not in st.session_state:
    st.session_state.monitor_thread: threading.Thread | None = None
if "event_loop" not in st.session_state:
    st.session_state.event_loop: asyncio.AbstractEventLoop | None = None
if "scan_log" not in st.session_state:
    st.session_state.scan_log: list[str] = []
if "synced_disk_files" not in st.session_state:
    # 启动时，将磁盘上现有的所有报告标记为已同步，这样它们只出现在“历史报告”中，而不会污染“实时报告”标签
    initial_files = set(f.name for f in REPORTS_DIR.glob("*.md")) if REPORTS_DIR.exists() else set()
    st.session_state.synced_disk_files: set = initial_files
if "synced_count" not in st.session_state:
    st.session_state.synced_count: int = 0


def _sync_shared_to_session() -> bool:
    """将后台线程写入的共享数据 + 磁盘新报告 同步到 session_state。

    返回: 是否有新数据需要刷新页面。
    """
    import re
    changed = False

    # ── 1. 同步内存中的报告（来自本进程的后台线程） ──
    if len(_shared_reports) > st.session_state.synced_count:
        new_reports = _shared_reports[st.session_state.synced_count:]
        for r in new_reports:
            st.session_state.reports.insert(0, r)
        st.session_state.synced_count = len(_shared_reports)
        changed = True

    # ── 2. 同步磁盘上的新报告（跨进程也能同步） ──
    if REPORTS_DIR.exists():
        pattern = re.compile(r"^(\d{8})_(\d{6})_(.+?)_(0x[a-f0-9]+)\.md$", re.IGNORECASE)
        for f in sorted(REPORTS_DIR.glob("*.md"), reverse=True):
            if f.name in st.session_state.synced_disk_files:
                continue
            m = pattern.match(f.name)
            if not m:
                st.session_state.synced_disk_files.add(f.name)
                continue
            # 把磁盘报告包装成和内存报告兼容的格式
            st.session_state.synced_disk_files.add(f.name)
            try:
                content = f.read_text(encoding="utf-8")
                symbol = m.group(3)
                address = m.group(4)
                date_str = m.group(1)
                time_str = m.group(2)
                time_display = f"{time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}"
                st.session_state.reports.insert(0, {
                    "disk_report": True,
                    "filename": f.name,
                    "symbol": symbol,
                    "address": address,
                    "time": time_display,
                    "date": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}",
                    "content": content,
                })
                changed = True
            except Exception:
                pass

    # ── 3. 同步日志 ──
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

async def _on_new_pair(token: Token, chain_name: str = "ethereum") -> None:
    """ScannerAgent 检测到新交易对时触发的回调。"""
    log_msg = f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] 新交易对 ({chain_name}): {token.symbol} — {token.address[:16]}…"
    _shared_log.append(log_msg)
    logger.info(log_msg)

    try:
        coordinator = CoordinatorAgent(chain_name=chain_name)
        result = await coordinator.run({"token": token})
        _shared_reports.append({
            "report": result["report"],
            "decisions": result["decisions"]
        })
        _shared_log.append(f"  📄 报告已保存: {result['file_path']}")
        logger.info("📄 报告已保存: {}", result['file_path'])
    except Exception as exc:
        error_msg = f"[错误] 代币 {token.address[:16]}… 仿真失败: {exc}"
        _shared_log.append(error_msg)
        logger.error(error_msg)


async def _manual_scan(token_address: str, chain_name: str = "ethereum") -> dict | None:
    """对手动输入的代币地址执行一次性编排审计。"""
    token = Token(address=token_address, pair_address="0x" + "0" * 40)
    try:
        coordinator = CoordinatorAgent(chain_name=chain_name)
        result = await coordinator.run({"token": token})
        return {
            "report": result["report"],
            "decisions": result["decisions"]
        }
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

    # 监控控制 (先选择链，再检查对应链的网络)
    st.sidebar.subheader("🔎 实时监控")
    selected_chain = st.sidebar.selectbox("选择链", ["ethereum", "bsc"])

    st.sidebar.markdown("---")

    # 连接状态
    loop = get_or_create_loop()
    future = asyncio.run_coroutine_threadsafe(check_connection(chain_name=selected_chain), loop)
    try:
        connected = future.result(timeout=5)
    except Exception:
        connected = False

    if connected:
        st.sidebar.success(f"🟢 {selected_chain.upper()} RPC 已连接")
    else:
        st.sidebar.error(f"🔴 {selected_chain.upper()} RPC 连接断开")

    display_rpc = settings.rpc_url if selected_chain == "ethereum" else settings.bsc_rpc_url
    display_chain_id = settings.chain_id if selected_chain == "ethereum" else settings.bsc_chain_id
    st.sidebar.caption(f"RPC: `{display_rpc[:40]}…`")
    st.sidebar.caption(f"链 ID: `{display_chain_id}`")
    if not st.session_state.monitor_running:
        if st.sidebar.button("▶️ 启动监控", use_container_width=True):
            # 将 chain_name 绑定到回调函数
            from functools import partial
            bound_callback = partial(_on_new_pair, chain_name=selected_chain)
            scanner = ScannerAgent(on_new_pair=bound_callback, chain_name=selected_chain)
            asyncio.run_coroutine_threadsafe(scanner.run({"action": "start"}), loop)
            st.session_state.scanner = scanner
            st.session_state.monitor_running = True
            st.rerun()
    else:
        st.sidebar.info("监控运行中…")
        col_stop, col_refresh = st.sidebar.columns(2)
        with col_stop:
            if st.button("⏹️ 停止", use_container_width=True):
                if "scanner" in st.session_state:
                    st.session_state.scanner.stop()
                st.session_state.monitor_running = False
                st.rerun()
        with col_refresh:
            if st.button("🔄 刷新", use_container_width=True):
                _sync_shared_to_session()
                st.rerun()

    st.sidebar.markdown("---")

    # 手动扫描
    st.sidebar.subheader("🎯 手动扫描")
    manual_chain = st.sidebar.selectbox("选择链 (手动扫描)", ["ethereum", "bsc"], key="manual_chain")
    manual_addr = st.sidebar.text_input(
        "代币地址",
        placeholder="0x…",
        key="manual_address",
    )
    if st.sidebar.button("🔬 扫描代币", use_container_width=True) and manual_addr:
        import time as _time
        log_snapshot = len(_shared_log)  # 记录扫描前的日志位置
        future = asyncio.run_coroutine_threadsafe(
            _manual_scan(manual_addr, manual_chain), loop
        )
        with st.sidebar.status("⏳ 扫描中…", expanded=True) as status:
            while not future.done():
                # 每 0.5 秒检查一次新日志并显示在状态框中
                _time.sleep(0.5)
                new_entries = _shared_log[log_snapshot:]
                if new_entries:
                    for entry in new_entries:
                        st.write(entry)
                    log_snapshot = len(_shared_log)
            # 扫描完成后，刷出最后的日志
            final_entries = _shared_log[log_snapshot:]
            for entry in final_entries:
                st.write(entry)
            try:
                report = future.result()
                if report:
                    st.session_state.reports.insert(0, report)
                    status.update(label="✅ 扫描完成", state="complete")
                else:
                    status.update(label="❌ 扫描失败", state="error")
            except Exception as exc:
                status.update(label=f"❌ 错误: {exc}", state="error")
        st.rerun()


def _load_reports_from_disk() -> dict[str, list[dict]]:
    """扫描 reports/ 目录，按日期分组返回报告列表。

    返回:
        {"2026-02-24": [{"filename": "...", "time": "11:39:07", "symbol": "FLOKI",
                         "address": "0xfb5b...", "path": Path(...), "content": "..."},
                        ...],
         ...}
    日期按降序排列（最新在前），每个日期内的报告也按时间降序排列。
    """
    import re
    reports_dir = REPORTS_DIR
    if not reports_dir.exists():
        return {}

    # 文件名格式: YYYYMMDD_HHMMSS_SYMBOL_ADDRESS.md
    pattern = re.compile(r"^(\d{8})_(\d{6})_(.+?)_(0x[a-f0-9]+)\.md$", re.IGNORECASE)

    grouped: dict[str, list[dict]] = {}
    for f in sorted(reports_dir.glob("*.md"), reverse=True):
        m = pattern.match(f.name)
        if not m:
            continue
        date_str = m.group(1)  # e.g. 20260224
        time_str = m.group(2)  # e.g. 113507
        symbol = m.group(3)
        address = m.group(4)

        date_display = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        time_display = f"{time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}"

        entry = {
            "filename": f.name,
            "date": date_display,
            "time": time_display,
            "symbol": symbol,
            "address": address,
            "path": f,
        }

        grouped.setdefault(date_display, []).append(entry)

    # 每个日期组内按时间降序
    for date_key in grouped:
        grouped[date_key].sort(key=lambda x: x["time"], reverse=True)

    return dict(sorted(grouped.items(), reverse=True))


def render_main() -> None:
    """主内容区域：审计报告仪表盘。"""
    st.title("🔍 MemeScan — The Rug-Pull Radar")
    st.caption("基于 Anvil 分叉仿真的实时 Memecoin 安全扫描")

    # ── 指标概览行（基于磁盘报告总数） ────────────────────────
    disk_reports = _load_reports_from_disk()
    total_disk = sum(len(v) for v in disk_reports.values())
    live_reports = st.session_state.reports

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📊 历史报告总数", total_disk)
    col2.metric("📡 本次扫描", len(live_reports))

    # 只统计内存中的结构化报告（磁盘报告没有 report 对象）
    agent_reports = [item for item in live_reports if not item.get("disk_report")]
    honeypots = sum(1 for item in agent_reports if item["report"].simulation.is_honeypot)
    dangerous = sum(1 for item in agent_reports if item["report"].is_dangerous)
    col3.metric("⚠️ 本次高风险", dangerous)
    col4.metric("🍯 本次蜜罐", honeypots)

    st.markdown("---")

    # ── 双标签页: 实时 / 历史 ─────────────────────────────────
    tab_live, tab_history = st.tabs(["📡 实时报告", "📁 历史报告"])

    # ━━━ Tab 1: 实时报告 (内存中的 Agent 结果) ━━━━━━━━━━━━━
    with tab_live:
        if live_reports:
            for idx, item in enumerate(live_reports):
                # 判断是内存报告还是磁盘报告
                if item.get("disk_report"):
                    # ── 磁盘加载的报告 (Markdown 渲染) ──
                    label = f"📄 [{item['date']} {item['time']}] {item['symbol']} — `{item['address']}`"
                    with st.expander(label, expanded=(idx == 0)):
                        st.markdown(item["content"])
                else:
                    # ── 内存中的 Agent 实时报告 (结构化渲染) ──
                    report = item["report"]
                    decisions = item.get("decisions", [])
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

                        if decisions:
                            st.info(f"**🤖 Agent 决策链路:** {' ➡️ '.join(decisions)}")
        else:
            st.info("暂无实时报告。请从侧边栏启动实时监控或执行手动扫描。")

    # ━━━ Tab 2: 历史报告 (从 reports/ 目录加载) ━━━━━━━━━━━━
    with tab_history:
        if disk_reports:
            for date_key, entries in disk_reports.items():
                st.subheader(f"📅 {date_key}  ({len(entries)} 份)")
                for entry in entries:
                    # 根据 symbol 猜测风险颜色
                    label = f"⏱️ {entry['time']}  |  **{entry['symbol']}**  |  `{entry['address']}`"
                    with st.expander(label, expanded=False):
                        try:
                            content = entry["path"].read_text(encoding="utf-8")
                            st.markdown(content)
                        except Exception as exc:
                            st.error(f"读取报告失败: {exc}")
                        st.download_button(
                            label="⬇️ 下载报告",
                            data=entry["path"].read_bytes(),
                            file_name=entry["filename"],
                            mime="text/markdown",
                            key=f"dl_{entry['filename']}",
                        )
        else:
            st.info("暂无历史报告。reports/ 目录为空。")

    # ── Chat with Contract ────────────────────────────────────
    st.markdown("---")
    st.subheader("💬 Chat with Contract")
    user_question = st.chat_input("输入关于最新审计代币的问题...")
    # Chat 只能用内存中的结构化 Agent 报告（磁盘报告没有 report 对象）
    agent_only = [item for item in live_reports if not item.get("disk_report")]
    if user_question and agent_only:
        current_report = agent_only[0]["report"]
        reporter = ReporterAgent()
        st.chat_message("user").write(user_question)
        with st.spinner("AI 正在思考..."):
            loop = get_or_create_loop()
            future = asyncio.run_coroutine_threadsafe(
                reporter.chat(user_question, current_report), loop
            )
            try:
                answer = future.result(timeout=30)
                st.chat_message("assistant").write(answer)
            except Exception as e:
                st.chat_message("assistant").write(f"⚠️ 查询超时或失败: {e}")
    elif user_question:
        st.chat_message("assistant").write("⚠️ 目前还没有任何审计报告，无法聊天。")

    # ── 实时日志 ────────────────────────────────────────────────
    if st.session_state.scan_log:
        st.markdown("---")
        st.subheader("📜 事件日志")
        log_text = "\n".join(st.session_state.scan_log[-50:])
        st.code(log_text, language="text")

    # ── 同步后台监控数据 ──────────────────────────────────────
    if st.session_state.monitor_running:
        _sync_shared_to_session()
        # 自动刷新，确保新扫描结果能显示出来
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=10000, limit=None, key="monitor_refresh")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 主入口
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main() -> None:
    """应用入口函数。"""
    if "logger_init" not in st.session_state:
        setup_logging()
        st.session_state.logger_init = True

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
