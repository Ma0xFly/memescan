import re

with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

replacement_func = """
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# UI 布局
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@st.dialog("🛡️ MemeScan 深度安全分析", width="large")
def show_scan_dialog(manual_addr: str, manual_chain: str, loop: asyncio.AbstractEventLoop):
    st.markdown(f"**目标代币:** `{manual_addr}` | **网络:** `{manual_chain.upper()}`")
    
    import time as _time
    log_snapshot = len(_shared_log)
    
    status_text = st.empty()
    status_text.info("⏳ 正在调度多智能体，初始化沙盒...")
    
    log_container = st.empty()
    logs_to_show = []

    future = asyncio.run_coroutine_threadsafe(
        _manual_scan(manual_addr, manual_chain), loop
    )
    
    while not future.done():
        _time.sleep(0.5)
        new_entries = _shared_log[log_snapshot:]
        if new_entries:
            logs_to_show.extend(new_entries)
            log_snapshot = len(_shared_log)
            # 制造自动滚动的终端效果
            log_text = "\\n".join(logs_to_show[-20:])
            log_container.code(log_text, language="text")
            
    final_entries = _shared_log[log_snapshot:]
    if final_entries:
        logs_to_show.extend(final_entries)
        
    log_text = "\\n".join(logs_to_show[-20:])
    log_container.code(log_text, language="text")
    
    try:
        report = future.result()
        if report:
            st.session_state.reports.insert(0, report)
            status_text.success("✅ 多智能体审计完成！分析报告已生成。")
        else:
            status_text.error("❌ 扫描失败，请检查日志。")
    except Exception as exc:
        status_text.error(f"❌ 运行错误: {exc}")
        
    st.markdown("---")
    if st.button("了解，返回报告大盘", use_container_width=True, type="primary"):
        st.rerun()

"""

content = content.replace(
    "# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n# UI 布局\n# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n",
    replacement_func
)

sidebar_old = """    if st.sidebar.button("🔬 扫描代币", use_container_width=True) and manual_addr:
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
        st.rerun()"""

sidebar_new = """    if st.sidebar.button("🔬 扫描代币", use_container_width=True) and manual_addr:
        show_scan_dialog(manual_addr, manual_chain, loop)"""

content = content.replace(sidebar_old, sidebar_new)

with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)

