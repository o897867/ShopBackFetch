import requests
from bs4 import BeautifulSoup

def test_encoding_methods():
    print("=== 字符编码对比测试 ===")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    response = requests.get('https://www.shopback.com.au/agoda', headers=headers, timeout=30)
    
    print(f"原始编码: {response.encoding}")
    print(f"检测到的编码: {response.apparent_encoding}")
    print(f"Content-Type: {response.headers.get('content-type')}")
    
    # 方法1: 使用原始内容
    print("\n=== 方法1: 原始response.content ===")
    try:
        soup1 = BeautifulSoup(response.content, 'html.parser')
        current_offer1 = soup1.find(attrs={'data-testid': 'current-offer'})
        cashback_rates1 = soup1.find('div', {'data-testid': 'cashback-rates'})
        print(f"current-offer: {'找到' if current_offer1 else '未找到'}")
        print(f"cashback-rates: {'找到' if cashback_rates1 else '未找到'}")
        if current_offer1:
            print(f"current-offer内容: {current_offer1.get_text()}")
    except Exception as e:
        print(f"错误: {e}")
    
    # 方法2: 使用response.text
    print("\n=== 方法2: response.text ===")
    try:
        soup2 = BeautifulSoup(response.text, 'html.parser')
        current_offer2 = soup2.find(attrs={'data-testid': 'current-offer'})
        cashback_rates2 = soup2.find('div', {'data-testid': 'cashback-rates'})
        print(f"current-offer: {'找到' if current_offer2 else '未找到'}")
        print(f"cashback-rates: {'找到' if cashback_rates2 else '未找到'}")
        if current_offer2:
            print(f"current-offer内容: {current_offer2.get_text()}")
    except Exception as e:
        print(f"错误: {e}")
    
    # 方法3: 强制UTF-8编码
    print("\n=== 方法3: 强制UTF-8 ===")
    try:
        response.encoding = 'utf-8'
        soup3 = BeautifulSoup(response.text, 'html.parser')
        current_offer3 = soup3.find(attrs={'data-testid': 'current-offer'})
        cashback_rates3 = soup3.find('div', {'data-testid': 'cashback-rates'})
        print(f"current-offer: {'找到' if current_offer3 else '未找到'}")
        print(f"cashback-rates: {'找到' if cashback_rates3 else '未找到'}")
        if current_offer3:
            print(f"current-offer内容: {current_offer3.get_text()}")
    except Exception as e:
        print(f"错误: {e}")
    
    # 方法4: 使用lxml解析器
    print("\n=== 方法4: lxml解析器 ===")
    try:
        soup4 = BeautifulSoup(response.content, 'lxml')
        current_offer4 = soup4.find(attrs={'data-testid': 'current-offer'})
        cashback_rates4 = soup4.find('div', {'data-testid': 'cashback-rates'})
        print(f"current-offer: {'找到' if current_offer4 else '未找到'}")
        print(f"cashback-rates: {'找到' if cashback_rates4 else '未找到'}")
        if current_offer4:
            print(f"current-offer内容: {current_offer4.get_text()}")
    except Exception as e:
        print(f"错误: {e}")

if __name__ == "__main__":
    test_encoding_methods()
