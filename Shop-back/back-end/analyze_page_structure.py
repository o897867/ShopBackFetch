import requests
from bs4 import BeautifulSoup
import re

def analyze_agoda_page():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    response = requests.get('https://www.shopback.com.au/agoda', headers=headers, timeout=30)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    print("=== 分析Agoda页面结构 ===")
    
    # 1. 查找所有data-testid元素
    print("\n1. 所有data-testid元素:")
    testid_elements = soup.find_all(attrs={'data-testid': True})
    for elem in testid_elements:
        testid = elem.get('data-testid')
        text = elem.get_text()[:100].strip()
        print(f"  {testid}: {text}")
    
    # 2. 查找包含百分号的元素
    print("\n2. 包含百分号的元素:")
    percentage_elements = soup.find_all(string=re.compile(r'\d+(?:\.\d+)?%'))
    for i, elem in enumerate(percentage_elements[:15]):
        parent = elem.parent
        print(f"  {i+1}. '{elem.strip()}' - 父元素: {parent.name} {parent.attrs}")
    
    # 3. 查找商家标题
    print("\n3. 商家标题相关:")
    title_candidates = [
        soup.find('h1'),
        soup.find(attrs={'data-testid': 'merchant-title'}),
        soup.find('title'),
    ]
    
    for i, elem in enumerate(title_candidates):
        if elem:
            print(f"  候选{i+1}: {elem.get_text()[:100]}")
    
    # 4. 查找current-offer和worse-offer
    print("\n4. 优惠信息:")
    offer_elements = ['current-offer', 'worse-offer', 'cashback-rates', 'all-cashback-rates']
    for testid in offer_elements:
        elem = soup.find(attrs={'data-testid': testid})
        if elem:
            print(f"  {testid}: 找到 - {elem.get_text()[:100]}")
        else:
            print(f"  {testid}: 未找到")
    
    # 5. 查找可能的新cashback结构
    print("\n5. 可能的cashback结构:")
    
    # 查找包含"cashback"字样的元素
    cashback_elements = soup.find_all(string=re.compile(r'cashback', re.IGNORECASE))
    for elem in cashback_elements[:10]:
        parent = elem.parent
        print(f"  '{elem.strip()}' - {parent.name} {parent.get('class', [])} {parent.get('data-testid', '')}")

if __name__ == "__main__":
    analyze_agoda_page()
