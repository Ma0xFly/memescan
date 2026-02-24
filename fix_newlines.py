with open("app.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
skip_next = False
for i, line in enumerate(lines):
    if skip_next:
        skip_next = False
        continue
        
    if 'log_text = "\\n' in line and i + 1 < len(lines) and '".join(logs_to_show)' in lines[i+1]:
        new_lines.append('            log_text = "\\n".join(logs_to_show)\n')
        skip_next = True
    else:
        new_lines.append(line)

with open("app.py", "w", encoding="utf-8") as f:
    f.writelines(new_lines)
