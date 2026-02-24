with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

import re

# To make code block scrollable we need to target the internal div
# that streamlit generates.
# Streamlit Code blocks usually have data-testid="stCodeBlock" 
# and inside there's a `<pre><code>` container.
css_old = """        /* 针对 Streamlit CodeBlock 的内部结构 */
        div[data-testid="stCodeBlock"] {
            max-height: 400px !important;
            overflow-y: auto !important;
        }
        /* 针对可能嵌套的一层 */
        div[data-testid="stCodeBlock"] div {
            overflow: visible !important;
        }"""

css_new = """        /* 针对 Streamlit CodeBlock 的内部结构 */
        div[data-testid="stCodeBlock"] > div > pre {
            max-height: 350px !important;
            overflow-y: auto !important;
            white-space: pre-wrap !important;
        }
        div[data-testid="stCodeBlock"] {
            margin-bottom: 1rem;
        }"""

content = content.replace(css_old, css_new)

with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)
