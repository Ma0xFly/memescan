with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

import re

# Fix 1: Add method to close dialog properly
old_button = """    if st.button("🟢 了解，返回报告大盘", use_container_width=True, type="primary"):
        st.rerun()"""

new_button = """    @st.fragment
    def _close_dialog():
        if st.button("🟢 了解，返回报告大盘", use_container_width=True, type="primary"):
            st.rerun()
            
    _close_dialog()"""

content = content.replace(old_button, new_button)


# Fix 2: Improve CSS to ensure codeblock can be scrolled
css_old = """        div[data-testid="stCodeBlock"] {
            max-height: 400px;
            overflow-y: auto;
        }"""

css_new = """        div[data-testid="stCodeBlock"] > div > pre {
            max-height: 400px;
            overflow-y: auto !important;
        }
        div[data-testid="stCodeBlock"] {
            max-height: 400px;
        }"""
        
content = content.replace(css_old, css_new)


# Fix 3: Remove Alchemy/URL and exact path leaks
clean_log_old = """    def _clean_log(text: str) -> str:
        # 去掉敏感路径信息，防止暴露给前端
        import os
        import re
        home_dir = os.path.expanduser("~")
        cwd = os.getcwd()
        # 针对日志中的具体文件路径进行正则替换
        text = re.sub(r'/home/[^/]+', '~', text)
        if home_dir != "/":
            text = text.replace(home_dir, "~")
        text = text.replace(cwd, ".")
        # 不使用 cwd.split因为如果cwd带了根目录结构可能会误杀正常单词
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
        text = re.sub(r'https://[^/]+\.alchemy\.com/v2/[a-zA-Z0-9_-]+', 'https://***.alchemy.com/v2/***', text)
        text = re.sub(r'https://[a-zA-Z0-9_-]+\.infura\.io/v3/[a-zA-Z0-9_-]+', 'https://***.infura.io/v3/***', text)
        text = re.sub(r'(--fork-url\s+)https?://\S+', r'\1***RPC_URL***', text)
        
        # 3. 替换当前工作目录
        text = text.replace(cwd, ".")
        
        return text"""

content = content.replace(clean_log_old, clean_log_new)

with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)
