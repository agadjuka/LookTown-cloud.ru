import asyncio
import sys
import os
import psycopg
from dotenv import load_dotenv
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

# Загружаем переменные
load_dotenv()

# ==========================================
# 🚑 ГЛАВНЫЙ ФИКС ДЛЯ WINDOWS
# Без этого psycopg на Windows падает с ошибкой ProactorEventLoop
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
# ==========================================

DB_URI = os.getenv("DATABASE_URL")
if not DB_URI:
    host = os.getenv("PG_HOST", "localhost")
    user = os.getenv("PG_USER", "postgres")
    password = os.getenv("PG_PASSWORD", "")
    db = os.getenv("PG_DB", "ai_db")
    port = os.getenv("PG_PORT", "5432")
    DB_URI = f"postgresql://{user}:{password}@{host}:{port}/{db}"

async def fix_database():
    print(f"🔌 Подключаюсь к базе (Windows fix active)...")
    
    # autocommit=True нужен для создания таблиц (обход ошибки транзакции)
    async with await psycopg.AsyncConnection.connect(DB_URI, autocommit=True) as conn:
        checkpointer = AsyncPostgresSaver(conn)
        print("🔨 Создаю таблицы...")
        
        # Эта команда создаст таблицы ровно под ту версию, которая у тебя стоит
        await checkpointer.setup()
        
        print("✅ УСПЕХ! Таблицы созданы. Можно запускать бота.")

if __name__ == "__main__":
    try:
        asyncio.run(fix_database())
    except Exception as e:
        print(f"❌ Ошибка: {e}")