#!/usr/bin/env python3
"""
ShopBack FastAPI后端
为React前端提供RESTful API接口
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Dict, Any
import sqlite3
import asyncio
import threading
import time
from datetime import datetime, timedelta
import logging
from pathlib import Path
import json

# 导入我们的抓取器
from sb_scrap import ShopBackSQLiteScraper, StoreInfo, CashbackRate

# Pydantic模型定义
class StoreResponse(BaseModel):
    id: int
    name: str
    url: str
    created_at: str
    updated_at: str

class CashbackHistoryResponse(BaseModel):
    id: int
    store_name: str
    store_url: str
    main_cashback: str
    main_rate_numeric: float
    category: str
    category_rate: str
    category_rate_numeric: float
    is_upsized: bool
    previous_offer: Optional[str]
    scraped_at: str

class RateStatisticsResponse(BaseModel):
    store_name: str
    category: str
    current_rate: float
    highest_rate: float
    lowest_rate: float
    highest_date: str
    lowest_date: str

class ScrapeRequest(BaseModel):
    url: HttpUrl
    
class ScrapeResponse(BaseModel):
    success: bool
    message: str
    store_name: Optional[str] = None
    main_cashback: Optional[str] = None
    detailed_rates_count: Optional[int] = None

class DashboardStats(BaseModel):
    total_stores: int
    total_records: int
    recent_scrapes: int
    upsized_stores: int
    avg_cashback_rate: float

# 初始化FastAPI应用
app = FastAPI(
    title="ShopBack Cashback API",
    description="RESTful API for ShopBack cashback data management",
    version="1.0.0"
)

# CORS中间件配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],  # React开发服务器
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局变量
scraper_instance = None
db_path = "shopback_data.db"

# 日志设置
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def get_scraper():
    """获取抓取器实例"""
    global scraper_instance
    if scraper_instance is None:
        scraper_instance = ShopBackSQLiteScraper(db_path)
    return scraper_instance

# API路由
@app.post("/api/rescrape-all", summary="重新抓取所有商家")
async def rescrape_all_stores(background_tasks: BackgroundTasks):
    """重新抓取所有商家的数据"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 获取所有商家URL
        cursor.execute("SELECT url FROM stores")
        urls = [row[0] for row in cursor.fetchall()]
        
        # 在后台执行批量抓取
        background_tasks.add_task(scrape_multiple_background, urls, 2)
        
        return {
            "success": True,
            "message": f"重新抓取任务已启动，共{len(urls)}个商家"
        }
    finally:
        conn.close()
