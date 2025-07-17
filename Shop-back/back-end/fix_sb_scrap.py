#!/usr/bin/env python3
"""
修复原始抓取脚本的问题
"""
import re

def fix_script_removal():
    """修复script标签移除问题"""
    with open('sb_scrap.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 查找并替换script清理部分
    old_pattern = r'# 移除script和style标签，避免抓取到它们的内容\s*for script in soup\(\["script", "style", "noscript"\]\):\s*script\.decompose\(\)'
    
    new_replacement = '''# 只移除style和noscript标签，保留script标签（Next.js需要）
for element in soup(["style", "noscript"]):
    element.decompose()'''
    
    content = re.sub(old_pattern, new_replacement, content, flags=re.DOTALL)
    
    # 写回文件
    with open('sb_scrap.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✓ 已修复script标签移除问题")

if __name__ == "__main__":
    fix_script_removal()
