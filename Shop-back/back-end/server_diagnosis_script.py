#!/usr/bin/env python3
"""
服务器抓取问题诊断脚本
直接运行即可诊断问题
"""

import requests
import time
import json
from bs4 import BeautifulSoup
import sys
import traceback
from datetime import datetime

def test_basic_connection():
    """测试基础网络连接"""
    print("=== 基础网络连接测试 ===")
    
    test_urls = [
        'https://www.google.com',
        'https://www.shopback.com.au',
        'https://www.shopback.com.au/agoda'
    ]
    
    for url in test_urls:
        try:
            print(f"\n测试连接: {url}")
            start_time = time.time()
            
            response = requests.get(url, timeout=30)
            response_time = time.time() - start_time
            
            print(f"  ✓ 状态码: {response.status_code}")
            print(f"  ✓ 响应时间: {response_time:.2f}秒")
            print(f"  ✓ 内容长度: {len(response.content)}")
            print(f"  ✓ 内容类型: {response.headers.get('content-type', 'Unknown')}")
            
            if response.status_code == 200:
                print(f"  ✓ 前200个字符: {response.text[:200]}")
            else:
                print(f"  ✗ HTTP错误: {response.status_code}")
                
        except requests.exceptions.Timeout:
            print(f"  ✗ 超时错误")
        except requests.exceptions.ConnectionError:
            print(f"  ✗ 连接错误")
        except Exception as e:
            print(f"  ✗ 其他错误: {e}")

def test_shopback_scraping():
    """测试ShopBack页面抓取"""
    print("\n=== ShopBack页面抓取测试 ===")
    
    test_url = 'https://www.shopback.com.au/agoda'
    
    try:
        print(f"测试抓取: {test_url}")
        
        # 使用更真实的请求头
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        response = requests.get(test_url, headers=headers, timeout=30)
        
        print(f"状态码: {response.status_code}")
        print(f"内容长度: {len(response.content)}")
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 保存完整HTML用于调试
            with open('debug_page.html', 'w', encoding='utf-8') as f:
                f.write(str(soup))
            print("✓ 完整页面HTML已保存到 debug_page.html")
            
            # 检查关键元素
            print("\n关键元素检查:")
            
            # 1. 页面标题
            title = soup.find('title')
            if title:
                print(f"  ✓ 页面标题: {title.get_text()}")
            else:
                print(f"  ✗ 未找到页面标题")
            
            # 2. 当前优惠
            current_offer = soup.find(attrs={'data-testid': 'current-offer'})
            if current_offer:
                print(f"  ✓ 当前优惠: {current_offer.get_text()}")
            else:
                print(f"  ✗ 未找到current-offer元素")
            
            # 3. Cashback rates容器
            cashback_rates = soup.find(attrs={'data-testid': 'cashback-rates'})
            if cashback_rates:
                print(f"  ✓ 找到cashback-rates容器")
            else:
                print(f"  ✗ 未找到cashback-rates容器")
            
            # 4. 所有cashback rates
            all_cashback_rates = soup.find(attrs={'data-testid': 'all-cashback-rates'})
            if all_cashback_rates:
                print(f"  ✓ 找到all-cashback-rates容器")
            else:
                print(f"  ✗ 未找到all-cashback-rates容器")
            
            # 5. 搜索所有包含百分号的元素
            percentage_elements = soup.find_all(string=lambda text: text and '%' in text)
            if percentage_elements:
                print(f"  ✓ 找到 {len(percentage_elements)} 个包含百分号的元素:")
                for i, elem in enumerate(percentage_elements[:5]):  # 只显示前5个
                    print(f"    - {elem.strip()}")
            else:
                print(f"  ✗ 未找到任何包含百分号的元素")
            
            # 6. 搜索所有data-testid属性
            testid_elements = soup.find_all(attrs={'data-testid': True})
            if testid_elements:
                print(f"  ✓ 找到 {len(testid_elements)} 个data-testid元素:")
                testids = [elem.get('data-testid') for elem in testid_elements]
                unique_testids = list(set(testids))
                for testid in unique_testids[:10]:  # 只显示前10个
                    print(f"    - {testid}")
            else:
                print(f"  ✗ 未找到任何data-testid元素")
            
            # 7. 检查是否被重定向或阻止
            if 'error' in soup.get_text().lower() or 'blocked' in soup.get_text().lower():
                print(f"  ⚠️ 页面可能包含错误或被阻止的信息")
            
            return True
            
        else:
            print(f"✗ HTTP错误: {response.status_code}")
            print(f"响应内容: {response.text[:500]}")
            return False
            
    except Exception as e:
        print(f"✗ 抓取失败: {e}")
        traceback.print_exc()
        return False

