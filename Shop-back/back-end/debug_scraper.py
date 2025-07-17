import requests
from bs4 import BeautifulSoup

response = requests.get('https://www.shopback.com.au/agoda')
print(f"状态码: {response.status_code}")
print(f"编码: {response.encoding}")
print(f"内容类型: {response.headers.get('content-type')}")
print(f"内容长度: {len(response.content)}")
print(f"是否压缩: {'gzip' in response.headers.get('content-encoding', '')}")

# 尝试不同的解码方式
print("原始内容前100字节:")
print(response.content[:100])

print("UTF-8解码:")
try:
    print(response.content.decode('utf-8')[:200])
except:
    print("UTF-8解码失败")

print("response.text前200字符:")
print(response.text[:200])