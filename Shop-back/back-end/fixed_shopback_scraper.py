#!/usr/bin/env python3
"""
修复版ShopBack抓取器
专门处理服务器环境的数据提取问题
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import time
import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict

@dataclass
class CashbackRate:
    """Cashback比例数据结构"""
    category: str
    rate: str
    rate_numeric: float

@dataclass
class StoreInfo:
    """商家信息数据结构"""
    name: str
    main_cashback: str
    main_rate_numeric: float
    detailed_rates: List[CashbackRate]
    is_upsized: bool
    previous_offer: Optional[str]
    url: str
    last_updated: str
    scraping_success: bool
    error_message: Optional[str] = None

class FixedShopBackScraper:
    """修复版ShopBack抓取器"""
    
    def __init__(self, db_path: str = "shopback_data.db"):
        self.db_path = db_path
        self.setup_logging()
        self.setup_session()
        self.init_database()
    
    def setup_logging(self):
        """设置日志"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('fixed_scraper.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def setup_session(self):
        """设置请求会话"""
        self.session = requests.Session()
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        self.session.headers.update(headers)
    
    def init_database(self):
        """初始化数据库"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
            
            cursor = self.conn.cursor()
            
            # 创建商家表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS stores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(name, url)
                )
            ''')
            
            # 创建cashback历史表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cashback_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    store_id INTEGER NOT NULL,
                    main_cashback TEXT,
                    main_rate_numeric REAL,
                    category TEXT,
                    category_rate TEXT,
                    category_rate_numeric REAL,
                    is_upsized BOOLEAN DEFAULT FALSE,
                    previous_offer TEXT,
                    scraping_success BOOLEAN DEFAULT TRUE,
                    error_message TEXT,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (store_id) REFERENCES stores (id)
                )
            ''')
            
            # 创建比例统计表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS rate_statistics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    store_id INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    current_rate REAL,
                    highest_rate REAL,
                    lowest_rate REAL,
                    highest_date TIMESTAMP,
                    lowest_date TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (store_id) REFERENCES stores (id),
                    UNIQUE(store_id, category)
                )
            ''')
            
            # 创建索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_stores_name ON stores (name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_cashback_store_id ON cashback_history (store_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_cashback_scraped_at ON cashback_history (scraped_at)')
            
            self.conn.commit()
            self.logger.info("数据库初始化成功")
            
        except Exception as e:
            self.logger.error(f"数据库初始化失败: {e}")
            raise
    
    def extract_numeric_rate(self, rate_text: str) -> float:
        """从文本中提取数字比例"""
        if not rate_text:
            return 0.0
        
        # 清理文本
        rate_text = rate_text.strip()
        
        # 匹配各种比例格式
        patterns = [
            r'Up to (\d+\.?\d*)%',
            r'(\d+\.?\d*)%\s*Cashback',
            r'(\d+\.?\d*)%',
            r'\$(\d+\.?\d*)',
            r'(\d+\.?\d*)\s*%',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, rate_text, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
        
        return 0.0
    
    def extract_json_data(self, soup: BeautifulSoup) -> Dict:
        """提取页面中的JSON数据"""
        json_data = {}
        
        # 查找所有script标签
        scripts = soup.find_all('script')
        
        for script in scripts:
            if not script.string:
                continue
                
            script_content = script.string.strip()
            
            # 查找包含cashback信息的JSON
            if 'cashback' in script_content.lower() or 'rate' in script_content.lower():
                # 尝试提取JSON对象
                json_patterns = [
                    r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
                    r'window\.__NEXT_DATA__\s*=\s*({.+?});',
                    r'__APOLLO_STATE__\s*=\s*({.+?});',
                    r'({.*?"cashback".*?})',
                    r'({.*?"rate".*?})',
                ]
                
                for pattern in json_patterns:
                    matches = re.findall(pattern, script_content, re.DOTALL)
                    for match in matches:
                        try:
                            data = json.loads(match)
                            if isinstance(data, dict):
                                json_data.update(data)
                        except json.JSONDecodeError:
                            continue
        
        return json_data
    
    def extract_store_name(self, soup: BeautifulSoup, url: str) -> str:
        """提取商家名称"""
        # 方法1: 从页面标题提取
        title_element = soup.find('title')
        if title_element:
            title_text = title_element.get_text().strip()
            if '|' in title_text:
                store_name = title_text.split('|')[0].strip()
                # 清理商家名称
                store_name = re.sub(r'\s*(Cashback|Discount|Codes|Vouchers|Deals)\s*', '', store_name, flags=re.IGNORECASE)
                if store_name:
                    return store_name
        
        # 方法2: 从URL提取
        url_parts = url.rstrip('/').split('/')
        if url_parts:
            store_slug = url_parts[-1]
            store_name = ' '.join(word.capitalize() for word in store_slug.split('-'))
            return store_name
        
        # 方法3: 从meta标签提取
        meta_title = soup.find('meta', attrs={'property': 'og:title'})
        if meta_title and meta_title.get('content'):
            return meta_title['content'].split('|')[0].strip()
        
        return "Unknown Store"
    
    def extract_main_cashback_info(self, soup: BeautifulSoup) -> Tuple[str, bool, Optional[str]]:
        """提取主要cashback信息"""
        main_cashback = "0%"
        is_upsized = False
        previous_offer = None
        
        self.logger.info("开始提取主要cashback信息")
        
        try:
            # 方法1: 查找data-testid="current-offer"
            current_offer_element = soup.find(attrs={'data-testid': 'current-offer'})
            if current_offer_element:
                main_cashback = current_offer_element.get_text().strip()
                self.logger.info(f"从current-offer找到: {main_cashback}")
            
            # 方法2: 查找h1-h6标签中包含百分号的
            if main_cashback == "0%":
                for tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    elements = soup.find_all(tag)
                    for element in elements:
                        text = element.get_text().strip()
                        if '%' in text and ('up to' in text.lower() or 'cashback' in text.lower()):
                            main_cashback = text
                            self.logger.info(f"从{tag}标签找到: {main_cashback}")
                            break
                    if main_cashback != "0%":
                        break
            
            # 方法3: 查找包含百分号的强调文本
            if main_cashback == "0%":
                emphasis_tags = ['strong', 'b', 'em']
                for tag in emphasis_tags:
                    elements = soup.find_all(tag)
                    for element in elements:
                        text = element.get_text().strip()
                        if '%' in text and len(text) < 50:  # 避免长文本
                            main_cashback = text
                            self.logger.info(f"从{tag}标签找到: {main_cashback}")
                            break
                    if main_cashback != "0%":
                        break
            
            # 方法4: 正则表达式搜索整个页面
            if main_cashback == "0%":
                page_text = soup.get_text()
                patterns = [
                    r'Up to (\d+\.?\d*%)\s*Cashback',
                    r'(\d+\.?\d*%)\s*Cashback',
                    r'Earn (\d+\.?\d*%)',
                    r'Get (\d+\.?\d*%)',
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, page_text, re.IGNORECASE)
                    if match:
                        main_cashback = match.group(1) if match.group(1).endswith('%') else match.group(0)
                        self.logger.info(f"从正则表达式找到: {main_cashback}")
                        break
            
            # 检查是否有upsized标签
            upsized_patterns = [
                soup.find('p', string=re.compile(r'Upsized', re.IGNORECASE)),
                soup.find('span', string=re.compile(r'Upsized', re.IGNORECASE)),
                soup.find('div', string=re.compile(r'Upsized', re.IGNORECASE)),
            ]
            
            for element in upsized_patterns:
                if element:
                    is_upsized = True
                    self.logger.info("检测到Upsized标签")
                    break
            
            # 查找previous offer
            worse_offer_element = soup.find(attrs={'data-testid': 'worse-offer'})
            if worse_offer_element:
                previous_text = worse_offer_element.get_text().strip()
                if previous_text:
                    previous_offer = previous_text
                    self.logger.info(f"从worse-offer找到之前的优惠: {previous_offer}")
            else:
                # 查找带删除线的文本
                strikethrough_elements = soup.find_all(['s', 'del', 'strike'])
                for element in strikethrough_elements:
                    text = element.get_text().strip()
                    if '%' in text:
                        previous_offer = text
                        self.logger.info(f"从删除线文本找到之前的优惠: {previous_offer}")
                        break
        
        except Exception as e:
            self.logger.warning(f"提取主要cashback信息时出错: {e}")
        
        return main_cashback, is_upsized, previous_offer
    
    def extract_detailed_rates(self, soup: BeautifulSoup) -> List[CashbackRate]:
        """提取详细的cashback比例"""
        detailed_rates = []
        
        self.logger.info("开始提取详细cashback比例")
        
        try:
            # 方法1: 查找cashback-rates容器
            rates_container = soup.find('div', {'data-testid': 'cashback-rates'})
            if rates_container:
                self.logger.info("找到cashback-rates容器")
                
                # 查找所有包含百分号的文本
                rate_elements = rates_container.find_all(string=re.compile(r'\d+\.?\d*%'))
                category_elements = rates_container.find_all('p')
                
                # 尝试配对分类和比例
                for i, rate_elem in enumerate(rate_elements):
                    if i < len(category_elements):
                        category = category_elements[i].get_text().strip()
                        rate = rate_elem.strip()
                        
                        if category and rate and len(category) < 100:
                            rate_obj = CashbackRate(
                                category=category,
                                rate=rate,
                                rate_numeric=self.extract_numeric_rate(rate)
                            )
                            detailed_rates.append(rate_obj)
                            self.logger.info(f"提取到rate: {category} -> {rate}")
            
            # 方法2: 查找all-cashback-rates容器
            if not detailed_rates:
                rates_container = soup.find('div', {'data-testid': 'all-cashback-rates'})
                if rates_container:
                    self.logger.info("找到all-cashback-rates容器")
                    
                    # 查找所有行
                    rate_rows = rates_container.find_all('div', recursive=True)
                    
                    for row in rate_rows:
                        text = row.get_text().strip()
                        if '%' in text and len(text) < 200:
                            # 尝试分离分类和比例
                            parts = text.split('%')
                            if len(parts) >= 2:
                                category = parts[0].strip()
                                rate = parts[0].split()[-1] + '%'
                                
                                if category and rate:
                                    rate_obj = CashbackRate(
                                        category=category,
                                        rate=rate,
                                        rate_numeric=self.extract_numeric_rate(rate)
                                    )
                                    detailed_rates.append(rate_obj)
                                    self.logger.info(f"提取到rate: {category} -> {rate}")
            
            # 方法3: 查找所有包含百分号的元素
            if not detailed_rates:
                all_elements = soup.find_all(string=re.compile(r'\d+\.?\d*%'))
                
                for element in all_elements:
                    parent = element.parent
                    if parent:
                        text = parent.get_text().strip()
                        if len(text) < 100 and ':' in text:
                            parts = text.split(':')
                            if len(parts) == 2:
                                category = parts[0].strip()
                                rate = parts[1].strip()
                                
                                if category and '%' in rate:
                                    rate_obj = CashbackRate(
                                        category=category,
                                        rate=rate,
                                        rate_numeric=self.extract_numeric_rate(rate)
                                    )
                                    detailed_rates.append(rate_obj)
                                    self.logger.info(f"提取到rate: {category} -> {rate}")
        
        except Exception as e:
            self.logger.error(f"提取详细rates时出错: {e}")
        
        return detailed_rates
    
    def scrape_store_page(self, url: str) -> StoreInfo:
        """抓取单个商家页面"""
        self.logger.info(f"开始抓取商家页面: {url}")
        
        try:
            # 发送请求
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            self.logger.info(f"请求成功，状态码: {response.status_code}")
            self.logger.info(f"内容长度: {len(response.content)}")
            
            # 解析HTML
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 保存调试HTML
            debug_filename = f"debug_{url.split('/')[-1]}.html"
            with open(debug_filename, 'w', encoding='utf-8') as f:
                f.write(str(soup))
            self.logger.info(f"调试HTML已保存到: {debug_filename}")
            
            # 提取数据
            store_name = self.extract_store_name(soup, url)
            main_cashback, is_upsized, previous_offer = self.extract_main_cashback_info(soup)
            detailed_rates = self.extract_detailed_rates(soup)
            
            self.logger.info(f"提取结果: {store_name}")
            self.logger.info(f"主要cashback: {main_cashback}")
            self.logger.info(f"详细rates数量: {len(detailed_rates)}")
            
            store_info = StoreInfo(
                name=store_name,
                main_cashback=main_cashback,
                main_rate_numeric=self.extract_numeric_rate(main_cashback),
                detailed_rates=detailed_rates,
                is_upsized=is_upsized,
                previous_offer=previous_offer,
                url=url,
                last_updated=datetime.now().isoformat(),
                scraping_success=True
            )
            
            # 保存到数据库
            self.save_to_database(store_info)
            
            return store_info
            
        except Exception as e:
            error_msg = f"抓取失败: {str(e)}"
            self.logger.error(error_msg)
            
            return StoreInfo(
                name="Unknown Store",
                main_cashback="0%",
                main_rate_numeric=0.0,
                detailed_rates=[],
                is_upsized=False,
                previous_offer=None,
                url=url,
                last_updated=datetime.now().isoformat(),
                scraping_success=False,
                error_message=str(e)
            )
    
    def save_to_database(self, store_info: StoreInfo):
        """保存数据到数据库"""
        try:
            cursor = self.conn.cursor()
            
            # 插入或获取商家信息
            cursor.execute('''
                INSERT OR IGNORE INTO stores (name, url) VALUES (?, ?)
            ''', (store_info.name, store_info.url))
            
            cursor.execute('''
                SELECT id FROM stores WHERE name = ? AND url = ?
            ''', (store_info.name, store_info.url))
            
            store_id = cursor.fetchone()[0]
            
            # 插入主要cashback历史
            cursor.execute('''
                INSERT INTO cashback_history 
                (store_id, main_cashback, main_rate_numeric, category, category_rate, 
                category_rate_numeric, is_upsized, previous_offer, scraping_success, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (store_id, store_info.main_cashback, store_info.main_rate_numeric,
                'Main', store_info.main_cashback, store_info.main_rate_numeric,
                store_info.is_upsized, store_info.previous_offer, 
                store_info.scraping_success, store_info.error_message))
            
            # 插入详细分类历史
            for rate in store_info.detailed_rates:
                cursor.execute('''
                    INSERT INTO cashback_history 
                    (store_id, main_cashback, main_rate_numeric, category, category_rate, 
                    category_rate_numeric, is_upsized, previous_offer, scraping_success, error_message)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (store_id, store_info.main_cashback, store_info.main_rate_numeric,
                    rate.category, rate.rate, rate.rate_numeric,
                    store_info.is_upsized, store_info.previous_offer,
                    store_info.scraping_success, store_info.error_message))
            
            # 更新商家时间戳
            cursor.execute('''
                UPDATE stores SET updated_at = CURRENT_TIMESTAMP WHERE id = ?
            ''', (store_id,))
            
            self.conn.commit()
            self.logger.info(f"数据已保存到数据库: {store_info.name}")
            
        except Exception as e:
            self.conn.rollback()
            self.logger.error(f"数据库保存失败: {e}")
    
    def test_scraping(self):
        """测试抓取功能"""
        test_urls = [
            'https://www.shopback.com.au/agoda',
            'https://www.shopback.com.au/amazon-australia',
            'https://www.shopback.com.au/booking-com'
        ]
        
        print("=== 测试抓取功能 ===")
        
        for url in test_urls:
            print(f"\n测试抓取: {url}")
            result = self.scrape_store_page(url)
            
            print(f"商家名称: {result.name}")
            print(f"主要cashback: {result.main_cashback}")
            print(f"是否upsized: {result.is_upsized}")
            print(f"详细rates数量: {len(result.detailed_rates)}")
            print(f"抓取成功: {result.scraping_success}")
            
            if result.detailed_rates:
                print("详细rates:")
                for rate in result.detailed_rates[:3]:  # 只显示前3个
                    print(f"  - {rate.category}: {rate.rate}")
            
            time.sleep(3)  # 避免请求过快
    
    def close_connection(self):
        """关闭数据库连接"""
        if hasattr(self, 'conn'):
            self.conn.close()

# 测试函数
def main():
    """主测试函数"""
    scraper = FixedShopBackScraper()
    scraper.test_scraping()
    scraper.close_connection()

if __name__ == "__main__":
    main()
