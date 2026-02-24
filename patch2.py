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
    import os
    
    log_snapshot = len(_shared_log)
    
    status_text = st.empty()
    status_text.info("⏳ 正在调度多智能体，初始化沙盒...")
    
    # 注入自定义 CSS 控制代码块高度并启用垂直滚动条
    st.markdown(
        \"\"\"
        <style>
        .scan-log-container {
            max-height: 400px;
            overflow-y: auto;
        }
        div[data-testid="stCodeBlock"] {
            max-height: 400px;
            overflow-y: auto;
        }
        </style>
        \"\"\",
        unsafe_allow_html=True,
    )
    
    log_container = st.empty()
    logs_to_show = []

    future = asyncio.run_coroutine_threadsafe(
        _manual_scan(manual_addr, manual_chain), loop
    )
    
    def _clean_log(text: str) -> str:
        # 去掉敏感路径信息
        home_dir = os.path.expanduser("~")
        cwd = os.getcwd()
        if home_dir != "/":
            text = text.replace(home_dir, "~")
        text = text.replace(cwd, ".")
        return text
    
    while not future.done():
        _time.sleep(0.5)
        new_entries = _shared_log[log_snapshot:]
        if new_entries:
            cleaned_entries = [_clean_log(entry) for entry in new_entries]
            logs_to_show.extend(cleaned_entries)
            log_snapshot = len(_shared_log)
            # 不再截断到最新的 20 行，而是展示全部日志并依赖 CSS 滚动条
            log_text = "\\n".join(logs_to_show)
            log_container.code(log_text, language="text")
            
    final_entries = _shared_log[log_snapshot:]
    if final_entries:
        cleaned_entries = [_clean_log(entry) for entry in final_entries]
        logs_to_show.extend(cleaned_entries)
        
    log_text = "\\n".join(logs_to_show)
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
    # 使用 type="primary" 可以渲染为主按钮（通常是系统主题的强调色，如果不强制指定绿色，primary 就是最好的选择）
    # 但由于 Streamlit 没有内置的绿底按钮，我们可以通过 HTML/CSS 或者依赖用户的 primary color 设置。
    # 这里我们采用 standard streamlit primary，并在文字上加上表情使其显眼
    if st.button("🟢 了解，返回报告大盘", use_container_width=True, type="primary"):
        st.rerun()

"""

import re
content = re.sub(
    r"# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n# UI 布局\n# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━.*?def render_sidebar",
    replacement_func + "\ndef render_sidebar",
    content,
    flags=re.DOTALL
)

with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)

