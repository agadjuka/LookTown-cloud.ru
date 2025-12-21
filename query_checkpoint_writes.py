import asyncio
import sys
import os
import psycopg
from dotenv import load_dotenv

# Загружаем переменные
load_dotenv()

# ==========================================
# 🚑 ГЛАВНЫЙ ФИКС ДЛЯ WINDOWS
# Без этого psycopg на Windows падает с ошибкой ProactorEventLoop
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
# ==========================================

# Получаем URL базы данных из .env
DB_URI = os.getenv("DATABASE_URL")
if not DB_URI:
    host = os.getenv("PG_HOST", "localhost")
    user = os.getenv("PG_USER", "postgres")
    password = os.getenv("PG_PASSWORD", "")
    db = os.getenv("PG_DB", "ai_db")
    port = os.getenv("PG_PORT", "5432")
    DB_URI = f"postgresql://{user}:{password}@{host}:{port}/{db}"

async def get_table_structure():
    """Получает структуру таблицы checkpoint_writes"""
    print("🔍 Получаю структуру таблицы checkpoint_writes...")
    
    async with await psycopg.AsyncConnection.connect(DB_URI, autocommit=True) as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'checkpoint_writes'
                ORDER BY ordinal_position;
            """)
            
            columns = await cur.fetchall()
            print("\n📋 Структура таблицы checkpoint_writes:")
            print("-" * 50)
            for col_name, col_type in columns:
                print(f"  {col_name:<30} {col_type}")
            print()
            return [col[0] for col in columns]

async def query_checkpoint_writes(thread_id: str = '261617302'):
    """
    Выполняет запрос к таблице checkpoint_writes для указанного thread_id.
    
    Args:
        thread_id: ID потока для поиска (по умолчанию '261617302')
    """
    print(f"🔌 Подключаюсь к базе данных...")
    
    # Сначала получаем структуру таблицы
    columns = await get_table_structure()
    
    # Формируем запрос на основе реальных колонок
    # Ищем колонки, которые могут содержать дату/время
    time_columns = [col for col in columns if 'time' in col.lower() or 'date' in col.lower() or 'created' in col.lower() or 'updated' in col.lower()]
    
    # Базовые колонки, которые точно есть
    select_columns = ['thread_id']
    if time_columns:
        select_columns.extend(time_columns)
    else:
        # Если не нашли колонки с датой, просто выберем все
        select_columns = columns[:5]  # Берем первые 5 колонок
    
    async with await psycopg.AsyncConnection.connect(DB_URI, autocommit=True) as conn:
        async with conn.cursor() as cur:
            # Формируем SELECT с реальными колонками
            columns_str = ', '.join(select_columns)
            query = f"""
                SELECT {columns_str}
                FROM checkpoint_writes 
                WHERE thread_id = %s
                ORDER BY {select_columns[-1]} DESC 
                LIMIT 10;
            """
            
            print(f"📊 Выполняю запрос для thread_id = {thread_id}...")
            await cur.execute(query, (thread_id,))
            
            results = await cur.fetchall()
            
            if results:
                print(f"\n✅ Найдено записей: {len(results)}\n")
                # Выводим заголовки
                header = " | ".join([f"{col:<20}" for col in select_columns])
                print(header)
                print("-" * len(header))
                # Выводим данные
                for row in results:
                    row_str = " | ".join([f"{str(val):<20}" for val in row])
                    print(row_str)
            else:
                print(f"\n⚠️ Записей для thread_id = {thread_id} не найдено")

if __name__ == "__main__":
    import sys
    
    # Можно передать thread_id как аргумент командной строки
    thread_id = sys.argv[1] if len(sys.argv) > 1 else '261617302'
    
    try:
        asyncio.run(query_checkpoint_writes(thread_id))
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
