import re

with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

css = """    # 注入自定义 CSS 控制代码块高度、启用垂直滚动条、修改 Primary 按钮为绿色
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
        /* 将 primary button 改为绿色 */
        button[kind="primary"] {
            background-color: #00C853 !important;
            border-color: #00C853 !important;
            color: white !important;
            font-weight: bold !important;
        }
        button[kind="primary"]:hover {
            background-color: #00E676 !important;
            border-color: #00E676 !important;
        }
        </style>
        \"\"\",
        unsafe_allow_html=True,
    )"""

content = re.sub(
    r"    # 注入自定义 CSS.*?unsafe_allow_html=True,\n    \)",
    css,
    content,
    flags=re.DOTALL
)

with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)

