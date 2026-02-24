with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

import re

# Fix 1: Properly close the dialog using st.rerun() directly on the main page
old_button = """    @st.fragment
    def _close_dialog():
        if st.button("🟢 了解，返回报告大盘", use_container_width=True, type="primary"):
            st.rerun()
            st.session_state["show_dialog"] = False
            
    _close_dialog()"""

new_button = """    if st.button("🟢 了解，返回报告大盘", use_container_width=True, type="primary"):
        st.rerun()"""

content = content.replace(old_button, new_button)


# Fix 2: Better UI scrolling for code blocks in Streamlit 1.34+
css_old = """        div[data-testid="stCodeBlock"] > div > pre {
            max-height: 400px;
            overflow-y: auto !important;
        }
        div[data-testid="stCodeBlock"] {
            max-height: 400px;
        }"""

css_new = """        /* 针对 Streamlit CodeBlock 的内部结构 */
        div[data-testid="stCodeBlock"] {
            max-height: 400px !important;
            overflow-y: auto !important;
        }
        /* 针对可能嵌套的一层 */
        div[data-testid="stCodeBlock"] div {
            overflow: visible !important;
        }"""

content = content.replace(css_old, css_new)

# Fix 3: Fix regex syntax in clean_log
clean_log_old = """    def _clean_log(text: str) -> str:
        # 去掉敏感路径信息，防止暴露给前端
        import os
        import re
        home_dir = os.path.expanduser("~")
        cwd = os.getcwd()
        
        # 1. 替换 /home/xxx 绝对路径
        text = re.sub(r'/home/[^/\s]+', '~', text)
        if home_dir != "/":
            text = text.replace(home_dir, "~")
            
        # 2. 隐藏 Alchemy/Infura 等 RPC URL 中的敏感 key
        text = re.sub(r'https://[^/]+\.alchemy\.com/v2/[a-zA-Z0-9_-]+', 'https://***.alchemy.com/v2/***', text)
        text = re.sub(r'https://[a-zA-Z0-9_-]+\.infura\.io/v3/[a-zA-Z0-9_-]+', 'https://***.infura.io/v3/***', text)
        text = re.sub(r'(--fork-url\s+)https?://\S+', r'\1***RPC_URL***', text)
        
        # 3. 替换当前工作目录
        text = text.replace(cwd, ".")
        
        return text"""

clean_log_new = """    def _clean_log(text: str) -> str:
        # 去掉敏感路径信息，防止暴露给前端
        import os
        import re
        home_dir = os.path.expanduser("~")
        cwd = os.getcwd()
        
        # 1. 替换 /home/xxx 绝对路径
        text = re.sub(r'/home/[^/\s]+', '~', text)
        if home_dir != "/":
            text = text.replace(home_dir, "~")
            
        # 2. 隐藏 Alchemy/Infura 等 RPC URL 中的敏感 key
        text = re.sub(r'https://[^/\s]+\.alchemy\.com/v2/[a-zA-Z0-9_-]+', 'https://eth-mainnet.g.alchemy.com/v2/***', text)
        text = re.sub(r'https://[a-zA-Z0-9_-]+\.infura\.io/v3/[a-zA-Z0-9_-]+', 'https://mainnet.infura.io/v3/***', text)
        
        # 拦截 --fork-url 参数后的任意 URL
        text = re.sub(r'--fork-url\s+https?://\S+', '--fork-url ***RPC_URL***', text)
        
        # 3. 替换当前工作目录
        text = text.replace(cwd, ".")
        
        return text"""

content = content.replace(clean_log_old, clean_log_new)

with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)
