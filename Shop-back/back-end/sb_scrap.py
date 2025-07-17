#!/usr/bin/env python3
"""
ShopBack 专用抓取器 - SQLite版本
针对ShopBack的现代网页结构进行优化，使用SQLite数据库存储
"""
import sqlite3
import requests
from bs4 import BeautifulSoup
import json
import time
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import re
from dataclasses import dataclass, asdict
import os
from pathlib import Path

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

class ShopBackSQLiteScraper:
    """ShopBack专用抓取器 - SQLite版本"""
    
    def __init__(self, db_path: str = "shopback_data.db"):
        self.session = requests.Session()
        self.setup_session()
        self.setup_logging()
        self.db_path = db_path
        self.init_database()
    
    def setup_session(self):
        """配置请求会话"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }
        self.session.headers.update(headers)
        
    def setup_logging(self):
        """设置日志"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('shopback_scraper.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def init_database(self):
        """初始化SQLite数据库和表结构"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row  # 使结果可以像字典一样访问
            
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
            
            # 创建索引提高查询性能
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_stores_name ON stores (name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_stores_url ON stores (url)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_cashback_store_id ON cashback_history (store_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_cashback_scraped_at ON cashback_history (scraped_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_stats_store_category ON rate_statistics (store_id, category)')
            
            self.conn.commit()
            self.logger.info(f"SQLite数据库初始化成功: {self.db_path}")
            
        except Exception as e:
            self.logger.error(f"数据库初始化失败: {e}")
            raise
    
    def extract_numeric_rate(self, rate_text: str) -> float:
        """从文本中提取数字比例"""
        if not rate_text:
            return 0.0
            
        # 匹配各种比例格式
        patterns = [
            r'Up to (\d+\.?\d*)%',  # Up to 4%
            r'(\d+\.?\d*)%',        # 4%
            r'\$(\d+\.?\d*)',       # $10
        ]
        
        for pattern in patterns:
            match = re.search(pattern, rate_text)
            if match:
                return float(match.group(1))
        
        return 0.0
    
    def extract_store_name(self, soup: BeautifulSoup, url: str) -> str:
        """提取商家名称"""
        # 尝试从页面标题提取
        title_element = soup.find('title')
        if title_element:
            title_text = title_element.get_text().strip()
            if '|' in title_text:
                store_name = title_text.split('|')[0].strip()
                # 清理商家名称
                store_name = re.sub(r'\s*(Cashback|Discount|Codes|Vouchers|Deals)\s*', '', store_name, flags=re.IGNORECASE)
                if store_name:
                    return store_name
        
        # 从URL提取
        url_parts = url.rstrip('/').split('/')
        if url_parts:
            store_slug = url_parts[-1]
            store_name = ' '.join(word.capitalize() for word in store_slug.split('-'))
            return store_name
        
        return "Unknown Store"
    
    def extract_main_cashback_info(self, soup: BeautifulSoup) -> Tuple[str, bool, Optional[str]]:
        """
        提取主要cashback信息
        支持两种HTML结构:
        1. data-testid="all-cashback-rates" (复杂结构)
        2. data-testid="cashback-rates" (简单结构)
        """
        main_cashback = "0%"
        is_upsized = False
        previous_offer = None
        
        try:
            # 方法1: 查找data-testid="current-offer"的元素 (新结构)
            current_offer_element = soup.find(attrs={'data-testid': 'current-offer'})
            if current_offer_element:
                main_cashback = current_offer_element.get_text().strip()
                self.logger.info(f"从current-offer找到主要cashback: {main_cashback}")
            else:
                # 方法2: 查找包含"Up to"和"Cashback"的h5元素 (旧结构)
                main_rate_element = soup.find('h5', string=re.compile(r'Up to.*%.*Cashback', re.IGNORECASE))
                if not main_rate_element:
                    # 备选：寻找包含百分号的h5元素
                    main_rate_element = soup.find('h5', string=re.compile(r'\d+\.?\d*%'))
                
                if main_rate_element:
                    main_cashback = main_rate_element.get_text().strip()
                    self.logger.info(f"从h5元素找到主要cashback: {main_cashback}")
            
            # 检查是否有upsized标签
            # 寻找包含"Upsized"文本的p元素
            upsized_element = soup.find('p', string=re.compile(r'Upsized', re.IGNORECASE))
            is_upsized = upsized_element is not None
            if is_upsized:
                self.logger.info("检测到Upsized标签")
            
            # 查找previous offer (有删除线的价格)
            # 方法1: 查找data-testid="worse-offer"的元素 (新结构)
            worse_offer_element = soup.find(attrs={'data-testid': 'worse-offer'})
            if worse_offer_element:
                previous_text = worse_offer_element.get_text().strip()
                if previous_text:  # 确保不是空文本
                    previous_offer = previous_text
                    self.logger.info(f"从worse-offer找到之前的优惠: {previous_offer}")
            else:
                # 方法2: 寻找有text-decor_line-through类的h5元素 (旧结构)
                previous_element = soup.find('h5', class_=lambda x: x and 'text-decor_line-through' in x)
                if previous_element:
                    previous_offer = previous_element.get_text().strip()
                    self.logger.info(f"从line-through元素找到之前的优惠: {previous_offer}")
            
        except Exception as e:
            self.logger.warning(f"提取主要cashback信息时出错: {e}")
        
        return main_cashback, is_upsized, previous_offer
    
    def extract_detailed_rates(self, soup: BeautifulSoup) -> List[CashbackRate]:
        """
        提取详细的cashback比例
        支持两种HTML结构:
        1. data-testid="all-cashback-rates" (复杂结构)
        2. data-testid="cashback-rates" (简单结构)
        """
        detailed_rates = []
        
        try:
            # 方法1: 尝试新的简单结构 (data-testid="cashback-rates")
            rates_container = soup.find('div', {'data-testid': 'cashback-rates'})
            if rates_container:
                self.logger.info("找到cashback-rates容器 (简单结构)")
                
                # 查找cashback-tier-block容器
                tier_block = rates_container.find('div', {'data-testid': 'cashback-tier-block'})
                if tier_block:
                    # 查找所有的rate行 (flex_row类的div)
                    rate_rows = tier_block.find_all('div', class_=lambda x: x and 'flex_row' in x and 'justify_space-between' in x)
                    
                    self.logger.info(f"在简单结构中找到 {len(rate_rows)} 个rate行")
                    
                    for i, row in enumerate(rate_rows):
                        try:
                            # 在每行中查找两个p元素：分类名称和比例
                            p_elements = row.find_all('p')
                            if len(p_elements) >= 2:
                                category = p_elements[0].get_text().strip()
                                rate = p_elements[1].get_text().strip()
                                
                                # 验证rate格式
                                if '%' in rate and category:
                                    # 限制分类名称长度
                                    if len(category) > 100:
                                        category = category[:100] + "..."
                                    
                                    rate_obj = CashbackRate(
                                        category=category,
                                        rate=rate,
                                        rate_numeric=self.extract_numeric_rate(rate)
                                    )
                                    detailed_rates.append(rate_obj)
                                    
                                    self.logger.info(f"简单结构提取到rate {i+1}: {category} -> {rate}")
                        
                        except Exception as e:
                            self.logger.warning(f"处理简单结构rate行 {i+1} 时出错: {e}")
                            continue
                
                # 如果简单结构成功提取到数据，直接返回
                if detailed_rates:
                    return detailed_rates
            
            # 方法2: 尝试复杂结构 (data-testid="all-cashback-rates")
            rates_container = soup.find('div', {'data-testid': 'all-cashback-rates'})
            if rates_container:
                self.logger.info("找到all-cashback-rates容器 (复杂结构)")
                
                # 查找所有rate行 (有bg_sbds-background-color-secondary类的div)
                rate_rows = rates_container.find_all('div', class_=lambda x: x and 'bg_sbds-background-color-secondary' in x)
                
                self.logger.info(f"在复杂结构中找到 {len(rate_rows)} 个rate行")
                
                for i, row in enumerate(rate_rows):
                    try:
                        # 查找分类名称
                        category_container = row.find('div', class_=lambda x: x and 'flex_1' in x)
                        if not category_container:
                            continue
                        
                        category_element = category_container.find('p')
                        if not category_element:
                            continue
                        
                        category = category_element.get_text().strip()
                        
                        # 查找当前cashback率 (寻找font_bold的p元素)
                        rate_elements = row.find_all('p', class_=lambda x: x and 'font_bold' in x)
                        
                        current_rate = None
                        for rate_elem in rate_elements:
                            rate_text = rate_elem.get_text().strip()
                            # 检查是否包含百分号 (当前率)
                            if '%' in rate_text and not any(keyword in rate_text.lower() for keyword in ['upsized', 'ends']):
                                current_rate = rate_text
                                break
                        
                        if category and current_rate:
                            # 限制分类名称长度，避免过长的描述
                            if len(category) > 100:
                                category = category[:100] + "..."
                            
                            rate_obj = CashbackRate(
                                category=category,
                                rate=current_rate,
                                rate_numeric=self.extract_numeric_rate(current_rate)
                            )
                            detailed_rates.append(rate_obj)
                            
                            self.logger.info(f"复杂结构提取到rate {i+1}: {category} -> {current_rate}")
                        
                    except Exception as e:
                        self.logger.warning(f"处理复杂结构rate行 {i+1} 时出错: {e}")
                        continue
            
            # 如果两种方法都没有找到容器
            if not detailed_rates:
                self.logger.warning("未找到任何cashback-rates容器")
        
        except Exception as e:
            self.logger.error(f"提取详细rates时出错: {e}")
        
        return detailed_rates
    
    def save_to_database(self, store_info: StoreInfo):
        """保存数据到SQLite数据库"""
        try:
            cursor = self.conn.cursor()
            
            # 记录要保存的完整信息
            self.logger.info(f"准备保存商家: {store_info.name}")
            self.logger.info(f"主要cashback: '{store_info.main_cashback}'")
            self.logger.info(f"URL: {store_info.url}")
            self.logger.info(f"是否upsized: {store_info.is_upsized}")
            
            # 插入或获取商家信息
            cursor.execute('''
                INSERT OR IGNORE INTO stores (name, url) VALUES (?, ?)
            ''', (store_info.name, store_info.url))
            
            # 获取store_id
            cursor.execute('''
                SELECT id FROM stores WHERE name = ? AND url = ?
            ''', (store_info.name, store_info.url))
            
            store_id = cursor.fetchone()[0]
            self.logger.info(f"商家ID: {store_id}")
            
            # 插入主要cashback历史
            self.logger.info("插入主要cashback记录...")
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
                self.logger.info(f"插入分类记录: {rate.category} -> {rate.rate}")
                cursor.execute('''
                    INSERT INTO cashback_history 
                    (store_id, main_cashback, main_rate_numeric, category, category_rate, 
                    category_rate_numeric, is_upsized, previous_offer, scraping_success, error_message)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (store_id, store_info.main_cashback, store_info.main_rate_numeric,
                    rate.category, rate.rate, rate.rate_numeric,
                    store_info.is_upsized, store_info.previous_offer,
                    store_info.scraping_success, store_info.error_message))
            
            # 更新统计信息
            self.logger.info("更新统计信息...")
            self.update_rate_statistics(store_id, store_info)
            
            # 更新stores表的updated_at字段
            cursor.execute('''
                UPDATE stores SET updated_at = CURRENT_TIMESTAMP WHERE id = ?
            ''', (store_id,))
            
            self.conn.commit()
            self.logger.info(f"成功保存到数据库: {store_info.name}")
            
        except Exception as e:
            self.conn.rollback()
            self.logger.error(f"数据库保存失败: {e}")
            
            # 将完整信息保存到文件作为备份
            error_filename = f"error_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(error_filename, 'w', encoding='utf-8') as f:
                json.dump(asdict(store_info), f, ensure_ascii=False, indent=2, default=str)
            self.logger.error(f"完整错误数据已保存到: {error_filename}")
    
    def update_rate_statistics(self, store_id: int, store_info: StoreInfo):
        """更新比例统计信息"""
        cursor = self.conn.cursor()
        
        # 更新主要比例统计
        self.update_category_stats(cursor, store_id, 'Main', store_info.main_rate_numeric)
        
        # 更新详细分类统计
        for rate in store_info.detailed_rates:
            self.update_category_stats(cursor, store_id, rate.category, rate.rate_numeric)
    
    def update_category_stats(self, cursor, store_id: int, category: str, current_rate: float):
        """更新单个分类的统计信息"""
        # 获取当前统计
        cursor.execute('''
            SELECT highest_rate, lowest_rate, highest_date, lowest_date
            FROM rate_statistics 
            WHERE store_id = ? AND category = ?
        ''', (store_id, category))
        
        result = cursor.fetchone()
        current_time = datetime.now().isoformat()
        
        if result:
            highest_rate, lowest_rate, highest_date, lowest_date = result
            new_highest = max(highest_rate, current_rate)
            new_lowest = min(lowest_rate, current_rate)
            
            # 更新日期
            new_highest_date = current_time if new_highest > highest_rate else highest_date
            new_lowest_date = current_time if new_lowest < lowest_rate else lowest_date
            
            cursor.execute('''
                UPDATE rate_statistics 
                SET current_rate = ?, highest_rate = ?, lowest_rate = ?,
                    highest_date = ?, lowest_date = ?, updated_at = CURRENT_TIMESTAMP
                WHERE store_id = ? AND category = ?
            ''', (current_rate, new_highest, new_lowest, new_highest_date, 
                new_lowest_date, store_id, category))
        else:
            # 首次记录
            cursor.execute('''
                INSERT INTO rate_statistics 
                (store_id, category, current_rate, highest_rate, lowest_rate,
                highest_date, lowest_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (store_id, category, current_rate, current_rate, current_rate,
                current_time, current_time))
    
    def scrape_store_page(self, url: str) -> StoreInfo:
        """抓取单个商家页面的详细信息"""
        start_time = time.time()
        
        try:
            self.logger.info(f"正在抓取: {url}")
            
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            print("头段",response.headers.get('Content-Type'))

            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 移除script和style标签，避免抓取到它们的内容
            for element in soup(["style", "noscript"]):
                element.decompose()
            
            # 提取商家名称
            store_name = self.extract_store_name(soup, url)
            
            # 提取主要cashback信息
            main_cashback, is_upsized, previous_offer = self.extract_main_cashback_info(soup)
            
            # 提取详细的cashback层级信息
            detailed_rates = self.extract_detailed_rates(soup)
            
            scrape_duration = time.time() - start_time
            
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
            
            self.logger.info(f"成功抓取 {store_name}: {main_cashback}, {len(detailed_rates)} 个详细分类 (耗时: {scrape_duration:.2f}秒)")
            
            # 保存到数据库
            self.save_to_database(store_info)
            
            return store_info
            
        except Exception as e:
            error_msg = f"抓取失败 {url}: {str(e)}"
            self.logger.error(error_msg)
            
            return StoreInfo(
                name=self.extract_store_name(BeautifulSoup(), url),
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
    
    def get_store_history(self, store_name: str = None, store_url: str = None, limit: int = 50):
        """查询商家的历史数据"""
        cursor = self.conn.cursor()
        
        if store_name:
            cursor.execute('''
                SELECT s.name, s.url, ch.main_cashback, ch.category, ch.category_rate, 
                       ch.is_upsized, ch.scraped_at
                FROM cashback_history ch
                JOIN stores s ON ch.store_id = s.id
                WHERE s.name LIKE ?
                ORDER BY ch.scraped_at DESC
                LIMIT ?
            ''', (f'%{store_name}%', limit))
        elif store_url:
            cursor.execute('''
                SELECT s.name, s.url, ch.main_cashback, ch.category, ch.category_rate, 
                       ch.is_upsized, ch.scraped_at
                FROM cashback_history ch
                JOIN stores s ON ch.store_id = s.id
                WHERE s.url = ?
                ORDER BY ch.scraped_at DESC
                LIMIT ?
            ''', (store_url, limit))
        else:
            cursor.execute('''
                SELECT s.name, s.url, ch.main_cashback, ch.category, ch.category_rate, 
                       ch.is_upsized, ch.scraped_at
                FROM cashback_history ch
                JOIN stores s ON ch.store_id = s.id
                ORDER BY ch.scraped_at DESC
                LIMIT ?
            ''', (limit,))
        
        return cursor.fetchall()
    
    def get_rate_statistics(self, store_name: str = None):
        """查询比例统计信息"""
        cursor = self.conn.cursor()
        
        if store_name:
            cursor.execute('''
                SELECT s.name, rs.category, rs.current_rate, rs.highest_rate, rs.lowest_rate,
                       rs.highest_date, rs.lowest_date
                FROM rate_statistics rs
                JOIN stores s ON rs.store_id = s.id
                WHERE s.name LIKE ?
                ORDER BY s.name, rs.category
            ''', (f'%{store_name}%',))
        else:
            cursor.execute('''
                SELECT s.name, rs.category, rs.current_rate, rs.highest_rate, rs.lowest_rate,
                       rs.highest_date, rs.lowest_date
                FROM rate_statistics rs
                JOIN stores s ON rs.store_id = s.id
                ORDER BY s.name, rs.category
            ''')
        
        return cursor.fetchall()
    
    def close_connection(self):
        """关闭数据库连接"""
        if hasattr(self, 'conn'):
            self.conn.close()
            self.logger.info("数据库连接已关闭")

# 使用示例和测试函数
def test_scraper():
    """测试抓取器"""
    scraper = ShopBackSQLiteScraper("shopback_data.db")
    
    # 测试URL
    test_urls = [
        'https://www.shopback.com.au/agoda',
        'https://www.shopback.com.au/amazon-australia',
        'https://www.shopback.com.au/booking-com',
        'https://www.shopback.com.au/david-jones'
    ]
    
    results = []
    for url in test_urls:
        result = scraper.scrape_store_page(url)
        results.append(result)
        
        print(f"\n=== {result.name} ===")
        print(f"主要Cashback: {result.main_cashback}")
        print(f"是否Upsized: {result.is_upsized}")
        print(f"之前优惠: {result.previous_offer}")
        print(f"详细分类数量: {len(result.detailed_rates)}")
        
        for rate in result.detailed_rates:
            print(f"  - {rate.category}: {rate.rate}")
        
        # 短暂延迟
        time.sleep(2)
    
    print(f"\n总共抓取了 {len(results)} 个商家")
    
    # 展示数据库查询功能
    print("\n=== 数据库查询示例 ===")
    
    # 查询Agoda的历史数据
    print("\nAgoda的历史数据:")
    history = scraper.get_store_history(store_name="Agoda", limit=10)
    for record in history:
        print(f"  {record['scraped_at']}: {record['category']} - {record['category_rate']}")
    
    # 查询统计信息
    print("\n比例统计信息:")
    stats = scraper.get_rate_statistics()
    for stat in stats[:10]:  # 显示前10条
        print(f"  {stat['name']} - {stat['category']}: 当前{stat['current_rate']}%, "
              f"最高{stat['highest_rate']}%, 最低{stat['lowest_rate']}%")
    
    scraper.close_connection()

if __name__ == "__main__":
    test_scraper()