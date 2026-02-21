import re

with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

old_manual = """async def _manual_scan(token_address: str) -> dict | None:
    \"\"\"对手动输入的代币地址执行一次性编排审计。\"\"\"
    token = Token(address=token_address, pair_address="0x" + "0" * 40)
    try:
        coordinator = CoordinatorAgent()
        result = await coordinator.run({"token": token})
        return {
            "report": result["report"],
            "decisions": result["decisions"]
        }"""

new_manual = """async def _manual_scan(token_address: str, chain_name: str = "ethereum") -> dict | None:
    \"\"\"对手动输入的代币地址执行一次性编排审计。\"\"\"
    token = Token(address=token_address, pair_address="0x" + "0" * 40)
    try:
        coordinator = CoordinatorAgent(chain_name=chain_name)
        result = await coordinator.run({"token": token})
        return {
            "report": result["report"],
            "decisions": result["decisions"]
        }"""
content = content.replace(old_manual, new_manual)


old_manual_ui = """    # 手动扫描
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
            )"""

new_manual_ui = """    # 手动扫描
    st.sidebar.subheader("🎯 手动扫描")
    manual_chain = st.sidebar.selectbox("选择链 (手动扫描)", ["ethereum", "bsc"], key="manual_chain")
    manual_addr = st.sidebar.text_input(
        "代币地址",
        placeholder="0x…",
        key="manual_address",
    )
    if st.sidebar.button("🔬 扫描代币", use_container_width=True) and manual_addr:
        with st.sidebar.status("扫描中…", expanded=True):
            future = asyncio.run_coroutine_threadsafe(
                _manual_scan(manual_addr, manual_chain), loop
            )"""
content = content.replace(old_manual_ui, new_manual_ui)

old_on_new = """async def _on_new_pair(token: Token) -> None:
    \"\"\"ScannerAgent 检测到新交易对时触发的回调。\"\"\"
    log_msg = f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] 新交易对: {token.symbol} — {token.address[:16]}…"
    _shared_log.append(log_msg)
    logger.info(log_msg)

    try:
        coordinator = CoordinatorAgent()"""

new_on_new = """async def _on_new_pair(token: Token, chain_name: str = "ethereum") -> None:
    \"\"\"ScannerAgent 检测到新交易对时触发的回调。\"\"\"
    log_msg = f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] 新交易对 ({chain_name}): {token.symbol} — {token.address[:16]}…"
    _shared_log.append(log_msg)
    logger.info(log_msg)

    try:
        coordinator = CoordinatorAgent(chain_name=chain_name)"""
content = content.replace(old_on_new, new_on_new)

old_start = """        if st.sidebar.button("▶️ 启动监控", use_container_width=True):
            scanner = ScannerAgent(on_new_pair=_on_new_pair, chain_name=selected_chain)
            asyncio.run_coroutine_threadsafe(scanner.run({"action": "start"}), loop)"""

new_start = """        if st.sidebar.button("▶️ 启动监控", use_container_width=True):
            # 将 chain_name 绑定到回调函数
            from functools import partial
            bound_callback = partial(_on_new_pair, chain_name=selected_chain)
            scanner = ScannerAgent(on_new_pair=bound_callback, chain_name=selected_chain)
            asyncio.run_coroutine_threadsafe(scanner.run({"action": "start"}), loop)"""
content = content.replace(old_start, new_start)

with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)
