#!/usr/bin/env python3
"""
HTML内容分析工具
分析生成的debug HTML文件，查找cashback数据
"""

import re
import json
from bs4 import BeautifulSoup
import sys

def analyze_html_file(filename):
    """分析HTML文件内容"""
    print(f"=== 分析文件: {filename} ===")
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
    except:
        print(f"无法读取文件: {filename}")
        return
    
    soup = BeautifulSoup(content, 'html.parser')
    
    # 1. 基本信息
    print(f"文件大小: {len(content)} 字符")
    print(f"标题: {soup.find('title').get_text() if soup.find('title') else 'N/A'}")
    
    # 2. 查找所有包含百分号的文本
    print("\n=== 包含百分号的文本 ===")
    percentage_texts = []
    for element in soup.find_all(string=re.compile(r'\d+\.?\d*%')):
        text = element.strip()
        if text and len(text) < 200:
            percentage_texts.append(text)
    
    if percentage_texts:
        print(f"找到 {len(percentage_texts)} 个包含百分号的文本:")
        for i, text in enumerate(percentage_texts[:10]):  # 只显示前10个
            print(f"  {i+1}. {text}")
    else:
        print("未找到任何包含百分号的文本")
    
    # 3. 查找所有data-testid属性
    print("\n=== data-testid 属性 ===")
    testid_elements = soup.find_all(attrs={'data-testid': True})
    if testid_elements:
        testids = [elem.get('data-testid') for elem in testid_elements]
        unique_testids = list(set(testids))
        print(f"找到 {len(unique_testids)} 个不同的data-testid:")
        for testid in sorted(unique_testids):
            print(f"  - {testid}")
    else:
        print("未找到任何data-testid属性")
    
    # 4. 查找script标签中的数据
    print("\n=== JavaScript数据 ===")
    scripts = soup.find_all('script')
    js_data_found = False
    
    for i, script in enumerate(scripts):
        if not script.string:
            continue
            
        script_content = script.string.strip()
        
        # 查找可能包含cashback数据的script
        if any(keyword in script_content.lower() for keyword in ['cashback', 'rate', 'offer', 'upsized']):
            print(f"Script {i+1} 包含相关关键词:")
            print(f"  长度: {len(script_content)} 字符")
            
            # 尝试提取JSON数据
            json_patterns = [
                r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
                r'window\.__NEXT_DATA__\s*=\s*({.+?});',
                r'__APOLLO_STATE__\s*=\s*({.+?});',
                r'self\.__next_f\.push\(\[.*?"([^"]*cashback[^"]*)"',
                r'self\.__next_f\.push\(\[.*?"([^"]*rate[^"]*)"',
            ]
            
            for pattern in json_patterns:
                matches = re.findall(pattern, script_content, re.DOTALL)
                if matches:
                    print(f"  找到匹配模式: {pattern[:30]}...")
                    for match in matches[:3]:  # 只显示前3个
                        print(f"    - {match[:100]}...")
            
            # 查找直接的cashback文本
            cashback_matches = re.findall(r'["\']([^"\']*\d+\.?\d*%[^"\']*)["\']', script_content)
            if cashback_matches:
                print(f"  找到可能的cashback数据:")
                for match in cashback_matches[:5]:
                    print(f"    - {match}")
            
            js_data_found = True
    
    if not js_data_found:
        print("未找到包含cashback相关数据的JavaScript")
    
    # 5. 查找特殊的HTML结构
    print("\n=== 特殊HTML结构 ===")
    
    # 查找可能的cashback容器
    containers = [
        soup.find('div', {'data-testid': 'current-offer'}),
        soup.find('div', {'data-testid': 'cashback-rates'}),
        soup.find('div', {'data-testid': 'all-cashback-rates'}),
        soup.find('div', {'data-testid': 'worse-offer'}),
    ]
    
    for i, container in enumerate(containers):
        if container:
            print(f"找到容器 {i+1}: {container.get('data-testid', 'unknown')}")
            print(f"  内容: {container.get_text().strip()[:100]}...")
        else:
            print(f"容器 {i+1}: 未找到")
    
    # 6. 查找包含"cashback"或"rate"的所有元素
    print("\n=== 包含关键词的元素 ===")
    keywords = ['cashback', 'rate', 'offer', 'upsized', 'discount']
    
    for keyword in keywords:
        elements = soup.find_all(string=re.compile(keyword, re.IGNORECASE))
        if elements:
            print(f"'{keyword}' 出现 {len(elements)} 次")
            for element in elements[:3]:  # 只显示前3个
                text = element.strip()
                if text:
                    print(f"  - {text[:100]}...")
    
    # 7. 检查是否是Next.js应用
    print("\n=== Next.js检测 ===")
    nextjs_indicators = [
        soup.find('script', {'src': re.compile(r'/_next/')}),
        soup.find(id='__next'),
        'Next.js' in content,
        '__NEXT_DATA__' in content,
    ]
    
    if any(nextjs_indicators):
        print("✓ 检测到Next.js应用")
        print("这可能意味着数据是通过客户端JavaScript动态加载的")
        
        # 查找Next.js数据
        next_data_match = re.search(r'__NEXT_DATA__\s*=\s*({.+?});', content, re.DOTALL)
        if next_data_match:
            try:
                next_data = json.loads(next_data_match.group(1))
                print("✓ 找到__NEXT_DATA__")
                print(f"  数据大小: {len(str(next_data))} 字符")
                
                # 递归搜索cashback相关数据
                def find_cashback_data(obj, path=""):
                    results = []
                    if isinstance(obj, dict):
                        for key, value in obj.items():
                            if any(keyword in key.lower() for keyword in ['cashback', 'rate', 'offer']):
                                results.append(f"{path}.{key}: {value}")
                            results.extend(find_cashback_data(value, f"{path}.{key}"))
                    elif isinstance(obj, list):
                        for i, item in enumerate(obj):
                            results.extend(find_cashback_data(item, f"{path}[{i}]"))
                    elif isinstance(obj, str):
                        if any(keyword in obj.lower() for keyword in ['cashback', 'rate', 'offer']) and '%' in obj:
                            results.append(f"{path}: {obj}")
                    return results
                
                cashback_data = find_cashback_data(next_data)
                if cashback_data:
                    print("  找到可能的cashback数据:")
                    for data in cashback_data[:5]:
                        print(f"    - {data}")
                else:
                    print("  未在__NEXT_DATA__中找到cashback数据")
                    
            except json.JSONDecodeError:
                print("✗ __NEXT_DATA__解析失败")
    else:
        print("未检测到Next.js应用")

def main():
    """主函数"""
    if len(sys.argv) > 1:
        filename = sys.argv[1]
    else:
        # 分析所有debug文件
        import glob
        debug_files = glob.glob('debug_*.html')
        
        if not debug_files:
            print("未找到debug_*.html文件")
            print("请先运行fixed_shopback_scraper.py生成debug文件")
            return
        
        for filename in debug_files:
            analyze_html_file(filename)
            print("\n" + "="*50 + "\n")
        
        return
    
    analyze_html_file(filename)

if __name__ == "__main__":
    main()
