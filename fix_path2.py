with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

import re

old_clean_log = """    def _clean_log(text: str) -> str:
        # 去掉敏感路径信息，防止暴露给前端
        home_dir = os.path.expanduser("~")
        cwd = os.getcwd()
        # 针对日志中的具体文件路径进行正则替换
        text = re.sub(r'/home/[^/]+', '~', text)
        if home_dir != "/":
            text = text.replace(home_dir, "~")
        text = text.replace(cwd, ".")
        text = text.replace(cwd.split('/')[-1], ".")
        return text"""

new_clean_log = """    def _clean_log(text: str) -> str:
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

content = content.replace(old_clean_log, new_clean_log)

with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)