@app.get("/", summary="API根路径")
async def root():
    """API欢迎信息"""
    return {
        "message": "ShopBack Cashback API",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/api/dashboard", response_model=DashboardStats, summary="获取仪表盘统计数据")
async def get_dashboard_stats():
    """获取仪表盘统计数据"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 总商家数
        cursor.execute("SELECT COUNT(*) FROM stores")
        total_stores = cursor.fetchone()[0]
        
        # 总记录数
        cursor.execute("SELECT COUNT(*) FROM cashback_history")
        total_records = cursor.fetchone()[0]
        
        # 最近24小时的抓取数
        yesterday = (datetime.now() - timedelta(days=1)).isoformat()
        cursor.execute("SELECT COUNT(*) FROM cashback_history WHERE scraped_at > ?", (yesterday,))
        recent_scrapes = cursor.fetchone()[0]
        
        # 当前upsized的商家数
        cursor.execute("""
            SELECT COUNT(DISTINCT store_id) FROM cashback_history 
            WHERE is_upsized = 1 AND id IN (
                SELECT MAX(id) FROM cashback_history GROUP BY store_id
            )
        """)
        upsized_stores = cursor.fetchone()[0]
        
        # 平均cashback比例
        cursor.execute("""
            SELECT AVG(main_rate_numeric) FROM (
                SELECT DISTINCT store_id, main_rate_numeric 
                FROM cashback_history 
                WHERE id IN (
                    SELECT MAX(id) FROM cashback_history GROUP BY store_id
                )
            )
        """)
        avg_rate = cursor.fetchone()[0] or 0.0
        
        return DashboardStats(
            total_stores=total_stores,
            total_records=total_records,
            recent_scrapes=recent_scrapes,
            upsized_stores=upsized_stores,
            avg_cashback_rate=round(avg_rate, 2)
        )
    
    finally:
        conn.close()

@app.get("/api/stores", response_model=List[StoreResponse], summary="获取所有商家")
async def get_stores(
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None, description="按名称搜索商家")
):
    """获取商家列表"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if search:
            cursor.execute("""
                SELECT * FROM stores 
                WHERE name LIKE ? 
                ORDER BY updated_at DESC 
                LIMIT ? OFFSET ?
            """, (f"%{search}%", limit, offset))
        else:
            cursor.execute("""
                SELECT * FROM stores 
                ORDER BY updated_at DESC 
                LIMIT ? OFFSET ?
            """, (limit, offset))
        
        stores = cursor.fetchall()
        return [StoreResponse(**dict(store)) for store in stores]
    
    finally:
        conn.close()

@app.get("/api/stores/{store_id}/history", response_model=List[CashbackHistoryResponse], summary="获取商家历史数据")
async def get_store_history(
    store_id: int,
    limit: int = Query(50, ge=1, le=1000),
    category: Optional[str] = Query(None, description="按分类筛选")
):
    """获取特定商家的历史数据"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if category:
            cursor.execute("""
                SELECT ch.*, s.name as store_name, s.url as store_url
                FROM cashback_history ch
                JOIN stores s ON ch.store_id = s.id
                WHERE ch.store_id = ? AND ch.category = ?
                AND ch.scraped_at = (
                    SELECT MAX(scraped_at) 
                    FROM cashback_history 
                    WHERE store_id = ch.store_id
                )
                ORDER BY ch.category
                LIMIT ?
            """, (store_id, category, limit))
        else:
            cursor.execute("""
                SELECT ch.*, s.name as store_name, s.url as store_url
                FROM cashback_history ch
                JOIN stores s ON ch.store_id = s.id
                WHERE ch.store_id = ?
                AND ch.scraped_at = (
                    SELECT MAX(scraped_at) 
                    FROM cashback_history 
                    WHERE store_id = ch.store_id
                )
                ORDER BY ch.category
                LIMIT ?
            """, (store_id, limit))
        
        history = cursor.fetchall()
        return [CashbackHistoryResponse(**dict(record)) for record in history]
    
    finally:
        conn.close()

@app.get("/api/history", response_model=List[CashbackHistoryResponse], summary="获取所有历史数据")
async def get_all_history(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    store_name: Optional[str] = Query(None, description="按商家名称筛选"),
    is_upsized: Optional[bool] = Query(None, description="按是否upsized筛选"),
    min_rate: Optional[float] = Query(None, description="最小cashback比例"),
    max_rate: Optional[float] = Query(None, description="最大cashback比例")
):
    """获取所有历史数据（支持多种筛选条件）"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 构建查询条件
    conditions = []
    params = []
    
    if store_name:
        conditions.append("s.name LIKE ?")
        params.append(f"%{store_name}%")
    
    if is_upsized is not None:
        conditions.append("ch.is_upsized = ?")
        params.append(is_upsized)
    
    if min_rate is not None:
        conditions.append("ch.category_rate_numeric >= ?")
        params.append(min_rate)
    
    if max_rate is not None:
        conditions.append("ch.category_rate_numeric <= ?")
        params.append(max_rate)
    
    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)
    
    query = f"""
        SELECT ch.*, s.name as store_name, s.url as store_url
        FROM cashback_history ch
        JOIN stores s ON ch.store_id = s.id
        {where_clause}
        ORDER BY ch.scraped_at DESC
        LIMIT ? OFFSET ?
    """
    
    params.extend([limit, offset])
    
    try:
        cursor.execute(query, params)
        history = cursor.fetchall()
        return [CashbackHistoryResponse(**dict(record)) for record in history]
    
    finally:
        conn.close()

