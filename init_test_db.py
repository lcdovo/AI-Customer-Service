"""
初始化测试数据库并启动 API 服务器
"""
import os
import sys
import asyncio

os.environ["MYSQL_HOST"] = "localhost"
os.environ["MYSQL_PORT"] = "9999"
os.environ["MYSQL_USER"] = "root"
os.environ["MYSQL_PASSWORD"] = ""
os.environ["MYSQL_DATABASE"] = "sqlite+aiosqlite:///./test.db"
os.environ["REDIS_HOST"] = "localhost"
os.environ["REDIS_PORT"] = "9999"
os.environ["REDIS_PASSWORD"] = ""
os.environ["REDIS_DB"] = "0"
os.environ["LLM_API_KEY"] = "test-key"

from app.utils.database import init_database
from app.models.models import Base
import sqlite3


async def init_test_db():
    """初始化测试数据库"""
    # 删除旧数据库
    if os.path.exists("test.db"):
        os.remove("test.db")
    
    # 使用同步 sqlite3 创建表
    conn = sqlite3.connect("test.db")
    cursor = conn.cursor()
    
    # 创建 users 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username VARCHAR(50) NOT NULL UNIQUE,
            email VARCHAR(100) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            status VARCHAR(20) DEFAULT 'active',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 创建 sessions 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id VARCHAR(36) PRIMARY KEY,
            user_id INTEGER NOT NULL,
            status VARCHAR(20) DEFAULT 'active',
            message_count INTEGER DEFAULT 0,
            last_intent VARCHAR(50),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 创建 messages 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id VARCHAR(36) NOT NULL,
            role VARCHAR(20) NOT NULL,
            content TEXT NOT NULL,
            token_count INTEGER,
            response_time_ms INTEGER,
            tool_calls TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 创建 agent_traces 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_traces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id VARCHAR(36) NOT NULL,
            session_id VARCHAR(36) NOT NULL,
            intent VARCHAR(50),
            node_name VARCHAR(50),
            node_order INTEGER,
            input_data TEXT,
            output_data TEXT,
            duration_ms INTEGER,
            success INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 创建 tickets 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id VARCHAR(36) UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            category VARCHAR(50),
            content TEXT,
            priority VARCHAR(20) DEFAULT 'normal',
            status VARCHAR(20) DEFAULT 'pending',
            assignee VARCHAR(100),
            sla_deadline DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 创建 orders 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id VARCHAR(50) UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            status VARCHAR(30) DEFAULT 'pending',
            total_amount DECIMAL(10, 2),
            shipping_info TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 创建 notifications 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type VARCHAR(30),
            channel VARCHAR(30),
            content TEXT,
            status VARCHAR(20) DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 插入测试数据
    cursor.execute("""
        INSERT OR IGNORE INTO users (id, username, email, password_hash, status) 
        VALUES (1, 'testuser', 'test@example.com', 'hashed_password', 'active')
    """)
    
    cursor.execute("""
        INSERT OR IGNORE INTO orders (order_id, user_id, status, total_amount, shipping_info) 
        VALUES ('ORD20260801', 1, 'shipped', 299.00, 
                '{"carrier": "顺丰快递", "tracking_no": "SF1234567890", "status": "运输中"}')
    """)
    
    conn.commit()
    conn.close()
    print("✅ 测试数据库初始化完成")
    print("   - 用户: testuser (ID: 1)")
    print("   - 订单: ORD20260801 (已发货)")


if __name__ == "__main__":
    asyncio.run(init_test_db())
