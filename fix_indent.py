with open("app.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "log_text = \"\\n\".join(logs_to_show)" in line:
        if i < 310:
            lines[i] = "            log_text = \"\\n\".join(logs_to_show)\n"
        else:
            lines[i] = "    log_text = \"\\n\".join(logs_to_show)\n"

    if "log_container.code(log_text" in line:
        if i < 310:
            lines[i] = "            log_container.code(log_text, language=\"text\")\n"
        else:
            lines[i] = "    log_container.code(log_text, language=\"text\")\n"
            
    if "不再截断到最新的" in line:
        lines[i] = "            # 不再截断到最新的 20 行，而是展示全部日志并依赖 CSS 滚动条\n"

with open("app.py", "w", encoding="utf-8") as f:
    f.writelines(lines)