@app.get("/api/statistics", response_model=List[RateStatisticsResponse], summary="获取比例统计")
async def get_statistics(
    store_name: Optional[str] = Query(None, description="按商家名称筛选")
):
    """获取比例统计信息"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if store_name:
            cursor.execute("""
                SELECT s.name as store_name, rs.category, rs.current_rate, 
                       rs.highest_rate, rs.lowest_rate, rs.highest_date, rs.lowest_date
                FROM rate_statistics rs
                JOIN stores s ON rs.store_id = s.id
                WHERE s.name LIKE ?
                ORDER BY s.name, rs.category
            """, (f"%{store_name}%",))
        else:
            cursor.execute("""
                SELECT s.name as store_name, rs.category, rs.current_rate, 
                       rs.highest_rate, rs.lowest_rate, rs.highest_date, rs.lowest_date
                FROM rate_statistics rs
                JOIN stores s ON rs.store_id = s.id
                ORDER BY s.name, rs.category
            """)
        
        stats = cursor.fetchall()
        return [RateStatisticsResponse(**dict(stat)) for stat in stats]
    
    finally:
        conn.close()

@app.get("/api/top-cashback", summary="获取最高cashback商家")
async def get_top_cashback(
    limit: int = Query(10, ge=1, le=50),
    category: Optional[str] = Query(None, description="按分类筛选")
):
    """获取cashback比例最高的商家"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if category and category != "Main":
            # 查询特定分类
            cursor.execute("""
                SELECT s.name, s.url, ch.category, ch.category_rate, ch.category_rate_numeric,
                       ch.is_upsized, ch.scraped_at
                FROM cashback_history ch
                JOIN stores s ON ch.store_id = s.id
                WHERE ch.category = ? AND ch.id IN (
                    SELECT MAX(id) FROM cashback_history 
                    WHERE category = ?
                    GROUP BY store_id
                )
                ORDER BY ch.category_rate_numeric DESC
                LIMIT ?
            """, (category, category, limit))
        else:
            # 查询主要cashback
            cursor.execute("""
                SELECT s.name, s.url, ch.main_cashback, ch.main_rate_numeric,
                       ch.is_upsized, ch.scraped_at
                FROM cashback_history ch
                JOIN stores s ON ch.store_id = s.id
                WHERE ch.category = 'Main' AND ch.id IN (
                    SELECT MAX(id) FROM cashback_history 
                    WHERE category = 'Main'
                    GROUP BY store_id
                )
                ORDER BY ch.main_rate_numeric DESC
                LIMIT ?
            """, (limit,))
        
        results = cursor.fetchall()
        return [dict(result) for result in results]
    
    finally:
        conn.close()

@app.get("/api/upsized-stores", summary="获取当前upsized的商家")
async def get_upsized_stores():
    """获取当前有upsized优惠的商家"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT s.name, s.url, ch.main_cashback, ch.main_rate_numeric,
                   ch.previous_offer, ch.scraped_at
            FROM cashback_history ch
            JOIN stores s ON ch.store_id = s.id
            WHERE ch.is_upsized = 1 AND ch.category = 'Main' AND ch.id IN (
                SELECT MAX(id) FROM cashback_history 
                WHERE category = 'Main'
                GROUP BY store_id
            )
            ORDER BY ch.main_rate_numeric DESC
        """)
        
        results = cursor.fetchall()
        return [dict(result) for result in results]
    
    finally:
        conn.close()

@app.post("/api/scrape", response_model=ScrapeResponse, summary="抓取单个商家")
async def scrape_store(request: ScrapeRequest, background_tasks: BackgroundTasks):
    """抓取单个商家的cashback数据"""
    url = str(request.url)
    
    # 验证URL是否为ShopBack
    if "shopback.com" not in url:
        raise HTTPException(status_code=400, detail="URL必须是ShopBack商家页面")
    
    # 在后台执行抓取任务
    background_tasks.add_task(scrape_store_background, url)
    
    return ScrapeResponse(
        success=True,
        message="抓取任务已启动，请稍后查看结果"
    )

