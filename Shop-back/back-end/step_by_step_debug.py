#!/usr/bin/env python3
"""
逐步调试脚本 - 找出服务器和本地的差异
"""

def step1_basic_import():
    print("=== 步骤1: 基本导入测试 ===")
    try:
        import requests
        import sqlite3
        from bs4 import BeautifulSoup
        import re
        from datetime import datetime
        from dataclasses import dataclass
        print("✓ 所有模块导入成功")
        return True
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        return False

def step2_network_test():
    print("\n=== 步骤2: 网络连接测试 ===")
    try:
        import requests
        response = requests.get('https://httpbin.org/get', timeout=10)
        print(f"✓ 基本网络连接正常: {response.status_code}")
        
        response = requests.get('https://www.shopback.com.au/', timeout=10)
        print(f"✓ ShopBack主页访问: {response.status_code}")
        return True
    except Exception as e:
        print(f"❌ 网络测试失败: {e}")
        return False

def step3_page_content_test():
    print("\n=== 步骤3: 页面内容测试 ===")
    try:
        import requests
        from bs4 import BeautifulSoup
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get('https://www.shopback.com.au/agoda', headers=headers, timeout=30)
        
        print(f"状态码: {response.status_code}")
        print(f"内容长度: {len(response.content)}")
        
        # 检查内容
        content = response.text.lower()
        checks = [
            ('包含agoda', 'agoda' in content),
            ('包含cashback', 'cashback' in content),
            ('包含data-testid', 'data-testid' in content),
        ]
        
        all_good = True
        for name, result in checks:
            status = '✓' if result else '❌'
            print(f"{status} {name}")
            if not result:
                all_good = False
        
        return all_good
        
    except Exception as e:
        print(f"❌ 页面内容测试失败: {e}")
        return False

def step4_parsing_test():
    print("\n=== 步骤4: 页面解析测试 ===")
    try:
        import requests
        from bs4 import BeautifulSoup
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get('https://www.shopback.com.au/agoda', headers=headers, timeout=30)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 测试关键元素解析
        current_offer = soup.find(attrs={'data-testid': 'current-offer'})
        if current_offer:
            print(f"✓ current-offer找到: {current_offer.get_text()}")
        else:
            print("❌ current-offer未找到")
            return False
            
        cashback_rates = soup.find('div', {'data-testid': 'cashback-rates'})
        if cashback_rates:
            print(f"✓ cashback-rates容器找到")
            
            # 查找详细分类
            rate_rows = cashback_rates.find_all('div', class_=lambda x: x and 'flex_row' in str(x))
            print(f"✓ 找到 {len(rate_rows)} 个分类行")
            
            for i, row in enumerate(rate_rows[:3]):  # 只显示前3个
                p_elements = row.find_all('p')
                if len(p_elements) >= 2:
                    category = p_elements[0].get_text().strip()
                    rate = p_elements[1].get_text().strip()
                    print(f"  分类{i+1}: {category} -> {rate}")
        else:
            print("❌ cashback-rates容器未找到")
            return False
            
        print("✓ 页面解析测试成功")
        return True
        
    except Exception as e:
        print(f"❌ 页面解析测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def step5_scraper_test():
    print("\n=== 步骤5: 完整抓取器测试 ===")
    try:
        from sb_scrap import ShopBackSQLiteScraper
        scraper = ShopBackSQLiteScraper('debug_test.db')
        
        result = scraper.scrape_store_page('https://www.shopback.com.au/agoda')
        
        print(f"抓取成功: {result.scraping_success}")
        print(f"商家名称: {result.name}")
        print(f"主要cashback: {result.main_cashback}")
        print(f"详细分类数量: {len(result.detailed_rates)}")
        
        if result.error_message:
            print(f"错误信息: {result.error_message}")
            
        return result.scraping_success
        
    except Exception as e:
        print(f"❌ 完整抓取器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("开始逐步调试...")
    
    steps = [
        step1_basic_import,
        step2_network_test, 
        step3_page_content_test,
        step4_parsing_test,
        step5_scraper_test
    ]
    
    for i, step in enumerate(steps, 1):
        success = step()
        if not success:
            print(f"\n💥 在步骤{i}失败，停止测试")
            break
        print(f"✅ 步骤{i}通过")
    else:
        print(f"\n🎉 所有步骤都通过了！问题可能在其他地方")

if __name__ == "__main__":
    main()
