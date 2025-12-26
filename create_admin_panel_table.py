"""
Скрипт для создания таблицы админ-панели в PostgreSQL.
Создает таблицу для хранения связей между пользователями Telegram и топиками форума.
"""
import asyncio
import sys
import os
import psycopg
from dotenv import load_dotenv

# ==========================================
# 🚑 ГЛАВНЫЙ ФИКС ДЛЯ WINDOWS
# Без этого psycopg на Windows падает с ошибкой ProactorEventLoop
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
# ==========================================

load_dotenv()

# Получаем строку подключения
DB_URI = os.getenv("DATABASE_URL")
if not DB_URI:
    host = os.getenv("PG_HOST", "localhost")
    user = os.getenv("PG_USER", "postgres")
    password = os.getenv("PG_PASSWORD", "")
    db = os.getenv("PG_DB", "ai_db")
    port = os.getenv("PG_PORT", "5432")
    DB_URI = f"postgresql://{user}:{password}@{host}:{port}/{db}"

# Название таблицы (можно изменить через переменную окружения)
TABLE_NAME = os.getenv("ADMIN_TOPICS_TABLE", "adminpanel")


async def create_admin_panel_table():
    """Создает таблицу для админ-панели."""
    print(f"🔌 Подключаюсь к базе данных...")
    print(f"📋 Таблица: {TABLE_NAME}")
    
    # autocommit=True нужен для создания таблиц
    async with await psycopg.AsyncConnection.connect(DB_URI, autocommit=True) as conn:
        async with conn.cursor() as cur:
            # Проверяем, существует ли таблица
            await cur.execute(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = %s
                )
                """,
                (TABLE_NAME,)
            )
            exists = await cur.fetchone()
            
            if exists[0]:
                print(f"⚠️  Таблица '{TABLE_NAME}' уже существует.")
                print(f"ℹ️  Пропускаю создание. Если нужно пересоздать, удалите таблицу вручную.")
                return
            
            print(f"🔨 Создаю таблицу '{TABLE_NAME}'...")
            
            # Создаем таблицу
            await cur.execute(
                f"""
                CREATE TABLE {TABLE_NAME} (
                    user_id BIGINT PRIMARY KEY,
                    topic_id BIGINT NOT NULL UNIQUE,
                    topic_name TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'auto' CHECK (mode IN ('auto', 'manual')),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
                """
            )
            
            # Создаем индексы для быстрого поиска
            print("📇 Создаю индексы...")
            await cur.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_topic_id ON {TABLE_NAME} (topic_id)"
            )
            await cur.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_mode ON {TABLE_NAME} (mode)"
            )
            
            print(f"✅ УСПЕХ! Таблица '{TABLE_NAME}' создана.")
            print(f"   Структура:")
            print(f"   - user_id (BIGINT, PRIMARY KEY) - ID пользователя Telegram")
            print(f"   - topic_id (BIGINT, UNIQUE) - ID топика в Telegram Forum")
            print(f"   - topic_name (TEXT) - Название топика")
            print(f"   - mode (TEXT, DEFAULT 'auto') - Режим работы ('auto' или 'manual')")
            print(f"   - created_at (TIMESTAMP) - Время создания")
            print(f"   - updated_at (TIMESTAMP) - Время обновления")
            print(f"   Индексы созданы для быстрого поиска по topic_id и mode.")


if __name__ == "__main__":
    try:
        asyncio.run(create_admin_panel_table())
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

