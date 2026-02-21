import re

with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

# Replace imports
content = content.replace(
    "from services.analyzer import AnalysisService\nfrom services.monitor import MonitorService\nfrom services.simulator import SimulationService",
    "from agents.coordinator import CoordinatorAgent\nfrom agents.scanner import ScannerAgent\nfrom agents.reporter import ReporterAgent"
)

# Replace Type hints
content = content.replace(
    "_shared_reports: list[AuditReport] = []",
    "_shared_reports: list[dict] = []"
)
content = content.replace(
    "st.session_state.reports: list[AuditReport] = []",
    "st.session_state.reports: list[dict] = []"
)

# Replace _on_new_pair
old_on_new_pair = """async def _on_new_pair(token: Token) -> None:
    \"\"\"MonitorService 检测到新交易对时触发的回调。

    ⚠️ 此函数在后台线程的事件循环中运行，所以只写入 _shared_*，
       不碰 st.session_state。
    \"\"\"
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
        logger.error(error_msg)"""

new_on_new_pair = """async def _on_new_pair(token: Token) -> None:
    \"\"\"ScannerAgent 检测到新交易对时触发的回调。\"\"\"
    log_msg = f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] 新交易对: {token.symbol} — {token.address[:16]}…"
    _shared_log.append(log_msg)
    logger.info(log_msg)

    try:
        coordinator = CoordinatorAgent()
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
        logger.error(error_msg)"""

content = content.replace(old_on_new_pair, new_on_new_pair)

# Replace _manual_scan
old_manual_scan = """async def _manual_scan(token_address: str) -> AuditReport | None:
    \"\"\"对手动输入的代币地址执行一次性仿真 + 分析。\"\"\"
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
        return None"""

new_manual_scan = """async def _manual_scan(token_address: str) -> dict | None:
    \"\"\"对手动输入的代币地址执行一次性编排审计。\"\"\"
    token = Token(address=token_address, pair_address="0x" + "0" * 40)
    try:
        coordinator = CoordinatorAgent()
        result = await coordinator.run({"token": token})
        return {
            "report": result["report"],
            "decisions": result["decisions"]
        }
    except Exception as exc:
        logger.error("手动扫描失败: {}", exc)
        return None"""

content = content.replace(old_manual_scan, new_manual_scan)

# Replace sidebar logic
old_sidebar_monitor = """    # 监控控制
    st.sidebar.subheader("🔎 实时监控")
    if not st.session_state.monitor_running:
        if st.sidebar.button("▶️ 启动监控", use_container_width=True):
            monitor = MonitorService(on_new_pair=_on_new_pair)
            asyncio.run_coroutine_threadsafe(monitor.start(), loop)
            st.session_state.monitor_running = True
            st.rerun()
    else:
        st.sidebar.info("监控运行中…")
        col_stop, col_refresh = st.sidebar.columns(2)
        with col_stop:
            if st.button("⏹️ 停止", use_container_width=True):
                st.session_state.monitor_running = False
                st.rerun()"""

new_sidebar_monitor = """    # 监控控制
    st.sidebar.subheader("🔎 实时监控")
    selected_chain = st.sidebar.selectbox("选择链", ["ethereum", "bsc"])
    if not st.session_state.monitor_running:
        if st.sidebar.button("▶️ 启动监控", use_container_width=True):
            scanner = ScannerAgent(on_new_pair=_on_new_pair, chain_name=selected_chain)
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
                st.rerun()"""

content = content.replace(old_sidebar_monitor, new_sidebar_monitor)

# Replace UI layout total logic
old_ui_total = """    total = len(reports)
    honeypots = sum(1 for r in reports if r.simulation.is_honeypot)
    dangerous = sum(1 for r in reports if r.is_dangerous)
    safe = total - dangerous"""

new_ui_total = """    total = len(reports)
    honeypots = sum(1 for item in reports if item["report"].simulation.is_honeypot)
    dangerous = sum(1 for item in reports if item["report"].is_dangerous)
    safe = total - dangerous"""

content = content.replace(old_ui_total, new_ui_total)

# Replace the loop
content = content.replace("for idx, report in enumerate(reports):", "for idx, item in enumerate(reports):\n            report = item[\"report\"]\n            decisions = item[\"decisions\"]")

# Add Chat and Decisions
chat_addition = """                if report.llm_summary:
                    st.info(f"**分析摘要:** {report.llm_summary}")
                
                st.info(f"**🤖 Agent 决策链路:** {' ➡️ '.join(decisions)}")

    st.markdown("---")
    st.subheader("💬 Chat with Contract")
    user_question = st.chat_input("输入关于最新审计代币的问题...")
    if user_question and reports:
        current_report = reports[0]["report"]
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
"""

content = content.replace("                if report.llm_summary:\n                    st.info(f\"**分析摘要:** {report.llm_summary}\")", chat_addition)

with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)