def test_enhanced_scraping():
    """测试增强版抓取方法"""
    print("\n=== 增强版抓取测试 ===")
    
    test_url = 'https://www.shopback.com.au/agoda'
    
    # 创建会话
    session = requests.Session()
    
    # 设置更完整的请求头
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'max-age=0',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'DNT': '1',
    }
    
    session.headers.update(headers)
    
    try:
        print(f"使用会话抓取: {test_url}")
        
        # 首先访问主页面建立会话
        print("先访问主页面...")
        session.get('https://www.shopback.com.au', timeout=30)
        time.sleep(2)
        
        # 再访问目标页面
        print("访问目标页面...")
        response = session.get(test_url, timeout=30)
        
        print(f"状态码: {response.status_code}")
        print(f"内容长度: {len(response.content)}")
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 保存增强版HTML
            with open('enhanced_debug_page.html', 'w', encoding='utf-8') as f:
                f.write(str(soup))
            print("✓ 增强版页面HTML已保存到 enhanced_debug_page.html")
            
            # 尝试提取数据
            print("\n尝试提取数据:")
            
            # 商家名称
            title = soup.find('title')
            if title:
                store_name = title.get_text().split('|')[0].strip()
                print(f"  商家名称: {store_name}")
            
            # 主要cashback
            current_offer = soup.find(attrs={'data-testid': 'current-offer'})
            if current_offer:
                main_cashback = current_offer.get_text().strip()
                print(f"  主要cashback: {main_cashback}")
            else:
                # 尝试其他方法
                h5_elements = soup.find_all('h5')
                for h5 in h5_elements:
                    if h5.get_text() and '%' in h5.get_text():
                        print(f"  可能的cashback: {h5.get_text()}")
                        break
            
            # 检查upsized
            upsized = soup.find('p', string=lambda text: text and 'upsized' in text.lower())
            if upsized:
                print(f"  ✓ 发现Upsized标签")
            
            return True
            
        else:
            print(f"✗ HTTP错误: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"✗ 增强版抓取失败: {e}")
        traceback.print_exc()
        return False

def save_environment_info():
    """保存环境信息"""
    print("\n=== 环境信息 ===")
    
    env_info = {
        'python_version': sys.version,
        'platform': sys.platform,
        'timestamp': datetime.now().isoformat(),
        'requests_version': requests.__version__,
    }
    
    try:
        import platform
        env_info['system'] = platform.system()
        env_info['machine'] = platform.machine()
        env_info['processor'] = platform.processor()
    except:
        pass
    
    print(f"Python版本: {env_info['python_version']}")
    print(f"系统平台: {env_info['platform']}")
    print(f"Requests版本: {env_info['requests_version']}")
    
    # 保存到文件
    with open('environment_info.json', 'w', encoding='utf-8') as f:
        json.dump(env_info, f, indent=2, ensure_ascii=False)
    
    print("✓ 环境信息已保存到 environment_info.json")

def main():
    """主函数"""
    print("ShopBack服务器抓取问题诊断脚本")
    print("=" * 50)
    
    # 保存环境信息
    save_environment_info()
    
    # 测试基础连接
    test_basic_connection()
    
    # 测试ShopBack抓取
    success1 = test_shopback_scraping()
    
    # 测试增强版抓取
    success2 = test_enhanced_scraping()
    
    print("\n" + "=" * 50)
    print("诊断结果总结:")
    print(f"基础ShopBack抓取: {'✓ 成功' if success1 else '✗ 失败'}")
    print(f"增强版抓取: {'✓ 成功' if success2 else '✗ 失败'}")
    
    print("\n生成的文件:")
    print("- debug_page.html (如果基础抓取成功)")
    print("- enhanced_debug_page.html (如果增强抓取成功)")
    print("- environment_info.json")
    
    if not success1 and not success2:
        print("\n⚠️ 两种抓取方法都失败了，可能的原因:")
        print("1. 服务器IP被ShopBack封禁")
        print("2. 地理位置限制")
        print("3. 网络防火墙阻止")
        print("4. 反爬虫系统检测")
    
    print("\n请检查生成的HTML文件内容，并将结果反馈给开发者。")

if __name__ == "__main__":
    main()