async def scrape_store_background(url: str):
    """后台抓取任务"""
    try:
        scraper = get_scraper()
        result = scraper.scrape_store_page(url)
        logger.info(f"后台抓取完成: {result.name} - {result.main_cashback}")
    except Exception as e:
        logger.error(f"后台抓取失败: {url} - {str(e)}")

@app.post("/api/scrape-multiple", summary="批量抓取多个商家")
async def scrape_multiple_stores(
    urls: List[HttpUrl], 
    background_tasks: BackgroundTasks,
    delay_seconds: int = Query(2, ge=1, le=10, description="每次抓取间隔秒数")
):
    """批量抓取多个商家的cashback数据"""
    # 验证所有URL
    for url in urls:
        if "shopback.com" not in str(url):
            raise HTTPException(status_code=400, detail=f"URL必须是ShopBack商家页面: {url}")
    
    # 在后台执行批量抓取任务
    background_tasks.add_task(scrape_multiple_background, [str(url) for url in urls], delay_seconds)
    
    return {
        "success": True,
        "message": f"批量抓取任务已启动，共{len(urls)}个商家",
        "estimated_time": f"{len(urls) * delay_seconds // 60}分钟"
    }

async def scrape_multiple_background(urls: List[str], delay_seconds: int):
    """后台批量抓取任务"""
    scraper = get_scraper()
    
    for i, url in enumerate(urls):
        try:
            result = scraper.scrape_store_page(url)
            logger.info(f"批量抓取进度 {i+1}/{len(urls)}: {result.name} - {result.main_cashback}")
            
            # 添加延迟，避免过于频繁的请求
            if i < len(urls) - 1:
                time.sleep(delay_seconds)
                
        except Exception as e:
            logger.error(f"批量抓取失败: {url} - {str(e)}")

@app.get("/api/trends/{store_id}", summary="获取商家趋势数据")
async def get_store_trends(
    store_id: int,
    days: int = Query(30, ge=1, le=365, description="查询天数"),
    category: str = Query("Main", description="分类名称")
):
    """获取商家的cashback趋势数据"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        start_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        cursor.execute("""
            SELECT DATE(scraped_at) as date, 
                   AVG(category_rate_numeric) as avg_rate,
                   MAX(category_rate_numeric) as max_rate,
                   MIN(category_rate_numeric) as min_rate,
                   COUNT(*) as count
            FROM cashback_history
            WHERE store_id = ? AND category = ? AND scraped_at >= ?
            GROUP BY DATE(scraped_at)
            ORDER BY date
        """, (store_id, category, start_date))
        
        trends = cursor.fetchall()
        return [dict(trend) for trend in trends]
    
    finally:
        conn.close()

@app.delete("/api/stores/{store_id}", summary="删除商家及其所有数据")
async def delete_store(store_id: int):
    """删除商家及其所有相关数据"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 检查商家是否存在
        cursor.execute("SELECT name FROM stores WHERE id = ?", (store_id,))
        store = cursor.fetchone()
        if not store:
            raise HTTPException(status_code=404, detail="商家不存在")
        
        store_name = store[0]
        
        # 删除相关数据
        cursor.execute("DELETE FROM rate_statistics WHERE store_id = ?", (store_id,))
        cursor.execute("DELETE FROM cashback_history WHERE store_id = ?", (store_id,))
        cursor.execute("DELETE FROM stores WHERE id = ?", (store_id,))
        
        conn.commit()
        
        return {
            "success": True,
            "message": f"商家 '{store_name}' 及其所有数据已删除"
        }
    
    finally:
        conn.close()

# 错误处理
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"detail": "资源未找到"}
    )

@app.exception_handler(500)
async def internal_error_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误"}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001, reload=False)
